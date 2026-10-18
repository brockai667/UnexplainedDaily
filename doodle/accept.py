# -*- coding: utf-8 -*-
"""Jedna kontrola hotoveho scenara pre autora (clovek alebo model): kompilacia + mechanicka rezijna kontrola + meranie na obrazovke.
  python doodle/accept.py doodle/episodes/<meno>
Vypise kratky zoznam problemov po scenach (alebo OK). Nic v subore nemeni. Navratovy kod 0 = bez problemov.
Najprv sa cely scenar prejde (lint_all) a NARAZ sa vypisu vsetky chyby, na ktorych by sa kompilator zastavil (sp.py hlasi len prvu):
ak nejake su, kompilacia sa nespusta a navratovy kod je 1."""
import difflib
import os
import re
import sys

import yaml

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import auto_writer as W   # noqa: E402


def lint_all(ep_dir, lib=None):
    """Scan of the WHOLE screenplay before it is compiled: every problem sp.compile_episode would stop at. The compiler reports only the first
    one, so a model that fixes one per round never catches up. Same wording, and the compiler's own tables and Clock (sp.KIND_VERBS, POSES,
    FACES, EMITTERS, SFX_NAMES, BUILTIN_SHAPES, Clock), plus the `check:` words that accept.py would find only after a successful compile.
    Nothing is rendered (no TTS). -> list of lines `COMPILE ERROR: ...` (empty = nothing found). `beat #n` = the n-th entry of `beats:`."""
    import sp                                   # here, not on top: sp pulls in numpy / soundfile / PIL
    E = sp.load_screenplay(ep_dir)              # the compiler's own loader: drawings of the library count as defined
    lib = W.load_lib([]) if lib is None else lib
    out, shown = [], set()

    def add(msg, tag="COMPILE ERROR"):
        out.append(f"{tag}: {msg}")

    def names(tag, items):                      # a long list of allowed names is spelled out once, later lines point back to it
        if tag in shown:
            return "(list above)"
        shown.add(tag)
        return ", ".join(sorted(str(i) for i in items))

    def near(name, pool):
        m = difflib.get_close_matches(str(name), sorted(str(p) for p in pool), n=3, cutoff=0.6)
        return f" Closest: {', '.join(m)}." if m else ""

    if not isinstance(E, dict):
        return ["COMPILE ERROR: the screenplay must be a YAML mapping (header, styles, shapes, sentences, scenes)"]
    try:
        sp.resolve_music(E.get("music"))
    except sp.SPError as e:
        add(str(e))
    raw = E.get("sentences")
    pairs = list(raw.items()) if isinstance(raw, dict) else [tuple(p) for p in (raw if isinstance(raw, list) else [])
                                                             if isinstance(p, (list, tuple)) and len(p) == 2]
    if not pairs:
        add("screenplay needs 'sentences'")
        return out
    scenes = E.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        add("screenplay needs 'scenes'")
        return out
    keys = [k for k, _ in pairs]
    skeys = ", ".join(str(k) for k in keys)
    allw = [{"w": t, "s": 0.0, "e": 0.0, "k": k} for k, v in pairs for t in str(v).split()]      # the compiler's words, without timing
    clock = sp.Clock(allw, keys)                # the compiler's own reader of `word:X`, `s3.end`, `hit:W@O` ... (its timings stay 0)
    shapes = E.get("shapes") if isinstance(E.get("shapes"), dict) else {}
    pool = {n for n, s in lib.items() if not (s or {}).get("hidden")} | set(shapes) | set(sp.BUILTIN_SHAPES)

    def clock_problem(expr, where, find=False):
        """a time / word reference exactly as the compiler's Clock reads it -> its error text, or ''"""
        try:
            if find:
                clock.find(str(expr), where)
            else:
                clock(expr, where)
        except sp.SPError as e:
            msg = str(e)
            m = re.search(r"word '([^'/#]+)/[^']*' not found", msg)
            return msg + (f" (there is no sentence '{m.group(1)}'; sentences: {skeys})" if m and m.group(1) not in clock.by_key else "")
        except Exception as e:                  # noqa: BLE001 - e.g. a malformed `#n`
            return f"{where}: cannot read '{expr}' ({type(e).__name__}: {e})"
        return ""

    def beat_problems(b, where, kinds, sid):
        found, variants = [], [b]
        rep = b.get("repeat")
        if rep is not None:                     # repeat {every, n | until, cycle | alt}: every copy is checked with its overrides
            try:
                good = isinstance(rep, dict) and float(rep.get("every", 0) or 0) > 0
            except (TypeError, ValueError):
                good = False
            if not good:
                found.append(f"{where}: repeat needs every: <seconds > 0> and n: <count> or until: <time>")
            else:
                if rep.get("until") is not None:
                    found.append(clock_problem(rep["until"], where))
                else:
                    try:
                        n = int(rep.get("n", 0) or 0)
                    except (TypeError, ValueError):
                        n = 0
                    if not 1 <= n <= 400:
                        found.append(f"{where}: repeat would make {n} beats (allowed 1..400) - check every, n or until")
                cycle = rep.get("cycle") or ([{}, rep["alt"]] if rep.get("alt") else [{}])
                if not isinstance(cycle, list) or not all(isinstance(c, dict) or c is None for c in cycle):
                    found.append(f"{where}: repeat cycle must be a list of key overrides, e.g. [{{name: arms_up}}, {{name: arms_down}}]")
                else:
                    variants = [{**b, **(c or {})} for c in cycle]
        found.append(clock_problem(b.get("at"), where))
        if "until" in b:
            found.append(clock_problem(b["until"], where))
        for v in variants:
            who, verb = v.get("who"), v.get("do")
            if who == "cam":
                if verb not in sp.CAM_VERBS:
                    found.append(f"{where}: camera verbs are {names('cam', sp.CAM_VERBS)}")
            elif who == "fx":
                if verb not in sp.FX_VERBS:
                    found.append(f"{where}: fx verbs are {', '.join(sorted(sp.FX_VERBS))}")
            elif who not in kinds:
                if not str(who).startswith("gold_"):
                    found.append(f"{where}: unknown object '{who}'. Objects in this scene: {names(f'objs:{sid}', kinds)}")
            elif kinds[who] is not None:        # (an object of an unknown kind was reported with its scene already)
                kind = kinds[who]
                allowed = sp.KIND_VERBS[kind] | sp.GENERIC
                if verb not in allowed:
                    hint = f" (`{verb}` is a pose: use `do: pose, name: {verb}`)" if verb in sp.POSES and "pose" in allowed else ""
                    found.append(f"{where}: '{kind}' cannot '{verb}'. Allowed: {names(f'verbs:{kind}', allowed)}{hint}")
                if verb == "pose" and v.get("name") not in sp.POSES:
                    found.append(f"{where}: unknown pose '{v.get('name')}'. Poses: {names('poses', sp.POSES)}{near(v.get('name'), sp.POSES)}")
                if verb == "face" and v.get("name") not in sp.FACES:
                    found.append(f"{where}: unknown face '{v.get('name')}'. Faces: {names('faces', sp.FACES)}{near(v.get('name'), sp.FACES)}")
                if verb in ("attach", "detach") and kind not in sp.CARRY:
                    found.append(f"{where}: only these kinds can be carried: {', '.join(sorted(sp.CARRY))}")
                if verb == "attach" and v.get("to") not in kinds and not str(v.get("to")).startswith("gold_"):
                    found.append(f"{where}: attach needs 'to: <object id>' of this scene")
            s = v.get("sfx")
            if s and s != "none":
                nm = s if isinstance(s, str) else (s[0] if isinstance(s, (list, tuple)) and len(s) >= 2 else None)
                if nm not in sp.SFX_NAMES:
                    found.append(f"{where}: unknown sfx '{nm}'. Sfx: {names('sfx', sp.SFX_NAMES)}{near(nm, sp.SFX_NAMES)}")
        if b.get("do") == "go" and kinds.get(b.get("who")) == "shockwave":
            clock.waves[b["who"]] = (0.0, 0.0, 1.0)             # later `hit:` anchors may name this wave
        return [f for f in dict.fromkeys(found) if f]

    def scan_scene(sc, sid, sk):
        clock.scene_keys = [k for k in sk if k in clock.by_key]
        objs = []
        for sec in ("set", "props", "cast"):
            items = sc.get(sec) or []
            if not isinstance(items, list):
                add(f"scene '{sid}': `{sec}:` must be a list of objects")
                continue
            for od in items:
                if not isinstance(od, dict):
                    add(f"scene '{sid}' {sec}: every object is a mapping with `kind:` and `id:`, got: {str(od)[:60]}")
                    continue
                od = dict(od)
                if sec == "cast" and "kind" not in od:
                    od["kind"] = "char"
                if "kind" not in od:
                    add(f"scene '{sid}' {sec}: object without kind: {str(od)[:100]}")
                    continue
                shp = od.get("shape")
                if od["kind"] not in sp.KIND_VERBS:
                    add(f"scene '{sid}': unknown kind '{od['kind']}'. Kinds: {names('kinds', sp.KIND_VERBS)}{near(od['kind'], sp.KIND_VERBS)}")
                    od["kind"] = None
                elif od["kind"] == "shape" and shp not in shapes and shp not in sp.BUILTIN_SHAPES:
                    add(f"scene '{sid}': unknown shape '{shp}' ({sec} object '{od.get('id')}') - use a name from the LIBRARY section "
                        f"or define it under `shapes:`.{near(shp, pool)}")
                elif od["kind"] == "emitter":
                    if od.get("emitter") not in sp.EMITTERS:
                        add(f"scene '{sid}': unknown emitter '{od.get('emitter')}'. Emitters: {names('emitters', sp.EMITTERS)}"
                            f"{near(od.get('emitter'), sp.EMITTERS)}")
                    if shp and shp not in shapes and shp not in sp.BUILTIN_SHAPES:
                        add(f"scene '{sid}': emitter '{od.get('id')}' uses unknown shape '{shp}'.{near(shp, pool)}")
                objs.append(od)
        kinds = {o["id"]: o["kind"] for o in objs if o.get("id")}
        for o in objs:                          # animatable parts of a custom shape: `<id>.<group>`
            if o["kind"] == "shape" and o.get("id"):
                for g in sp.shape_groups(shapes, shapes.get(o.get("shape"))):
                    kinds[f"{o['id']}.{g}"] = "part"
        for o in objs:
            if o.get("on") is not None and o["on"] not in kinds and not str(o["on"]).startswith("gold_"):
                add(f"scene '{sid}': object '{o.get('id')}' is attached to unknown object '{o['on']}' (on:)")
        for o in objs:
            if o.get("id"):
                clock.xs[o["id"]] = 0.0         # `hit:W@OBJ` may name any object seen so far (the compiler keeps them across scenes)
        beats = sc.get("beats") or []
        if not isinstance(beats, list):
            add(f"scene '{sid}': `beats:` must be a list")
            beats = []
        for bi, b in enumerate(beats, 1):
            if not isinstance(b, dict):
                add(f"scene '{sid}' beat #{bi}: a beat is a mapping (at, who, do, ...), got: {str(b)[:60]}")
                continue
            for p in beat_problems(b, f"scene '{sid}' beat #{bi} ({b.get('who')} {b.get('do')})", kinds, sid):
                add(p)
        for c in sc.get("check") or []:         # the same words visibility_problems() would look for after a compile
            if not isinstance(c, dict) or not c.get("word") or not c.get("ids"):
                continue
            word = str(c["word"])
            if "/" in word:
                key, wd = word.split("/", 1)
                ws, where_txt, want = clock.by_key.get(key, []), " in the narration", sp.norm(wd)
            elif sk:
                ws = [w for k in sk for w in clock.by_key.get(k, [])]
                where_txt, want = f" in this scene's sentences ({', '.join(str(k) for k in sk)})", sp.norm(word)
            else:
                ws, where_txt, want = allw, " in the narration", sp.norm(word)
            if not any(sp.norm(w["w"]) == want for w in ws):
                add(f"scene '{sid}': check '{c.get('thing')}': the word '{word}' is not{where_txt} - use an exact spoken word of the scene")

    used = [k for sc in scenes if isinstance(sc, dict) and isinstance(sc.get("sents"), list) for k in sc["sents"]]
    missing = [k for k in keys if k not in used]
    if missing:
        add(f"sentences without a scene: {missing} (every sentence must belong to exactly one scene)", "PROBLEM")
    for si, sc in enumerate(scenes, 1):
        if not isinstance(sc, dict):
            add(f"scene #{si} must be a mapping (id, sents, set, props, cast, beats, check)")
            continue
        sid = sc.get("id") or f"#{si}"
        if not sc.get("id"):
            add(f"scene #{si} has no `id:`")
        sk = sc.get("sents") if isinstance(sc.get("sents"), list) else []
        if not sk:
            add(f"scene '{sid}' has no `sents:` list (the keys of the sentences it narrates, e.g. [s1, s2])")
        for k in sk:
            if k not in clock.by_key:
                add(f"scene '{sid}': unknown sentence '{k}' (sentences: {skeys})")
        try:
            scan_scene(sc, sid, sk)
        except Exception as e:                  # noqa: BLE001 - odd structure: say so instead of dying
            add(f"scene '{sid}' could not be scanned ({type(e).__name__}: {e}) - is every object and beat a YAML mapping?")

    def uses(items):                            # the drawings a custom shape builds on (`use: NAME`), at any depth
        for it in items or []:
            if isinstance(it, dict):
                if it.get("use"):
                    yield it["use"]
                yield from uses(it.get("items"))
    try:                                        # own drawings only: a library entry is not ours to fix
        for n, items in shapes.items():
            if n in lib and items == (lib[n] or {}).get("items"):
                continue
            for u in dict.fromkeys(uses(items)):
                if u not in shapes and u not in sp.BUILTIN_SHAPES:
                    add(f"shapes '{n}': unknown drawing '{u}' in a `use:` - use a name from the LIBRARY section or define it under `shapes:`."
                        f"{near(u, pool)}")
    except Exception as e:                      # noqa: BLE001
        add(f"`shapes:` could not be scanned ({type(e).__name__}: {e})")

    clock.scene_keys = keys                     # gold, sfx and loop read the whole narration
    for gi, g in enumerate(E.get("gold") or [], 1):
        if not isinstance(g, dict) or g.get("word") is None or g.get("label") is None:
            add(f"gold #{gi}: needs `label:` and `word:` (the spoken word at which it appears), got: {str(g)[:60]}")
            continue
        where = f"gold #{gi} ({g.get('label')})"
        for p in (clock_problem(g["word"], where, find=True), clock_problem(g["until"], where) if g.get("until") is not None else ""):
            if p:
                add(p)
    for si, c in enumerate(E.get("sfx") or [], 1):
        if not isinstance(c, dict) or "name" not in c or "at" not in c:
            add(f"sfx #{si}: needs `name:` and `at:`, got: {str(c)[:60]}")
            continue
        if c["name"] not in sp.SFX_NAMES:
            add(f"sfx #{si}: unknown name '{c['name']}'. Sfx: {names('sfx', sp.SFX_NAMES)}{near(c['name'], sp.SFX_NAMES)}")
        p = clock_problem(c["at"], f"sfx #{si} ({c['name']})")
        if p:
            add(p)
    if E.get("loop"):
        if not isinstance(E["loop"], dict):
            add("loop: must be a mapping (at, dur)")
        else:
            p = clock_problem(E["loop"].get("at", f"{keys[-1]}.end+0.55"), "loop")
            if p:
                add(p)
    return out


