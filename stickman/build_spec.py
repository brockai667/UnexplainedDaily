#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UnexplainedDaily engine: spec JSON -> hotove video.

    python build_spec.py specs\\the-antikythera-mechanism.json
    python build_spec.py specs\\x.json --html-only     (bez renderu, na snapshoty)

Drzi vsetko, co je na kanali overene: Bob ako stala postava, 1 veta = 1 zaber,
zlate 3D cisla (numEN), titulky s aktivnym zlatym slovom, hook s duchmi pod zemou,
neviditelna slucka (posledny zaber dobieha na hodnoty frameu 0), hudba s loop-crossfadom, -16 LUFS.
"""
import json
import math
import os
import re
import subprocess
import sys
import unicodedata

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import voice_stage  # noqa: E402
from props import DIRT, GOLD, INK, PAPER, prop_view  # noqa: E402
import shots  # noqa: E402

WORK = os.path.join(ROOT, "work")
OUT = os.path.join(ROOT, "out")
# Vsetko relativne k tomuto priecinku - engine bezi rovnako lokalne aj v Actions.
FONT_SRC = os.path.join(ROOT, "assets", "fonts", "ComicNeue-Bold.ttf")
MUSIC_SRC = os.path.join(ROOT, "assets", "music", "sneaky_snitch.mp3")
FPS, VW, VH, CW, CH = 24, 720, 1280, 1080, 1920
V0, LOOP_LEAD = 0.10, 1.30
SR = 48000
MIN_LEN, MAX_LEN = 28.0, 33.0
SPEEDS = (1.12, 1.20, 1.28, 1.36, 1.44, 1.52)


def sh(cmd, env=None):
    r = subprocess.run(cmd, cwd=ROOT, shell=isinstance(cmd, str), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if r.returncode:
        raise RuntimeError(f"{cmd}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r.stdout


# ================================================================== text
_PUNCT = {"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": " - ", "\u2018": "'",
          "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " ", "\u2026": "...", "\u00d7": "x"}


def normalize(s):
    for a, b in _PUNCT.items():
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip()


def norm_tok(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


# ================================================================== hlas
def monotonic(words):
    """Zarovnanie z whisperu obcas vrati slova mimo poradia (koniec slova az za
    zaciatkom nasledujuceho). Bez tejto poistky vyjde zaporna medzera, reshape_gaps
    do nej naleje sekundy ticha a z 30 s videa je 38 s."""
    bad, pe = 0, 0.0
    for w in words:
        if w["s"] < pe - 0.001:
            w["s"] = round(pe, 3)
            bad += 1
        if w["e"] < w["s"]:
            w["e"] = round(w["s"] + 0.04, 3)
        pe = w["e"]
    return words, bad


GAP_LO, GAP_HI = -0.70, 0.50


def reshape_gaps(words, a, fixes, sr):
    ops = []
    for i in sorted(fixes):
        if i + 1 >= len(words):
            continue
        cur = words[i + 1]["s"] - words[i]["e"]
        d = fixes[i] - cur
        # nikdy neposuvaj jednu medzeru o viac ako pol sekundy - aj keby zarovnanie
        # tvrdilo cokolvek, taky skok je vzdy chyba merania, nie zamer
        d = max(GAP_LO, min(GAP_HI, d))
        ops.append(((words[i]["e"] + words[i + 1]["s"]) / 2.0, round(d, 4), i))
    for mid, d, i in reversed(ops):
        k = int(round(mid * sr))
        if d > 0:
            a = np.concatenate([a[:k], np.zeros(int(round(d * sr)), dtype=np.float32), a[k:]])
        elif d < 0:
            h = int(round(-d * sr / 2))
            a = np.concatenate([a[:k - h], a[k + h:]])
    for mid, d, i in ops:
        for w in words[i + 1:]:
            w["s"] = round(w["s"] + d, 3)
            w["e"] = round(w["e"] + d, 3)
    return a, words


# ================================================================== SFX
rng = np.random.default_rng(11)


def env_ad(n, a=0.005, curve=5.0):
    t = np.arange(n) / n
    e = np.exp(-curve * t)
    k = max(1, int(a * SR))
    e[:k] *= np.linspace(0, 1, k)
    return e.astype(np.float32)


def band(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x)).astype(np.float32)


def s_pop(f0=420, f1=980, dur=0.09, vol=0.32):
    n = int(dur * SR)
    return (np.sin(2 * np.pi * np.cumsum(np.linspace(f0, f1, n)) / SR) * env_ad(n, 0.003, 6) * vol).astype(np.float32)


def s_thud(vol=0.55, f0=120, dur=0.24):
    n = int(dur * SR)
    body = np.sin(2 * np.pi * np.cumsum(np.linspace(f0, 45, n)) / SR) * env_ad(n, 0.002, 7)
    click = band(rng.standard_normal(n).astype(np.float32), 200, 1800) * env_ad(n, 0.001, 40) * 0.5
    return ((body + click) * vol).astype(np.float32)


def s_whoosh(dur=0.3, vol=0.22, lo=300, hi=3500):
    n = int(dur * SR)
    x = band(rng.standard_normal(n).astype(np.float32), lo, hi)
    return (x / (np.abs(x).max() + 1e-9) * np.hanning(n) ** 1.5 * vol).astype(np.float32)


def s_scrape(vol=0.30, dur=0.16):
    n = int(dur * SR)
    x = band(rng.standard_normal(n).astype(np.float32), 1500, 7000)
    am = 0.6 + 0.4 * np.sign(np.sin(2 * np.pi * 55 * np.arange(n) / SR))
    return (x / (np.abs(x).max() + 1e-9) * am * env_ad(n, 0.004, 4.5) * vol).astype(np.float32)


def s_whistle(f0, f1, dur, vol=0.16, vib=7.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / dur) * (1 + 0.025 * np.sin(2 * np.pi * vib * t))
    e = np.minimum(1, t / 0.04) * np.minimum(1, (dur - t) / 0.08)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * e * vol).astype(np.float32)


def s_ting(vol=0.14):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    return ((np.sin(2 * np.pi * 2350 * t) + 0.5 * np.sin(2 * np.pi * 3520 * t)) * env_ad(n, 0.002, 8) * vol).astype(np.float32)


def s_ding(f=1180, vol=0.2, dur=0.6):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * f * 2.02 * t) + 0.2 * np.sin(2 * np.pi * f * 3.01 * t)
    return (x * env_ad(n, 0.002, 5.5) * vol).astype(np.float32)


def s_scrib(dur, vol=0.13):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = band(rng.standard_normal(n).astype(np.float32), 2500, 9000)
    am = 0.35 + 0.65 * np.abs(np.sin(2 * np.pi * 9 * t))
    e = np.minimum(1, t / 0.03) * np.minimum(1, (dur - t) / 0.05)
    return (x / (np.abs(x).max() + 1e-9) * am * e * vol).astype(np.float32)


def s_boing(vol=0.2, dur=0.6, f=190):
    n = int(dur * SR)
    t = np.arange(n) / SR
    ff = f * (1 + 0.35 * np.exp(-5 * t) * np.sin(2 * np.pi * 11 * t))
    return (np.sin(2 * np.pi * np.cumsum(ff) / SR) * env_ad(n, 0.004, 4) * vol).astype(np.float32)


def s_step(vol=0.07):
    n = int(0.06 * SR)
    return (band(rng.standard_normal(n).astype(np.float32), 150, 900) * env_ad(n, 0.002, 9) * vol * 0.35).astype(np.float32)


def s_pour(dur=0.45, vol=0.26):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = band(rng.standard_normal(n).astype(np.float32), 300, 4200)
    am = 0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 26 * t))
    e = np.minimum(1, t / 0.02) * np.minimum(1, (dur - t) / 0.18)
    return (x / (np.abs(x).max() + 1e-9) * am * e * vol).astype(np.float32)


def slam_ev(t, ev, hard=1.0):
    ev += [(t, s_thud(0.70 * hard, 105, 0.3)), (t, s_pop(360, 900, 0.09, 0.26 * hard)),
           (t - 0.09, s_whoosh(0.11, 0.15 * hard, 400, 5200))]


def shot_sfx(kind, c, ev, total):
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    D = t1 - t0
    step = math.pi / (math.pi * 1.9)
    if kind in ("walk_in", "loop_lead"):
        k = 0
        while True:
            tk = (t0 + k * step) if kind == "walk_in" else (total - (k + 1) * step)
            if kind == "walk_in" and tk > t1 - 0.12:
                break
            if kind == "loop_lead" and tk <= t0 + 0.05:
                break
            ev.append((tk, s_step()))
            k += 1
            if k > 9:
                break
        if kind == "walk_in":
            ev.append((max(cu, t0 + D * 0.55), s_boing(0.16, 0.45, 240)))
    elif kind == "spot":
        ev += [(cu, s_pop(660, 1500, 0.07, 0.22)), (cu + 0.06, s_ting()), (cu, s_thud(0.34, 150, 0.2))]
    elif kind == "dig":
        for ts in (t0 + 0.08, t0 + 0.46):
            if ts < t1 - 0.1:
                ev += [(ts, s_scrape()), (ts, s_thud(0.25, 90, 0.15)), (ts + 0.14, s_whoosh(0.18, 0.13, 600, 5000))]
        ev += [(max(cu, t0 + 0.64), s_thud(0.6, 100, 0.3)), (max(cu, t0 + 0.64), s_scrib(0.4, 0.1))]
    elif kind == "descend":
        ev += [(t0, s_whistle(1450, 300, D + 0.1, 0.13)), (t0, s_whoosh(D, 0.11, 150, 1200))]
    elif kind == "scale_measure":
        ev += [(cu, s_pop(420, 1000, 0.1, 0.3)), (cu, s_scrib(min(0.9, D - 0.3), 0.12)),
               (min(t1 - 0.2, cu + 0.7), s_ding(1320, 0.17, 0.5))]
    elif kind == "human_stack":
        for i, ts in enumerate((t0 + 0.16, t0 + D * 0.42, t0 + D * 0.68)):
            ev += [(ts, s_thud(0.55, 110 + i * 30)), (ts, s_pop(380 + i * 110, 760 + i * 220, 0.07, 0.21)),
                   (ts + 0.02, s_ding(900 + i * 260, 0.11, 0.35))]
    elif kind == "wide_reveal":
        for i in range(4):
            ts = t0 + 0.05 + i * (D - 0.35) / 4.0
            ev += [(ts, s_pop(420, 1250, 0.10, 0.30 - i * 0.02)), (ts, s_thud(0.24, 150, 0.16))]
        ev.append((t1 - 0.4, s_whistle(1300, 520, 0.4, 0.09, 0)))
    elif kind == "timeline_compare":
        arrive = max(cu + 0.4, t1 - 0.55)
        ev.append((cu - 0.1, s_whoosh(min(2.0, arrive - cu + 0.3), 0.11, 200, 2600)))
        ev += [(cu + 0.2 + i * 0.09, s_step(0.22 - i * 0.008)) for i in range(int(min(16, (arrive - cu) / 0.09)))]
        slam_ev(arrive, ev, 1.25)
        ev.append((arrive + 0.12, s_whoosh(0.3, 0.12, 120, 1400)))
    elif kind == "no_list":
        items = (c["gold"] or {}).get("items") or [1, 2, 3]
        n = len(items)
        slots = list(c.get("slots") or [])
        span = (D - 0.30) / n
        for i in range(n):
            ts = slots[i] if len(slots) == n else (t0 + 0.14 + i * span)
            nxt = (slots[i + 1] if len(slots) == n and i + 1 < n else ts + span)
            sp_i = max(0.30, nxt - ts)
            slam_ev(ts, ev, 1.0)
            ev += [(ts + min(0.30, sp_i * 0.5), s_scrape(0.34, 0.2)), (ts + min(0.30, sp_i * 0.5), s_thud(0.34, 160, 0.2))]
    elif kind == "action_crowd":
        for i, ts in enumerate((t0 + D * 0.30, t0 + D * 0.52, t0 + D * 0.74)):
            ev += [(ts, s_pour(0.42, 0.24)), (ts + 0.10, s_thud(0.34, 85, 0.26))]
        ev += [(t1 - 0.34, s_ding(1550, 0.16, 0.45)), (t1 - 0.34, s_pop(560, 1250, 0.08, 0.22))]
    elif kind == "punch":
        slam_ev(cu, ev, 1.2)
        ev.append((cu + 0.3, s_boing(0.12, 0.6, 170)))
    elif kind == "loop_close":
        Q = t0 + min(0.55, D * 0.22)
        slam_ev(Q + 0.10, ev, 1.4)
        ev += [(Q + 0.34, s_boing(0.16, 0.8, 150)), (Q + 0.6, s_scrib(0.7, 0.085)),
               (t0 + D * 0.46 - 0.05, s_whoosh(0.5, 0.16, 120, 1600))]
        slam_ev(t0 + D * 0.62, ev, 1.15)
        ev.append((t1 - 0.2, s_ting(0.11)))


# ================================================================== build
SHIPS = ("ship", "ship_stern", "ship_far", "wreck")
# Palubny inventar sa strieda - sest reakcnych zaberov s tym istym sudom
# je rovnaka jednotvarnost ako sestkrat ta ista lod.
DECK_SET = ("ship_deck", "deck_wheel", "deck_anchor", "deck_nets", "deck_bell", "chest")
WHOLE = ("object_reveal", "scale_measure", "wide_reveal", "detail_compare", "timeline_compare",
         "walk_in", "loop_close")


def _deckify(key, world, kind, i=0):
    """Ked uz stojime na lodi, reakcny zaber nema ukazovat dalsiu cely lod,
    ale to, co je na palube: sud, kormidlo, kotva, siete, zvon, truhlica."""
    if key in SHIPS and kind == "scale_measure":
        return "ship"      # dlzku lode vidno z boku, nie od kormy
    if shots.W.world_kind(world) == "sea" and key in SHIPS and kind not in WHOLE:
        return DECK_SET[i % len(DECK_SET)]
    return key


def build(spec_path, html_only=False):
    spec = json.load(open(spec_path, encoding="utf-8"))
    slug = os.path.splitext(os.path.basename(spec_path))[0]
    for d in (WORK, OUT, os.path.join(ROOT, "assets", "audio"), os.path.join(ROOT, "assets", "fonts"),
              os.path.join(ROOT, "assets", "img")):
        os.makedirs(d, exist_ok=True)
    import shutil
    font_dst = os.path.join(ROOT, "assets", "fonts", "ComicNeue-Bold.ttf")
    if os.path.abspath(FONT_SRC) != os.path.abspath(font_dst):
        shutil.copy(FONT_SRC, font_dst)
    if not os.path.exists(font_dst):
        raise RuntimeError("chyba font " + font_dst)

    lines = [dict(l) for l in spec["lines"]]
    for l in lines:
        l["say"] = normalize(l["say"])
    if lines[0].get("shot") != "walk_in":
        lines[0]["shot"] = "walk_in"          # prvy zaber musi byt kopec - uzatvara slucku
    if lines[-1].get("shot") != "loop_close":
        lines[-1]["shot"] = "loop_close"

    TEXT = " ".join(l["say"] for l in lines)
    toks = TEXT.split()
    # ---- hlas: rychlost sa zvysuje, kym cela stopa (vratane preskladania medzier
    #      a minimalnej dlzky zaverecneho zaberu) nesadne pod MAX_LEN
    import copy as _copy
    idx, starts = 0, []
    for l in lines:
        starts.append(idx)
        idx += len(l["say"].split())
    fixes = {sx - 1: 0.26 for sx in starts[1:]}
    words = a = None
    # spec moze rychlost zafixovat ("speed": 1.28) -> preskoci sa hladanie a setri sa cas v crone
    ladder = SPEEDS
    if spec.get("speed"):
        sp0 = float(spec["speed"])
        # zafixovana rychlost je prve slovo, nie posledne: ked aj tak presiahne
        # MAX_LEN, engine pokracuje rebrickom nahor namiesto toho, aby spadol
        ladder = (sp0,) + tuple(s for s in SPEEDS if s > sp0 + 0.001)
    for sp in ladder:
        w0, vdur = voice_stage.run(TEXT, WORK, [0.24] * (len(lines) + 6), sp)
        if len(w0) != len(toks):
            raise RuntimeError(f"alignment: {len(w0)} slov vs {len(toks)} tokenov")
        w0, nbad = monotonic(_copy.deepcopy(w0))
        if nbad:
            print(f"  !! zarovnanie: {nbad} slov mimo poradia, opravene")
        a0, _ = sf.read(os.path.join(WORK, "voice.wav"), dtype="float32")
        a, words = reshape_gaps(_copy.deepcopy(w0), a0, fixes, 24000)
        cz = max(words[-1]["e"] + V0 + 0.34, words[starts[-1]]["s"] + V0 - 0.05 + 2.70)
        total = round(round((cz + LOOP_LEAD) * FPS) / FPS, 6)
        print(f"  speed {sp}: hlas {round(vdur, 2)} s -> celok {round(total, 2)} s")
        if total <= MAX_LEN or sp == ladder[-1]:
            break
    sf.write(os.path.join(WORK, "voice_fix.wav"), a, 24000)
    for w in words:
        w["s"] = round(w["s"] + V0, 3)
        w["e"] = round(w["e"] + V0, 3)

    CZ = round(max(words[-1]["e"] + 0.34, words[starts[-1]]["s"] - 0.05 + 2.70), 3)
    TOTAL = round(round((CZ + LOOP_LEAD) * FPS) / FPS, 6)

    # ---- kontext kazdej scene
    ctxs = []
    prev_prop, kind_seq, seen_prop, deck_i = None, {}, {}, 0
    world = spec.get("world", "hill")
    # --world=sea prepise svet zo spec-u (test noveho sveta bez zasahu do spec-u)
    for _a in sys.argv[1:]:
        if _a.startswith("--world="):
            world = _a.split("=", 1)[1]
    hero = spec.get("hero", "archaeologist")
    shots.WORLD_NOW = shots.W.world_kind(world)
    ZB, UB = (1.22, 1.10) if shots.WORLD_NOW == "sea" else (1.0, 1.0)
    for li, l in enumerate(lines):
        n = len(l["say"].split())
        lw = words[starts[li]:starts[li] + n]
        t0 = 0.0 if li == 0 else round(lw[0]["s"] - 0.05, 3)
        t1 = CZ if li == len(lines) - 1 else round(words[starts[li + 1]]["s"] - 0.05, 3)
        cue = str(l.get("cue") or "").strip()
        cue_t = None
        if cue:
            cn = norm_tok(cue)
            for w in lw:
                if norm_tok(w["w"]) == cn or (cn and cn in norm_tok(w["w"])):
                    cue_t = w["s"]
                    break
        if cue_t is None:
            cue_t = lw[min(len(lw) - 1, max(0, len(lw) // 2))]["s"]
        cue_t = max(t0 + 0.06, min(cue_t, t1 - 0.30))
        kind = l.get("shot", "punch")
        if kind not in shots.SHOTS:
            kind = "punch"
        pr = _pick(l["say"], spec, prev_prop)
        # rampa count-upu ma dobehnut na poslednom cisle vo vete (inak kota visi po doznieni)
        # no_list: slamy musia sadnut na skutocne slova ("no metal / no wheel / no writing"),
        # nie sa rovnomerne rozlozit po zabere - inak text ujde o pol sekundy
        slots = []
        if kind == "no_list":
            items = [str(x) for x in ((l.get("gold") or {}).get("items") or [])]
            used = 0
            for it in items:
                key = norm_tok(it.split()[-1]) if it.split() else ""
                for wi in range(used, len(lw)):
                    if key and key in norm_tok(lw[wi]["w"]):
                        j = wi - 1 if wi > 0 and norm_tok(lw[wi - 1]["w"]) == "no" else wi
                        slots.append(round(lw[j]["s"], 3))
                        used = wi + 1
                        break
            if len(slots) != len(items):
                slots = []
        ramp, steps = None, []
        nums = [w for w in lw if any(ch.isdigit() for ch in w["w"])]
        if nums:
            ramp = 0.45
            # viac rozmerov v jednej vete ("34 cm x 18 cm x 9 cm"): zlate cislo ich
            # preklika presne na slovach, nech nevisi zamrznute na prvom
            for w in nums[1:]:
                try:
                    steps.append((round(w["s"], 3), float(re.sub(r"[^0-9.]", "", w["w"]) or 0)))
                except ValueError:
                    pass
        ctxs.append({"p": f"s{li:02d}", "t0": t0, "t1": t1, "words": lw, "cue": cue, "cue_t": cue_t,
                     "gold": l.get("gold"), "prop": pr, "vs": l.get("vs"), "ramp": ramp, "steps": steps, "slots": slots,
                     "world": world, "hero": hero, "era": l.get("era", "ancient"), "seq": kind_seq.get(kind, 0),
                     "rep": 1 if pr == prev_prop else 0,
                     "bob": f"s{li:02d}bob", "first": li == 0, "last": li == len(lines) - 1,
                     "text": l["say"], "kind": kind,
                     "bubble": l.get("bubble"),
                     "prev_bubble": lines[li - 1].get("bubble") if li > 0 else None,
                     "view_prop": _deckify(prop_view(pr, seen_prop.get(pr, 0)), world, kind, deck_i),
                     # dve po sebe iduce "theory" vety = jedna myslienka v dvoch bublinach
                     "pair": (1 if (kind == "theory" and li + 1 < len(lines)
                                    and lines[li + 1].get("shot") == "theory") else
                              2 if (kind == "theory" and li > 0
                                    and lines[li - 1].get("shot") == "theory") else 0),
                     "prev_text": lines[li - 1]["say"] if li > 0 else ""})
        if ctxs[-1]["view_prop"] in DECK_SET:
            deck_i += 1
        seen_prop[pr] = seen_prop.get(pr, 0) + 1
        kind_seq[kind] = kind_seq.get(kind, 0) + 1
        prev_prop = pr
    # loop-uzatvaraci zaber pouziva rovnaky svet ako prvy
    zc = {"p": "sZZ", "t0": CZ, "t1": TOTAL, "total": TOTAL, "first_dur": ctxs[0]["t1"] - ctxs[0]["t0"],
          "prop": ctxs[0]["prop"], "bob": "sZZbob", "words": [], "gold": None, "cue_t": CZ,
          "world": world, "hero": hero, "era": "ancient", "vs": None, "ramp": None, "steps": [], "slots": [], "seq": 0, "rep": 0,
          "first": False, "last": True, "text": "", "kind": "loop_lead"}

    # ---- scény
    sections, ev = [], []
    js_all = "ZB = %.3f; UB = %.3f;" % (ZB, UB) + chr(10)

    for c in ctxs:
        # povrch zaberu: na mori stojime na palube, okrem zaberov, ktore ukazuju
        # CELU lod - tie patria na hladinu, inak stoji lod na lodi
        if shots.WORLD_NOW == "sea":
            shots.SURFACE = ("water" if c["kind"] in ("object_reveal", "scale_measure", "wide_reveal",
                                                      "detail_compare", "timeline_compare") else "deck")
        else:
            shots.SURFACE = "land"
        svg, js = shots.SHOTS[c["kind"]](c["p"], c)
        sections.append((c["p"], c["t0"], c["t1"], svg))
        js_all += f'\n/* ---- {c["p"]} {c["kind"]} ({c["t0"]:.2f}-{c["t1"]:.2f}) prop={c["prop"]} */\n(function(){{\n{js}}})();\n'
        shot_sfx(c["kind"], c, ev, TOTAL)
    svg, js = shots.shot_loop_lead("sZZ", zc)
    sections.append(("sZZ", CZ, TOTAL, svg))
    js_all += f'\n/* ---- sZZ loop_lead */\n(function(){{\n{js}}})();\n'
    shot_sfx("loop_lead", zc, ev, TOTAL)
    for c in ctxs[1:] + [zc]:
        ev.append((c["t0"] - 0.06, s_whoosh(0.20, 0.155)))

    # ---- titulky
    cap_html, cap_js = captions(words, lines, starts, TOTAL)

    # ---- audio
    build_audio(TOTAL, ev)
    paper_png(os.path.join(ROOT, "assets", "img", "paper.jpg"))

    import worlds as _W
    W_kind = _W.world_kind(world)
    # ---- html
    html = page(spec, sections, js_all, cap_html, cap_js, TOTAL)
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(ROOT, "hyperframes.json"), "w", encoding="utf-8").write(
        '{"paths":{"assets":"assets"},"media":{"autoProxy":false}}')
    print(f"index.html  {TOTAL}s ({round(TOTAL * FPS)} frames)  scen: {len(sections)}  world={W_kind}  hero={hero}")
    for c in ctxs:
        print(f"   {c['p']} {c['kind']:16s} {c['t0']:6.2f}-{c['t1']:6.2f} ({c['t1'] - c['t0']:4.2f}s) "
              f"prop={c['prop']:9s} | {c['text'][:52]}")
    print(f"   sZZ loop_lead        {CZ:6.2f}-{TOTAL:6.2f} ({TOTAL - CZ:4.2f}s)")
    if not (MIN_LEN <= TOTAL <= MAX_LEN):
        print(f"   !! dlzka {TOTAL}s mimo {MIN_LEN}-{MAX_LEN}s")
    if html_only:
        return TOTAL, slug
    render(slug, TOTAL)
    return TOTAL, slug


def _pick(say, spec, prev=None):
    from props import pick_prop_seq
    import worlds as W
    ov = W.apply_overrides(say)          # "case" -> vitrina, nie piratska truhla
    if ov:
        return ov
    return pick_prop_seq(say, normalize(spec.get("topic", "") + " " + spec.get("title", "")), prev)


# ================================================================== titulky
def captions(words, lines, starts, TOTAL):
    chunks = []
    for li, l in enumerate(lines):
        n = len(l["say"].split())
        lw = words[starts[li]:starts[li] + n]
        i = 0
        while i < len(lw):
            take = 2 if i + 1 < len(lw) and len(lw[i]["w"]) + len(lw[i + 1]["w"]) <= 17 else 1
            chunks.append(lw[i:i + take])
            i += take
    hh, js = "", ""
    for ci, ch in enumerate(chunks):
        spans = " ".join(f'<span class="cw" id="c{ci}_{wi}" data-t="{x["w"]}">{x["w"]}</span>' for wi, x in enumerate(ch))
        txt = " ".join(x["w"] for x in ch)
        fs = min(64, int(628.0 / (0.615 * max(1, len(txt)))))
        hh += f'<div class="cap" id="cap{ci}" style="font-size:{fs}px">{spans}</div>\n'
        c0 = max(0.0, ch[0]["s"] - 0.04)
        c1 = chunks[ci + 1][0]["s"] - 0.04 if ci < len(chunks) - 1 else round(ch[-1]["e"] + 0.40, 3)
        rot = (-2.2, 1.6, -1.2, 2.0)[ci % 4]
        js += (f'tl.set("#cap{ci}", {{ opacity: 1 }}, {c0:.3f}); tl.set("#cap{ci}", {{ opacity: 0 }}, {c1:.3f});\n'
               f'tl.fromTo("#cap{ci}", {{ scale: 0.72, rotation: {rot * 2.5:.1f} }}, {{ scale: 1, rotation: {rot}, '
               f'duration: 0.16, ease: "back.out(3)", immediateRender: false }}, {c0:.3f});\n')
        for wi, x in enumerate(ch):
            off = min(x["e"] + 0.05, ch[wi + 1]["s"] - 0.03) if wi + 1 < len(ch) else x["e"] + 0.05
            js += (f'tl.set("#c{ci}_{wi}", {{ color: "{GOLD}" }}, {max(0.0, x["s"] - 0.03):.3f}); '
                   f'tl.set("#c{ci}_{wi}", {{ color: "{INK}" }}, {off:.3f});\n')
    return hh, js


# ================================================================== audio + papier
def build_audio(TOTAL, ev):
    v48 = os.path.join(WORK, "voice48.wav")
    sh(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(WORK, "voice_fix.wav"), "-ar", str(SR), "-ac", "1", v48])
    voice, _ = sf.read(v48, dtype="float32")
    voice *= 0.85 / (np.abs(voice).max() + 1e-9)
    n = int(TOTAL * SR)
    out = np.zeros(n + SR, dtype=np.float32)
    i0 = int(V0 * SR)
    out[i0:i0 + len(voice)] += voice
    vr = float(np.sqrt((voice ** 2).mean()))
    if os.path.exists(MUSIC_SRC):
        m48 = os.path.join(WORK, "music48.wav")
        sh(["ffmpeg", "-v", "error", "-y", "-stream_loop", "2", "-i", MUSIC_SRC, "-t", str(TOTAL + 3),
            "-ar", str(SR), "-ac", "1", m48])
        mus, _ = sf.read(m48, dtype="float32")
        X = int(1.15 * SR)
        mus = np.resize(mus, n + X).astype(np.float32)
        f = np.linspace(0, 1, X, dtype=np.float32)
        mus[:X] = mus[:X] * f + mus[n:n + X] * (1 - f)          # loop-crossfade
        mus = mus[:n]
        mus *= (vr * 0.30) / (float(np.sqrt((mus ** 2).mean())) + 1e-9)
        vv = np.zeros(n, dtype=np.float32)
        vv[i0:i0 + len(voice)] = np.abs(voice[:max(0, n - i0)])
        w1 = int(0.030 * SR)
        envv = np.convolve(vv, np.ones(w1, dtype=np.float32) / w1, mode="same")
        k = int(0.18 * SR)
        envv = np.convolve(envv, np.ones(k, dtype=np.float32) / k, mode="same")
        envv /= (np.percentile(envv, 96) + 1e-9)
        mus *= 1.0 - 0.72 * np.clip(envv, 0, 1)
        out[:len(mus)] += mus
    for t, s in ev:
        i = int(t * SR)
        if 0 <= i < len(out) - len(s):
            out[i:i + len(s)] += s
    out = out[:n]
    out *= min(1.0, 0.95 / (float(np.abs(out).max()) + 1e-9))
    sf.write(os.path.join(ROOT, "assets", "audio", "mix.wav"), out, SR)


def paper_png(path):
    from PIL import Image, ImageFilter
    r = np.random.default_rng(5)
    base = np.array([246, 241, 228], dtype=np.float32)
    h, w = CH, CW
    fine = r.normal(0, 3.2, (h, w, 1)).astype(np.float32)
    blot = Image.fromarray((r.normal(128, 40, (h // 16, w // 16))).clip(0, 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    blot = (np.asarray(blot.filter(ImageFilter.GaussianBlur(9)), dtype=np.float32)[..., None] - 128) * 0.08
    yy, xx = np.mgrid[0:h, 0:w]
    vig = (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)[..., None] * -7.0
    Image.fromarray((base + fine + blot + vig).clip(0, 255).astype(np.uint8)).save(path, quality=92)


# ================================================================== HTML
BOIL = (f'<svg class="defs" aria-hidden="true"><defs>'
        f'<filter id="boilf" filterUnits="userSpaceOnUse" x="-20" y="-20" width="{CW + 40}" height="{CH + 40}">'
        f'<feTurbulence class="boil" type="fractalNoise" baseFrequency="0.022" numOctaves="2" seed="1" result="n"/>'
        f'<feDisplacementMap in="SourceGraphic" in2="n" scale="7" xChannelSelector="R" yChannelSelector="G"/>'
        f'</filter></defs></svg>')


def page(spec, sections, js_all, cap_html, cap_js, TOTAL):
    css = f"""
  @font-face {{ font-family: "Comic Neue"; src: url("assets/fonts/ComicNeue-Bold.ttf") format("truetype"); font-weight: 700; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{VW}px; height:{VH}px; overflow:hidden; background:{PAPER}; }}
  #root {{ position:relative; width:{VW}px; height:{VH}px; overflow:hidden; background:{PAPER} url("assets/img/paper.jpg") center/cover; font-family:"Comic Neue", cursive; font-weight:700; }}
  .clip {{ position:absolute; inset:0; overflow:hidden; background:{PAPER} url("assets/img/paper.jpg") center/cover; }}
  #caps {{ background:none; }}
  svg {{ position:absolute; left:0; top:0; width:{VW}px; height:{VH}px; }}
  svg.defs {{ width:0; height:0; position:absolute; left:-10px; top:-10px; }}
  .hand {{ font-family:"Comic Neue", cursive; font-weight:700; }}
  .pen {{ stroke-dasharray: 1 1; stroke-dashoffset: 1; }}
  .cap {{ position:absolute; left:0; width:{VW}px; top:876px; height:86px; line-height:86px; text-align:center; font-size:64px;
         color:{INK}; opacity:0; letter-spacing:0.005em; white-space:nowrap; isolation:isolate; }}
  .cw {{ display:inline-block; position:relative; color:{INK}; }}
  .cw::before {{ content:attr(data-t); position:absolute; left:0; top:0; z-index:-2; color:#fff; -webkit-text-stroke:14px #fff; text-shadow:0 5px 0 rgba(0,0,0,0.22); }}
  .cw::after {{ content:attr(data-t); position:absolute; left:0; top:0; z-index:-1; color:{INK}; -webkit-text-stroke:6px {INK}; }}
"""
    eng = open(os.path.join(ROOT, "engine.js"), encoding="utf-8").read()
    eng = eng.replace("/*__SCENES__*/", js_all).replace("/*__CAPTIONS__*/", cap_js)
    secs = "\n".join(f'  <section id="{sid}" class="clip" data-start="{a:.3f}" data-duration="{b - a:.3f}" data-track-index="1">{svg}</section>'
                     for sid, a, b, svg in sections)
    title = spec.get("title", "UnexplainedDaily")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width={VW}, height={VH}" />
<title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css}</style></head>
<body><div id="root" data-composition-id="main" data-start="0" data-duration="{TOTAL}" data-fps="{FPS}" data-width="{VW}" data-height="{VH}">
{secs}
  <section id="caps" class="clip" data-start="0" data-duration="{TOTAL}" data-track-index="2">{BOIL}
{cap_html}  </section>
  <audio id="mix" src="assets/audio/mix.wav" data-start="0" data-duration="{TOTAL}" data-track-index="10" data-volume="1"></audio>
</div>
<script>
var TM = {{ "total": {TOTAL} }};
{eng}
</script></body></html>
"""


# ================================================================== render + QC
def render(slug, TOTAL):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    # V cloude (SwiftShader) je `check` pomaly a nic nove uz nepovie - kod je overeny
    # lokalne. STICKMAN_SKIP_CHECK=1 ho preskoci, aby denny beh nepadol na timeout.
    if os.environ.get("STICKMAN_SKIP_CHECK", "").strip() in ("1", "true", "yes"):
        print("check preskoceny (STICKMAN_SKIP_CHECK)")
    else:
        try:
            print(sh("npx hyperframes check .", env=env)[-700:].encode("ascii", "replace").decode())
        except RuntimeError as e:
            print("CHECK FAIL:", str(e)[-2000:].encode("ascii", "replace").decode())
            sys.exit(2)
    rdir = os.path.join(ROOT, "renders")
    os.makedirs(rdir, exist_ok=True)
    sh("npx hyperframes render .", env=env)
    mp4s = [os.path.join(rdir, f) for f in os.listdir(rdir) if f.endswith(".mp4")]
    if not mp4s:
        raise RuntimeError("hyperframes render nevyrobil ziadne mp4 v " + rdir)
    rend = sorted(mp4s, key=os.path.getmtime)[-1]
    final = os.path.join(OUT, f"{slug}.mp4")
    sh(["ffmpeg", "-v", "error", "-y", "-i", rend, "-vf", "format=yuv420p", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-profile:v", "high", "-level", "4.1",
        "-maxrate", "6M", "-bufsize", "10M", "-g", "48", "-bf", "2", "-refs", "3",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", final])
    sh(["ffmpeg", "-v", "error", "-y", "-i", final, "-vf", f"fps=32/{TOTAL},scale=240:-1,tile=8x4",
        "-frames:v", "1", "-q:v", "3", os.path.join(OUT, f"{slug}_qc.jpg")])
    dur = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final]).strip())
    print("FINAL", final, round(dur, 2), "s")
    try:
        sh([sys.executable, os.path.join(ROOT, "loopcheck.py"), final, os.path.join(OUT, f"{slug}_loop.jpg")])
    except RuntimeError as e:
        print("loopcheck:", str(e)[-400:])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    sp = args[0] if os.path.isabs(args[0]) else os.path.join(ROOT, args[0])
    build(sp, html_only="--html-only" in sys.argv)
