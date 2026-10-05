# -*- coding: utf-8 -*-
"""Autor epizody bez Clauda: bezplatny model pise v dvoch krokoch a kazdu scenu hned overuje kompilator.
 1. REZIA  - z viet a kratkeho zadania napise podrobny rezijny scenar (JSON): pre kazdu scenu pozadie, objekty s polohou
             a velkostou, kresby (z kniznice lib/shapes.yaml alebo nove s popisom tvaru), akcie naviazane na slova, kamera.
 2. KOD    - rezijny scenar prepise do screenplay YAML (po 3 scenach); scena sa skompiluje (sp.py), drobne chyby sa orezu,
             vazne chyby a nalezy mechanickej kontroly idu spat do modelu (OPRAVA).
 3. QA     - qa.py (render + kontroly) na konci.
  python doodle/auto_writer.py doodle/briefs/devon.yaml --provider openrouter --model nvidia/nemotron-3-ultra-550b-a55b:free
  python doodle/auto_writer.py doodle/briefs/devon.yaml --provider mock --model doodle/examples/devon1855/screenplay.yaml   (test bez siete)
Kluce len z prostredia alebo ~/.config/watch/.env; nikdy sa nevypisuju."""
import argparse
import copy
import json
import os
import re
import subprocess
import sys
import time

import yaml

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
PROVIDERS = {
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "MISTRAL_API_KEY"),
    "cerebras": ("https://api.cerebras.ai/v1/chat/completions", "CEREBRAS_API_KEY"),
    "nvidia": ("https://integrate.api.nvidia.com/v1/chat/completions", "NVIDIA_API_KEY"),
}
FACES = "ok happy wow shout sick dizzy scared think flat curious worried sad angry sleep".split()
STATS = {"calls": 0, "in": 0, "out": 0, "sec": 0.0, "log": []}
MAX_CALLS = 14                                  # strop volani na epizodu (OpenRouter free = 50 denne)


def key_for(env_name):
    v = os.environ.get(env_name, "")
    if not v:
        p = os.path.expanduser("~/.config/watch/.env")
        if os.path.exists(p):
            m = re.search(rf"^{env_name}=(.*)$", open(p, encoding="utf-8").read(), re.M)
            v = m.group(1).strip().strip('"') if m else ""
    if not v:
        raise SystemExit(f"chyba kluc {env_name} (prostredie alebo ~/.config/watch/.env)")
    return v


# ----------------------------------------------------------------------------------------------- model
def mock_answer(path, meta):
    """Test bez siete: 'model' odpoveda scenami z hotoveho scenara."""
    d = yaml.safe_load(open(path, encoding="utf-8"))
    if meta["stage"] == "script":
        return json.dumps([{"id": s["id"], "sents": s["sents"], "idea": "mock"} for s in d["scenes"] if s["id"] in meta["ids"]])
    scenes = [s for s in d["scenes"] if s["id"] in meta["ids"]]
    doc = {"styles": d.get("styles") or {}, "shapes": d.get("shapes") or {}, "scenes": scenes}
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=170, default_flow_style=None)