def main():
    ep_dir = os.path.abspath(sys.argv[1])
    doc = yaml.safe_load(open(os.path.join(ep_dir, "screenplay.yaml"), encoding="utf-8"))
    lib = W.load_lib([])
    sents = doc.get("sentences") or {}
    try:
        found = lint_all(ep_dir, lib)           # EVERYTHING the compiler would reject, at once (it names only the first problem)
    except Exception as e:                      # noqa: BLE001 - a bug in the scan must never keep a screenplay from being compiled
        print(f"NOTE: the pre-compile scan was skipped ({type(e).__name__}: {e})")
        found = []
    if found:
        for line in found:
            print(line)
        print(f"RESULT: {len(found)} problems in all (nothing was compiled yet): fix ALL of them in one go; "
              "`beat #n` = the n-th entry of that scene's `beats:`")
        return 1
    ok, msg = W.compile_ep(ep_dir)
    if not ok:
        print("COMPILE ERROR:", msg)
        return 1
    print("COMPILE OK:", msg[:230])
    total = 0
    for sc in doc["scenes"]:
        text = " ".join(sents[k] for k in sc.get("sents") or [])
        _, issues = W.lint(yaml.safe_load(yaml.safe_dump(sc)), lib, text)          # kopia: lint dopĺňa pozadie, subor sa nemeni
        issues = [i for i in issues]
        objs = [o for sec in ("set", "props", "cast") for o in (sc.get(sec) or [])]
        if not any(o.get("kind") == "sky" or ((lib.get(o.get("shape")) or {}).get("box") and (lib[o["shape"]]["box"][2] - lib[o["shape"]]["box"][0]) >= 700) for o in objs):
            issues.append("no backdrop: the first object of `set` must be a sky or a full-frame backdrop shape")
        if not sc.get("check"):
            issues.append("no `check:` list (things the sentence names + the spoken word at which each must be visible)")
        issues += W.visibility_problems(ep_dir, sc.get("check"), sc.get("sents"))
        total += len(issues)
        print(f"- {sc['id']}: beats {len(sc.get('beats') or [])}" + ("  OK" if not issues else ""))
        for i in issues:
            print("    *", i)
    print("RESULT:", "no problems" if not total else f"{total} problems")
    return 0 if not total else 2


if __name__ == "__main__":
    sys.exit(main())
