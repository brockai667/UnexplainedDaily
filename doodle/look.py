# -*- coding: utf-8 -*-
"""look.py - "mechanical eyes": where is every screenplay object on screen at time t, and is it visible?

    python doodle/look.py <episode folder> --at 6.5,8.0 [--ids a,b] [--word prints,snow]   -> JSON on stdout
    from look import measure, word_time          (doodle/ on sys.path)

Opens <episode>/index.html (run sp.py first) in headless Chromium, seeks the GSAP timeline like qa.py does and asks the DOM:
runtime.js tags the root <g> of every screenplay object with data-oid (+ data-kind), the scene clip is <div id="sc_<scene>">.

    measure(ep_dir, times, ids=None) -> [{"t": 8.61, "scene": "yard", "objects": [
        {"id": "p1", "kind": "shape", "box": [x0, y0, x1, y1], "w": 128.0, "h": 60.0, "opacity": 1.0, "in_frame": 0.97}, ...]}, ...]

  * scene     the scene visible at t (during a transition the one that owns most of the world area); null if none.
  * box       frame pixels (720 x 1280, camera + page transforms included, may extend outside) = union of the drawn leaf shapes
              of the object, strokes included. Sub-parts that are fully transparent / display:none are skipped (an emitter
              box covers only the particles drawn right now); the object's own opacity is NOT applied to the box, so a hidden
              object (opacity 0) still says where it would appear. null = nothing drawn at all.
  * opacity   effective opacity (product over all ancestors; 0 when display:none / visibility:hidden), same as qa.py.
  * in_frame  share of the box area inside the world area x 0..720, y 0..926 (below 926 the paper/caption band starts).
  * ids       optional filter: exact object id or id prefix ("p" -> p1, p2..; "cot" -> cot, cot.door, cotL ...; parts are "id.part").
Only objects that have an id are tagged. Not measured: the line-boil displacement filter (about +-2 px), clip-paths, the
white flash / speed-line overlays, HTML captions and gold counters (qa.py checks those)."""
import argparse
import json
import re
import sys
from pathlib import Path

W, H, WORLD_H = 720, 1280, 926                 # frame and the world area above the caption band (qa.py: ART_ROWS * 4)
WORD_DELAY = 0.6                               # --word: look this long after the word starts

LOOK_JS = r"""
async ([t, ids]) => {
  const tl = window.__timelines.main;
  tl.totalTime(t + 0.001, true); tl.totalTime(t, false);
  const on = el => { const s = +el.dataset.start, d = +el.dataset.duration; return t >= s && t < s + d; };
  const eff = el => { let o = 1; for (let e = el; e && e !== document.body; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.visibility === 'hidden' || cs.display === 'none') return 0; o *= parseFloat(cs.opacity); } return o; };
  document.body.getBoundingClientRect();
  await document.fonts.ready;
  const clips = [...document.querySelectorAll('#root > .clip.scene')];
  clips.forEach(c => c.style.visibility = on(c) ? 'visible' : 'hidden');
  const pgOf = c => c.querySelector('.page') || c;                   // the page is what slides / fades, the clip div never moves
  const cands = clips.filter(c => on(c) && eff(pgOf(c)) > 0.02);
  let host = cands[cands.length - 1] || null;
  if (cands.length > 1) {                                            // transition: the scene whose page owns most of the world area
    const own = new Map(), pages = cands.map(pgOf);
    for (let iy = 0; iy < 8; iy++) for (let ix = 0; ix < 6; ix++) {
      const p = document.elementsFromPoint((ix + 0.5) * 120, (iy + 0.5) * 115.75).map(e => e.closest('.page, .scene')).find(e => e && pages.includes(e));
      if (p) own.set(p, (own.get(p) || 0) + 1);
    }
    host = cands.reduce((b, c) => (own.get(pgOf(c)) || 0) >= (own.get(pgOf(b)) || 0) ? c : b);
  }
  const SKIP = new Set(['defs', 'clipPath', 'mask', 'linearGradient', 'radialGradient', 'filter', 'pattern', 'symbol', 'marker', 'title', 'desc', 'style', 'script']);
  const drawn = root => {                                            // union of the leaf boxes that are really painted
    let b = null;
    const walk = (e, o) => {
      if (SKIP.has(e.localName)) return;
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden') return;
      if (e !== root) { o *= parseFloat(cs.opacity); if (o < 0.02) return; }
      if (e.firstElementChild) { for (const c of e.children) walk(c, o); return; }
      const r = e.getBoundingClientRect();                           // Chromium gives the geometry box only: the stroke is added below
      if (!r.width && !r.height) return;
      let pad = 0;
      if (cs.stroke !== 'none' && parseFloat(cs.strokeOpacity) > 0) {
        const m = e.getScreenCTM(), k = cs.vectorEffect === 'non-scaling-stroke' || !m ? 1 : Math.sqrt(Math.abs(m.a * m.d - m.b * m.c));
        pad = (parseFloat(cs.strokeWidth) || 0) * k / 2;
      }
      const q = [r.left - pad, r.top - pad, r.right + pad, r.bottom + pad];
      b = b ? [Math.min(b[0], q[0]), Math.min(b[1], q[1]), Math.max(b[2], q[2]), Math.max(b[3], q[3])] : q;
    };
    walk(root, 1);
    return b;
  };
  const objects = !host ? [] : [...host.querySelectorAll('[data-oid]')]
    .filter(g => !ids || ids.some(f => g.dataset.oid === f || g.dataset.oid.startsWith(f)))
    .map(g => ({ id: g.dataset.oid, kind: g.dataset.kind || null, box: drawn(g), opacity: eff(g) }));
  return { scene: host ? (host.dataset.scene || host.id.replace(/^sc_/, '')) : null, objects, tagged: document.querySelectorAll('[data-oid]').length };
}
"""


