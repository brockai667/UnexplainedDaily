#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doodle/factory.py - ONE episode from doodle/queue/ -> video (-> Buffer).

    python doodle/factory.py --dry-run [--name 001-devon1855] [--keep]    # render + QA only, nothing published or moved
    python doodle/factory.py [--name 001-devon1855]                       # ... and publish, move to done/, log in published.json

1. picks the alphabetically first folder of doodle/queue/ (or --name) and validates its meta.json
2. copies it to doodle/work/<name>/ and runs sp.py (voice + compile), then qa.py (check, render, loudness, analysis) on the copy;
   a non-zero exit of either stops everything with exit code 1 and prints the last 30 lines of its output
3. writes doodle/out/<name>.mp4, <name>_sheet.jpg and <name>.txt (title, blank line, description, tags, music credit)
4. without --dry-run: publishes through stickman/run_daily.py publish() (GitHub Release hosting, Cloudinary fallback, Buffer posts to
   the channels of config.json), moves the queue folder to doodle/done/ and appends {name, title, date, slot} to doodle/published.json
5. prints one line:  RESULT name=<..> duration=<s> qa=<PASS|FAIL> out=<path>

Environment (publishing only; appconfig.py / push_to_buffer.py read them): BUFFER_TOKEN, GITHUB_TOKEN + GITHUB_REPOSITORY (video
hosting), optional CLOUDINARY_CLOUD_NAME / _API_KEY / _API_SECRET (hosting fallback).
DOODLE_SLOT = HH:MM in UTC, the next occurrence of that time is the Buffer post time (default 12:00).
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import traceback

for _stream in (sys.stdout, sys.stderr):      # Windows consoles default to cp1250: never die on a print
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DOODLE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(DOODLE)
QUEUE, DONE, WORK, OUT = (os.path.join(DOODLE, d) for d in ("queue", "done", "work", "out"))
STATE = os.path.join(DOODLE, "published.json")
STICKMAN = os.path.join(REPO, "stickman")
META_KEYS = ("title", "description", "tags", "music_credit")
DEFAULT_SLOT = "12:00"


class FactoryError(Exception):
    pass


def log(msg=""):
    print(msg, flush=True)


def rel(path):
    """repo-relative path with forward slashes (same text on Windows and Linux)"""
    return os.path.relpath(path, REPO).replace("\\", "/")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ queue + meta
def pick_episode(name):
    if name:
        if name in (".", "..") or name != os.path.basename(name.replace("\\", "/")):
            raise FactoryError(f"--name must be a plain folder name of doodle/queue, got {name!r}")
        if not os.path.isfile(os.path.join(QUEUE, name, "screenplay.yaml")):
            raise FactoryError(f"no queue folder '{name}' with a screenplay.yaml in {rel(QUEUE)}")
        return name
    if not os.path.isdir(QUEUE):
        return None
    names = sorted(d for d in os.listdir(QUEUE) if os.path.isfile(os.path.join(QUEUE, d, "screenplay.yaml")))
    return names[0] if names else None


def load_meta(name):
    path = os.path.join(QUEUE, name, "meta.json")
    try:
        meta = load_json(path, None)
    except ValueError as e:
        raise FactoryError(f"{rel(path)}: invalid JSON ({e})")
    if not isinstance(meta, dict):
        raise FactoryError(f"{rel(path)} is missing or not a JSON object")
    missing = [k for k in META_KEYS if k not in meta]
    if missing:
        raise FactoryError(f"{rel(path)}: missing keys {', '.join(missing)}")
    if not str(meta["title"]).strip() or not str(meta["description"]).strip():
        raise FactoryError(f"{rel(path)}: title and description must not be empty")
    if not isinstance(meta["tags"], list) or not all(isinstance(t, str) and t.strip() for t in meta["tags"]):
        raise FactoryError(f"{rel(path)}: tags must be a list of non-empty strings")
    return meta


def caption(meta):
    """-> (title, body). Body = description, tags on one line, music credit - paragraphs, like make_video.py writes its .txt;
    push_to_buffer.read_txt() reads the same file (first line = title, the rest = description)."""
    parts = [str(meta["description"]).strip(), " ".join(t.strip() for t in meta["tags"]), str(meta["music_credit"] or "").strip()]
    return str(meta["title"]).strip(), "\n\n".join(p for p in parts if p)


# ------------------------------------------------------------------ build
def stage(name):
    """queue/<name> -> work/<name>. Stale compile output and renders of an earlier run go away; work/<name>/work stays
    (voice cache, keyed by text + speed + voice) so a re-run with --keep does not repeat TTS and whisper."""
    src, dst = os.path.join(QUEUE, name), os.path.join(WORK, name)
    if os.path.isdir(dst):
        for entry in os.listdir(dst):
            if entry == "work":
                continue
            p = os.path.join(dst, entry)
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst


def run_step(label, cmd):
    """Run cmd with its output streamed live (a killed job still leaves a log). -> (exit code, all output lines)"""
    log(f"--- {label}")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    lines = []
    for line in proc.stdout:
        line = line.rstrip("\r\n")
        lines.append(line)
        log("    " + line)
    return proc.wait(), lines


def show_tail(label, lines):
    log(f"\n!!! {label} failed - last 30 lines of its output:")
    for line in lines[-30:]:
        log("    " + line)


def probe_duration(mp4, wd):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                           capture_output=True, text=True, timeout=60)
        return round(float(r.stdout.strip().splitlines()[0]), 1)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        pass
    try:
        return round(float(load_json(os.path.join(wd, "work", "timing.json"), {})["total"]), 1)
    except (OSError, ValueError, KeyError):
        return None


