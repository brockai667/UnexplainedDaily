# -*- coding: utf-8 -*-
"""qa.py - one-command quality gate for an episode.

    python doodle/qa.py <episode folder>              check + render + normalise + analyse (run sp.py on it first)
    python doodle/qa.py <episode folder> --no-render  re-analyse the last render (renders/<name>.mp4)
    options: --no-dom (skip headless-Chrome sampling), --keep-raw (keep renders/_raw.mp4)

Steps: hyperframes check -> render -> loudness normalisation to -16 LUFS (fixed recipe) -> frame analysis of the final mp4
(near-empty frames, frozen stretches, loop seam, duration) -> audio (loudness, true peak, AAC packets) -> DOM sampling
at 2 fps in headless Chromium (caption collisions, captions / gold / world text off-canvas) -> ONE contact sheet (2 fps)
next to the mp4. Prints a short report; exit code 1 if anything FAILs (warnings do not fail)."""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

for _stream in (sys.stdout, sys.stderr):      # Windows consoles default to cp1250: never die on a print
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
HF = "hyperframes@0.8.77"
FONT = os.path.join(HERE, "anim_src", "assets", "fonts", "ComicNeue-Bold.ttf")
W, H, SW, SH = 720, 1280, 180, 320            # canvas and analysis size (1/4)
ART_ROWS = 926 // 4                          # world area above the caption band (the world is masked below 926 px)
PAPER = np.array([246, 241, 228], dtype=np.int16)
GOLD_SLAM = 0.45                             # s after a gold stamp starts in which it may overshoot the frame (slam-in, scale 2.2 -> 1)
RESULTS = []


def res(name, status, text):
    RESULTS.append((name, status, text))
    print(f"  {name:<11}{status:<5}{text}", flush=True)


def run(cmd, cwd=None, timeout=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout or "") + (r.stderr or ""))


def npx():
    p = shutil.which("npx") or shutil.which("npx.cmd")
    if not p:
        raise SystemExit("npx not found")
    return p


def fmt_t(sec):
    return f"{sec:.2f}s"


def stretches(mask, fps, min_len):
    """runs of True in mask -> [(t0, t1)] with length >= min_len seconds"""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if (j - i) / fps >= min_len:
                out.append((i / fps, j / fps))
            i = j
        else:
            i += 1
    return out


# ------------------------------------------------------------------------------------------ steps
def step_check(ep):
    code, out = run([npx(), "--yes", HF, "check", "."], cwd=ep, timeout=600)
    errs = sum(int(x) for x in re.findall(r"(\d+) error\(s\)", out))
    warns = sum(int(x) for x in re.findall(r"(\d+) warning\(s\)", out))
    ok = "Check passed" in out and errs == 0
    first_err = next((ln.strip() for ln in out.splitlines() if "✗" in ln and "contrast" not in ln.lower() and ":1 (need" not in ln), "")
    res("check", "OK" if ok else "FAIL", f"{errs} errors, {warns} warnings (lint/contrast)" + ("" if ok else f" | {first_err[:120]}"))
    return ok


def step_render(ep, raw):
    t0 = time.time()
    code, out = run([npx(), "--yes", HF, "render", ".", "-o", raw, "--quiet"], cwd=ep, timeout=3600)
    ok = code == 0 and os.path.exists(raw) and os.path.getsize(raw) > 10000
    res("render", "OK" if ok else "FAIL", f"{time.time() - t0:.0f} s wall" + ("" if ok else " | " + out.strip().splitlines()[-1][:160] if out.strip() else ""))
    return ok


def loud(path):
    code, out = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    js = out[out.rfind("{"):out.rfind("}") + 1]
    d = json.loads(js)
    return float(d["input_i"]), float(d["input_tp"])


def step_normalise(raw, final):
    li, tp = loud(raw)
    g = -16.0 - li
    af = f"volume={g:.2f}dB,aresample=192000,alimiter=limit=0.8413:attack=5:release=60:level=false:latency=true,aresample=48000"
    code, out = run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k", final])
    if code != 0 or not os.path.exists(final):
        res("loudness", "FAIL", "normalisation failed: " + out.strip()[:160])
        return False
    return li


