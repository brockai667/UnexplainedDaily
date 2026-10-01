# -*- coding: utf-8 -*-
"""Screenplay compiler:  python doodle/sp.py <episode folder>   ->  <folder>/index.html (+ assets/, work/)

The episode is ONE data file <folder>/screenplay.yaml (see API.md). This script:
voice (Kokoro, cached) -> word timings -> resolves every "at" expression -> validates -> expands gold,
transitions and sfx -> audio mix -> index.html that runs anim_src/runtime.js (no per-episode JavaScript)."""
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np
import soundfile as sf
import yaml
from PIL import ImageFont

for _stream in (sys.stdout, sys.stderr):      # Windows consoles default to cp1250: never die on a print
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "anim_src")
MUSIC_DIR = os.path.join(HERE, "assets", "music")
# voice_stage (Kokoro TTS + whisper word timing): $DOODLE_ENGINE if set, else the vendored copy in doodle/engine/
ENGINE = os.environ.get("DOODLE_ENGINE") or os.path.join(HERE, "engine")
sys.path.insert(0, ENGINE)
sys.path.insert(0, SRC)
import voice_stage as VS   # noqa: E402
import sfx as SFX          # noqa: E402

FPS, WIDTH, HEIGHT = 24, 720, 1280


class SPError(Exception):
    pass


GENERIC = {"move", "path", "rotate", "scale", "fade", "show", "hide", "pop", "stamp", "shake", "jiggle", "bob", "rock", "pulse", "spin", "attach", "detach"}
CARRY = {"shape", "text", "rock", "flask", "sign", "tent", "house"}
KIND_VERBS = {
    "char": {"enter", "walk_to", "walk", "exit", "turn", "pose", "point", "face", "color", "look", "hold", "drop", "startle", "jump_back",
             "step_back", "kneel_down", "bend_over", "sit_down", "sniff", "tremble", "nod", "heave", "sway", "get_sick", "dizzy", "sweat"},
    "rider": {"ride", "wobble", "tip_over", "wave", "face"},
    "building": {"shatter"}, "sign": {"hammer"}, "tape": {"unroll"}, "line": {"draw_line", "draw"},
    "meteor": {"fly"}, "impact": {"explode"}, "shockwave": {"go"}, "crater": {"water_level", "boil", "splash"},
    "thought": {"pop", "grow", "darken", "bolt"}, "bigface": {"bump"}, "emitter": {"emit", "start", "stop", "burst", "pulse"},
    "sky": set(), "mountains": set(), "hill": set(), "ground": set(), "house": set(), "tent": set(), "text": set(), "rock": set(),
    "shape": set(), "underground": set(), "flask": set(), "part": set(),
}
CAM_VERBS = {"push", "pull", "pan", "tilt", "frame", "move", "whip", "reset", "shake", "follow"}
FX_VERBS = {"flash", "lines"}
POSES = {"stand", "point", "look_up", "lean_in", "hands_up", "cover", "head", "cheeks", "belly", "kneel", "sit", "shrug", "scratch", "think",
         "shade", "reach", "megaphone", "stop", "cower", "clasp", "help", "recoil", "wave", "arms_crossed"}
FACES = {"ok", "happy", "wow", "shout", "sick", "dizzy", "scared", "think", "flat", "curious", "worried", "sad", "angry", "sleep"}
EMITTERS = {"steam", "smoke", "fumes", "dust", "bubbles", "sparks", "drops", "shards", "stars", "sweat", "spiral", "sound", "particles", "birds"}
KEEP_UNTIL = {"tremble", "nod", "heave", "sway", "bob", "rock", "pulse", "spin", "emit", "start", "get_sick", "dizzy", "sweat", "bend_over", "sit_down", "kneel_down"}
SFX_NAMES = set(SFX.MAKERS)
VERB_SFX = {"explode": ("boom", 0.95, 0.0), "shatter": ("glass", 0.5, 0.0), "tip_over": ("clatter", 0.4, 0.34), "stamp": ("thud", 0.4, 0.06)}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


class _Loader(yaml.SafeLoader):
    """YAML 1.2-style booleans: only true/false. (YAML 1.1 would turn the key 'on:' into True, 'no' into False...)"""