def copy_outputs(name, wd):
    """renders/<name>.mp4 + _sheet.jpg -> out/. Returns the out mp4 path, or None if there is no render."""
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(wd, "renders", name + ".mp4")
    if not os.path.exists(src):
        return None
    out = os.path.join(OUT, name + ".mp4")
    shutil.copyfile(src, out)
    sheet = os.path.join(wd, "renders", name + "_sheet.jpg")
    if os.path.exists(sheet):
        shutil.copyfile(sheet, os.path.join(OUT, name + "_sheet.jpg"))
    return out


def write_sidecar(name, title, body):
    with open(os.path.join(OUT, name + ".txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(title + "\n\n" + body + "\n")


def result(name, duration, qa, out):
    log(f"RESULT name={name} duration={'-' if duration is None else duration} qa={qa} out={rel(out) if out else '-'}")


# ------------------------------------------------------------------ publish
def slot_iso(hhmm):
    """'HH:MM' (UTC) -> ISO time of its next occurrence, at least 10 minutes ahead, in the format Buffer's dueAt wants."""
    try:
        h, m = (int(x) for x in str(hhmm).strip().split(":"))
        now = datetime.datetime.now(datetime.timezone.utc)
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    except ValueError:
        raise FactoryError(f"slot must be HH:MM (UTC), got {hhmm!r}")
    if t <= now + datetime.timedelta(minutes=10):
        t += datetime.timedelta(days=1)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def publish(mp4, title, body, due):
    """Same code path as the stickman factory: stickman/run_daily.py publish() = video hosting (GitHub Release, fallback Cloudinary)
    + one Buffer post per channel of config.json + an entry in the shared pushed.json. publish() asks run_daily.next_slot() for the
    post time (a random time in 06-11 UTC); that one function is replaced by the slot of this run, nothing else is copied."""
    cfg = os.path.join(REPO, "config.json")
    if not os.path.exists(cfg):          # secrets come from the environment (appconfig.py overlays BUFFER_TOKEN etc.)
        shutil.copyfile(os.path.join(REPO, "config.example.json"), cfg)
        log("  [config] config.json was missing -> copied from config.example.json (secrets are taken from the environment)")
    sys.path.insert(0, STICKMAN)
    import run_daily                      # puts stickman/ and the repo root (push_to_buffer, appconfig) on sys.path
    run_daily.next_slot = lambda: due
    return run_daily.publish(mp4, title, body)


def finish_publish(name, title, due):
    """After a successful publish: log it in published.json, then move queue/<name> to done/<name>."""
    state = load_json(STATE, [])
    if not isinstance(state, list):
        raise FactoryError(f"{rel(STATE)} must be a JSON list")
    state.append({"name": name, "title": title,
                  "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"), "slot": due})
    with open(STATE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.makedirs(DONE, exist_ok=True)
    dst = os.path.join(DONE, name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.move(os.path.join(QUEUE, name), dst)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Render (and publish) the next doodle episode from doodle/queue/.")
    ap.add_argument("--dry-run", action="store_true", help="render + QA + write doodle/out/; publish nothing, move nothing")
    ap.add_argument("--name", default=None, help="queue folder to use (default: the alphabetically first)")
    ap.add_argument("--keep", action="store_true", help="keep doodle/work/<name>/ after a successful run (a failed run always keeps it)")
    a = ap.parse_args()

    name = pick_episode(a.name)
    if not name:
        log("doodle/queue is empty - nothing to do")
        return 0
    meta = load_meta(name)
    title, body = caption(meta)
    due = None if a.dry_run else slot_iso(os.environ.get("DOODLE_SLOT") or DEFAULT_SLOT)   # a typo fails now, not after the render
    log(f"=== {name}: {title}  ({'dry-run' if a.dry_run else 'publish at ' + due}) ===")

    wd = stage(name)
    code, lines = run_step("sp.py - voice + compile", [sys.executable, os.path.join(DOODLE, "sp.py"), wd])
    if code != 0:
        show_tail("sp.py", lines)
        log(f"work folder kept: {rel(wd)}")
        result(name, None, "FAIL", None)
        return 1

    code, lines = run_step("qa.py - check + render + loudness + analysis", [sys.executable, os.path.join(DOODLE, "qa.py"), wd])
    out = copy_outputs(name, wd)             # also after a FAIL: the video and the contact sheet are the only debugging aid in CI
    duration = probe_duration(out, wd) if out else None
    if code != 0:
        show_tail("qa.py", lines)
        log(f"work folder kept: {rel(wd)}")
        result(name, duration, "FAIL", out)
        return 1
    if not out:
        raise FactoryError(f"qa.py passed but {rel(os.path.join(wd, 'renders', name + '.mp4'))} is missing")
    write_sidecar(name, title, body)
    log(f"  [out] {rel(out)}  {rel(out)[:-4]}_sheet.jpg  {rel(out)[:-4]}.txt")

    if a.dry_run:
        log("DRY-RUN: nothing published, queue folder stays.")
    else:
        try:
            url, due_sent, ok_services, fails = publish(out, title, body, due)
        except Exception:
            traceback.print_exc()
            log("PUBLISH FAILED - the queue folder stays, nothing was logged.")
            result(name, duration, "PASS", out)
            return 1
        if fails:
            log("  WARNING: not accepted by " + ", ".join(fails) + " (the others were queued, so the episode counts as published)")
        finish_publish(name, title, due_sent)
        log(f"PUBLISHED: {title} -> {', '.join(ok_services)} at {due_sent}  {url}")

    if not a.keep:
        shutil.rmtree(wd, ignore_errors=True)
    result(name, duration, "PASS", out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FactoryError as e:
        log(f"FACTORY ERROR: {e}")
        sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