def step_audio(final, raw_i):
    li, tp = loud(final)
    ok = abs(li + 16) <= 1.0 and tp <= -1.0
    res("loudness", "OK" if ok else "FAIL", f"{li:.1f} LUFS, true peak {tp:.1f} dBTP" + (f" (raw {raw_i:.1f} LUFS)" if raw_i is not None else ""))
    code, out = run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "packet=pts,duration", "-of", "csv=p=0", final])
    pk = []
    for ln in out.splitlines():
        p = ln.strip().split(",")
        if len(p) >= 2 and p[0] not in ("", "N/A") and p[1] not in ("", "N/A"):
            pk.append((int(p[0]), int(p[1])))
    if not pk:
        res("aac", "FAIL", "no audio packets")
        return False
    short = sum(1 for _, d in pk[:-1] if d <= 1)
    gaps = sum(1 for (a, da), (b, _) in zip(pk, pk[1:]) if abs((b - a) - da) > 1)
    ok2 = short == 0 and gaps == 0
    res("aac", "OK" if ok2 else "FAIL", f"{len(pk)} packets, {short} with duration<=1, {gaps} timestamp gaps")
    return ok and ok2


def probe_dur(path, sel):
    code, out = run(["ffprobe", "-v", "error", "-select_streams", sel, "-show_entries", "stream=duration,width,height,r_frame_rate", "-of", "json", path])
    s = json.loads(out)["streams"][0]
    return s