_BOOL = "tag:yaml.org,2002:bool"
_Loader.yaml_implicit_resolvers = {k: [r for r in v if r[0] != _BOOL] for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
_Loader.add_implicit_resolver(_BOOL, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def load_screenplay(ep_dir):
    for fn in ("screenplay.yaml", "screenplay.yml", "screenplay.json"):
        p = os.path.join(ep_dir, fn)
        if os.path.exists(p):
            return yaml.load(open(p, encoding="utf-8"), Loader=_Loader)
    raise SPError(f"no screenplay.yaml in {ep_dir}")


def resolve_music(music):
    """`music:` of the screenplay -> file path. Absolute path = as is; a bare file name = doodle/assets/music/<name>.
    A music file that is named but missing is an error (a silently music-less episode would still carry the music credit)."""
    if not music:
        return None
    music = str(music)
    path = music if os.path.isabs(music) else os.path.join(MUSIC_DIR, music)
    if not os.path.isfile(path):
        raise SPError(f"music file not found: {path} (a bare file name is looked up in {MUSIC_DIR})")
    return path


# ------------------------------------------------------------------------------------------ timing expressions
class Clock:
    """Resolves 'word:X', 'word:s3/X#2', 'word:X.end', 's3', 's3.end', 'scene', 'scene.end', 'prev', 'prev.end',
    'hit:WAVE@OBJ' and plain numbers, each optionally followed by +/- offsets (e.g. 'word:blast+0.2')."""

    def __init__(self, words, sent_keys):
        self.words, self.keys = words, sent_keys
        self.by_key = {k: [w for w in words if w["k"] == k] for k in sent_keys}
        self.scene_keys, self.t0, self.end, self.prev, self.prev_end = sent_keys, 0.0, 0.0, 0.0, 0.0
        self.waves, self.xs = {}, {}

    def find(self, spec, where):
        spec = spec[5:] if spec.startswith("word:") else spec
        if spec.endswith(".end"):
            spec = spec[:-4]
        nth = 0
        if "#" in spec:
            spec, n = spec.split("#")
            nth = int(n) - 1
        if "/" in spec:
            key, wd = spec.split("/", 1)
            pools = [self.by_key.get(key, [])]
        else:
            wd = spec
            pools = [[w for k in self.scene_keys for w in self.by_key[k]], self.words]
        for pool in pools:
            hits = [w for w in pool if norm(w["w"]) == norm(wd)]
            if len(hits) > nth:
                return hits[nth]
        raise SPError(f"{where}: word '{spec}' not found in the narration")

    def word(self, spec, where):
        w = self.find(spec, where)
        return w["e"] if spec.endswith(".end") else w["s"]

    def __call__(self, expr, where):
        if expr is None:
            raise SPError(f"{where}: missing time")
        if isinstance(expr, (int, float)):
            return float(expr)
        s = str(expr).strip()
        m = re.match(r"^(.*?)((?:\s*[+\-]\s*\d+(?:\.\d+)?)*)\s*$", s)
        base, offs = m.group(1).strip(), m.group(2)
        off = sum(float(x.replace(" ", "")) for x in re.findall(r"[+\-]\s*\d+(?:\.\d+)?", offs or ""))
        if base == "":
            return self.prev_end + off
        if re.fullmatch(r"\d+(\.\d+)?", base):
            return float(base) + off
        if base == "prev":
            return self.prev + off
        if base == "prev.end":
            return self.prev_end + off
        if base == "scene":
            return self.t0 + off
        if base == "scene.end":
            return self.end + off
        if base.startswith("word:"):
            return self.word(base[5:], where) + off
        if base.startswith("hit:"):
            wv, _, ob = base[4:].partition("@")
            if wv not in self.waves:
                raise SPError(f"{where}: shockwave '{wv}' has no earlier 'go' beat")
            gt, wx, spd = self.waves[wv]
            if ob.startswith("x="):
                ox = float(ob[2:])
            elif ob in self.xs:
                ox = self.xs[ob]
            else:
                raise SPError(f"{where}: unknown object '{ob}' in {base}")
            return gt + abs(wx - ox) / spd + off
        k = base[:-4] if base.endswith(".end") else base
        if k in self.by_key:
            ws = self.by_key[k]
            return (ws[-1]["e"] if base.endswith(".end") else ws[0]["s"]) + off
        raise SPError(f"{where}: cannot read time '{expr}' (use word:X, s3, s3.end, scene, scene.end, prev, prev.end, hit:W@O or seconds)")


# ------------------------------------------------------------------------------------------ audio
def mix_audio(voice, v0, total, music, fx, sr, work):
    n = int(total * sr)
    out = np.zeros(n, dtype=np.float32)
    i0 = int(v0 * sr)
    out[i0:i0 + len(voice)] += voice[:n - i0]
    env = np.zeros(n, dtype=np.float32)
    env[i0:i0 + len(voice)] = np.abs(voice[:n - i0])
    k = int(0.2 * sr)
    env = np.convolve(env, np.ones(k, dtype=np.float32) / k, mode="same")
    env /= (np.percentile(env, 96) + 1e-9)
    vr = float(np.sqrt((voice ** 2).mean()))
    if music and os.path.exists(music):
        tmp = os.path.join(work, "music.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", music, "-t", str(total + 1), "-ar", str(sr), "-ac", "1", tmp], check=True)
        mus, _ = sf.read(tmp, dtype="float32")
        mus = np.resize(mus, n).astype(np.float32)
        mus *= (vr * 0.28) / (float(np.sqrt((mus ** 2).mean())) + 1e-9)
        mus *= 1.0 - 0.7 * np.clip(env, 0, 1)
        f = int(0.6 * sr)
        mus[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
        out += mus
    if fx is not None and len(fx):
        fx = fx[:n] if len(fx) >= n else np.pad(fx, (0, n - len(fx)))
        out += fx * (1.0 - 0.45 * np.clip(env, 0, 1)) * (vr * 2.2)
    out *= min(1.0, 0.95 / (float(np.abs(out).max()) + 1e-9))
    return out


# ------------------------------------------------------------------------------------------ compile
def compile_episode(ep_dir):
    ep_dir = os.path.abspath(ep_dir)
    E = load_screenplay(ep_dir)
    music = resolve_music(E.get("music"))          # fail now, not after minutes of TTS
    work = os.path.join(ep_dir, "work")
    for d in ("assets/fonts", "assets/img", "assets/audio"):
        os.makedirs(os.path.join(ep_dir, d), exist_ok=True)
    os.makedirs(work, exist_ok=True)
    shutil.copy(os.path.join(SRC, "assets", "fonts", "ComicNeue-Bold.ttf"), os.path.join(ep_dir, "assets", "fonts"))
    shutil.copy(os.path.join(SRC, "assets", "img", "paper.jpg"), os.path.join(ep_dir, "assets", "img"))
    json.dump({"paths": {"assets": "assets"}, "media": {"autoProxy": False}}, open(os.path.join(ep_dir, "hyperframes.json"), "w"))

    sents = E.get("sentences")
    if isinstance(sents, dict):
        sents = list(sents.items())
    if not sents:
        raise SPError("screenplay needs 'sentences'")
    keys, texts = [k for k, _ in sents], [t for _, t in sents]
    V = dict(voice="am_michael", speed=1.10, pause=0.30)
    V.update(E.get("voice") or {})
    V0, TAIL = float(E.get("v0", 0.35)), float(E.get("tail", 1.0))
    words, dur = VS.run(" ".join(texts), work, [], speed=V["speed"], voice=V["voice"], sentences=texts, pause=V["pause"])
    total = round(round((V0 + dur + TAIL) * FPS) / FPS, 6)
    idx, allw = 0, []
    for key, s in sents:
        for w in words[idx:idx + len(s.split())]:
            allw.append({"w": w["w"], "s": round(w["s"] + V0, 4), "e": round(w["e"] + V0, 4), "k": key})
        idx += len(s.split())
    clock = Clock(allw, keys)
    sent_start = {k: (0.0 if i == 0 else round(clock.by_key[k][0]["s"] - 0.22, 4)) for i, k in enumerate(keys)}

    scenes = E.get("scenes") or []
    if not scenes:
        raise SPError("screenplay needs 'scenes'")
    ids = [sc["id"] for sc in scenes]
    for i, sc in enumerate(scenes):
        for k in sc.get("sents", []):
            if k not in keys:
                raise SPError(f"scene '{sc['id']}': unknown sentence '{k}'")
    # clip windows
    wins = []
    for i, sc in enumerate(scenes):
        st = sent_start[sc["sents"][0]]
        en = sent_start[scenes[i + 1]["sents"][0]] if i + 1 < len(scenes) else total
        wins.append([st, en, en])
    trans, fx_flash, fx_lines, cues = [], [], [], []
    extra_cam = {sc["id"]: [] for sc in scenes}
    cam0 = {}
    for i, sc in enumerate(scenes):
        cf = sc.get("camera") or {}
        first = [float(cf.get("zoom", 1.0)), *(cf.get("at") or [360, 640]), *(cf.get("screen") or [360, 640])]
        cam0[sc["id"]] = first
        tr = sc.get("in") or {"type": "cut"}
        typ = tr.get("type", "cut") if isinstance(tr, dict) else tr
        if i == 0 or typ == "cut":
            continue
        b = wins[i][0]
        prev = scenes[i - 1]["id"]
        if typ in ("slide", "drop"):
            wins[i][0] = round(b - 0.10, 4)
            wins[i - 1][1] = round(b + 0.22, 4)
            trans.append({"type": typ, "from": prev, "to": sc["id"], "a": wins[i][0], "b": wins[i - 1][1]})
            cues.append((wins[i][0], "whoosh", 0.18, {"dur": 0.35, "seed": 21 + i}))
        elif typ in ("whip", "zoom"):
            tg = tr.get("target") or [360, 640]
            fr = tr.get("from") or first[1:3]
            if typ == "whip":
                extra_cam[prev].append({"t": b - 0.34, "who": "cam", "do": "whip", "zoom": float(tr.get("zoom_out", 3.6)), "target": tg, "screen": [360, 590], "dur": 0.34})
                fx_flash.append([b, 0.9, 0.16, 0.3])
                fx_lines.append([b - 0.26, b + 0.22, 360, 590])
                cues.append((b - 0.3, "whoosh", 0.3, {"dur": 0.4, "seed": 3}))
                cam0[sc["id"]] = [float(tr.get("zoom_in", 5.0)), fr[0], fr[1], 360, 610]
            else:
                extra_cam[prev].append({"t": b - 0.32, "who": "cam", "do": "whip", "zoom": float(tr.get("zoom_out", 5.0)), "target": tg, "screen": [360, 600], "dur": 0.32})
                fx_lines.append([b - 0.28, b + 0.26, 360, 600])
                cues.append((b - 0.3, "whoosh", 0.2, {"dur": 0.35, "seed": 7}))
                cam0[sc["id"]] = [float(tr.get("zoom_in", 1.6)), fr[0], fr[1], 360, 600]
            extra_cam[sc["id"]].append({"t": b, "who": "cam", "do": "frame", "zoom": first[0], "target": first[1:3], "screen": first[3:5], "dur": 0.62, "ease": "power3.out"})
        elif typ == "flash":
            fx_flash.append([b, 0.8, 0.08, 0.3])
        else:
            raise SPError(f"scene '{sc['id']}': unknown transition '{typ}' (cut, whip, zoom, slide, drop, flash)")
    loop = None
    if E.get("loop"):
        lp = E["loop"]
        clock.scene_keys, clock.t0, clock.end = keys, 0.0, total
        lt0 = clock(lp.get("at", f"{keys[-1]}.end+0.55"), "loop")
        loop = {"t0": round(lt0, 4), "t1": round(lt0 + float(lp.get("dur", 1.3)), 4)}
        wins[0][1] = total
        cues.append((lt0, "whoosh", 0.25, {"dur": 1.2, "seed": 23}))

    # gold
    gold, gold_objs = [], {sc["id"]: [] for sc in scenes}
    scene_of = {k: sc["id"] for sc in scenes for k in sc["sents"]}
    for gi, g in enumerate(E.get("gold") or []):
        where = f"gold #{gi + 1} ({g.get('label')})"
        clock.scene_keys, clock.t0, clock.end = keys, 0.0, total
        wrec = clock.find(str(g["word"]), where)
        t = wrec["s"] - 0.03
        sid = scene_of[wrec["k"]]
        si = ids.index(sid)
        until = clock(g["until"], where) if g.get("until") is not None else (wins[si][2] - 0.45)
        kind = g.get("kind", "stamp")
        key = norm(g["label"])
        if kind == "measure":
            pts = g["points"]
            mx, my = (pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2
            la = g.get("label_at") or [mx, my - 30]
            gold_objs[sid] += [
                {"id": f"gold_{key}_arrow", "kind": "line", "points": pts, "style": "gold", "arrows": "both", "width": g.get("width", 7), "section": "props"},
                {"id": f"gold_{key}_label", "kind": "text", "text": g["label"], "style": "gold", "size": g.get("size", 40), "x": la[0], "y": la[1], "hidden": True, "section": "props"}]
            gold_objs[sid + "_beats"] = gold_objs.get(sid + "_beats", []) + [
                {"t": t, "who": f"gold_{key}_arrow", "do": "draw_line", "dur": 0.4},
                {"t": t, "who": f"gold_{key}_label", "do": "stamp", "dur": 0.4},
                {"t": until - 0.25, "who": f"gold_{key}_arrow", "do": "fade", "to": 0, "dur": 0.25},
                {"t": until - 0.25, "who": f"gold_{key}_label", "do": "fade", "to": 0, "dur": 0.25}]
            cues.append((t + 0.06, "thud", 0.5))
            continue
        item = {"key": key, "label": g["label"], "kind": kind, "t": round(t, 4), "until": round(until, 4), "scene": sid,
                "top": g.get("top", 120), "size": g.get("size", 110), "stamp": g.get("stamp") or {}, "total": total}
        if kind == "counter":
            item.update({"from": g.get("from", 0), "to": g.get("to", int(re.sub(r"[^0-9]", "", g["label"]) or 0)), "dur": g.get("dur", 0.6)})
            cues += [(t + 0.05 + i * 0.055, "tick", 0.12) for i in range(10)]
            cues.append((t + item["dur"] + 0.02, "thud", 0.45))
        elif kind == "stamp":
            cues.append((t + 0.06, "thud", 0.55))
        else:
            raise SPError(f"{where}: kind must be stamp, counter or measure")
        gold.append(item)

    # scenes: objects + beats
    styles, shapes = E.get("styles") or {}, E.get("shapes") or {}
    out_scenes = []
    for i, sc in enumerate(scenes):
        sid = sc["id"]
        clock.scene_keys, clock.t0, clock.end = sc["sents"], wins[i][0], wins[i][2]
        clock.prev = clock.prev_end = wins[i][0]
        objs = []
        for sec in ("set", "props", "cast"):
            for od in sc.get(sec) or []:
                od = dict(od)
                if sec == "cast" and "kind" not in od:
                    od["kind"] = "char"
                if "kind" not in od:
                    raise SPError(f"scene '{sid}' {sec}: object without kind: {od}")
                if od["kind"] not in KIND_VERBS:
                    raise SPError(f"scene '{sid}': unknown kind '{od['kind']}'. Kinds: {', '.join(sorted(KIND_VERBS))}")
                if od["kind"] == "shape" and od.get("shape") not in shapes and od.get("shape") not in ("check", "cross", "question", "exclaim", "arrow_down"):
                    raise SPError(f"scene '{sid}': unknown shape '{od.get('shape')}'")
                if od["kind"] == "emitter" and od.get("emitter") not in EMITTERS:
                    raise SPError(f"scene '{sid}': unknown emitter '{od.get('emitter')}'. Emitters: {', '.join(sorted(EMITTERS))}")
                if od["kind"] == "emitter" and od.get("shape") and od["shape"] not in shapes and od["shape"] not in ("check", "cross", "question", "exclaim", "arrow_down"):
                    raise SPError(f"scene '{sid}': emitter '{od.get('id')}' uses unknown shape '{od['shape']}'")
                od["section"] = sec
                objs.append(od)
        objs += gold_objs[sid]
        kinds = {o["id"]: o["kind"] for o in objs if o.get("id")}

        def groups(items, seen=0):                                  # animatable parts of a custom shape: its named groups
            out = []
            for it in items or []:
                if it.get("group"):
                    out += [it["group"]] + groups(it.get("items"), seen + 1)
                elif it.get("use") and seen < 5:
                    out += groups(shapes.get(it["use"]), seen + 1)
            return out
        for o in objs:
            if o["kind"] == "shape" and o.get("id"):
                for gname in groups(shapes.get(o.get("shape"))):
                    kinds[f"{o['id']}.{gname}"] = "part"
        for o in objs:
            if o.get("on") is not None and o["on"] not in kinds:
                raise SPError(f"scene '{sid}': object '{o.get('id')}' is attached to unknown object '{o['on']}' (on:)")
        for o in objs:
            if o.get("id"):
                clock.xs[o["id"]] = float(o.get("x", (o.get("at") or [0])[0] if isinstance(o.get("at"), list) else 0) or 0)
        beats = []
        raw = [dict(b) for b in (sc.get("beats") or [])]
        bi = 0
        while bi < len(raw):
            b = raw[bi]
            bi += 1
            where = f"scene '{sid}' beat #{bi} ({b.get('who')} {b.get('do')})"
            rep = b.pop("repeat", None)
            if rep is not None:            # repeat {every, n | until, cycle | alt}: the same beat again and again
                if not isinstance(rep, dict) or float(rep.get("every", 0) or 0) <= 0:
                    raise SPError(f"{where}: repeat needs every: <seconds > 0> and n: <count> or until: <time>")
                every = float(rep["every"])
                tr = clock(b.get("at"), where)
                if rep.get("until") is not None:
                    n = int((clock(rep["until"], where) - tr) / every) + 1
                else:
                    n = int(rep.get("n", 0) or 0)
                if not 1 <= n <= 400:
                    raise SPError(f"{where}: repeat would make {n} beats (allowed 1..400) - check every, n or until")
                cycle = rep.get("cycle") or ([{}, rep["alt"]] if rep.get("alt") else [{}])
                if not isinstance(cycle, list) or not all(isinstance(c, dict) or c is None for c in cycle):
                    raise SPError(f"{where}: repeat cycle must be a list of key overrides, e.g. [{{name: arms_up}}, {{name: arms_down}}]")
                copies = []
                for k in range(n):
                    nb = dict(b)
                    nb.update(cycle[k % len(cycle)] or {})
                    nb["at"] = round(tr + k * every, 4)
                    copies.append(nb)
                raw[bi - 1:bi] = copies
                bi -= 1
                continue
            t = clock(b.pop("at", None), where)
            if "until" in b and b.get("do") not in KEEP_UNTIL:
                b["dur"] = clock(b.pop("until"), where) - t
            elif "until" in b:
                b["until"] = clock(b["until"], where)
            who, verb = b.get("who"), b.get("do")
            if who == "cam":
                if verb not in CAM_VERBS:
                    raise SPError(f"{where}: camera verbs are {', '.join(sorted(CAM_VERBS))}")
            elif who == "fx":
                if verb not in FX_VERBS:
                    raise SPError(f"{where}: fx verbs are flash, lines")
            else:
                if who not in kinds:
                    raise SPError(f"{where}: unknown object '{who}'. Objects in this scene: {', '.join(sorted(kinds))}")
                allowed = KIND_VERBS[kinds[who]] | GENERIC
                if verb not in allowed:
                    raise SPError(f"{where}: '{kinds[who]}' cannot '{verb}'. Allowed: {', '.join(sorted(allowed))}")
                if verb == "pose" and b.get("name") not in POSES:
                    raise SPError(f"{where}: unknown pose '{b.get('name')}'. Poses: {', '.join(sorted(POSES))}")
                if verb == "face" and b.get("name") not in FACES:
                    raise SPError(f"{where}: unknown face '{b.get('name')}'. Faces: {', '.join(sorted(FACES))}")
                if verb in ("attach", "detach") and kinds[who] not in CARRY:
                    raise SPError(f"{where}: only these kinds can be carried: {', '.join(sorted(CARRY))}")
                if verb == "attach" and b.get("to") not in kinds:
                    raise SPError(f"{where}: attach needs 'to: <object id>' of this scene")
            b["t"] = round(t, 4)
            d = b.get("dur")
            clock.prev, clock.prev_end = t, t + (float(d) if d else 0.0)
            if who == "fx":
                if verb == "flash":
                    fx_flash.append([t, b.get("peak", 0.7), b.get("up", 0.02), b.get("down", 0.34)])
                else:
                    tg = b.get("target") or [360, 600]
                    fx_lines.append([t, t + (d or 0.5), tg[0], tg[1]])
            else:
                beats.append(b)
            if verb == "go" and kinds.get(who) == "shockwave":
                o = next(o for o in objs if o.get("id") == who)
                clock.waves[who] = (t, float(o["at"][0]), float(o.get("speed", 390)))
            s = b.get("sfx")
            if s and s != "none":
                nm, gain = (s, 0.45) if isinstance(s, str) else (s[0], s[1])
                if nm not in SFX_NAMES:
                    raise SPError(f"{where}: unknown sfx '{nm}'. Sfx: {', '.join(sorted(SFX_NAMES))}")
                kw = {"dur": round(d, 2)} if nm in ("whoosh", "bubbles", "hiss") and d else {}
                cues.append((t, nm, gain, kw))
            elif s != "none" and verb in VERB_SFX:
                nm, gain, dt = VERB_SFX[verb]
                cues.append((t + (d if verb == "tip_over" and d else dt), nm, gain))
            elif s != "none" and verb == "hammer":
                cues += [(t + 0.12 + j * b.get("every", 0.2), "thud", 0.35) for j in range(b.get("hits", 3))]
            elif s != "none" and verb == "fly":
                cues.append((t, "whoosh", 0.55, {"dur": round(d or 1.0, 2)}))
            elif s != "none" and verb == "boil":
                cues.append((t, "bubbles", 0.45, {"dur": 2.4}))
        beats += extra_cam[sid] + gold_objs.get(sid + "_beats", [])
        beats.sort(key=lambda x: x["t"])
        out_scenes.append({"id": sid, "t0": wins[i][0], "t1": wins[i][1], "end": wins[i][2], "cam0": cam0[sid], "objects": objs, "beats": beats,
                           "home": bool(loop) and i == 0, "last": bool(loop) and i == len(scenes) - 1})

    for c in E.get("sfx") or []:
        clock.scene_keys, clock.t0, clock.end = keys, 0.0, total
        nm = c["name"]
        if nm not in SFX_NAMES:
            raise SPError(f"sfx: unknown name '{nm}'")
        kw = {k: c[k] for k in ("dur", "seed") if k in c}
        cues.append((clock(c["at"], "sfx"), nm, c.get("gain", 0.45), kw))

    # audio
    voice, sr = sf.read(os.path.join(work, "voice.wav"), dtype="float32")
    SFX.SR = sr
    fx = SFX.render(cues, total, sr) if cues else None
    sf.write(os.path.join(ep_dir, "assets", "audio", "mix.wav"), mix_audio(voice, V0, total, music, fx, sr, work), sr)

    # html
    clips = []
    for i, S in enumerate(out_scenes):
        sid, sc = S["id"], scenes[i]
        gh = ""
        for g in gold:
            if g["scene"] == sid:
                inner = "".join(f'<div class="gline">{html.escape(x)}</div>' for x in g["label"].split("|"))
                gh += (f'<div class="goldwrap" id="gw_{g["key"]}"><div class="gold" id="gold_{g["key"]}" data-layout-allow-overlap="stacked title" '
                       f'style="top:{g["top"]}px;font-size:{g["size"]}px;line-height:{int(g["size"] * 1.16)}px">{inner}</div></div>')
        typ = (sc.get("in") or {}).get("type", "cut") if isinstance(sc.get("in"), dict) else sc.get("in", "cut")
        shadow = "0 24px 40px rgba(60,40,10,0.30)" if (typ == "drop" or S["last"]) else "-24px 0 40px rgba(60,40,10,0.30)"
        clips.append(f'''<div class="clip scene" id="sc_{sid}" data-start="{S["t0"]:.3f}" data-duration="{S["t1"] - S["t0"]:.3f}" data-track-index="{1 + i}">
<div class="page" id="pg_{sid}" style="box-shadow:{shadow}">
<svg class="world{' nss' if sc.get('fixed_strokes') else ''}" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" xmlns="http://www.w3.org/2000/svg">
<defs><filter id="boil_{sid}" filterUnits="userSpaceOnUse" x="0" y="0" width="{WIDTH}" height="{HEIGHT}">
<feTurbulence id="turb_{sid}" type="fractalNoise" baseFrequency="0.024" numOctaves="1" seed="1" result="n"/>
<feDisplacementMap in="SourceGraphic" in2="n" scale="3.4" xChannelSelector="R" yChannelSelector="G"/></filter></defs>
<g filter="url(#boil_{sid})" data-layout-allow-overflow="camera"><g id="cam_{sid}"></g></g>
</svg>
{gh}
</div>
</div>''')

    caps, js_caps, chunk, c = [], [], [], 0
    cap_font = ImageFont.truetype(os.path.join(SRC, "assets", "fonts", "ComicNeue-Bold.ttf"), 66)
    for n_i, w in enumerate(allw):
        chunk.append(w)
        last_in_sent = n_i + 1 == len(allw) or allw[n_i + 1]["k"] != w["k"]
        too_wide = not last_in_sent and cap_font.getlength(" ".join(x["w"] for x in chunk + [allw[n_i + 1]])) > 680
        if len(chunk) == 3 or last_in_sent or too_wide or re.search(r"[.,!?:]$", w["w"]):
            cs = chunk[0]["s"] - 0.04
            nxt = allw[n_i + 1]["s"] - 0.04 if n_i + 1 < len(allw) else chunk[-1]["e"] + 0.5
            ce = min(nxt, chunk[-1]["e"] + 0.6)
            if last_in_sent:
                ki = keys.index(w["k"])
                if ki + 1 < len(keys):
                    ce = min(ce, sent_start[keys[ki + 1]])
            ce = min(ce, total - 0.5, loop["t0"] if loop else total)
            sp = " ".join(f'<span class="cw" id="k{c}w{j}">{html.escape(x["w"])}</span>' for j, x in enumerate(chunk))
            caps.append(f'<div class="clip over" id="k{c}" data-start="{cs:.3f}" data-duration="{max(0.2, ce - cs):.3f}" '
                        f'data-track-index="{len(scenes) + 3}"><div class="cap" id="kc{c}">{sp}</div></div>')
            js_caps.append(f'tl.fromTo("#kc{c}", {{scale:0.86, y:12}}, {{scale:1, y:0, duration:0.16, ease:"back.out(2.4)"}}, {cs:.3f});')
            for j, x in enumerate(chunk):
                js_caps.append(f'tl.set("#k{c}w{j}", {{color:"#FFCD28"}}, {x["s"]:.3f});')
                js_caps.append(f'tl.set("#k{c}w{j}", {{color:"#1b1b1b"}}, {x["e"] + 0.02:.3f});')
            chunk, c = [], c + 1

    speed = "".join(
        f'<path d="M{math.cos(a) * r0:.0f},{math.sin(a) * r0:.0f} L{math.cos(a) * (r0 + ln):.0f},{math.sin(a) * (r0 + ln):.0f}" fill="none" stroke="#1b1b1b" stroke-width="{w}" stroke-linecap="round"/>'
        for a, r0, ln, w in [(2 * math.pi * i / 22 + (i % 3) * 0.05, 330 + (i * 37) % 90, 200 + (i * 53) % 160, 5 + i % 3 * 2) for i in range(22)])
    SP = {"total": total, "scenes": out_scenes, "gold": gold, "loop": loop, "styles": styles, "shapes": shapes,
          "fx": {"flashes": fx_flash, "speeds": fx_lines}, "trans": trans}
    lib = open(os.path.join(SRC, "doodle_lib.js"), encoding="utf-8").read()
    rt = open(os.path.join(SRC, "runtime.js"), encoding="utf-8").read()
    n_sc = len(scenes)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width={WIDTH}, height={HEIGHT}" />
<title>{html.escape(E.get("title", "episode"))}</title>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
  @font-face {{ font-family: "Comic Neue"; src: url("assets/fonts/ComicNeue-Bold.ttf") format("truetype"); font-weight: 700; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{WIDTH}px; height:{HEIGHT}px; overflow:hidden; background:#f6f1e4; }}
  #root {{ position:relative; width:100%; height:100%; overflow:hidden; background:#f6f1e4 url("assets/img/paper.jpg") center/cover; font-family:"Comic Neue", cursive; font-weight:700; }}
  .clip {{ position:absolute; inset:0; overflow:hidden; }}
  .scene {{ z-index:1; }}
  .page {{ position:absolute; inset:0; background:#f6f1e4 url("assets/img/paper.jpg") center/cover; }}
  .world {{ position:absolute; left:0; top:0; width:{WIDTH}px; height:{HEIGHT}px; overflow:hidden;
            -webkit-mask-image:linear-gradient(to bottom, #000 0, #000 926px, transparent 966px); mask-image:linear-gradient(to bottom, #000 0, #000 926px, transparent 966px); }}
  .nss path, .nss circle, .nss ellipse, .nss rect {{ vector-effect:non-scaling-stroke; }}
  .goldwrap {{ position:absolute; inset:0; }}
  .gold {{ position:absolute; left:0; width:{WIDTH}px; text-align:center; color:#FFCD28; paint-order:stroke fill; -webkit-text-stroke:14px #1b1b1b; letter-spacing:0.01em; opacity:0; }}
  .gline {{ display:block; white-space:nowrap; }}
  .fx {{ z-index:{n_sc + 2}; pointer-events:none; }}
  #fx_speed {{ position:absolute; left:0; top:0; width:{WIDTH}px; height:{HEIGHT}px; }}
  #fx_flash {{ position:absolute; inset:0; background:#fffdf4; opacity:0; }}
  .over {{ z-index:{n_sc + 5}; background:none; pointer-events:none; }}
  .cap {{ position:absolute; left:0; width:{WIDTH}px; top:985px; text-align:center; font-size:66px; line-height:80px; color:#1b1b1b; paint-order:stroke fill; -webkit-text-stroke:12px #fffdf6; white-space:nowrap; }}
  .cw {{ display:inline-block; color:#1b1b1b; }}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total:.6f}" data-fps="{FPS}" data-width="{WIDTH}" data-height="{HEIGHT}">
{chr(10).join(clips)}
<div class="clip fx" id="fx" data-start="0" data-duration="{total:.6f}" data-track-index="{n_sc + 1}">
<svg id="fx_speed" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}" xmlns="http://www.w3.org/2000/svg"><g id="fx_speed_g" opacity="0">{speed}</g></svg>
<div id="fx_flash"></div>
</div>
{chr(10).join(caps)}
<audio id="mix" src="assets/audio/mix.wav" data-start="0" data-duration="{total:.6f}" data-track-index="{n_sc + 6}" data-volume="1"></audio>
</div>
<script>
{lib}
</script>
<script>
{rt}
</script>
<script>
var SP = {json.dumps(SP)};
var tl = gsap.timeline({{ paused: true }});
SP.fx.flashes.forEach(function (f) {{ D.FX.flashes.push(f); }});
SP.fx.speeds.forEach(function (f) {{ D.FX.speeds.push(f); }});
SP.gold.forEach(function (g) {{
  if (g.kind === "stamp") {{
    D.stamp(tl, "#gold_" + g.key, g.t, g.stamp || {{}});
    tl.fromTo("#gold_" + g.key, {{ opacity: 1 }}, {{ opacity: 0, duration: 0.2, ease: "power1.in", immediateRender: false }}, g.until - 0.2);
  }} else if (g.kind === "counter") RT.counter(tl, g);
}});
SP.scenes.forEach(function (S) {{ RT.scene(tl, S, {{ styles: SP.styles, shapes: SP.shapes, loop: SP.loop }}); }});
SP.trans.forEach(function (tr) {{
  var d = tr.b - tr.a;
  if (tr.type === "slide") {{
    tl.fromTo("#pg_" + tr.to, {{ x: {WIDTH} }}, {{ x: 0, duration: d, ease: "power3.inOut", immediateRender: true }}, tr.a);
    tl.fromTo("#pg_" + tr.from, {{ x: 0 }}, {{ x: -260, duration: d, ease: "power3.inOut", immediateRender: false }}, tr.a);
  }} else if (tr.type === "drop") {{
    tl.fromTo("#pg_" + tr.to, {{ y: -{HEIGHT} }}, {{ y: 0, duration: d, ease: "power3.inOut", immediateRender: true }}, tr.a);
    tl.fromTo("#pg_" + tr.from, {{ y: 0 }}, {{ y: 360, duration: d, ease: "power3.inOut", immediateRender: false }}, tr.a);
  }}
}});
D.fxDriver(tl, SP.total);
{chr(10).join(js_caps)}
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
</script></body></html>
"""
    open(os.path.join(ep_dir, "index.html"), "w", encoding="utf-8").write(page)
    json.dump({"total": total, "V0": V0, "words": allw, "sent_start": sent_start, "loop": loop,
               "scenes": [{k: s[k] for k in ("id", "t0", "t1", "end")} for s in out_scenes], "sfx": [list(x[:3]) for x in cues]},
              open(os.path.join(work, "timing.json"), "w"), indent=1)
    nb = sum(len(s["beats"]) for s in out_scenes)
    print(f"{os.path.basename(ep_dir)}: {total:.2f} s | scenes " + ", ".join(f'{s["id"]} {s["t0"]:.2f}-{s["t1"]:.2f}' for s in out_scenes) +
          f" | beats {nb} | captions {c} | gold {len(gold)} | sfx {len(cues)}")
    return total


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python doodle/sp.py <episode folder with screenplay.yaml>   (or just: python doodle/factory.py --dry-run)")
        sys.exit(2)
    try:
        compile_episode(sys.argv[1])
    except SPError as e:
        print("SCREENPLAY ERROR:", e)
        sys.exit(2)
