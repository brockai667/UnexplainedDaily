# -*- coding: utf-8 -*-
"""Kniznica kresieb pre autora epizod: pozbiera vlastne tvary z hotovych scenarov (pisal ich Claude) do lib/shapes.yaml.
Kazdy tvar je sebestacny (styly su rozpustene v polozkach, `use:` odkazuje na meno v kniznici) a ma hrubu obalku [x0, y0, x1, y1]
v lokalnych suradniciach, aby autor vedel, aky je velky a kde ma pociatok.
  python doodle/build_lib.py <screenplay.yaml> [<screenplay.yaml> ...]      (meno epizody = meno priecinka)
"""
import copy
import os
import re
import sys

import yaml

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "lib", "shapes.yaml")
# tvary viazane na jednu epizodu alebo s nic nehovoriacim menom - do kniznice nejdu
SKIP = {"hoofv", "hoof4", "hoofp", "trailrun", "cover", "dot", "dogr", "hillsG", "devonmap", "pipewall", "lampwin", "frontD", "frontG",
        "wavesA", "wavesB", "pframe", "sheet", "swarmA", "swarmB", "swarmC", "switchplate", "glowdisc", "halo", "deepbg", "veil", "panels",
        "sface", "crowdfaces", "shimmer", "frame", "hillslope", "crossstaff", "bignote", "shiprail"}
NOTES = {  # co to je (pre model); ostatne mena hovoria sami za seba
    "dusk": "full-frame dusk sky backdrop with low sun and far hills (absolute coords, place at x 0 y 0)",
    "nightsky": "full-frame night sky backdrop with stars (absolute coords, place at x 0 y 0)",
    "daysky": "full-frame pale day sky backdrop (absolute coords, place at x 0 y 0)",
    "snowland": "snow-covered ground with a soft horizon (absolute coords, place at x 0 y 0)",
    "seadark": "dark night sea surface, full width", "seapale": "pale glowing sea surface, full width",
    "harbour": "harbour quay backdrop", "plaza": "town square backdrop", "street": "cobbled street backdrop",
    "cottage": "snowy cottage with chimney, door and window", "church": "small church with tower", "minster": "big cathedral",
    "houseL": "half-timbered town house (left side of a street)", "houseR": "half-timbered town house (right side)",
    "guildhall": "big hall with double doors", "chapel": "small hilltop chapel", "townhall": "town hall facade",
    "sat": "satellite with solar panels", "earth": "planet Earth disc", "cargo": "modern cargo ship", "galleon": "old sailing ship",
    "bubble": "thought bubble (put a small drawing inside)", "ban": "red prohibition sign (circle with a slash)", "redx": "red X mark",
    "nomusic": "crossed-out music note", "note": "music note", "pipe": "flute (musical pipe)", "bow": "fiddle bow",
    "hoof": "hoof print (horseshoe shape)", "ruler": "wooden ruler", "gun": "long hunting gun", "tophat": "top hat",
    "lens": "magnifying lens", "logbook": "open ship logbook", "lab": "laboratory room backdrop", "counter": "shop counter",
    "uniform": "officer uniform on a hanger", "cashbox": "cash box with a lid (part: lid)", "loaf": "loaf of bread",
}


def numbers(s):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", s)]


def bbox_items(items, lib):
    xs, ys = [], []

    def add(x, y):
        xs.append(x)
        ys.append(y)
    for it in items or []:
        if it.get("rect"):
            x, y, w, h = it["rect"][:4]
            add(x, y), add(x + w, y + h)
        elif it.get("circle"):
            cx, cy, r = it["circle"]
            add(cx - r, cy - r), add(cx + r, cy + r)
        elif it.get("ellipse"):
            cx, cy, rx, ry = it["ellipse"]
            add(cx - rx, cy - ry), add(cx + rx, cy + ry)
        elif it.get("poly") or it.get("line"):
            for p in it.get("poly") or it.get("line"):
                add(p[0], p[1])
        elif it.get("path"):
            n = numbers(re.sub(r"[Aa][^MLQCTSZHVmlqctszhv]*", " ", it["path"]))
            for i in range(0, len(n) - 1, 2):
                add(n[i], n[i + 1])
        elif it.get("text"):
            add(it["text"][0], it["text"][1])
        elif it.get("group"):
            b = bbox_items(it.get("items"), lib)
            if b:
                add(b[0], b[1]), add(b[2], b[3])
        elif it.get("use") and it["use"] in lib:
            b = lib[it["use"]].get("box")
            if b:
                ax, ay = (it.get("at") or [0, 0])
                s = it.get("scale", 1)
                add(ax + b[0] * s, ay + b[1] * s), add(ax + b[2] * s, ay + b[3] * s)
    if not xs:
        return None
    return [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))]


def resolve(items, styles, rename):
    out = []
    for it in items or []:
        it = copy.deepcopy(it)
        if "style" in it:
            for k, v in (styles.get(it.pop("style")) or {}).items():
                it.setdefault(k, v)
        if "items" in it:
            it["items"] = resolve(it["items"], styles, rename)
        if "use" in it:
            it["use"] = rename.get(it["use"], it["use"])
        out.append(it)
    return out


def main(paths):
    lib = {}
    for p in paths:
        ep = os.path.basename(os.path.dirname(os.path.abspath(p)))
        ep = re.sub(r"^\d+-", "", ep)
        d = yaml.safe_load(open(p, encoding="utf-8"))
        styles, shapes = d.get("styles") or {}, d.get("shapes") or {}
        rename = {n: (n if n not in lib else f"{n}_{ep[:6]}") for n in shapes}
        for n, items in shapes.items():
            lib[rename[n]] = {"from": ep, "note": NOTES.get(n, n.replace("_", " ")), "items": resolve(items, styles, rename)}
            if n in SKIP:                                 # pomocne tvary: v katalogu sa neukazuju, ale vzorove sceny ich pouzivaju
                lib[rename[n]]["hidden"] = True
    for _ in range(3):                                    # obalky (use: potrebuje obalku pouziteho tvaru)
        for n, s in lib.items():
            s["box"] = bbox_items(s["items"], lib)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# Generovane: python doodle/build_lib.py ... - neupravovat rucne.\n")
        yaml.safe_dump({"shapes": lib}, f, sort_keys=False, allow_unicode=True, width=200, default_flow_style=None)
    print(f"{len(lib)} tvarov ({sum(1 for v in lib.values() if not v.get('hidden'))} v katalogu) -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