def load_frames(final):
    code = subprocess.run(["ffmpeg", "-v", "error", "-i", final, "-vf", f"scale={SW}:{SH}:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True)
    buf = code.stdout
    n = len(buf) // (SW * SH * 3)
    return np.frombuffer(buf[:n * SW * SH * 3], dtype=np.uint8).reshape(n, SH, SW, 3)


def step_frames(fr, fps, total, loop):
    ok = True
    art = fr[:, :ART_ROWS].astype(np.int16)
    # ink coverage: share of the world area that is not plain paper
    diff = np.abs(art - PAPER).max(axis=3)
    ink = (diff > 34).mean(axis=(1, 2))
    empty = ink < 0.03
    bad = stretches(empty, fps, 0.5)
    short = stretches(empty, fps, 0.2)
    lo = int(np.argmin(ink))
    if bad:
        ok = False
        res("blank", "FAIL", "near-empty " + ", ".join(f"{fmt_t(a)}-{fmt_t(b)}" for a, b in bad))
    elif short:
        res("blank", "WARN", "short near-empty flashes " + ", ".join(f"{fmt_t(a)}-{fmt_t(b)}" for a, b in short[:6]))
    else:
        res("blank", "OK", f"min ink {100 * ink[lo]:.1f} % at {fmt_t(lo / fps)}")
    # frozen: compare frames 12 apart (same line-boil seed) -> only real motion counts
    g = art.mean(axis=3)
    d12 = np.zeros(len(g))
    d12[12:] = np.abs(g[12:] - g[:-12]).mean(axis=(1, 2))
    d12[:12] = d12[12] if len(g) > 12 else 1
    still = d12 < 0.35                                               # approved Carancas never goes below 0.84
    # a run of low d12 of length L means the picture stood still for L + 0.5 s (it starts 12 frames earlier)
    fz = [(a - 12 / fps, b) for a, b in stretches(still, fps, 0.5)]    # >= 1.0 s without motion
    fw = [(a - 12 / fps, b) for a, b in stretches(still, fps, 0.25)]   # >= 0.75 s
    lo2 = int(np.argmin(d12))
    if fz:
        ok = False
        res("frozen", "FAIL", "no motion " + ", ".join(f"{fmt_t(a)}-{fmt_t(b)}" for a, b in fz))
    elif fw:
        res("frozen", "WARN", "almost still " + ", ".join(f"{fmt_t(a)}-{fmt_t(b)}" for a, b in fw))
    else:
        res("frozen", "OK", f"no still stretch; least motion {d12[lo2]:.2f} at {fmt_t(lo2 / fps)} (limit 0.35, frames 0.5 s apart)")
    # loop seam
    if loop:
        seam = float(np.abs(fr[-1].astype(np.int16) - fr[0].astype(np.int16)).mean())
        s_ok = seam <= 4.0
        ok &= s_ok
        res("loop seam", "OK" if s_ok else "FAIL", f"last vs first frame mean diff {seam:.2f} (<= 4)")
    return ok


def step_duration(final, total):
    v, a = probe_dur(final, "v:0"), probe_dur(final, "a:0")
    vd, ad = float(v.get("duration", 0)), float(a.get("duration", 0))
    ok = abs(vd - total) <= 0.1 and abs(ad - vd) <= 0.12
    res("duration", "OK" if ok else "FAIL", f"video {vd:.2f} s, audio {ad:.2f} s, screenplay {total:.2f} s, {v.get('width')}x{v.get('height')} @ {v.get('r_frame_rate')}")
    return ok


def step_sheet(fr, fps, total, path):
    n = int(math.floor(total * 2 + 1e-6))
    idx = [min(len(fr) - 1, int(round(k * fps / 2))) for k in range(n)]
    cols, tw, th, lab = 10, SW, SH, 22
    rows = math.ceil(len(idx) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + lab)), (27, 27, 27))
    try:
        font = ImageFont.truetype(FONT, 17)
    except OSError:
        font = ImageFont.load_default()
    dr = ImageDraw.Draw(sheet)
    for k, i in enumerate(idx):
        x, y = (k % cols) * tw, (k // cols) * (th + lab)
        sheet.paste(Image.fromarray(fr[i]), (x, y + lab))
        dr.text((x + 5, y + 2), f"{i / fps:.1f}s", fill=(235, 235, 235), font=font)
    sheet.save(path, quality=88)
    res("sheet", "OK", os.path.relpath(path, HERE))


DOM_JS = r"""
async (t) => {
  const tl = window.__timelines.main;
  tl.totalTime(t + 0.001, true); tl.totalTime(t, false);
  const on = el => { const s = +el.dataset.start, d = +el.dataset.duration; return t >= s && t < s + d; };
  const clips = [...document.querySelectorAll('#root > .clip')];
  clips.forEach(c => c.style.visibility = on(c) ? 'visible' : 'hidden');
  const box = r => [r.left, r.top, r.right, r.bottom];
  const textBox = el => {                                            // union of the glyph runs (not the full-width blocks)
    const wk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let n, b = null;
    while ((n = wk.nextNode())) { if (!n.textContent.trim()) continue; const rg = document.createRange(); rg.selectNodeContents(n);
      const r = rg.getBoundingClientRect(); b = b ? [Math.min(b[0], r.left), Math.min(b[1], r.top), Math.max(b[2], r.right), Math.max(b[3], r.bottom)] : box(r); }
    return b || [0, 0, 0, 0]; };
  const eff = el => { let o = 1; for (let e = el; e && e !== document.body; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.visibility === 'hidden' || cs.display === 'none') return 0; o *= parseFloat(cs.opacity); } return o; };
  const caps = clips.filter(c => c.classList.contains('over') && on(c)).map(c => {
    const ws = [...c.querySelectorAll('.cw')].map(w => w.getBoundingClientRect());
    return { id: c.id, text: c.textContent.trim(), box: [Math.min(...ws.map(r => r.left)), Math.min(...ws.map(r => r.top)), Math.max(...ws.map(r => r.right)), Math.max(...ws.map(r => r.bottom))] };
  });
  const sg = (typeof SP !== 'undefined' && SP && SP.gold) || [];            // SP.gold[].t = the moment a gold stamp starts (index.html)
  const golds = [...document.querySelectorAll('.gold')].filter(g => eff(g) > 0.05).map(g => {
    const s = sg.find(x => 'gold_' + x.key === g.id);
    return { id: g.id, text: g.textContent.trim(), box: textBox(g), t0: s ? s.t : null }; });
  const texts = [...document.querySelectorAll('.scene svg text')].filter(x => eff(x) > 0.1 && x.textContent.trim()).map(x => ({ id: x.textContent.trim(), box: box(x.getBoundingClientRect()) }));
  return { caps, golds, texts };
}
"""


def step_dom(ep, total):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        res("dom", "WARN", "playwright not installed - DOM checks skipped")
        return True
    samples = [round(k * 0.5, 3) for k in range(int(total * 2)) if k * 0.5 < total - 0.05]
    cap_coll, cap_off, gold_off, gold_hit, text_off = [], [], [], [], {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(Path(ep, "index.html").resolve().as_uri())          # file:///C:/... on Windows, file:///home/... on Linux
        pg.wait_for_function("!!(window.__timelines && window.__timelines.main)", timeout=30000, polling=200)
        pg.evaluate("document.fonts.ready.then(() => 1)")
        for t in samples:
            d = pg.evaluate(DOM_JS, t)
            caps = d["caps"]
            if len(caps) > 1:
                cap_coll.append(f"{t:.1f}s: {' | '.join(c['text'] for c in caps)}")
            for c in caps:
                x0, y0, x1, y1 = c["box"]
                if x0 < 2 or x1 > W - 2 or y1 > H - 2:
                    cap_off.append(f"{t:.1f}s '{c['text']}' x {x0:.0f}..{x1:.0f}")
                for g in d["golds"]:
                    gx0, gy0, gx1, gy1 = g["box"]
                    if gx0 < x1 and x0 < gx1 and gy0 < y1 and y0 < gy1:
                        gold_hit.append(f"{t:.1f}s gold '{g['text']}' over caption '{c['text']}'")
            for g in d["golds"]:                                         # gold cut by the frame edge
                if g.get("t0") is not None and t < g["t0"] + GOLD_SLAM:      # the slam-in (scale 2.2 -> 1 in ~0.4 s) overshoots the frame on purpose
                    continue
                gx0, gy0, gx1, gy1 = g["box"]
                area = max(0.0, gx1 - gx0) * max(0.0, gy1 - gy0)
                vis = max(0.0, min(gx1, W) - max(gx0, 0)) * max(0.0, min(gy1, H) - max(gy0, 0))
                if area > 4 and 0 < vis < 0.98 * area:
                    gold_off.append(f"{t:.1f}s '{g['text']}' box {gx0:.0f},{gy0:.0f}..{gx1:.0f},{gy1:.0f}")
            for x in d["texts"]:                                         # world text cut by the frame edge (fully hidden = fine)
                tx0, ty0, tx1, ty1 = x["box"]
                area = max(0.0, tx1 - tx0) * max(0.0, ty1 - ty0)
                if area < 4:
                    continue
                vis = max(0.0, min(tx1, W) - max(tx0, 0)) * max(0.0, min(ty1, 926) - max(ty0, 0))
                if 0 < vis < 0.9 * area:
                    text_off.setdefault(x["id"], []).append(t)
        b.close()
    ok = not (cap_coll or cap_off or gold_off or gold_hit or errors)
    res("captions", "OK" if not (cap_coll or cap_off) else "FAIL",
        f"{len(samples)} samples, {len(cap_coll)} collisions, {len(cap_off)} off-canvas" + (" | " + "; ".join((cap_coll + cap_off)[:3]) if cap_coll or cap_off else ""))
    res("gold", "OK" if not (gold_off or gold_hit) else "FAIL",
        f"{len(gold_off)} off-canvas, {len(gold_hit)} over captions" + (" | " + "; ".join((gold_off + gold_hit)[:3]) if gold_off or gold_hit else ""))
    if text_off:
        res("world text", "WARN", "; ".join(f"'{k}' leaves the frame at {min(v):.1f}-{max(v):.1f}s ({len(v)}x)" for k, v in list(text_off.items())[:4]))
    else:
        res("world text", "OK", "all visible SVG texts inside the frame")
    if errors:
        res("js", "FAIL", "; ".join(errors[:2])[:200])
    return ok


# ------------------------------------------------------------------------------------------ main
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        raise SystemExit("usage: python doodle/qa.py <episode folder> [--no-render] [--no-dom] [--keep-raw]   (sp.py first, or: python doodle/factory.py --dry-run)")
    ep = os.path.abspath(args[0])
    name = os.path.basename(ep)
    rdir = os.path.join(ep, "renders")
    os.makedirs(rdir, exist_ok=True)
    raw, final, sheet = os.path.join(rdir, "_raw.mp4"), os.path.join(rdir, f"{name}.mp4"), os.path.join(rdir, f"{name}_sheet.jpg")
    tj = os.path.join(ep, "work", "timing.json")
    if not os.path.exists(tj) or not os.path.exists(os.path.join(ep, "index.html")):
        raise SystemExit(f"compile first: python sp.py {os.path.relpath(ep, HERE)}")
    timing = json.load(open(tj, encoding="utf-8"))
    total, loop = float(timing["total"]), timing.get("loop")
    print(f"QA {name}  ({total:.2f} s)")
    ok = step_check(ep)
    raw_i = None
    if "--no-render" not in flags:
        if not step_render(ep, raw):
            return 1
        raw_i = step_normalise(raw, final)
        if raw_i is False:
            return 1
        if "--keep-raw" not in flags:
            os.remove(raw)
    elif not os.path.exists(final):
        raise SystemExit(f"no render at {final}")
    ok &= step_duration(final, total)
    ok &= step_audio(final, raw_i)
    fr = load_frames(final)
    fps = float(eval(probe_dur(final, "v:0")["r_frame_rate"]))
    ok &= step_frames(fr, fps, total, loop)
    if "--no-dom" not in flags:
        ok &= step_dom(ep, total)
    step_sheet(fr, fps, total, sheet)
    res("video", "OK", os.path.relpath(final, HERE))
    warns = sum(1 for r in RESULTS if r[1] == "WARN")
    fails = [r[0] for r in RESULTS if r[1] == "FAIL"]
    print(f"RESULT: {'PASS' if not fails else 'FAIL (' + ', '.join(fails) + ')'}" + (f" ({warns} warning{'s' if warns != 1 else ''})" if warns else ""))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
