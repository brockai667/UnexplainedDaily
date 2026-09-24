#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Denny beh stickman fabriky (UnexplainedDaily): tema -> spec -> video -> Buffer.

    python stickman/run_daily.py              # cely retazec vratane publikovania
    python stickman/run_daily.py --dry-run    # vyrobi video a skonci, nic nepublikuje
    python stickman/run_daily.py --topic "The Mary Celeste"   # konkretna tema (test)

Pravidla:
  * Tema sa presuva do `used` az PO uspesnom publikovani. Kazde zlyhanie = nenulovy
    navratovy kod a tema ostava v banke, takze zajtrajsi beh ju skusi znova.
  * Video sa hostuje rovnako ako vo zvysku flotily - GitHub Releases, fallback
    Cloudinary (funkcie beriem z push_to_buffer.py, nerobim vlastny hosting).
  * Publikuje sa do okna 06-11 UTC.
"""
import argparse
import datetime
import json
import os
import random
import re
import subprocess
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, REPO)

TOPICS = os.path.join(ROOT, "topics.json")
OUT = os.path.join(ROOT, "out")
SPECS = os.path.join(ROOT, "specs")
STATE = os.path.join(ROOT, "published.json")

MUSIC_CREDIT = ('Music: "Sneaky Snitch" by Kevin MacLeod (incompetech.com), '
                "licensed under Creative Commons: By Attribution 3.0")
HASHTAGS = "#mystery #unexplained #history #shorts"
PUBLISH_UTC = (6, 11)        # okno, v ktorom sa planuje prispevok


def log(msg):
    print(msg, flush=True)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


# ------------------------------------------------------------------ 1) tema
def pick_topic(bank, forced=None):
    used = [u.strip().lower() for u in bank.get("used", [])]
    if forced:
        return forced
    for t in bank.get("topics", []):
        if t.strip().lower() not in used:
            return t
    return None


# ------------------------------------------------------------------ 2) spec
def make_spec(topic):
    """storyboard.py ako podproces - ma vlastny sys.exit(2) pri problemoch a
    vlastne retry; nechcem, aby mi jeho vynimka zhodila cely beh bez hlasky."""
    slug = slugify(topic)
    path = os.path.join(SPECS, slug + ".json")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "storyboard.py"), topic],
                       cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    log(((r.stdout or "") + (r.stderr or "")).strip()[-2500:])
    if not os.path.exists(path):
        raise RuntimeError("storyboard nevyrobil spec: " + path)
    spec = load_json(path, {})
    if len(spec.get("lines", [])) < 8:
        raise RuntimeError("spec ma len %d viet" % len(spec.get("lines", [])))
    if r.returncode not in (0, 2):
        raise RuntimeError("storyboard zlyhal (kod %s)" % r.returncode)
    if r.returncode == 2:
        log("  [spec] storyboard hlasi problemy, ale spec je pouzitelny - pokracujem")
    return path, spec


# ------------------------------------------------------------------ 3) video
def make_video(spec_path):
    import build_spec
    total, slug = build_spec.build(spec_path)
    mp4 = os.path.join(OUT, slug + ".mp4")
    if not os.path.exists(mp4):
        raise RuntimeError("render nevyrobil " + mp4)
    if not (build_spec.MIN_LEN - 0.5 <= total <= build_spec.MAX_LEN + 0.5):
        raise RuntimeError("dlzka %.2f s mimo rozsahu" % total)
    return mp4, slug, total


def loop_check(mp4, slug):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "loopcheck.py"), mp4,
                        os.path.join(OUT, slug + "_loop.jpg")],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    log(out[-600:])
    if "slucka sedi" not in out:
        raise RuntimeError("slucka nesedi - video by v kanale blikalo")


# ------------------------------------------------------------------ 4) texty
def build_text(spec):
    """Titulok = spec["title"]. Popis zacina zaverecnou otazkou (otvara komentare),
    potom hashtagy a kredit hudby."""
    title = (spec.get("title") or spec.get("topic") or "Unexplained").strip()
    lines = spec.get("lines", [])
    question = ""
    for l in reversed(lines):
        say = (l.get("say") or "").strip()
        if say.endswith("?"):
            question = say
            break
    if not question and lines:
        question = (lines[-1].get("say") or "").strip()
    body = "\n\n".join(x for x in (question, HASHTAGS, MUSIC_CREDIT) if x)
    return title, body


def write_sidecar(mp4, title, body):
    """Rovnaky format ako cita push_to_buffer.read_txt: 1. riadok titulok, zvysok popis."""
    with open(mp4[:-4] + ".txt", "w", encoding="utf-8") as f:
        f.write(title + "\n" + body + "\n")


# ------------------------------------------------------------------ 5) publikovanie
def next_slot():
    """Najblizsi buduci cas v okne 06-11 UTC, s jitterom (nie vzdy presna hodina)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    lo, hi = PUBLISH_UTC
    for day in range(0, 3):
        t = (now + datetime.timedelta(days=day)).replace(
            hour=lo, minute=0, second=0, microsecond=0)
        t += datetime.timedelta(minutes=random.randint(0, (hi - lo) * 60 - 1),
                                seconds=random.randint(0, 59))
        if t > now + datetime.timedelta(minutes=10):
            return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return (now + datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def publish(mp4, title, body):
    """Hosting + Buffer presne tak, ako to robi zvysok flotily (push_to_buffer.py)."""
    import push_to_buffer as P
    cfg = P.load_cfg()
    token = (cfg.get("buffer_token") or "").strip()
    if not token:
        raise RuntimeError("chyba buffer_token (BUFFER_TOKEN secret)")
    targets = cfg.get("buffer_channels") or []
    if not targets:
        targets = [c for c in P.get_channels(token)
                   if c.get("service", "").lower() in P.WANT_SERVICES]
    if not targets:
        raise RuntimeError("ziadne cielove kanaly")

    log("  [host] nahravam video...")
    url = P.host_video(cfg, mp4)
    due = next_slot()
    log("  [buffer] planujem na %s UTC -> %s" % (due, ", ".join(c["service"] for c in targets)))

    yt_title = (title + " #shorts")[:100]
    ok_services, fails = [], []
    for c in targets:
        svc = c["service"].lower()
        t = yt_title if svc == "youtube" else title
        promo = cfg.get("promo_yt", "") if svc == "youtube" else cfg.get("promo_social", "")
        ok, msg = P.create_post(token, svc, c["id"], body + promo, url, t, due)
        log(("  [buffer] %-10s OK" % svc) if ok else ("  [buffer] %-10s CHYBA: %s" % (svc, msg[:200])))
        (ok_services if ok else fails).append(svc)
    if not ok_services:
        raise RuntimeError("Buffer odmietol vsetky kanaly: " + "; ".join(fails))

    # zapis aj do spolocneho pushed.json, nech sa video neposle este raz inym skriptom
    pushed = P.load_pushed()
    name = os.path.basename(mp4)
    pushed[name] = sorted(set(pushed.get(name, [])) | set(ok_services))
    P.save_pushed(pushed)
    return url, due, ok_services, fails


# ------------------------------------------------------------------ hlavny retazec
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="vyrob video, nepublikuj")
    ap.add_argument("--topic", default=None, help="konkretna tema namiesto banky")
    a = ap.parse_args()

    bank = load_json(TOPICS, {"used": [], "topics": []})
    topic = pick_topic(bank, a.topic)
    if not topic:
        log("Banka tem je prazdna - nic na vyrobu.")
        return 0
    log("=== TEMA: %s%s ===" % (topic, "  (dry-run)" if a.dry_run else ""))

    spec_path, spec = make_spec(topic)
    log("  [spec] %s  (%d viet, world=%s, hero=%s, speed=%s)"
        % (spec.get("title"), len(spec["lines"]), spec.get("world"),
           spec.get("hero"), spec.get("speed")))

    mp4, slug, total = make_video(spec_path)
    loop_check(mp4, slug)
    title, body = build_text(spec)
    write_sidecar(mp4, title, body)
    log("  [video] %s  %.2f s" % (mp4, total))
    log("  [text ] %s | %s" % (title, body.split("\n")[0]))

    if a.dry_run:
        log("DRY-RUN: video hotove, nepublikujem, temu v banke nechavam.")
        return 0

    url, due, ok_services, fails = publish(mp4, title, body)

    # stav sa zapisuje az tu - po uspesnom publikovani
    if not a.topic:
        bank.setdefault("used", []).append(topic)
        bank["topics"] = [t for t in bank.get("topics", []) if t != topic]
        save_json(TOPICS, bank)
    state = load_json(STATE, {"runs": []})
    state["runs"].append({"date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
                          "topic": topic, "slug": slug, "title": title, "seconds": round(total, 2),
                          "due": due, "url": url, "services": ok_services, "failed": fails})
    state["runs"] = state["runs"][-120:]
    save_json(STATE, state)
    log("HOTOVO: %s -> %s (%s)" % (title, ", ".join(ok_services), due))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as e:
        # build_spec pri zlyhanom `hyperframes check` vola sys.exit(2)
        code = e.code if isinstance(e.code, int) else 1
        if code:
            log("ZLYHANIE (kod %s) - tema ostava v banke." % code)
        sys.exit(code)
    except Exception:
        traceback.print_exc()
        log("ZLYHANIE - tema ostava v banke, zajtra sa skusi znova.")
        sys.exit(1)