def chat(provider, model, messages, meta, max_tokens=24000, temperature=0.5):
    if STATS["calls"] >= MAX_CALLS:
        print("    strop volani dosiahnuty", flush=True)
        return ""
    if provider == "mock":
        STATS["calls"] += 1
        return mock_answer(model, meta)
    import requests
    url, env_name = PROVIDERS[provider]
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if provider == "groq":
        body["max_tokens"] = max(1200, min(3200, 7800 - sum(len(m["content"]) for m in messages) // 3))
        if "gpt-oss" in model:
            body["reasoning_effort"] = "low"
    t0 = time.time()
    for att in range(5):
        try:
            r = requests.post(url, headers={"Authorization": "Bearer " + key_for(env_name), "Content-Type": "application/json",
                                            "X-Title": "doodle-writer"}, json=body, timeout=900)
        except requests.RequestException as e:
            print(f"    siet: {str(e)[:120]} -> cakam 20s", flush=True)
            time.sleep(20)
            continue
        if r.status_code in (429, 502, 503, 524, 529):
            msg = r.text[:300]
            if "per-day" in msg or "daily" in msg.lower():
                print("    DENNY LIMIT bezplatnych volani vycerpany: " + msg[:160], flush=True)
                STATS["calls"] = MAX_CALLS
                return ""
            wait = 15.0 * (att + 1)
            print(f"    [{r.status_code}] {msg[:120]!r} -> cakam {wait:.0f}s", flush=True)
            time.sleep(wait)
            continue
        if not r.ok:
            print(f"    HTTP {r.status_code}: {r.text[:300]}", flush=True)
            return ""
        j = r.json()
        if j.get("error"):
            print(f"    chyba modelu: {str(j['error'])[:200]} -> cakam 15s", flush=True)
            time.sleep(15)
            continue
        u = j.get("usage") or {}
        msg = (j.get("choices") or [{}])[0].get("message") or {}
        txt = msg.get("content") or ""
        if isinstance(txt, list):
            txt = "".join(p.get("text", "") for p in txt if isinstance(p, dict))
        STATS["calls"] += 1
        STATS["in"] += u.get("prompt_tokens", 0)
        STATS["out"] += u.get("completion_tokens", 0)
        dt = time.time() - t0
        STATS["sec"] += dt
        STATS["log"].append({"stage": meta["stage"], "ids": meta.get("ids"), "in": u.get("prompt_tokens"), "out": u.get("completion_tokens"), "s": round(dt)})
        print(f"    [{meta['stage']}] {u.get('prompt_tokens')} -> {u.get('completion_tokens')} tokenov, {dt:.0f}s", flush=True)
        if provider == "groq":
            time.sleep(45)
        else:
            time.sleep(4)
        if txt.strip():
            return txt.strip()
        print("    prazdna odpoved (model minul tokeny na uvazovanie?)", flush=True)
    return ""


# ----------------------------------------------------------------------------------------------- podklady
def load_lib(exclude):
    p = os.path.join(HERE, "lib", "shapes.yaml")
    if not os.path.exists(p):
        return {}
    lib = (yaml.safe_load(open(p, encoding="utf-8")) or {}).get("shapes") or {}
    return {n: s for n, s in lib.items() if s.get("from") not in exclude}


def catalog(lib):
    rows = [f"- {n}  box {s.get('box')}  {s.get('note', '')}" for n, s in lib.items()]
    return ("LIBRARY of ready-made drawings (use as `{kind: shape, shape: NAME, x: .., y: .., scale: ..}`; `box` = [left, top, right, bottom] "
            "of the drawing around its own x,y at scale 1, so box [-170,-334,170,0] stands ON y and is 334 px tall):\n" + "\n".join(rows))


def api_doc():
    return open(os.path.join(HERE, "API.md"), encoding="utf-8").read()


def example_yaml():
    out = []
    for ep, sid in (("carancas2", "village"), ("koepenick", "shop")):
        d = yaml.safe_load(open(os.path.join(HERE, "examples", ep, "screenplay.yaml"), encoding="utf-8"))
        sc = next(s for s in d["scenes"] if s["id"] == sid)
        used = {o.get("shape") for sec in ("set", "props", "cast") for o in (sc.get(sec) or []) if o.get("shape")}
        doc = {"styles": d.get("styles") or {}, "shapes": {n: v for n, v in (d.get("shapes") or {}).items() if n in used}, "scenes": [sc]}
        out.append(f"# example from another story; its sentence(s): {' '.join(d['sentences'][k] for k in sc['sents'])}\n" +
                   yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=170, default_flow_style=None))
    return "\n".join(out)


DIRECTOR = """You are the director of a 45-second hand-drawn doodle animation: 720x1280 vertical video, thick black ink lines and flat
colours on paper, stick-figure people. A narrator reads the sentences. Decide for EVERY scene exactly what the viewer sees and
what moves, in enough detail that a programmer can build it without guessing. The programmer only has the engine documented
below (its kinds, verbs, poses, emitters) plus the library of ready-made drawings, and can draw new simple shapes.

Return ONLY a JSON array (no prose, no code fences), one object per scene, in story order:
{"id": "...", "sents": ["s1"],
 "idea": "the one clear picture of this scene, in one sentence",
 "backdrop": "sky + time of day + weather + ground: name a library backdrop or an engine kind, with colours",
 "objects": [{"id": "cottage", "what": "snowy cottage", "source": "lib:cottage" | "kind:house" | "draw",
              "draw": "only for source draw: the drawing as simple geometry - parts, proportions in px, colours",
              "x": 230, "y": 880, "size": "334 px tall (scale 1)"}],
 "people": [{"id": "woman", "who": "village woman", "look": "long rose coat, brown hair", "x": 420, "k": 1.5, "facing": "r"}],
 "actions": [{"when": "start" | "word:<exact word of this scene's sentences>" | "+0.4s after previous",
              "who": "woman", "what": "one concrete movement"}],
 "camera": "start framing, then moves: zoom values and what is centred",
 "check": ["every thing the sentences name that must be visible"]}

DIRECTING RULES
- Show exactly what the sentence says. Every thing a sentence names is on screen while it is spoken. Nothing unrelated.
- Sizes must make sense: a person with k 1.3 is about 310 px tall; a cottage about 330 px, a church 480 px, a dog 100 px,
  a horse 230 px. Buildings are never smaller than the people next to them. The ground line is near y 880.
- BIG and readable: the main subject fills at least a third of the frame height; for small things (a footprint, a ruler,
  a coin) use a close-up: camera zoom 1.6-2.2 centred on it.
- Never an empty paper background: every scene has a sky or backdrop and a ground. Night scenes use a night backdrop,
  snow scenes a snow ground, both from the library when they exist.
- Animals and things are real drawings (library or draw), never a person standing in for them.
- 8 to 14 actions per scene and something moves all the time: people walk or run in, react with their faces and poses,
  things pop up one after another, the camera pushes, pans or follows. At least four actions start on a spoken word.
- Rhythmic things (prints appearing in a row, hopping, running, snow falling) are one action with "repeat every N s".
- Keep it buildable: at most 10 different objects per scene (a row of identical prints counts as one).
- Captions cover everything below y 926 and big gold words sit at y 100-260: keep the action between y 280 and y 900."""

CODER = """You write scenes of a short animated doodle video (720x1280 vertical, hand-drawn ink on paper) as YAML for the engine
documented below. A director's script tells you what each scene contains; follow it: its objects, sizes, positions, actions.

OUTPUT: only YAML, no prose, no code fences. Top-level keys:
styles: {}        # optional named styles for your new shapes
shapes: {}        # NEW custom drawings (name -> list of items). Library drawings need no definition: just use their name.
scenes: [...]     # the requested scenes, each: id, sents, optional in/camera, set, props, cast, beats

HARD RULES
- Use ONLY kinds, verbs, poses, faces, emitters and sfx that the documentation lists. Never invent names.
- A beat's `at` with word: must name a word that occurs in THAT scene's sentences. Quote "word:..." strings.
- Quote every "#rrggbb" colour. Every object a beat animates needs an `id` (lowercase letters, digits, underscore), unique in its scene.
- Every `shape:` name must be either in the library list or defined by you under `shapes:` in this answer (or listed as already defined).
- First object of `set` is the backdrop (kind sky, or a library backdrop shape at x 0, y 0); every scene also has a ground.
- World is visible for y < 926. Keep drawings between x 20..700 and y 280..900.
- People are `cast` entries (stick figures). Animals and things are shapes, never cast entries.
- Each action of the script becomes one or more beats; rhythmic actions use `repeat`. At least 8 beats per scene.
- New shapes: thick black outline (width 5-7), flat fills, 4-14 items, drawn around their own origin (0,0 = bottom centre for
  things that stand on the ground) at the pixel size the script gives."""


# ----------------------------------------------------------------------------------------------- spracovanie odpovede
def strip_fences(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
    return re.sub(r"^```[a-zA-Z]*\s*$", "", txt.strip(), flags=re.M).strip()


def parse_json_list(txt):
    txt = strip_fences(txt)
    i, j = txt.find("["), txt.rfind("]")
    return json.loads(txt[i:j + 1])


def parse_yaml_doc(txt):
    txt = strip_fences(txt)
    m = re.search(r"^(styles|shapes|scenes|scene):", txt, flags=re.M)
    if m:
        txt = txt[m.start():]
    txt = re.sub(r"(:\s*)(#[0-9a-fA-F]{3,8})\b", r'\1"\2"', txt)
    txt = re.sub(r"(\[\s*|,\s*)(#[0-9a-fA-F]{6})\b", r'\1"\2"', txt)
    doc = yaml.safe_load(txt)
    if not isinstance(doc, dict):
        raise ValueError("answer is not a YAML mapping")
    scenes = doc.get("scenes") or ([doc["scene"]] if isinstance(doc.get("scene"), dict) else [])
    if not scenes or not all(isinstance(s, dict) for s in scenes):
        raise ValueError("no `scenes:` list in the answer")
    return (doc.get("styles") or {}), (doc.get("shapes") or {}), scenes


def sanitize(scene):
    notes = []
    for sec in ("set", "props", "cast"):
        objs = scene.get(sec)
        if objs is None:
            continue
        if not isinstance(objs, list):
            scene[sec] = []
            continue
        scene[sec] = [o for o in objs if isinstance(o, dict)]
        for o in scene[sec]:
            if "face" in o and o["face"] not in FACES:
                notes.append(f"face '{o['face']}' is not a face name")
                o["face"] = "ok"
            if "hat" in o and not (isinstance(o["hat"], list) and len(o["hat"]) == 2):
                del o["hat"]
    scene["beats"] = [b for b in (scene.get("beats") or []) if isinstance(b, dict)]
    return notes


def shape_refs(scene, shapes):
    """mena tvarov, ktore scena potrebuje (aj vnorene use:)"""
    need, todo = set(), []
    for sec in ("set", "props", "cast"):
        for o in scene.get(sec) or []:
            if o.get("shape") and o.get("kind") in ("shape", "emitter"):
                todo.append(o["shape"])
    while todo:
        n = todo.pop()
        if n in need:
            continue
        need.add(n)

        def walk(items):
            for it in items or []:
                if isinstance(it, dict):
                    if it.get("use"):
                        todo.append(it["use"])
                    walk(it.get("items"))
        walk(shapes.get(n))
    return need


BUILTIN_SHAPES = {"check", "cross", "question", "exclaim", "arrow_down"}


def lint(scene, shapes, lib):
    """mechanicka kontrola rezie; vrati (automaticke opravy, vyhrady pre model)"""
    fixed, issues = [], []
    sset = scene.setdefault("set", [])
    objs = [o for sec in ("set", "props", "cast") for o in (scene.get(sec) or [])]

    def is_backdrop(o):
        if o.get("kind") == "sky":
            return True
        b = (lib.get(o.get("shape")) or {}).get("box") if o.get("kind") == "shape" else None
        return bool(b and (b[2] - b[0]) >= 700 and (b[3] - b[1]) >= 500)
    if not any(is_backdrop(o) for o in objs):
        sset.insert(0, {"kind": "sky"})
        fixed.append("pridane pozadie sky")
    if not any(o.get("kind") in ("ground", "underground") or o.get("shape") in ("snowland", "street", "plaza", "harbour", "seadark", "seapale") for o in objs):
        sset.insert(1, {"kind": "ground", "y": 880})
        fixed.append("pridana zem")
    people = [o for o in (scene.get("cast") or []) if o.get("kind", "char") == "char"]
    tall = max([float(o.get("k", 1)) * 240 for o in people] or [0])
    for o in objs:
        if o.get("kind") in ("house", "building") and tall and float(o.get("h", 100)) < 0.85 * tall:
            issues.append(f"building '{o.get('id')}' is {o.get('h', 100)} px high but a person here is {tall:.0f} px tall: make the building h >= {tall * 1.1:.0f} "
                          f"(w about the same) or the people smaller")
    beats = scene.get("beats") or []
    if len(beats) < 6:
        issues.append(f"only {len(beats)} beats: the scene is static, add actions from the script (people entering, reacting, camera move)")
    if sum(1 for b in beats if isinstance(b.get("at"), str) and "word:" in b["at"]) < 2:
        issues.append("fewer than 2 beats are tied to spoken words with word:...")
    if not any(b.get("who") == "cam" for b in beats) and not scene.get("camera"):
        issues.append("no camera work: add a camera start framing or a push/pan beat")
    for o in objs:                                     # x mimo zaber je bezne (siroky svet pre pan kamery), kontroluje sa len y
        y = o.get("y", o.get("gy"))
        if isinstance(y, (int, float)) and not -200 <= y <= 1100:
            issues.append(f"object '{o.get('id')}' y {y} is outside the visible area (0..926)")
    return fixed, issues


def compile_ep(ep_dir):
    p = subprocess.run([sys.executable, os.path.join(HERE, "sp.py"), ep_dir], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=HERE, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    out = (p.stdout or "") + (p.stderr or "")
    m = re.search(r"SCREENPLAY ERROR: (.*)", out)
    if m:
        return False, m.group(1).strip()
    if p.returncode != 0:
        return False, " | ".join([x for x in out.strip().splitlines() if x.strip()][-3:])[:500]
    return True, out.strip().splitlines()[-1]


def prune(scene, err):
    beats = scene.get("beats") or []
    m = re.search(r"beat #(\d+) \((\S+) (\S+)\)", err)
    if m:
        i, who, do = int(m.group(1)) - 1, m.group(2), m.group(3)
        cand = [k for k, b in enumerate(beats) if str(b.get("who")) == who and str(b.get("do")) == do]
        k = i if (0 <= i < len(beats) and i in cand) else (min(cand, key=lambda c: abs(c - i)) if cand else (i if 0 <= i < len(beats) else None))
        if k is None:
            return None
        beats.pop(k)
        return "beat"
    for pat, field in ((r"unknown kind '([^']+)'", "kind"), (r"unknown emitter '([^']*)'", "emitter")):
        m = re.search(pat, err)
        if m:
            for sec in ("set", "props", "cast"):
                scene[sec] = [o for o in (scene.get(sec) or []) if str(o.get(field)) != m.group(1)]
            return "object"
    m = re.search(r"object '([^']+)' is attached to unknown object", err)
    if m:
        for sec in ("set", "props", "cast"):
            scene[sec] = [o for o in (scene.get(sec) or []) if o.get("id") != m.group(1)]
        return "object"
    if re.search(r"object without kind", err):
        for sec in ("set", "props"):
            scene[sec] = [o for o in (scene.get(sec) or []) if "kind" in o]
        return "object"
    return None


# ----------------------------------------------------------------------------------------------- hlavny postup
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("brief")
    ap.add_argument("--provider", default="openrouter")
    ap.add_argument("--model", required=True)
    ap.add_argument("--lib-exclude", default="", help="epizody, ktorych kresby sa z kniznice nepouziju (test bez napovede)")
    ap.add_argument("--scenes", default="", help="len tieto sceny (id,id)")
    ap.add_argument("--no-script", action="store_true", help="bez rezijneho kroku (model dostane len kratke zadanie)")
    ap.add_argument("--chunk", type=int, default=3)
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-qa", action="store_true")
    a = ap.parse_args()
    B = yaml.safe_load(open(a.brief, encoding="utf-8"))
    tag = a.tag or re.sub(r"[^a-z0-9]+", "-", a.model.split("/")[-1].lower()).strip("-")[:24]
    name = f"{B['name']}_{tag}" if a.provider != "mock" else f"{B['name']}_mock"
    ep_dir = os.path.join(HERE, "episodes", name)
    os.makedirs(ep_dir, exist_ok=True)
    head = yaml.safe_load(B["header"])
    sents, keys = head["sentences"], list(head["sentences"])
    plans = [p for p in B["scenes"] if not a.scenes or p["id"] in a.scenes.split(",")]
    lib = load_lib([x for x in a.lib_exclude.split(",") if x])
    cat = catalog(lib)
    story = "STORY (narration, one line per sentence):\n" + "\n".join(f"{k}: {v}" for k, v in sents.items())
    gold = "GOLD WORDS already handled by another program (leave y 100-260 free while they show): " + \
           "; ".join(f"\"{g.get('label')}\" on the word {g.get('word')}" for g in head.get("gold") or [])
    t_start = time.time()
    state = {"styles": {}, "shapes": {}, "scenes": [], "report": []}

    def write_file():
        doc = copy.deepcopy(head)
        doc["styles"] = state["styles"]
        doc["shapes"] = state["shapes"]
        done = [s for sc in state["scenes"] for s in sc.get("sents", [])]
        rest = [k for k in keys if k not in done]
        order = [p["id"] for p in B["scenes"]]
        scs = sorted(state["scenes"], key=lambda s: order.index(s["id"]))
        doc["scenes"] = scs + ([{"id": "zz_rest", "sents": rest, "set": [{"kind": "sky"}, {"kind": "ground", "y": 880}], "beats": []}] if rest else [])
        doc["scenes"].sort(key=lambda s: keys.index(s["sents"][0]))
        with open(os.path.join(ep_dir, "screenplay.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True, width=170, default_flow_style=None)

    # ---------- 1) REZIA
    scripts = {}
    if not a.no_script:
        user = (story + "\n\n" + gold + "\n\nSCENES TO DIRECT (id, sentences, what the producer wants to see):\n" +
                "\n".join(f"- {p['id']} {p['sents']}: {p['must']}" for p in plans) + "\n\n" + cat)
        for attempt in (1, 2):
            txt = chat(a.provider, a.model, [{"role": "system", "content": DIRECTOR + "\n\n=== ENGINE DOCUMENTATION ===\n" + api_doc()},
                                             {"role": "user", "content": user}], {"stage": "script", "ids": [p["id"] for p in plans]}, temperature=0.7)
            open(os.path.join(ep_dir, f"raw_script_{attempt}.txt"), "w", encoding="utf-8").write(txt)
            try:
                scripts = {s["id"]: s for s in parse_json_list(txt) if isinstance(s, dict) and s.get("id")}
                break
            except Exception as e:                                         # noqa: BLE001
                print(f"  rezia pokus {attempt}: JSON sa neda citat ({str(e)[:100]})", flush=True)
        json.dump(scripts, open(os.path.join(ep_dir, "script.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"REZIA: {len(scripts)}/{len(plans)} scen, {sum(len(s.get('actions') or []) for s in scripts.values())} akcii", flush=True)

    system = CODER + "\n\n=== ENGINE DOCUMENTATION ===\n" + api_doc() + "\n\n=== EXAMPLES OF THE OUTPUT FORMAT ===\n" + example_yaml()

    def brief_for(p):
        s = scripts.get(p["id"])
        words = " ".join(sents[k] for k in p["sents"])
        base = f"SCENE {p['id']}  sents: {p['sents']}\n  its sentences (only these words may be used in word: anchors): {words}\n"
        if s:
            return base + "  DIRECTOR'S SCRIPT:\n" + json.dumps(s, ensure_ascii=False, indent=1)
        return base + f"  WHAT MUST BE SEEN: {p['must']}"

    def accept(p, scene, new_styles, new_shapes):
        """vlozi scenu, kompiluje, oreze drobnosti; vrati (ok, zoznam problemov pre model)"""
        scene["id"], scene["sents"] = p["id"], p["sents"]
        problems = sanitize(scene)
        shapes = dict(state["shapes"])
        shapes.update({k: v for k, v in new_shapes.items() if isinstance(v, list)})
        missing = []
        for n in shape_refs(scene, {**{k: v["items"] for k, v in lib.items()}, **shapes}):
            if n in shapes or n in BUILTIN_SHAPES:
                continue
            if n in lib:
                shapes[n] = lib[n]["items"]
            else:
                missing.append(n)
        if missing:
            problems.append("these shapes are used but not defined and not in the library: " + ", ".join(missing) + " - define them under shapes: or use a library name")
            for sec in ("set", "props", "cast"):
                scene[sec] = [o for o in (scene.get(sec) or []) if o.get("shape") not in missing]
        fixed, issues = lint(scene, shapes, lib)
        problems += issues
        backup = (state["styles"], state["shapes"], list(state["scenes"]))
        state["styles"] = {**state["styles"], **{k: v for k, v in new_styles.items() if isinstance(v, dict)}}
        state["shapes"] = shapes
        state["scenes"] = [s for s in state["scenes"] if s["id"] != p["id"]] + [scene]
        n0, npr, ok, msg = len(scene["beats"]), 0, False, ""
        for _ in range(60):
            write_file()
            ok, msg = compile_ep(ep_dir)
            if ok:
                break
            kind = prune(scene, msg)
            if not kind:
                break
            npr += 1
            problems.append("compiler: " + msg[:220])
        if not ok:
            state["styles"], state["shapes"], state["scenes"] = backup
            write_file()
            return False, problems + ["compiler (fatal): " + msg[:300]], n0, 0
        return True, problems, n0, len(scene["beats"])

    # ---------- 2) KOD po davkach
    todo = list(plans)
    results = {}
    for i in range(0, len(todo), a.chunk):
        chunk = todo[i:i + a.chunk]
        user = (story + "\n\n" + gold + "\n\nWRITE THESE SCENES NOW:\n\n" + "\n\n".join(brief_for(p) for p in chunk) + "\n\n" + cat +
                ("\n\nCustom shapes you already defined earlier (reuse by name, do not redefine): " + ", ".join(sorted(n for n in state["shapes"] if n not in lib))
                 if any(n not in lib for n in state["shapes"]) else ""))
        txt = chat(a.provider, a.model, [{"role": "system", "content": system}, {"role": "user", "content": user}], {"stage": "code", "ids": [p["id"] for p in chunk]})
        open(os.path.join(ep_dir, f"raw_code_{i // a.chunk + 1}.txt"), "w", encoding="utf-8").write(txt)
        try:
            st, sh, scenes = parse_yaml_doc(txt)
        except Exception as e:                                             # noqa: BLE001
            print(f"  kod davka {i // a.chunk + 1}: YAML sa neda citat ({str(e)[:140]})", flush=True)
            for p in chunk:
                results[p["id"]] = {"ok": False, "problems": [f"YAML could not be parsed: {str(e)[:200]}"], "yaml": ""}
            continue
        by_id = {s.get("id"): s for s in scenes}
        for p in chunk:
            sc = by_id.get(p["id"])
            if not sc:
                results[p["id"]] = {"ok": False, "problems": ["scene missing in the answer"], "yaml": ""}
                continue
            ok, problems, n0, n1 = accept(p, copy.deepcopy(sc), st, sh)
            results[p["id"]] = {"ok": ok, "problems": problems, "n0": n0, "n1": n1,
                                "yaml": yaml.safe_dump({"shapes": {k: v for k, v in sh.items()}, "scenes": [sc]}, sort_keys=False, allow_unicode=True, width=170, default_flow_style=None)}
            print(f"  {p['id']}: {'OK' if ok else 'CHYBA'} udery {n0}->{n1} | problemy {len(problems)}", flush=True)

    # ---------- 3) OPRAVY (najhorsie sceny prve)
    def badness(pid):
        r = results[pid]
        return (0 if r["ok"] else 100) + len(r["problems"]) * 3 + (r.get("n0", 0) - r.get("n1", 0))
    for rnd in (1, 2):
        worst = sorted([p for p in plans if badness(p["id"]) >= 3], key=lambda p: -badness(p["id"]))
        for p in worst:
            if STATS["calls"] >= MAX_CALLS:
                break
            r = results[p["id"]]
            user = (story + "\n\n" + brief_for(p) + "\n\n" + cat + "\n\nYOUR PREVIOUS YAML FOR THIS SCENE:\n" + (r["yaml"] or "(could not be read)") +
                    "\n\nPROBLEMS FOUND (compiler + automatic check) - fix every one of them and return the corrected `shapes` and `scenes` (this one scene):\n- " +
                    "\n- ".join(dict.fromkeys(r["problems"][:14])) +
                    ("\n\nCustom shapes already defined (reuse by name): " + ", ".join(sorted(n for n in state["shapes"] if n not in lib)) if any(n not in lib for n in state["shapes"]) else ""))
            txt = chat(a.provider, a.model, [{"role": "system", "content": system}, {"role": "user", "content": user}], {"stage": "fix", "ids": [p["id"]]}, temperature=0.3)
            open(os.path.join(ep_dir, f"raw_fix_{p['id']}_{rnd}.txt"), "w", encoding="utf-8").write(txt)
            try:
                st, sh, scenes = parse_yaml_doc(txt)
                sc = next((s for s in scenes if s.get("id") == p["id"]), scenes[0])
            except Exception as e:                                         # noqa: BLE001
                print(f"  oprava {p['id']}: YAML sa neda citat ({str(e)[:100]})", flush=True)
                continue
            ok, problems, n0, n1 = accept(p, copy.deepcopy(sc), st, sh)
            new = {"ok": ok, "problems": problems, "n0": n0, "n1": n1,
                   "yaml": yaml.safe_dump({"shapes": sh, "scenes": [sc]}, sort_keys=False, allow_unicode=True, width=170, default_flow_style=None)}
            better = (new["ok"] and not r["ok"]) or (new["ok"] == r["ok"] and (len(problems), -n1) <= (len(r["problems"]), -r.get("n1", 0)))
            print(f"  oprava {p['id']} (kolo {rnd}): {'OK' if ok else 'CHYBA'} udery {n0}->{n1} | problemy {len(r['problems'])}->{len(problems)} | {'beriem' if better else 'nechavam povodnu'}", flush=True)
            if better:
                results[p["id"]] = new
            elif r["ok"]:                                                   # vratit povodnu verziu sceny
                st0, sh0, sc0 = parse_yaml_doc(r["yaml"])
                accept(p, copy.deepcopy(sc0[0]), st0, sh0)

    # sceny, ktore sa nepodarilo vobec: prazdna nahrada, aby sa epizoda dala zlozit
    for p in plans:
        if not results[p["id"]]["ok"] and not any(s["id"] == p["id"] for s in state["scenes"]):
            state["scenes"].append({"id": p["id"], "sents": p["sents"], "set": [{"kind": "sky"}, {"kind": "ground", "y": 880}], "beats": []})
    write_file()
    ok, msg = compile_ep(ep_dir)
    print("KOMPILACIA", "OK" if ok else "CHYBA", msg[:260], flush=True)
    report = {"model": a.model, "provider": a.provider, "calls": STATS["calls"], "tokens_in": STATS["in"], "tokens_out": STATS["out"], "model_seconds": round(STATS["sec"]),
              "wall_seconds": round(time.time() - t_start), "compiled": ok,
              "scenes": {pid: {"ok": r["ok"], "beats": r.get("n1", 0), "pruned": r.get("n0", 0) - r.get("n1", 0), "open_problems": r["problems"][:6]} for pid, r in results.items()},
              "custom_shapes": sorted(n for n in state["shapes"] if n not in lib), "library_shapes_used": sorted(n for n in state["shapes"] if n in lib), "calls_log": STATS["log"]}
    json.dump(report, open(os.path.join(ep_dir, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"STATS volania={STATS['calls']} vstup={STATS['in']} vystup={STATS['out']} cas_modelu={STATS['sec']:.0f}s spolu={time.time() - t_start:.0f}s")
    print("TVARY vlastne:", report["custom_shapes"], "| z kniznice:", report["library_shapes_used"])
    if ok and not a.no_qa:
        q = subprocess.run([sys.executable, os.path.join(HERE, "qa.py"), ep_dir], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=HERE, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        tail = [x for x in ((q.stdout or "") + (q.stderr or "")).splitlines() if re.match(r"\s+(check|render|duration|blank|frozen|loop|captions|world)|RESULT", x)]
        print("\n".join(tail[-12:]))
    print(f"EPISODE_DIR {ep_dir}")


if __name__ == "__main__":
    main()
