# -*- coding: utf-8 -*-
"""Jedna kontrola hotoveho scenara pre autora (clovek alebo model): kompilacia + mechanicka rezijna kontrola + meranie na obrazovke.
  python doodle/accept.py doodle/episodes/<meno>
Vypise kratky zoznam problemov po scenach (alebo OK). Nic v subore nemeni. Navratovy kod 0 = bez problemov."""
import os
import sys

import yaml

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import auto_writer as W   # noqa: E402


def main():
    ep_dir = os.path.abspath(sys.argv[1])
    doc = yaml.safe_load(open(os.path.join(ep_dir, "screenplay.yaml"), encoding="utf-8"))
    lib = W.load_lib([])
    sents = doc.get("sentences") or {}
    used = [k for sc in doc.get("scenes") or [] for k in sc.get("sents") or []]
    missing = [k for k in sents if k not in used]
    if missing:
        print(f"PROBLEM: sentences without a scene: {missing} (every sentence must belong to exactly one scene)")
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
        issues += W.visibility_problems(ep_dir, sc.get("check"))
        total += len(issues)
        print(f"- {sc['id']}: beats {len(sc.get('beats') or [])}" + ("  OK" if not issues else ""))
        for i in issues:
            print("    *", i)
    print("RESULT:", "no problems" if not total else f"{total} problems")
    return 0 if not total else 2


if __name__ == "__main__":
    sys.exit(main())