def _norm(s):
    return re.sub(r"[\W_]+", "", str(s).lower())            # case-insensitive, punctuation ignored (same idea as sp.py norm)


def word_time(ep_dir, word, sentence_key=None):
    """Start time (s) of the first narrated `word` in <ep>/work/timing.json. `sentence_key` ("s2") limits the search to that
    sentence; "s2/snow" does the same inline (useful when a word is said in several sentences). Raises LookupError."""
    tj = Path(ep_dir) / "work" / "timing.json"
    if not tj.is_file():
        raise FileNotFoundError(f"{tj} not found - compile first: python doodle/sp.py {ep_dir}")
    words = json.loads(tj.read_text(encoding="utf-8"))["words"]
    word = str(word)
    if sentence_key is None and "/" in word:
        sentence_key, word = word.split("/", 1)
    want = _norm(word)
    if want:
        for w in words:
            if (sentence_key is None or w["k"] == sentence_key) and _norm(w["w"]) == want:
                return float(w["s"])
    raise LookupError(f"word {word!r} not found" + (f" in sentence {sentence_key!r}" if sentence_key else "") + f" in {tj} ({len(words)} words)")


def _frac(a0, a1, lo, hi):
    if a1 - a0 > 1e-9:
        return max(0.0, min(a1, hi) - max(a0, lo)) / (a1 - a0)
    return 1.0 if lo <= a0 <= hi else 0.0                   # degenerate (line / point): inside or not


def _shape(o):
    box = o["box"]
    row = {"id": o["id"], "kind": o["kind"], "box": None, "w": None, "h": None, "opacity": round(float(o["opacity"]), 3), "in_frame": None}
    if box:
        x0, y0, x1, y1 = box
        row.update(box=[round(v, 1) + 0.0 for v in box], w=round(x1 - x0, 1) + 0.0, h=round(y1 - y0, 1) + 0.0,
                   in_frame=round(_frac(x0, x1, 0, W) * _frac(y0, y1, 0, WORLD_H), 3))
    return row


def measure(ep_dir, times, ids=None):
    """Where is every screenplay object at each time in `times` (seconds)? One browser launch for all times; see the module doc."""
    page = Path(ep_dir).resolve() / "index.html"
    if not page.is_file():
        raise FileNotFoundError(f"{page} not found - compile first: python doodle/sp.py {ep_dir}")
    if isinstance(times, (int, float)):
        times = [times]
    if isinstance(ids, str):
        ids = ids.split(",")
    ids = [s for s in (str(i).strip() for i in (ids or [])) if s] or None      # None = every object
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        raise RuntimeError("playwright is not installed (pip install playwright; python -m playwright install chromium)")
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            pg = b.new_page(viewport={"width": W, "height": H})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(page.as_uri())                                       # file:///C:/... on Windows, file:///home/... on Linux
            try:
                pg.wait_for_function("!!(window.__timelines && window.__timelines.main)", timeout=30000, polling=200)
            except PWTimeout:
                raise RuntimeError("the page never built its timeline (gsap is loaded from a CDN - offline?)" + (": " + "; ".join(errors[:2]) if errors else ""))
            pg.evaluate("document.fonts.ready.then(() => 1)")
            for t in times:
                d = pg.evaluate(LOOK_JS, [float(t), ids])
                if not d["tagged"]:
                    raise RuntimeError(f"{page} has no data-oid tags - it was compiled before runtime.js tagged objects: re-run python doodle/sp.py {ep_dir}")
                out.append({"t": round(float(t), 3), "scene": d["scene"], "objects": [_shape(o) for o in d["objects"]]})
        finally:
            b.close()
    return out


def to_json(res):
    """valid JSON, one object per line (readable and greppable)"""
    rows = []
    for r in res:
        head = json.dumps({"t": r["t"], "scene": r["scene"]}, ensure_ascii=False)[:-1]
        objs = ",\n".join("   " + json.dumps(o, ensure_ascii=False) for o in r["objects"])
        rows.append(f'  {head}, "objects": [\n{objs}\n  ]}}' if objs else f'  {head}, "objects": []}}')
    return "[\n" + ",\n".join(rows) + "\n]"


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):                  # Windows consoles default to cp1250: never die on a print
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Where is each screenplay object on screen at time t? (JSON)")
    ap.add_argument("episode", help="episode folder (compiled with sp.py)")
    ap.add_argument("--at", default="", help="comma-separated times in seconds, e.g. 6.5,8.0")
    ap.add_argument("--ids", default="", help="comma-separated object ids or id prefixes, e.g. p,wom")
    ap.add_argument("--word", default="", help=f"comma-separated narrated words: measure {WORD_DELAY} s after each word starts (s2/snow = word in sentence s2)")
    a = ap.parse_args(argv)
    try:
        times = [float(x) for x in a.at.split(",") if x.strip()]
        times += [round(word_time(a.episode, w.strip()) + WORD_DELAY, 3) for w in a.word.split(",") if w.strip()]
        if not times:
            ap.error("give --at <seconds,...> and/or --word <word,...>")
        print(to_json(measure(a.episode, times, a.ids)))
    except (LookupError, ValueError, OSError, RuntimeError) as e:
        print(f"look.py: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
