# -*- coding: utf-8 -*-
"""Archetypy zaberov. Kazdy typ = funkcia, ktora dostane kontext (casy slov, rekvizitu,
zlate cislo/text) a vrati (svg, js). JS sa vklada do engine.js; casy su uz vyratane v Pythone.

Kontext c:
  p       prefix id-ciek scény (napr. "s03")
  t0,t1   zaciatok/koniec klipu (absolutne sekundy)
  words   [{"w","s","e"}] slova tejto vety
  cue_t   cas slova, na ktorom ma zlaty prvok slamnut
  gold    {"text":..} | {"count":.., "unit":..} | {"items":[..]} | None
  prop    kluc rekvizity
  bob     id rigu Boba v tejto scene
  first/last
"""
import math
import random

import worlds as W
from props import (BRONZE, DIRT, DIRT2, GH, GOLD, INK, LEAF, METAL, PAPER, PACK, RED, SHADE, STONE, SUN,
                   WATER, WOOD, BASKET, BASKET_D, CHIP, CLOD, DROP, PUFF, SPARK, STAR, SHOVEL, THUMB,
                   bone, cloud, ell, grass, num3d, pebbles, prop_svg, prop_size, rig, sun)

CW, CH = 1080, 1920
GY = 1290                      # ciara zeme vo svete
CAP_TOP = 1314                 # horna hrana pasma titulkov (v 1080-priestore)


# ================================================================== spolocne kusy sveta
def svg_wrap(body):
    return f'<svg viewBox="0 0 {CW} {CH}" xmlns="http://www.w3.org/2000/svg"><g filter="url(#boilf)">{body}</g></svg>'


def sky(p, sun_at=(880, 300), clouds=((200, 360, 0.95), (930, 480, 0.7)), cls="sunray"):
    c = "".join(cloud(*k) for k in clouds)
    return c + (sun(p + "_rays", sun_at[0], sun_at[1], cls) if sun_at else "")


# Aktualny svet epizody. build_spec ho nastavi pred generovanim scen, aby aj
# zabery, ktore o svete nic nevedia (spot, punch, theory...), stali na spravnom
# povrchu: na mori je tym povrchom paluba lode, nie piesok.
WORLD_NOW = "hill"
# Povrch konkretneho zaberu: "land" | "deck" (stojime na lodi) | "water" (objekt na hladine).
# Nastavuje ho build_spec pred kazdou scenou.
SURFACE = "land"


def deck(y=GY, x0=-1800, x1=2800):
    """Paluba: morsky horizont za nou, drevene dosky pod nohami."""
    hz = y - 300
    waves = "".join(f'<path d="M{x},{hz + 46 + (i % 3) * 52} q24,-13 48,0 q24,13 48,0" stroke="{PAPER}" '
                    f'stroke-width="6" fill="none" stroke-linecap="round"/>'
                    for i, x in enumerate(range(x0 + 120, x1, 330)))
    sea = (f'<path d="M{x0},{hz} H{x1} V{y} H{x0} Z" fill="{WATER}" stroke="none" opacity="0.85"/>'
           f'<path d="M{x0},{hz} H{x1}" stroke="{INK}" stroke-width="8" fill="none"/>{waves}')
    planks = "".join(f'<path d="M{x0},{y + 54 + i * 74} H{x1}" stroke="#8a6a3a" stroke-width="6" '
                     f'fill="none" opacity="0.5"/>' for i in range(9))
    # skary sa zbiehaju k stredu = perspektiva paluby, inak je to len hneda plocha
    seams = "".join(f'<path d="M{540 + (x - 540) * 0.34:.0f},{y + 4} L{x},{y + 700}" stroke="#8a6a3a" '
                    f'stroke-width="6" fill="none" opacity="0.45"/>' for x in range(x0, x1, 300))
    return (f'{sea}<path d="M{x0},{y} H{x1} V4200 H{x0} Z" fill="#c9a97a" stroke="{INK}" '
            f'stroke-width="9" stroke-linejoin="round"/>{planks}{seams}')


def water_top(y=GY, x0=-1800, x1=2800):
    """Hladina ako povrch zaberu: rekvizita na nej stoji, pod nou je voda."""
    waves = "".join(f'<path d="M{x},{y + 70 + (i % 4) * 96} q28,-15 56,0 q28,15 56,0" stroke="{PAPER}" '
                    f'stroke-width="8" fill="none" stroke-linecap="round"/>'
                    for i, x in enumerate(range(x0 + 140, x1, 300)))
    hz = y - 250
    band = (f'<path d="M{x0},{hz} H{x1} V{y} H{x0} Z" fill="#a9d6e8" stroke="none" opacity="0.7"/>'
            f'<path d="M{x0},{hz} H{x1}" stroke="{INK}" stroke-width="7" fill="none"/>')
    return (f'{band}<path d="M{x0},{y} H{x1} V4200 H{x0} Z" fill="{WATER}" stroke="{INK}" '
            f'stroke-width="9"/>{waves}')


SUBM = 64          # o kolko je trup ponoreny pod hladinou v hladinovych zaberoch


def water_front(x0, x1, y=GY):
    """Vodna clona PRED rekvizitou: prekryje jej spodok, takze objekt v nej sedi,
    nie na nej. Kresli sa az za rekvizitou, preto to nejde spravit v ground()."""
    waves = "".join(f'<path d="M{x},{y + 26 + (i % 2) * 40} q26,-14 52,0 q26,14 52,0" stroke="{PAPER}" '
                    f'stroke-width="8" fill="none" stroke-linecap="round"/>'
                    for i, x in enumerate(range(int(x0) + 30, int(x1), 190)))
    return (f'<path d="M{x0:.0f},{y} H{x1:.0f} V{y + 420} H{x0:.0f} Z" fill="{WATER}" stroke="none"/>'
            f'<path d="M{x0:.0f},{y} H{x1:.0f}" stroke="{INK}" stroke-width="9" fill="none" '
            f'stroke-linecap="round"/>{waves}')


def ground(y=GY, x0=-1800, x1=2800, wave=True):
    if SURFACE == "deck":
        return deck(y, x0, x1)
    if SURFACE == "water":
        return water_top(y, x0, x1)
    if wave:
        d = (f'M{x0},{y + 30} Q{x0 / 2},{y - 16} 200,{y} T1400,{y - 12} T{x1},{y + 14} L{x1},4200 L{x0},4200 Z')
    else:
        d = f'M{x0},{y} H{x1} V4200 H{x0} Z'
    return f'<path d="{d}" fill="{DIRT}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'


def far_ridge(y=1150):
    return (f'<path d="M-900,{y + 20} Q-400,{y - 140} 100,{y} T1100,{y - 40} T2100,{y + 10}" '
            f'fill="none" stroke="#a39d8f" stroke-width="7" stroke-linecap="round"/>')


def deck_props(seed, y=GY):
    """Drobnosti na palube namiesto travy a kamienkov: zvinute lano, vedro, uzol."""
    r = random.Random(seed)
    x1 = -560 + r.randrange(0, 200)
    x2 = 1180 + r.randrange(0, 240)
    rope = (f'<path d="{ell(x1, y - 24, 78, 30)}" fill="none" stroke="#8a6a3a" stroke-width="9"/>'
            f'<path d="{ell(x1, y - 30, 48, 18)}" fill="none" stroke="#8a6a3a" stroke-width="8"/>')
    pail = (f'<path d="M{x2 - 44},{y - 96} h88 l-13,96 h-62 z" fill="{PAPER}" stroke="{INK}" '
            f'stroke-width="8" stroke-linejoin="round"/>'
            f'<path d="M{x2 - 44},{y - 96} q44,-58 88,0" fill="none" stroke="{INK}" stroke-width="7"/>')
    return rope + pail


def dressing(seed, y=GY, xs=(-700, -260, 260, 900, 1500)):
    if SURFACE == "deck":
        return deck_props(seed, y)
    if SURFACE == "water":
        return "".join(W.foam(x, y + 40 + (i % 3) * 78, i) for i, x in enumerate(range(-800, 2200, 280)))
    return "".join(grass(x, y + 3) for x in xs) + pebbles(seed, 34, -900, 2000, y + 50, 2500)


def ghosts(p):
    """Duchovia zasypanych objektov pod zemou - hook v prvom zabere aj koncovka slucky."""
    cx, cy = 330, 1530
    out = (f'<path id="{p}_g0" class="pen" pathLength="1" d="{ell(cx, cy, 200, 62)}" fill="none" stroke="{GH}" stroke-width="8"/>'
           f'<path id="{p}_g1" class="pen" pathLength="1" d="{ell(cx, cy + 40, 390, 120)}" fill="none" stroke="{GH}" stroke-width="8"/>')
    for k, (dx, dy, h, w) in enumerate(((0, -14, 132, 46), (-170, 6, 108, 40), (172, 4, 112, 40),
                                        (-330, 74, 92, 34), (334, 70, 96, 34), (-78, 96, 84, 32), (96, 100, 86, 32))):
        x, y = cx + dx, cy + dy
        out += (f'<path id="{p}_gp{k}" class="pen" pathLength="1" d="M{x - w / 2:.0f},{y:.0f} V{y - h + 22:.0f} '
                f'Q{x:.0f},{y - h:.0f} {x + w / 2:.0f},{y - h + 24:.0f} V{y:.0f}" fill="none" stroke="{GH}" '
                f'stroke-width="8" stroke-linejoin="round"/>')
    return f'<g id="{p}_ghost" opacity="0">{out}</g>'


def gold_layer(p, gold, fallback_word):
    """Zlate 3D cislo/slovo ako fixna vrstva nad scenou (mimo kamery)."""
    if not gold:
        return ""
    if "items" in gold:
        return "".join(f'<g id="{p}_w{i}" opacity="0">{num3d(p + "_wn" + str(i), t, fit_size(t, 116, 980))}</g>'
                       for i, t in enumerate(gold["items"][:3]))
    if "count" in gold:
        unit = gold.get("unit", "")
        seed = "0" + (" " + unit if unit else "")
        return f'<g id="{p}_cnt" opacity="0">{num3d(p + "_num", seed, 168)}</g>'
    txt = str(gold.get("text") or fallback_word or "").strip()
    if not txt:
        return ""
    return f'<g id="{p}_cnt" opacity="0">{num3d(p + "_num", txt, fit_size(txt, 210, 940))}</g>'


def fit_size(txt, want, maxw):
    """Zmensi pismo tak, aby sa text zmestil do maxw (hruby odhad sirky Comic Neue Bold)."""
    n = max(1, len(str(txt)))
    return int(min(want, maxw / (0.62 * n)))


def fit_scale(pw, ph, maxw, maxh, cap=2.4):
    """Mierka rekvizity tak, aby sa zmestila do (maxw x maxh) - musi brat oboje, inak siroke
    rekvizity (truhla, auto) preliezu cez cely zaber."""
    return min(cap, maxw / max(120.0, float(pw)), maxh / max(140.0, float(ph)))


_STOP = {"the", "a", "an", "of", "to", "by", "in", "on", "and", "it", "its", "than", "is", "was", "were",
         "that", "this", "these", "those", "with", "for", "from", "older", "years", "year", "ago", "about"}


def _last_noun(text):
    """Popisok pre neutralny milnik. Vlastne meno (Stonehenge, Gutenberg) ma prednost -
    inak by z vety "predates Stonehenge by six thousand years" vysiel popisok "thousand"."""
    raw = [x.strip(" ,.;:!?'\"") for x in (text or "").split()]
    caps = [x for x in raw[1:] if x[:1].isupper() and x.lower() not in _STOP and len(x) > 3]
    if caps:
        return caps[-1]
    for x in reversed([r.lower() for r in raw]):
        if x and x not in _STOP and not x.isdigit() and len(x) > 2:
            return x
    return ""


# rekvizity, ktore davaju zmysel ako "krajinny orientacny bod" na kopci v prvom zabere
LANDMARKS = ("pillar", "stone", "statue", "tower", "ruin", "cave", "door", "tree", "forest", "mountain", "tunnel")
# rekvizity, ktore znesu opakovanie v poli/kruhoch (jednoduchy obrys); ostatne sa nahradia markerom
REPEATABLE = ("pillar", "stone", "statue", "tower", "tree", "coin", "skull", "tablet")


def wrap2(text, per=15):
    """Rozdeli vetu na max 2 vyvazene riadky velkych pismen."""
    w = text.upper().replace("—", " ").split()
    if not w:
        return ["?"]
    best, bi = 10 ** 9, 1
    for i in range(1, len(w)):
        a, b = len(" ".join(w[:i])), len(" ".join(w[i:]))
        if max(a, b) <= per and abs(a - b) < best:
            best, bi = abs(a - b), i
    if best == 10 ** 9:                       # nezmesti sa -> rozdel na polovicu
        bi = max(1, len(w) // 2)
    return [" ".join(w[:bi]), " ".join(w[bi:])] if len(w) > 1 else [w[0]]


def js_gold(p, c, at, scene_cam=None, gy=560, ramp=None):
    """JS pre zlaty prvok (staticky text / count-up / tri slamy)."""
    g = c["gold"]
    if not g:
        return ""
    if "items" in g:
        js, items = "", g["items"][:3]
        n = len(items)
        span = max(0.22, (c["t1"] - at - 0.25) / max(1, n))
        for i in range(n):
            t = at + i * span
            js += (f'var w{i} = node("{p}_w{i}", {{ x: 540, y: 700, s: 0, o: 0, r: {(i - 1) * 3} }});\n'
                   f'slamIn(w{i}, {t:.3f});\n')
            if scene_cam:
                js += f'shake({scene_cam}, {t:.3f}, 22, 0.32);\n'
            if i < n - 1:
                js += f'unpop(w{i}, {t + span - 0.10:.3f}, 0.14);\n'
        return js
    if "count" in g:
        val, unit = float(g["count"]), g.get("unit", "")
        dec = 1 if abs(val - round(val)) > 1e-6 else 0
        u = (' + " ' + unit + '"') if unit else ""
        fmt = f'function (v) {{ return numEN(v, {dec}){u}; }}'
        step = "" if dec else (" / 100) * 100" if val >= 900 else "")
        rounder = f'Math.round(v{step})' if step else "v"
        return (f'var cnt = node("{p}_cnt", {{ x: 540, y: {gy}, s: 0, o: 0, r: -3 }}), '
                f'cv = n3("{p}_num", {fmt.replace("numEN(v", "numEN(" + rounder)});\n'
                f'slamIn(cnt, {at:.3f}, 1.9, 1, 0.22);\n'
                f'tl.fromTo(cv, {{ v: 0 }}, {{ v: {val}, duration: {ramp or 0.52:.2f}, ease: "power2.out", immediateRender: false }}, {at:.3f});\n'
                # viac rozmerov v jednej vete: cislo preklikne presne na dalsich cislach,
                # inak visi zamrznute na prvom, kym hlas hovori ostatne
                + "".join(f'tl.to(cv, {{ v: {sv}, duration: 0.16, ease: "power2.out" }}, {stp:.3f});\n'
                          f'tl.to(cnt, {{ s: 1.14, duration: 0.07 }}, {stp:.3f}); '
                          f'tl.to(cnt, {{ s: 1, duration: 0.18, ease: "back.out(3)" }}, {stp + 0.07:.3f});\n'
                          for stp, sv in (c.get("steps") or []) if stp > at + 0.25)
                + (f'shake({scene_cam}, {at:.3f}, 20, 0.34);\n' if scene_cam else ""))
    return (f'var cnt = node("{p}_cnt", {{ x: 540, y: {gy}, s: 0, o: 0, r: -3 }});\n'
            f'slamIn(cnt, {at:.3f}, 2.1, 1, 0.24);\n'
            f'tl.to(cnt, {{ r: 2.5, duration: 0.6, ease: "elastic.out(1.1,0.28)" }}, {at + 0.24:.3f});\n'
            + (f'shake({scene_cam}, {at:.3f}, 22, 0.36);\n' if scene_cam else ""))


def pkey(c):
    """Kluc rekvizity pre kresbu: variant pohladu, ak ho build pridelil."""
    return c.get("view_prop") or c["prop"]


def puff_ids(p, n):
    return "".join(f'<g id="{p}_pf{i}" opacity="0">{PUFF}</g>' for i in range(n))


# ================================================================== 1) walk_in  (aj uzatvaraci zaber slucky)
def hill_world(p, rigid, prop, with_ghost=True, loop_cls=False, world="hill", hero="archaeologist"):
    """Uvodny a slucku uzatvarajuci zaber. Profil terenu, vypln, pozadie aj "duchovia"
    sa riadia spec["world"], takze pribeh o potapacoch sa uz neotvara travnatou lukou."""
    kind = W.world_kind(world)
    hy, js_ter = W.terrain(kind)
    st = W.STYLE[kind]
    pts = " ".join(f"L{x},{hy(x):.1f}" for x in range(-600, 2600, 40))
    surf = f'<path d="M-600,3200 {pts} L2600,3200 Z" fill="{st["fill"]}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
    sub = ""
    if st["sub"]:
        f0 = st["sub_from"]
        pts2 = " ".join(f"L{x},{hy(x) + f0:.1f}" for x in range(-600, 2600, 40))
        sub = (f'<path d="M-600,3200 {pts2} L2600,3200 Z" fill="{st["sub"]}" stroke="none" opacity="0.55"/>'
               f'<path d="M-600,{hy(-600) + f0:.0f} {pts2[1:]}" fill="none" stroke="{INK}" stroke-width="6" opacity="0.5"/>')
    gr = "".join(grass(x, hy(x) + 2) for x in (-40, 230, 520, 700, 940, 1230, 1560, 1700, 1960)) if st["grass"] else ""
    peb = pebbles(3, 40 if kind != "snow" else 22, -300, 2300, 1000, 2300, avoid=lambda x, y: y < hy(x) + 60)
    deco = (bone(760, 1560, 20) + bone(1500, 1250, -30, 0.9)) if kind in ("hill", "desert") else ""
    if kind == "sea":
        # Na otvorenom mori nie je po com kracat: hrdinu nesie lod. Trup sa kresli
        # PRED hladinou, takze ho voda dolu prekryje a lod naozaj sedi vo vode.
        shipsvg, _sw, _sh = prop_svg(p + "_shipp", "ship")
        ship = f'<g id="{p}_ship"><g transform="scale(1.15)">{shipsvg}</g></g>'
        fm = "".join(W.foam(x, hy(x) + 34 + (i % 4) * 58, i)
                     for i, x in enumerate(range(-560, 2400, 210)))
        surf_w = surf.replace('stroke-width="9"', 'stroke-width="9" opacity="0.88"')
        body = (f'{W.world_far(p, kind)}{sun(p + "_rays", 880, 330, "sunray2" if loop_cls else "sunray")}'
                f'<g id="{p}_cam">{ship}{surf_w}{sub}{fm}'
                f'{W.ghosts(p, kind) if with_ghost else ""}'
                f'{puff_ids(p, 10)}{W.hero_rig(rigid, hero)}</g>')
        return body, hy, False, js_ter
    show = prop in LANDMARKS and kind != "shore"
    psvg, pw, ph = prop_svg(p + "_prop", prop if show else "stone")
    scl = fit_scale(pw, ph, 560, 620, 1.25)
    body = (f'{W.world_far(p, kind)}{sun(p + "_rays", 880, 330, "sunray2" if loop_cls else "sunray")}'
            f'<g id="{p}_cam">{surf}{sub}{gr}{peb}{deco}'
            f'{W.ghosts(p, kind) if with_ghost else ""}'
            f'<g id="{p}_propwrap" opacity="0">'
            + (f'<g transform="translate(1470,{hy(1470):.0f}) scale({scl:.3f})">{psvg}</g>' if show else "")
            + f'</g>{puff_ids(p, 10)}{W.hero_rig(rigid, hero)}</g>')
    return body, hy, show, js_ter


def shot_walk_in(p, c):
    body, hy, show, jter = hill_world(p, c["bob"], c["prop"], with_ghost=c["first"],
                                      world=c.get("world"), hero=c.get("hero"))
    svg = svg_wrap(body + gold_layer(p, c["gold"], c["words"][0]["w"] if c["words"] else ""))
    t0, t1 = c["t0"], c["t1"]
    D = t1 - t0
    AV = 1200.0 / max(0.8, D)
    sea = W.world_kind(c.get("world")) == "sea"
    SH = f', "{p}_ship"' if sea else ""
    WALK = ("" if sea else
            "tl.set(rg, { w: 1, wa: 1, ph: PH0 }, %.3f);%s"
            "tl.to(rg, { ph: PH0 + OM * %.3f, duration: %.3f, ease: \"none\" }, %.3f);%s"
            % (t0, "\n", D, D, t0, "\n"))
    if sea:
        WALK = ("tl.set(rg, { w: 0, lean: 7 }, %.3f);\n"
                "setPose(rg, { aL: 118, aL2: 58, aR: -128, aR2: -60, head: 8 }, %.3f);\n" % (t0, t0))
    js = f'''var H = HillShot("{p}", "{c['bob']}", function () {{ return -(CLK.t - {t0:.3f}) * 22; }}, function (x) {{ return {jter}; }}{SH});
var rg = H.rig, cam = H.cam;
{WALK}tl.fromTo(cam, {{ bx: 100, lead: 120, z: 1.68 }}, {{ bx: 1300, duration: {D:.3f}, ease: "none", immediateRender: false }}, {t0:.3f});
tl.to(cam, {{ z: 1.06, lead: 210, duration: {D * 0.42:.3f}, ease: "power2.inOut" }}, {t0:.3f});
tl.to(cam, {{ z: 1.3, lead: 175, duration: {D * 0.58:.3f}, ease: "none" }}, {t0 + D * 0.42:.3f});
'''
    if c["first"]:
        js += (f'tl.set(H.ghost, {{ o: 1 }}, 0);\n'
               f'tl.to(H.ghost, {{ o: 0, duration: 0.42, ease: "power2.in" }}, 0.68);\n')
    for k in range(1, 9):
        tk = t0 + k * math.pi / (math.pi * 1.9)
        if sea or tk > t1 - 0.12 or k > 9:
            break
        x = 100 + AV * (tk - t0) - 25
        js += (f'(function(){{var n = node("{p}_pf{k - 1}", {{ o: 0 }});'
               f'tl.fromTo(n, {{ x: {x:.0f}, y: {hy(x) - 8:.0f}, s: 0.35, o: 0.95 }}, '
               f'{{ x: {x - 46:.0f}, y: {hy(x) - 40:.0f}, s: 1.35, o: 0, duration: 0.5, ease: "power1.out", immediateRender: false }}, {tk:.3f});}})();\n')
    # rekvizita vyrastie zo zeme pred nim
    pr = max(c["cue_t"], t0 + D * 0.55)
    if show and not sea:
        js += (f'var pw = node("{p}_propwrap", {{ o: 0 }});\n'
               f'tl.set(pw, {{ o: 1 }}, {pr - 0.001:.3f});\n'
               f'tl.fromTo(pw, {{ sy: 0.02, y: 0 }}, {{ sy: 1, duration: 0.34, ease: "back.out(2.2)", immediateRender: false }}, {pr:.3f});\n'
               f'pose(rg, {{ head: -12, lean: 10 }}, {pr + 0.1:.3f}, 0.2);\n')
    js += js_gold(p, c, c["cue_t"], "cam")
    if c["gold"]:
        js += f'unpop(cnt, {min(t1 - 0.12, c["cue_t"] + 1.25):.3f}, 0.2);\n'
    return svg, js


# ================================================================== 2) spot
def shot_spot(p, c):
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    rep = int(c.get("rep", 0))
    scl = fit_scale(pw, ph, 600, 720, 2.0) * (1.0, 0.82, 1.14)[rep % 3]
    body = (f'{sky(p, (930, 250))}<g id="{p}_cam">{ground()}{dressing(21)}'
            f'<g transform="translate({720 + (rep % 3) * 90},{GY}) scale({scl:.3f})">{psvg}</g>'
            f'{W.hero_rig(c["bob"], c.get("hero"))}<g id="{p}_spark" opacity="0">{SPARK}</g>'
            f'<g id="{p}_q" opacity="0"><text x="0" y="0" class="hand" font-size="190" fill="{RED}" text-anchor="middle">!</text></g></g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    js = f'''var cam = GCam("{p}_cam", {GY}, {{ x: 520, z: 1.0, up: 330 }});
var rg = Rig("{c['bob']}", {{ s: 1.4, x: 300, y: {GY}, idle: 1, seed: 3, eye: 0.6 }});
tl.fromTo(cam, {{ x: 540, z: 0.92 }}, {{ x: 626, z: 1.16, duration: {t1 - t0:.3f}, ease: "power1.inOut", immediateRender: false }}, {t0:.3f});
setPose(rg, POINT, {t0:.3f});
tl.set(rg, {{ eye: 1, mo: 1 }}, {cu:.3f});
pose(rg, {{ head: -26, lean: -6, aL: 158, aL2: 16 }}, {cu:.3f}, 0.16);
tl.to(rg, {{ oy: -30, duration: 0.10, ease: "power2.out" }}, {cu:.3f});
tl.to(rg, {{ oy: 0, duration: 0.16, ease: "bounce.out" }}, {cu + 0.10:.3f});
var q = node("{p}_q", {{ x: 320 + 130, y: {GY - 560}, s: 0, o: 0 }});
pop(q, {cu:.3f}, 0.3, 3.5);
tl.to(q, {{ r: 10, duration: 0.5, ease: "sine.inOut", repeat: 1, yoyo: true }}, {cu + 0.1:.3f});
var sp = node("{p}_spark", {{ x: 720, y: {GY - int(ph * scl * 0.7)}, s: 0, o: 0 }});
pop(sp, {cu + 0.06:.3f}, 0.2, 4);
tl.to(sp, {{ o: 0, r: 40, s: 1.5, duration: 0.3 }}, {cu + 0.28:.3f});
shake(cam, {cu:.3f}, 12, 0.26);
'''
    js += js_gold(p, c, cu, "cam")
    return svg, js


# ================================================================== 3) dig
def shot_dig(p, c):
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    scl = fit_scale(pw, ph, 520, 560, 1.3)
    clumps = "".join(f'<g id="{p}_cl{i}" opacity="0">{CLOD}</g>' for i in range(8))
    digs = "".join(f'<g id="{p}_dig{i}" opacity="0"><text class="hand" font-size="96" fill="{RED}" text-anchor="middle">{t}</text></g>'
                   for i, t in enumerate(("dig!", "DIG!")))
    pile = (f'<g id="{p}_pile"><path d="M-150,0 Q-70,-120 0,-132 Q80,-120 160,0 Z" fill="{DIRT}" stroke="{INK}" stroke-width="8" stroke-linejoin="round"/>'
            f'<path d="M-40,-60 l20,-8 M20,-80 l18,6" stroke="{DIRT2}" stroke-width="5" stroke-linecap="round"/></g>')
    body = (f'{sky(p, (250, 260), ((760, 330, 0.9),))}<g id="{p}_cam">'
            f'<g id="{p}_propwrap" opacity="0"><g transform="translate(760,{GY}) scale({scl:.3f})">{psvg}</g></g>'
            f'<path id="{p}_dirt" d="M0,0" fill="{DIRT}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
            f'{dressing(8)}{pile}{W.hero_rig(c["bob"], c.get("hero"), SHOVEL)}{clumps}{digs}</g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    st1, st2 = t0 + 0.08, t0 + 0.46
    js = f'''var rg = Rig("{c['bob']}", {{ s: 1.35, x: 380 }});
var S = ctl({{ depth: 60, cx: 520, z: 1.2, shy: 0 }}, function (st) {{
  var dp = {GY} + st.depth; rg.y = dp;
  $("{p}_dirt").setAttribute("d", "M-900,{GY} L262,{GY} L280," + dp + " L1010," + dp + " L1028,{GY} L2000,{GY} L2000,4200 L-900,4200 Z");
  camSet("{p}_cam", st.cx, dp - 330 / st.z + st.shy, st.z);
}});
setPose(rg, DIG_B, {t0 - 0.01:.3f});
var pile = node("{p}_pile", {{ x: 150, y: {GY + 2}, s: 0.4 }});
var pwp = node("{p}_propwrap", {{ o: 0 }});
tl.to(S, {{ z: 1.34, duration: {t1 - t0:.3f}, ease: "none" }}, {t0:.3f});
'''
    for i, ts in enumerate((st1, st2)):
        if ts > t1 - 0.1:
            break
        js += f'''pose(rg, DIG_A, {ts - 0.09:.3f}, 0.09, "power2.in");
tl.to(S, {{ depth: {150 + i * 110}, duration: 0.15, ease: "power2.out" }}, {ts:.3f});
shake(S, {ts:.3f}, 12, 0.18);
(function(){{var dg = node("{p}_dig{i}", {{ x: {660 if i else 600}, y: {GY - (440 if i else 320)}, r: {8 if i else -12}, s: 0, o: 0 }});
pop(dg, {ts:.3f}, 0.15, 4); tl.to(dg, {{ o: 0, y: "-=40", duration: 0.18 }}, {ts + 0.22:.3f});}})();
pose(rg, DIG_B, {ts + 0.12:.3f}, 0.16, "power2.out");
tl.to(pile, {{ s: {0.58 + i * 0.16}, duration: 0.14, ease: "back.out(3)" }}, {ts + 0.5:.3f});
'''
        for k in range(4):
            js += (f'ball("{p}_cl{i * 4 + k}", {350 - k * 12}, {GY + 150 + i * 110 - 470}, {-330 - k * 95}, {-1050 + k * 90}, 2900, '
                   f'{ts + 0.18 + k * 0.015:.3f}, 0.7, {300 - k * 140});\n')
    rev = max(cu, st2 + 0.18)
    js += (f'tl.set(pwp, {{ o: 1 }}, {rev - 0.001:.3f});\n'
           f'tl.fromTo(pwp, {{ sy: 0.02 }}, {{ sy: 1, duration: 0.38, ease: "back.out(2.0)", immediateRender: false }}, {rev:.3f});\n'
           f'shake(S, {rev + 0.1:.3f}, 18, 0.34);\n'
           f'pose(rg, {{ lean: -14, aL: 40, aL2: 20, aR: -40, aR2: 20, head: -26, eye: 1, mo: 1 }}, {rev + 0.06:.3f}, 0.2);\n')
    js += js_gold(p, c, cu, "S")
    return svg, js


# ================================================================== 4) descend
def shot_descend(p, c):
    m = 420
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    scl = fit_scale(pw, ph, 400, 420, 1.0)
    shaft = (f'<path d="M620,-200 h300 V3900 h-300 Z" fill="{STONE}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
             + "".join(f'<path d="M{700 + (k % 3) * 60},{120 + k * 300} l60,-54" stroke="{SHADE}" stroke-width="6" fill="none"/>' for k in range(13)))
    dirt = f'<path d="M-900,0 H300 L318,3900 H1260 L1278,0 H2000 V4400 H-900 Z" fill="{DIRT}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
    marks = "".join(f'<path d="M322,{k * m} h-56" stroke="{INK}" stroke-width="8" stroke-linecap="round" fill="none"/>'
                    f'<text x="194" y="{k * m + 22}" class="hand" font-size="60" text-anchor="middle" fill="{INK}" '
                    f'transform="rotate({(-6, 4, -3, 5, -5, 3, -4, 5)[(k - 1) % 8]} 194 {k * m})">{k} m</text>'
                    for k in range(1, 9))
    lines = "".join(f'<g><path d="M{x},0 v{l}" stroke="{INK}" stroke-width="5" stroke-linecap="round" opacity="0.5"/></g>'
                    for x, l in ((150, 150), (250, 90), (430, 170), (500, 110), (960, 140), (1040, 80), (120, 60)))
    body = (f'<g id="{p}_cam">{shaft}{dirt}{marks}'
            f'<g transform="translate(770,-40) scale({scl:.3f})">{psvg}</g>'
            f'{pebbles(6, 16, 60, 280, 60, 3400)}{bone(180, 900, 25, 0.9)}{bone(160, 2100, -20, 0.9)}'
            f'{W.hero_rig(c["bob"], c.get("hero"))}'
            f'<g id="{p}_aa"><text class="hand" font-size="84" fill="{RED}" text-anchor="start" transform="rotate(-78)">AAAAAH!</text></g></g>'
            f'<g id="{p}_lines" opacity="0">{lines}</g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1 = c["t0"], c["t1"]
    js = f'''var rg = Rig("{c['bob']}", {{ s: 1.3, x: 470, aL: 171, aL2: 8, aR: 187, aR2: -8, eye: 1, mo: 1, w: 1, A: 40, lean: 4, head: -12 }});
var aa = node("{p}_aa", {{}});
var S = ctl({{ cy: 300, off: -170, sp: 0 }}, function (st) {{
  var t = CLK.t, by = st.cy + st.off;
  camSet("{p}_cam", 540 + 5 * Math.sin(t * 31), st.cy, 1);
  rg.y = by; rg.ox = 7 * Math.sin(t * 19);
  rg.haty = -52 - 14 * Math.sin(t * 23); rg.hatr = -16 + 9 * Math.sin(t * 17); rg.hatx = -6;
  aa.x = 600; aa.y = by - 230; aa.sy = 1 + 0.5 * (st.cy - 300) / 1100; aa.r = 3 * Math.sin(t * 27);
  $("{p}_lines").setAttribute("opacity", Math.max(0, st.sp).toFixed(3));
  var L = $("{p}_lines").children;
  for (var i = 0; i < L.length; i++) {{
    var y = ((i * 397 - t * 3000) % 2300 + 2300) % 2300 - 190;
    L[i].setAttribute("transform", "translate(0," + y.toFixed(1) + ")");
  }}
}});
tl.fromTo(S, {{ cy: 300 }}, {{ cy: 2600, duration: {t1 - t0:.3f}, ease: "power1.in", immediateRender: false }}, {t0:.3f});
tl.fromTo(S, {{ off: -170 }}, {{ off: 330, duration: {t1 - t0:.3f}, ease: "power1.in", immediateRender: false }}, {t0:.3f});
tl.fromTo(S, {{ sp: 0 }}, {{ sp: 0.9, duration: 0.3, ease: "power2.out", immediateRender: false }}, {t0 + 0.1:.3f});
tl.to(S, {{ sp: 0, duration: 0.25, ease: "power2.in" }}, {t1 - 0.3:.3f});
tl.fromTo(rg, {{ ph: 0 }}, {{ ph: 34, duration: {t1 - t0:.3f}, ease: "none", immediateRender: false }}, {t0:.3f});
'''
    js += js_gold(p, c, c["cue_t"], None)
    return svg, js


# ================================================================== 5) scale_measure
def _scale_h(p, c, psvg, scl, pw, ph):
    """Dlzka/sirka/rozpatie = VODOROVNA kota pod objektom. Zvisla sipka na 103 stop
    dlzky lode vyzerala ako vyska staziara."""
    w = pw * scl
    cx = 560
    x0, x1 = cx - w / 2, cx + w / 2
    # na hladine musi kota lezat NAD vodou, inak je cela cervena sipka pod ciarou
    yy = (GY - 34) if SURFACE == "water" else (GY + 92)
    arrow = (f'<path id="{p}_arrow" class="pen" pathLength="1" d="M{x0:.0f},{yy} C{(x0 + cx) / 2:.0f},{yy - 10} '
             f'{(cx + x1) / 2:.0f},{yy + 10} {x1:.0f},{yy}" fill="none" stroke="{RED}" stroke-width="10" stroke-linecap="round"/>')
    ah = lambda pid, left: (f'<g id="{pid}" opacity="0"><path d="M{30 if left else -30},-26 L0,0 L{30 if left else -30},26" '
                            f'fill="none" stroke="{RED}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>'
                            f'<path d="M{4 if left else -4},-34 v68" stroke="{RED}" stroke-width="8" stroke-linecap="round"/></g>')
    sub = SUBM if SURFACE == "water" else 0
    body = (f'{sky(p, (200, 250), ((820, 300, 0.8),))}<g id="{p}_cam">{ground()}{dressing(12)}'
            f'<g transform="translate({cx},{GY + sub}) scale({scl:.3f})">{psvg}</g>'
            + (water_front(x0 - 70, x1 + 70) if sub else "")
            + f'{arrow}{ah(p + "_ah0", True)}{ah(p + "_ah1", False)}{W.hero_rig(c["bob"], c.get("hero"))}</g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    draw = max(0.45, min(0.9, t1 - cu - 0.3))
    js = f'''var cam = GCam("{p}_cam", {GY}, {{ x: 560, z: 0.94, up: 300 }});
var rg = Rig("{c['bob']}", {{ s: 1.05, x: {x1 + 150:.0f}, y: {GY}, idle: 1, seed: 4, eye: 0.7 }});
tl.fromTo(cam, {{ z: 1.00, x: 540 }}, {{ z: 0.88, x: 572, duration: {t1 - t0:.3f}, ease: "power1.inOut", immediateRender: false }}, {t0:.3f});
setPose(rg, POINT, {t0:.3f});
var arrow = pen("{p}_arrow"), ah0 = node("{p}_ah0", {{ x: {x0:.0f}, y: {yy}, s: 0, o: 0 }}), ah1 = node("{p}_ah1", {{ x: {x1:.0f}, y: {yy}, s: 0, o: 0 }});
pop(ah0, {cu - 0.03:.3f}, 0.20, 1.4);
tl.to(arrow, {{ d: 1, duration: {draw:.3f}, ease: "power1.inOut" }}, {cu:.3f});
pop(ah1, {cu + draw:.3f}, 0.20, 1.6);
pose(rg, {{ aL: 196, aL2: 10, head: 26, lean: 6 }}, {cu:.3f}, 0.2);
'''
    js += js_gold(p, c, cu, "cam", gy=430, ramp=c.get("ramp"))
    if c["gold"]:
        js += f'unpop(cnt, {min(t1 - 0.10, cu + (c.get("ramp") or 0.52) + 0.55):.3f}, 0.18);\n'
    return svg, js


def shot_scale(p, c):
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    scl = fit_scale(pw, ph, 520, 640, 2.4)
    ptop = GY - ph * scl
    ax = 620 + pw * scl / 2 + 86           # kota vzdy VEDLA rekvizity, nie cez nu
    # viac rozmerov v jednej vete -> tri koty vedla seba, kazda sa nakresli na svojom cisle
    dims = _dims(c)
    if dims:
        return _scale_multi(p, c, psvg, scl, ptop, ax, dims)
    if ((c.get("gold") or {}).get("axis") or "v").lower() == "h":
        return _scale_h(p, c, psvg, scl, pw, ph)
    arrow = (f'<path id="{p}_arrow" class="pen" pathLength="1" d="M{ax},{GY - 6} C{ax - 10},{(GY + ptop) / 2} {ax + 10},{(GY + ptop) / 2} {ax - 2},{ptop + 6}" '
             f'fill="none" stroke="{RED}" stroke-width="10" stroke-linecap="round"/>')
    ah = lambda pid, up: (f'<g id="{pid}" opacity="0"><path d="M-26,{30 if up else -30} L0,0 L26,{30 if up else -30}" fill="none" '
                          f'stroke="{RED}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>'
                          f'<path d="M-34,{-4 if up else 4} h68" stroke="{RED}" stroke-width="8" stroke-linecap="round"/></g>')
    body = (f'{sky(p, (200, 250), ((820, 300, 0.8),))}<g id="{p}_cam">{ground()}{dressing(12)}'
            f'<g transform="translate(620,{GY}) scale({scl:.3f})">{psvg}</g>'
            f'{arrow}{ah(p + "_ah0", False)}{ah(p + "_ah1", True)}{W.hero_rig(c["bob"], c.get("hero"))}</g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    draw = max(0.45, min(0.9, t1 - cu - 0.3))
    js = f'''var cam = GCam("{p}_cam", {GY}, {{ x: 600, z: 0.98, up: 330 }});
var rg = Rig("{c['bob']}", {{ s: 1.25, x: 180, y: {GY}, idle: 1, seed: 4, eye: 0.7 }});
tl.fromTo(cam, {{ z: 1.04, x: 580 }}, {{ z: 0.92, x: 612, duration: {t1 - t0:.3f}, ease: "power1.inOut", immediateRender: false }}, {t0:.3f});
setPose(rg, POINT, {t0:.3f});
var arrow = pen("{p}_arrow"), ah0 = node("{p}_ah0", {{ x: {ax:.0f}, y: {GY - 6}, s: 0, o: 0 }}), ah1 = node("{p}_ah1", {{ x: {ax - 2:.0f}, y: {ptop + 6:.0f}, s: 0, o: 0 }});
pop(ah0, {cu - 0.03:.3f}, 0.20, 1.4);
tl.to(arrow, {{ d: 1, duration: {draw:.3f}, ease: "power1.inOut" }}, {cu:.3f});
pop(ah1, {cu + draw:.3f}, 0.20, 1.6);
pose(rg, {{ aL: 166, aL2: 4, head: -30, lean: -6 }}, {cu:.3f}, 0.2);
'''
    js += js_gold(p, c, cu, "cam", gy=430, ramp=c.get("ramp"))
    if c["gold"]:
        js += f'unpop(cnt, {min(t1 - 0.10, cu + (c.get("ramp") or 0.52) + 0.55):.3f}, 0.18);\n'
    return svg, js


# ================================================================== 6) human_stack
def shot_stack(p, c):
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    SH = 220 * 1.44
    tgt = 3 * SH + 120
    scl = fit_scale(pw, ph, 620, tgt, 2.2)
    stars = "".join(f'<g id="{p}_st{i}" opacity="0">{STAR}</g>' for i in range(3))
    nums = "".join(f'<g id="{p}_n{i}" opacity="0">{num3d(p + "_nn" + str(i), str(i + 1), 132)}</g>' for i in range(3))
    body = (f'{sky(p, (900, 270), ((240, 360, 0.85),))}<g id="{p}_cam">{ground()}{dressing(15)}'
            f'<g transform="translate(760,{GY}) scale({scl:.3f})">{psvg}</g>'
            f'{rig(p + "u1", hat=False, pack=False)}{rig(p + "u2", hat=False, pack=False)}{W.hero_rig(c["bob"], c.get("hero"))}'
            f'{stars}{nums}</g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1 = c["t0"], c["t1"]
    lands = [t0 + 0.16, t0 + (t1 - t0) * 0.42, t0 + (t1 - t0) * 0.68]
    js = f'''var P1 = Rig("{p}u1", {{ s: 1.44, o: 0, seed: 2 }}), P2 = Rig("{p}u2", {{ s: 1.44, o: 0, seed: 3 }}), P3 = Rig("{c['bob']}", {{ s: 1.44, o: 0, seed: 4 }});
var cam = GCam("{p}_cam", {GY}, {{ x: 430, z: 1.28, up: 330 }});
var SH = {SH}, SX = 260;
var STK = ctl({{ h1: 1, h2: 1, h3: 1, a: 0 }}, function (st) {{
  var t = CLK.t, w = 2 * Math.PI * 1.15, rad = Math.PI / 180;
  function hop(h, lvl) {{ return [-560 * h, lvl * SH * h - (330 + 110 * lvl) * Math.sin(Math.PI * Math.min(1, h))]; }}
  var th1 = st.a * Math.sin(w * t), th2 = th1 + st.a * 1.5 * Math.sin(w * t - 0.6), th3 = th2 + st.a * 2.0 * Math.sin(w * t - 1.2);
  var rigs = [P1, P2, P3], hs = [st.h1, st.h2, st.h3], ths = [th1, th2, th3], bx = SX, by = {GY};
  for (var i = 0; i < 3; i++) {{
    var h = hs[i], o = hop(h, i), th = h > 0 ? -35 * h : ths[i];
    rigs[i].o = h >= 1 ? 0 : 1; rigs[i].x = bx + o[0]; rigs[i].y = by + o[1]; rigs[i].rot = th;
    var thr = ths[i] * rad; bx = bx + Math.sin(thr) * SH; by = by - Math.cos(thr) * SH;
  }}
}});
var AIR = {{ lL: 58, lL2: -88, lR: 30, lR2: -70, aL: 150, aL2: 10, aR: 200, aR2: -10, eye: 0.8, mo: 1 }};
var BASE = {{ lean: 0, drop: 10, lL: 16, lL2: -26, lR: -16, lR2: -6, aL: 158, aL2: 16, aR: -158, aR2: -16, head: 0 }};
var TOP = {{ lean: 0, drop: 0, lL: 13, lL2: 0, lR: -13, lR2: 0, aL: 80, aL2: 10, aR: -80, aR2: 10, head: 0 }};
var rigs = [P1, P2, P3], hk = ["h1", "h2", "h3"], lands = [{lands[0]:.3f}, {lands[1]:.3f}, {lands[2]:.3f}], durs = [0.30, 0.28, 0.32];
rigs.forEach(function (r, i) {{
  var a0 = {{}}; for (var k in AIR) a0[k] = AIR[k]; tl.set(r, a0, lands[i] - durs[i] - 0.01);
  var f = {{}}, to = {{ duration: durs[i], ease: "none", immediateRender: false }}; f[hk[i]] = 1; to[hk[i]] = 0;
  tl.fromTo(STK, f, to, lands[i] - durs[i]);
  pose(r, {{ lean: 0, drop: 0, lL: 13, lL2: 0, lR: -13, lR2: 0, aL: 70, aL2: 10, aR: -70, aR2: 10, sq: 0.74 }}, lands[i], 0.05);
  tl.to(r, {{ sq: 1, duration: 0.45, ease: "elastic.out(1.3,0.3)" }}, lands[i] + 0.05);
  tl.set(r, {{ mo: 0, eye: 0, idle: 0.5 }}, lands[i] + 0.2);
  for (var j = 0; j < i; j++) {{ tl.to(rigs[j], {{ sq: 0.86, duration: 0.05 }}, lands[i]); tl.to(rigs[j], {{ sq: 1, duration: 0.4, ease: "elastic.out(1.4,0.3)" }}, lands[i] + 0.05); }}
  shake(cam, lands[i], 14 + i * 4, 0.3);
  var st = node("{p}_st" + i, {{ x: SX + 70, y: {GY} - i * SH - 10, s: 0, o: 0 }});
  pop(st, lands[i], 0.12, 4); tl.to(st, {{ o: 0, s: 1.6, duration: 0.2 }}, lands[i] + 0.14);
  var nn = node("{p}_n" + i, {{ x: 440, y: {GY - 90} - i * SH, s: 0, o: 0, r: (i - 1) * 5 }});
  pop(nn, lands[i] + 0.04, 0.26, 3.4);
}});
pose(P1, BASE, lands[1] - 0.04, 0.12); tl.set(P1, {{ trem: 2.2, eye: 0.9 }}, lands[1] + 0.05);
pose(P2, BASE, lands[2] - 0.04, 0.12); tl.set(P2, {{ trem: 1.2 }}, lands[2] + 0.05);
pose(P3, TOP, lands[2] + 0.12, 0.2);
tl.to(STK, {{ a: 1.2, duration: 0.3 }}, lands[1]); tl.to(STK, {{ a: 2.2, duration: 0.3 }}, lands[2]);
tl.to(cam, {{ z: 0.86, x: 470, duration: {t1 - t0:.3f}, ease: "power1.inOut" }}, {t0:.3f});
'''
    js += js_gold(p, c, c["cue_t"], "cam")
    return svg, js


# ================================================================== 7) wide_reveal
MARKER = (f'<path d="M-24,12 L-20,-74 Q0,-88 21,-72 L25,12 Z" fill="{STONE}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'
          f'<path d="M-6,-58 l8,18 l-6,14" stroke="{SHADE}" stroke-width="5" fill="none"/>')


def shot_wide(p, c):
    """Zhora: to iste sa opakuje dookola. Zlozite rekvizity (stroj, auto, mapa) by sa v 50 kopiach
    zliali na kasu - tie nahradzame jednoduchym kamennym markerom."""
    rep = c["prop"] in REPEATABLE
    psvg, pw, ph = prop_svg(p + "_x", c["prop"])
    cx, cy, sq = 540, 1010, 0.42
    rings = [(200, 7), (400, 11), (640, 15), (920, 20)]
    base = (190.0 / max(120.0, ph)) if rep else 1.0
    out = ""
    for ri, (R, n) in enumerate(rings):
        items = []
        for k in range(n):
            a = 2 * math.pi * k / n + ri * 0.21
            x = cx + R * math.cos(a)
            y = cy + R * sq * math.sin(a)
            s = base * (0.6 + 0.48 * (0.5 + 0.5 * math.sin(a)))
            items.append((y, x, s))
        items.sort()
        bodyk = "".join(
            f'<g transform="translate({x:.0f},{y:.0f}) scale({s:.3f})">'
            f'<ellipse cx="6" cy="10" rx="{34 / s:.0f}" ry="{13 / s:.0f}" fill="{DIRT2}" stroke="none" opacity="0.45"/>'
            + (prop_svg(p + "_r" + str(ri) + "_" + str(i), c["prop"])[0] if rep else MARKER) + '</g>'
            for i, (y, x, s) in enumerate(items))
        guide = (f'<path d="{ell(cx, cy, R, R * sq)}" fill="none" stroke="{DIRT2}" stroke-width="5" '
                 f'stroke-dasharray="22 26" opacity="0.6"/>')
        out += f'<g id="{p}_ring{ri}" opacity="0">{guide}{bodyk}</g>'
    field = f'<rect x="-3000" y="-2600" width="7000" height="7600" fill="{DIRT}"/>' + pebbles(41, 54, -2400, 3400, -1800, 3600)
    body = (f'<g id="{p}_cam">{field}<ellipse cx="{cx}" cy="{cy}" rx="86" ry="38" fill="{DIRT2}" stroke="none" opacity="0.45"/>'
            f'{out}{W.hero_rig(c["bob"], c.get("hero"))}</g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1 = c["t0"], c["t1"]
    D = t1 - t0
    js = f'''var rg = Rig("{c['bob']}", {{ s: 0.66, x: {cx}, y: {cy}, idle: 1, seed: 9 }});
var cam = ctl({{ x: {cx}, y: {cy}, z: 1.72, rot: -7 }}, function (st) {{ camSetR("{p}_cam", st.x, st.y, st.z, st.rot); }});
tl.fromTo(cam, {{ z: 1.72 }}, {{ z: 0.40, duration: {D:.3f}, ease: "power1.inOut", immediateRender: false }}, {t0:.3f});
tl.fromTo(cam, {{ rot: -7 }}, {{ rot: 5, duration: {D:.3f}, ease: "none", immediateRender: false }}, {t0:.3f});
tl.set(rg, {{ aL: 150, aL2: 20, wave: 1, eye: 0.8, mo: 1 }}, {t0 - 0.01:.3f});
'''
    for i in range(4):
        ts = t0 + 0.05 + i * (D - 0.35) / 4.0
        js += (f'(function(){{var r = cNode("{p}_ring{i}", {cx}, {cy}, {{ s: 0.6, o: 0 }});\n'
               f'tl.set(r, {{ o: 1 }}, {ts - 0.001:.3f});\n'
               f'tl.fromTo(r, {{ s: 0.66 }}, {{ s: 1, duration: 0.30, ease: "back.out(2.4)", immediateRender: false }}, {ts:.3f});}})();\n')
    js += (f'pose(rg, {{ aL: 140, aL2: 60, aR: -140, aR2: -60, head: -10 }}, {t1 - 0.4:.3f}, 0.25);\n'
           f'tl.set(rg, {{ wave: 0, mo: 0 }}, {t1 - 0.4:.3f});\n')
    js += js_gold(p, c, c["cue_t"], None)
    return svg, js


# ================================================================== 8) timeline_compare
def shot_timeline(p, c):
    base = 1180
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    scl = fit_scale(pw, ph, 460, 480, 1.3)
    line = f'<path d="M-700,{base} H4200" stroke="{INK}" stroke-width="11" stroke-linecap="round" fill="none"/>'
    ticks = "".join(f'<path d="M{x},{base} v{44 if (x // 110) % 5 == 0 else 24}" stroke="{INK}" '
                    f'stroke-width="{8 if (x // 110) % 5 == 0 else 5}" stroke-linecap="round" fill="none" '
                    f'opacity="{0.9 if (x // 110) % 5 == 0 else 0.5}"/>' for x in range(-600, 4200, 110))
    # porovnavaci objekt podla spec["vs"]; bez neho neutralny milnik s popiskom z vety
    vs_txt = (c.get("vs") or "").strip()
    vbody, vw, vh = W.vs_object(vs_txt, _last_noun(c["text"]))
    vscl = fit_scale(vw, vh, 720, 620, 1.2)
    # popisok nekreslime zvlast: rozpoznany objekt (pyramida/hodiny/trilit) hovori sam za seba
    # a neutralny milnik ma text uz vyryty v kameni -> ziadna kolizia so zlatym cislom
    pyr = (f'<g id="{p}_pyr"><g transform="translate(3130,{base}) scale({vscl:.3f})">{vbody}</g>'
           f'<ellipse cx="3130" cy="{base - 4}" rx="{vw * vscl / 2:.0f}" ry="20" fill="{DIRT2}" stroke="none" opacity="0.45"/></g>')
    dunes = (f'<path d="M2200,{base} q160,-70 330,-16 q150,48 300,-10 q170,-64 340,-4 q180,56 360,-14 L4200,{base} Z" '
             f'fill="{DIRT}" stroke="none" opacity="0.7"/>')
    speed = "".join(f'<g id="{p}_sl{i}"><path d="M0,{180 + i * 118} h{200 + (i % 3) * 120}" stroke="{INK}" stroke-width="{6 - i % 3}" '
                    f'stroke-linecap="round" fill="none" opacity="0.5"/></g>' for i in range(12))
    site = (f'<g transform="translate(300,{base}) scale({scl:.3f})">{psvg}</g>'
            f'<ellipse cx="300" cy="{base - 6}" rx="150" ry="14" fill="{DIRT2}" stroke="none" opacity="0.45"/>')
    body = (f'<g id="{p}_cam">{cloud(400, 340, 0.85)}{cloud(1900, 280, 0.7)}{cloud(3000, 360, 0.9)}'
            f'{dunes}{line}{ticks}{site}{pyr}{W.hero_rig(c["bob"], c.get("hero"))}</g>'
            f'<g id="{p}_speed" opacity="0">{speed}</g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    arrive = max(cu + 0.4, t1 - 0.55)
    js = f'''var rg = Rig("{c['bob']}", {{ s: 1.0, x: 640, y: {base}, idle: 1, seed: 11, eye: 0.7 }});
var cam = ctl({{ x: 430, z: 1.12, shx: 0, shy: 0, sp: 0 }}, function (st) {{
  camSet("{p}_cam", st.x + st.shx, {base} - 330 / st.z + st.shy, st.z);
  var t = CLK.t, L = $("{p}_speed").children;
  for (var i = 0; i < L.length; i++) {{
    var x = ((i * 271 - t * 3100) % 1560 + 1560) % 1560 - 340;
    L[i].setAttribute("transform", "translate(" + x.toFixed(1) + ",0)");
  }}
  $("{p}_speed").setAttribute("opacity", Math.max(0, st.sp).toFixed(3));
}});
setPose(rg, POINT, {t0:.3f});
tl.to(cam, {{ x: 500, duration: {max(0.12, cu - t0 - 0.1):.3f}, ease: "none" }}, {t0:.3f});
tl.to(cam, {{ x: 3130, duration: {arrive - (cu - 0.1):.3f}, ease: "power2.inOut" }}, {cu - 0.1:.3f});
tl.to(cam, {{ x: 3168, duration: {max(0.1, t1 - arrive):.3f}, ease: "none" }}, {arrive:.3f});
tl.fromTo(cam, {{ sp: 0 }}, {{ sp: 0.85, duration: 0.3, ease: "power2.out", immediateRender: false }}, {cu - 0.1:.3f});
tl.to(cam, {{ sp: 0, duration: 0.45, ease: "power2.in" }}, {arrive - 0.45:.3f});
(function(){{var pyr = cNode("{p}_pyr", 3130, {base}, {{ s: 1 }});
tl.fromTo(pyr, {{ s: 1.14 }}, {{ s: 1, duration: 0.5, ease: "elastic.out(1.2,0.32)", immediateRender: false }}, {arrive:.3f});}})();
shake(cam, {arrive:.3f}, 28, 0.42);
'''
    js += js_gold(p, c, cu, "cam")
    return svg, js


# ================================================================== 9) no_list
NO_ICONS = {
    "metal": (f'<path d="M-14,-10 L-6,150" stroke="{WOOD}" stroke-width="20" stroke-linecap="round" fill="none"/>'
              f'<path d="M-96,-66 h150 q22,0 22,26 v40 q0,26 -22,26 h-150 q-22,0 -22,-26 v-40 q0,-26 22,-26 z" fill="{METAL}" stroke="{INK}" stroke-width="9" stroke-linejoin="round"/>'),
    "wheel": (f'<circle r="106" fill="{PACK}" stroke="{INK}" stroke-width="11"/>'
              + "".join(f'<path d="M{math.cos(a) * 30:.0f},{math.sin(a) * 30:.0f} L{math.cos(a) * 102:.0f},{math.sin(a) * 102:.0f}" '
                        f'stroke="{INK}" stroke-width="10" stroke-linecap="round" fill="none"/>' for a in [k * math.pi / 3 for k in range(6)])
              + f'<circle r="34" fill="{PAPER}" stroke="{INK}" stroke-width="9"/>'),
    "writing": (f'<path d="M-104,-124 h208 q20,0 20,22 v204 q0,22 -20,22 h-208 q-20,0 -20,-22 v-204 q0,-22 20,-22 z" '
                f'fill="{PAPER}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>'
                + "".join(f'<path d="M-70,{-70 + k * 50} q26,-16 52,0 t52,0 t30,-2" stroke="{SHADE}" stroke-width="8" fill="none" stroke-linecap="round"/>'
                          for k in range(5))),
}


def _no_icon(text):
    low = text.lower()
    for k in NO_ICONS:
        if k in low:
            return NO_ICONS[k]
    return (f'<path d="M-100,-80 h200 q22,0 22,22 v116 q0,22 -22,22 h-200 q-22,0 -22,-22 v-116 q0,-22 22,-22 z" '
            f'fill="{PACK}" stroke="{INK}" stroke-width="10" stroke-linejoin="round"/>'
            f'<text x="0" y="46" class="hand" font-size="118" text-anchor="middle" fill="{INK}" stroke="none">?</text>')


def shot_no_list(p, c):
    items = (c["gold"] or {}).get("items") or ["NO METAL", "NO WHEEL", "NO WRITING"]
    items = [str(x).upper() for x in items[:3]]
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    scl = fit_scale(pw, ph, 460, 400, 1.5)
    icons = "".join(f'<g id="{p}_i{i}" opacity="0">{_no_icon(t)}</g>' for i, t in enumerate(items))
    xs = "".join(f'<g id="{p}_x{i}" opacity="0">'
                 f'<path id="{p}_xa{i}" class="pen" pathLength="1" d="M-150,-150 L150,150" stroke="{RED}" stroke-width="22" stroke-linecap="round" fill="none"/>'
                 f'<path id="{p}_xb{i}" class="pen" pathLength="1" d="M150,-150 L-150,150" stroke="{RED}" stroke-width="22" stroke-linecap="round" fill="none"/></g>'
                 for i in range(len(items)))
    words = "".join(f'<g id="{p}_w{i}" opacity="0">{num3d(p + "_wn" + str(i), t, fit_size(t, 116, 960))}</g>'
                    for i, t in enumerate(items))
    body = (f'{sky(p, None, ((260, 340, 0.9), (920, 250, 0.65)))}'
            f'<g id="{p}_cam">{ground()}{dressing(51)}'
            f'<g transform="translate(760,{GY}) scale({scl:.3f})">{psvg}</g>'
            f'{W.crowd_rig(p + "b", c.get("era"), 0)}</g>'
            f'<g id="{p}_ico">{icons}{xs}</g>{words}')
    svg = svg_wrap(body)
    t0, t1 = c["t0"], c["t1"]
    n = len(items)
    span = (t1 - t0 - 0.30) / n
    slots = list(c.get("slots") or [])
    js = f'''var cam = ctl({{ x: 900, z: 1.25, shx: 0, shy: 0 }}, function (st) {{ camSet("{p}_cam", st.x + st.shx, {GY} - 330 / st.z + st.shy, st.z); }});
var rg = Rig("{p}b", {{ s: 1.5, x: 400, y: {GY}, seed: 5, eye: 0.8, mo: 1, idle: 1 }});
tl.to(cam, {{ x: 560, z: 1.05, duration: {t1 - t0:.3f}, ease: "power1.out" }}, {t0:.3f});
setPose(rg, SHRUG, {t0:.3f});
'''
    for i in range(n):
        ts = slots[i] if len(slots) == n else (t0 + 0.14 + i * span)
        nxt = (slots[i + 1] if len(slots) == n and i + 1 < n else ts + span)
        span_i = max(0.30, nxt - ts)
        tx = ts + min(0.30, span_i * 0.5)
        js += f'''(function(){{
var ic = node("{p}_i{i}", {{ x: 540, y: 340, s: 0, o: 0 }}), wd = node("{p}_w{i}", {{ x: 540, y: 700, s: 0, o: 0, r: {(i - 1) * 3} }});
var xg = node("{p}_x{i}", {{ x: 540, y: 340, s: 1, o: 0 }}), xa = pen("{p}_xa{i}"), xb = pen("{p}_xb{i}");
pop(ic, {ts - 0.10:.3f}, 0.22, 3);
slamIn(wd, {ts:.3f}, 2.0, 1, 0.20);
shake(cam, {ts:.3f}, 22, 0.32);
tl.set(xg, {{ o: 1 }}, {tx - 0.001:.3f});
tl.to(xa, {{ d: 1, duration: 0.10, ease: "power2.out" }}, {tx:.3f});
tl.to(xb, {{ d: 1, duration: 0.10, ease: "power2.out" }}, {tx + 0.07:.3f});
unpop(wd, {ts + span_i - 0.12:.3f}, 0.14); unpop(ic, {ts + span_i - 0.12:.3f}, 0.14);
tl.to(xg, {{ s: 0, duration: 0.14, ease: "power2.in" }}, {ts + span_i - 0.12:.3f});
}})();
'''
    js += f'pose(rg, SHRUG, {t1 - 0.3:.3f}, 0.22);\n'
    return svg, js


# ================================================================== 10) action_crowd
BURY_WORDS = ("bury", "buried", "burying", "cover", "covered", "fill", "filled", "backfill", "hide", "hid", "sink", "sank")


def shot_crowd(p, c):
    bury = any(w in c["text"].lower() for w in BURY_WORDS)
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    scl = fit_scale(pw, ph, 480, 460, 1.2)
    def _basket(i):
        mound = (f'<path id="{p}_bd{i}" d="M-44,-12 q14,-40 46,-40 q34,0 46,40" fill="{DIRT2}" '
                 f'stroke="{INK}" stroke-width="8" stroke-linejoin="round"/>')
        return f'<g id="{p}_bk{i}" opacity="0">{BASKET.replace("__MOUND__", mound)}</g>'
    bask = "".join(_basket(i) for i in range(3))
    clods = "".join(f'<g id="{p}_po{i}" opacity="0">' + "".join(
        f'<g transform="translate({dx},{dy})">{CLOD}</g>' for dx, dy in ((0, 0), (38, 30), (-34, 34), (12, 66), (50, -20), (-16, -30))) + '</g>'
        for i in range(3))
    dust = "".join(f'<g id="{p}_du{i}" opacity="0">{PUFF}</g>' for i in range(6))
    body = (f'{sky(p, (900, 200), ((240, 300, 0.9), (960, 360, 0.7)))}'
            f'<g id="{p}_cam">{ground()}{dressing(71)}'
            f'<g id="{p}_propwrap"><g transform="translate(520,{GY}) scale({scl:.3f})">{psvg}</g></g>'
            f'{W.crowd_rig(p + "c1", c.get("era"), 0)}{W.crowd_rig(p + "c2", c.get("era"), 1)}'
            f'{W.crowd_rig(p + "c3", c.get("era"), 2)}{bask}{clods}{dust}'
            f'<g id="{p}_th" opacity="0">{THUMB}</g></g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1 = c["t0"], c["t1"]
    D = t1 - t0
    acts = [t0 + D * 0.30, t0 + D * 0.52, t0 + D * 0.74]
    js = f'''var MB = [Rig("{p}c1", {{ s: 1.15, y: {GY}, seed: 14, eye: 0.7, flip: -1 }}), Rig("{p}c2", {{ s: 1.15, y: {GY}, seed: 15, eye: 0.7, flip: -1 }}),
  Rig("{p}c3", {{ s: 1.15, y: {GY}, seed: 16, eye: 0.7, flip: -1 }})];
var cam = GCam("{p}_cam", {GY}, {{ x: 700, z: 0.9, up: 330 }});
var pwp = node("{p}_propwrap", {{}});
var XS = [1020, 1220, 1420], CARRY = {{ lean: -4, aL: 168, aL2: 12, aR: -168, aR2: -12, head: -4, drop: 0 }};
MB.forEach(function (r, i) {{
  var c0 = {{}}; for (var k in CARRY) c0[k] = CARRY[k]; tl.set(r, c0, {t0 - 0.01:.3f});
  tl.set(r, {{ w: 1, wa: 0, A: 24, ph: PH0 + i * 1.1 }}, {t0 - 0.01:.3f});
  tl.fromTo(r, {{ x: XS[i] + 620 }}, {{ x: XS[i], duration: {max(0.25, acts[0] - 0.08 - t0):.3f}, ease: "power1.out", immediateRender: false }}, {t0:.3f});
  tl.fromTo(r, {{ ph: PH0 + i * 1.1 }}, {{ ph: PH0 + i * 1.1 + OM * {max(0.25, acts[0] - 0.08 - t0):.3f}, duration: {max(0.25, acts[0] - 0.08 - t0):.3f}, ease: "none", immediateRender: false }}, {t0:.3f});
  tl.set(r, {{ w: 0 }}, {acts[0] - 0.08:.3f});
}});
tl.to(cam, {{ x: 640, z: 0.95, duration: {D:.3f}, ease: "none" }}, {t0:.3f});
'''
    lv = [0.72, 0.42, 0.02] if bury else [1, 1, 1]
    for i, ts in enumerate(acts):
        by = GY - 1.15 * 330
        js += f'''(function(){{
var r = MB[{i}], bk = node("{p}_bk{i}", {{ o: 0 }}), bd = node("{p}_bd{i}", {{ o: 1 }}), bx = XS[{i}];
tl.set(bk, {{ x: bx, y: {by:.0f}, r: 0, o: 1 }}, {t0 - 0.01:.3f});
var bc = ctl({{ u: 0 }}, function (st) {{ bk.x = r.x - 22 * st.u; bk.y = {by:.0f} - 10 * st.u; bk.r = -104 * st.u; }});
tl.fromTo(bc, {{ u: 0 }}, {{ u: 1, duration: 0.16, ease: "power2.in", immediateRender: false }}, {ts - 0.14:.3f});
tl.to(bc, {{ u: 0, duration: 0.3, ease: "power2.out" }}, {ts + 0.26:.3f});
tl.set(bd, {{ o: 0 }}, {ts + 0.02:.3f});
pose(r, {{ lean: -14, aL: 196, aL2: 4, aR: -196, aR2: -4, head: -12 }}, {ts - 0.14:.3f}, 0.14, "power2.in");
pose(r, {{ lean: 2, aL: 150, aL2: 26, aR: -150, aR2: -26, head: 4 }}, {ts + 0.26:.3f}, 0.26);
var po = node("{p}_po{i}", {{ o: 0 }});
var pc = ctl({{ tau: -1 }}, function (st) {{
  if (st.tau < 0 || st.tau > 0.6) {{ po.o = 0; return; }}
  po.o = 1; po.x = bx - 80 - 760 * st.tau; po.y = {by + 120:.0f} - 150 * st.tau + 0.5 * 2300 * st.tau * st.tau;
  po.r = 40 * st.tau; po.s = 1 + 0.5 * st.tau;
}});
tl.fromTo(pc, {{ tau: 0 }}, {{ tau: 0.6, duration: 0.6, ease: "none", immediateRender: false }}, {ts - 0.04:.3f});
tl.set(pc, {{ tau: -1 }}, {ts + 0.58:.3f});
shake(cam, {ts + 0.14:.3f}, 11, 0.26);
var du = node("{p}_du{i * 2}", {{ o: 0 }}), du2 = node("{p}_du{i * 2 + 1}", {{ o: 0 }});
tl.fromTo(du, {{ x: 420, y: {GY - 60}, s: 0.9, o: 0.95 }}, {{ x: 260, y: {GY - 250}, s: 2.6, o: 0, duration: 0.55, ease: "power2.out", immediateRender: false }}, {ts + 0.14:.3f});
tl.fromTo(du2, {{ x: 640, y: {GY - 60}, s: 0.9, o: 0.95 }}, {{ x: 800, y: {GY - 260}, s: 2.4, o: 0, duration: 0.55, ease: "power2.out", immediateRender: false }}, {ts + 0.16:.3f});
}})();
'''
        if bury:
            js += f'tl.to(pwp, {{ sy: {lv[i]}, duration: 0.24, ease: "power2.out" }}, {ts + 0.14:.3f});\n'
    js += (f'tl.set(MB[2], {{ idle: 1, eye: 1 }}, {t1 - 0.5:.3f});\n'
           f'pose(MB[2], {{ aL: 156, aL2: 10, aR: -30, aR2: 20, head: -6 }}, {t1 - 0.46:.3f}, 0.14);\n'
           f'(function(){{var th = node("{p}_th", {{ x: 1500, y: {GY - 560}, s: 0, o: 0, r: 8 }});\n'
           f'pop(th, {t1 - 0.34:.3f}, 0.26, 3.4);\n'
           f'tl.to(th, {{ r: -4, duration: 0.5, ease: "elastic.out(1.1,0.3)" }}, {t1 - 0.08:.3f});}})();\n')
    js += js_gold(p, c, c["cue_t"], "cam")
    return svg, js


# ================================================================== 11) punch
def shot_punch(p, c):
    """Tri ramovania, aby dva punche za sebou nevyzerali rovnako:
       0 = detail na tvar, 1 = detail na rekvizitu, 2 = bocny odjazd."""
    v = int(c.get("seq", 0)) % 3
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    scl = fit_scale(pw, ph, 560, 580, 1.6) * (1.0, 1.0, 0.82)[v]
    px = (980, 700, 430)[v]
    bx = (300, 280, 900)[v]
    body = (f'{sky(p, (890, 260) if v != 2 else (200, 240))}<g id="{p}_cam">{ground()}{dressing(33 + v)}'
            f'<g transform="translate({px},{GY}) scale({scl:.3f})">{psvg}</g>{W.hero_rig(c["bob"], c.get("hero"))}'
            f'{puff_ids(p, 4)}</g>')
    word = None
    if c["gold"] and "items" not in c["gold"]:
        word = c["gold"].get("text")
    if not word:
        word = (c.get("cue") or "").strip(" ,.;:!?").upper() or None
    gl = ""
    if word:
        gl = f'<g id="{p}_cnt" opacity="0">{num3d(p + "_num", str(word), fit_size(str(word), 190, 940))}</g>'
    svg = svg_wrap(body + (gl if word else gold_layer(p, c["gold"], "")))
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    cam0 = ((bx + 90, 1.0, bx + 120, 1.52), (620, 0.94, px - 60, 1.46), (900, 0.8, 560, 0.96))[v]
    js = f'''var cam = GCam("{p}_cam", {GY}, {{ x: {cam0[0]}, z: {cam0[1]}, up: 330 }});
var rg = Rig("{c['bob']}", {{ s: {1.3 if v != 0 else 1.55}, x: {bx}, y: {GY}, idle: 1, seed: 6, eye: 0.7 }});
setPose(rg, POINT, {t0:.3f});
tl.to(cam, {{ x: {(cam0[0] + cam0[2]) / 2:.0f}, z: {(cam0[1] + cam0[3]) / 2:.3f}, duration: {max(0.1, cu - t0):.3f}, ease: "none" }}, {t0:.3f});
tl.to(cam, {{ x: {cam0[2]}, z: {cam0[3]}, duration: 0.26, ease: "power2.inOut" }}, {cu - 0.08:.3f});
shake(cam, {cu:.3f}, 26, 0.4);
pose(rg, {{ head: -20, lean: -8, aL: 150, aL2: 40, eye: 1, mo: 1 }}, {cu:.3f}, 0.16);
'''
    for i in range(4):
        js += (f'(function(){{var n = node("{p}_pf{i}", {{ o: 0 }});'
               f'tl.fromTo(n, {{ x: {px - 80 + (i % 2) * 150}, y: {GY - 20}, s: 0.5, o: 1 }}, '
               f'{{ x: {px - 180 + (i % 2) * 330}, y: {GY - 180 - i * 30}, s: 2.2, o: 0, duration: 0.5, ease: "power2.out", immediateRender: false }}, {cu:.3f});}})();\n')
    if word:
        # v detaile na tvar (v=0) musi zlate slovo vyssie, inak lezi Bobovi na hlave
        js += (f'var cnt = node("{p}_cnt", {{ x: 540, y: {(300, 520, 520)[v]}, s: 0, o: 0, r: -2 }});\n'
               f'slamIn(cnt, {cu:.3f}, 2.1, 1, 0.22);\n'
               f'tl.to(cnt, {{ r: 2, duration: 0.6, ease: "elastic.out(1.1,0.28)" }}, {cu + 0.22:.3f});\n')
    else:
        js += js_gold(p, c, cu, "cam")
    return svg, js


# ================================================================== 12) loop_close (otazka do komentarov)
def shot_loop_close_sea(p, c):
    """Zaverecna otazka na otvorenom mori: rovnaka kompozicia ako uvod (lod na hladine),
    takze uzavretie slucky nepotrebuje ziadny iny svet - lod len dopláva tam, kde zacala."""
    # duch musi v SVG existovat, aj ked ho tu neanimujeme: HillShot ho vzdy hlada
    # (bez neho spadne cela stranka na "Cannot read properties of null")
    body, hy, _show, jter = hill_world(p, c["bob"], c["prop"], with_ghost=True, loop_cls=True,
                                       world=c.get("world"), hero=c.get("hero"))
    lines = wrap2(c["text"].strip().rstrip(".!"), per=14)
    fs = fit_size(max(lines, key=len), 112, 950)
    asks = "".join(f'<g id="{p}_ask{i}" opacity="0">{num3d(p + "_askn" + str(i), t_, fs)}</g>'
                   for i, t_ in enumerate(lines))
    body += f'<g id="{p}_q" opacity="0">{num3d(p + "_qn", "?", 460)}</g>{asks}'
    svg = svg_wrap(body)
    t0, t1 = c["t0"], c["t1"]
    D = t1 - t0
    Q = t0 + min(0.55, D * 0.22)
    slam_at = t0 + D * 0.62
    js = f'''var H = HillShot("{p}", "{c['bob']}", function () {{ return -(CLK.t - {t0:.3f}) * 22; }}, function (x) {{ return {jter}; }}, "{p}_ship");
var rg = H.rig, cam = H.cam;
tl.set(rg, {{ w: 0, lean: 7 }}, {t0:.3f});
tl.fromTo(cam, {{ bx: 640, lead: 150, z: 0.90 }}, {{ bx: 300, lead: 130, z: 1.00, duration: {D:.3f}, ease: "power1.inOut", immediateRender: false }}, {t0:.3f});
pose(rg, SHRUG, {t0 + 0.14:.3f}, 0.22);
tl.set(rg, {{ mo: 1, eye: 1 }}, {t0 + 0.14:.3f});
var q = node("{p}_q", {{ x: 790, y: -420, s: 1, o: 0, r: -10 }});
tl.set(q, {{ o: 1 }}, {Q - 0.001:.3f});
tl.fromTo(q, {{ y: -420 }}, {{ y: 520, duration: 0.14, ease: "power2.in", immediateRender: false }}, {Q:.3f});
tl.fromTo(q, {{ sy: 0.78, sx: 1.2 }}, {{ sy: 1, sx: 1, duration: 0.5, ease: "elastic.out(1.1,0.3)", immediateRender: false }}, {Q + 0.14:.3f});
tl.to(q, {{ r: 4, duration: 0.5, ease: "elastic.out(1.05,0.25)" }}, {Q + 0.14:.3f});
shake(cam, {Q + 0.14:.3f}, 30, 0.5);
tl.to(q, {{ o: 0, duration: 0.14 }}, {slam_at - 0.04:.3f});
'''
    for i, _ln in enumerate(lines):
        at = slam_at + i * 0.16
        js += (f'(function(){{var a = node("{p}_ask{i}", {{ x: 540, y: {640 + i * int(fs * 1.16)}, s: 1, o: 0 }});'
               f'tl.set(a, {{ o: 1 }}, {at - 0.001:.3f});'
               f'slamIn(a, {at:.3f}, 2.1, 1, 0.24);}})();\n')
    return svg, js


def shot_loop_close(p, c):
    if W.world_kind(c.get("world")) == "sea":
        return shot_loop_close_sea(p, c)
    lines = wrap2(c["text"].strip().rstrip(".!"), per=14)
    ghost = (f'<path id="{p}_gp" class="pen" pathLength="1" d="M446,1700 L450,1390 Q540,1356 632,1392 L638,1700" '
             f'fill="none" stroke="{GH}" stroke-width="9" stroke-linecap="round"/>')
    for i, (R, yy) in enumerate(((330, 1500), (620, 1610), (940, 1730))):
        ghost += (f'<path id="{p}_gr{i}" class="pen" pathLength="1" d="{ell(540, yy, R, R * 0.30)}" '
                  f'fill="none" stroke="{GH}" stroke-width="8"/>')
    shov = (f'<g transform="translate(830,{GY}) rotate(12)"><path d="M0,0 V-300" stroke="{WOOD}" stroke-width="11" fill="none" stroke-linecap="round"/>'
            f'<path d="M-16,-300 h32" stroke="{WOOD}" stroke-width="10" stroke-linecap="round" fill="none"/>'
            f'<path d="M-24,-10 h48 l-6,52 q-18,20 -36,0 z" fill="{METAL}" stroke="{INK}" stroke-width="8" stroke-linejoin="round"/></g>')
    dust = "".join(f'<g id="{p}_du{i}" opacity="0">{PUFF}</g>' for i in range(6))
    fs = fit_size(max(lines, key=len), 118, 950)
    asks = "".join(f'<g id="{p}_ask{i}" opacity="0">{num3d(p + "_askn" + str(i), t, fs)}</g>' for i, t in enumerate(lines))
    body = (f'<g id="{p}_sky">{sky(p, (880, 250))}</g>'
            f'<g id="{p}_cam">{ground()}{dressing(81)}{bone(1500, 1700, 25, 0.9)}{ghost}{shov}{W.hero_rig(c["bob"], c.get("hero"))}{dust}</g>'
            f'<g id="{p}_q" opacity="0">{num3d(p + "_qn", "?", 460)}</g>{asks}')
    svg = svg_wrap(body)
    t0, t1 = c["t0"], c["t1"]
    D = t1 - t0
    Q = t0 + min(0.55, D * 0.22)
    dive_at = t0 + D * 0.46
    slam_at = t0 + D * 0.62
    js = f'''var rg = Rig("{c['bob']}", {{ s: 1.3, x: 540, y: {GY}, idle: 1, seed: 13, eye: 0.8 }});
var cam = GCam("{p}_cam", {GY}, {{ x: 560, z: 1.34, up: 350 }});
pose(rg, {{ head: 22, lean: 8, aL: 40, aL2: 30 }}, {t0:.3f}, 0.22);
tl.to(cam, {{ z: 1.06, x: 546, duration: {Q - t0:.3f}, ease: "none" }}, {t0:.3f});
tl.to(cam, {{ z: 0.95, x: 540, duration: {dive_at - Q:.3f}, ease: "power1.inOut" }}, {Q:.3f});
pose(rg, SHRUG, {t0 + 0.14:.3f}, 0.22);
tl.set(rg, {{ mo: 1, eye: 1 }}, {t0 + 0.14:.3f});
var q = node("{p}_q", {{ x: 540, y: -420, s: 1, o: 0, r: -10 }});
tl.set(q, {{ o: 1 }}, {Q - 0.001:.3f});
tl.fromTo(q, {{ y: -420 }}, {{ y: 660, duration: 0.14, ease: "power2.in", immediateRender: false }}, {Q:.3f});
tl.fromTo(q, {{ sy: 0.78, sx: 1.2 }}, {{ sy: 1, sx: 1, duration: 0.5, ease: "elastic.out(1.1,0.3)", immediateRender: false }}, {Q + 0.14:.3f});
tl.to(q, {{ r: 4, duration: 0.5, ease: "elastic.out(1.05,0.25)" }}, {Q + 0.14:.3f});
shake(cam, {Q + 0.14:.3f}, 34, 0.5);
pose(rg, {{ lean: -18, aL: -40, aL2: 40, aR: -110, aR2: 30, head: -40, lR: -26, lR2: -20 }}, {Q + 0.12:.3f}, 0.14, "power1.out");
tl.to(rg, {{ ox: -46, duration: 0.18, ease: "power2.out" }}, {Q + 0.12:.3f});
pose(rg, {{ lean: 0, aL: 132, aL2: 66, aR: -132, aR2: -66, head: -30, lR: -10, lR2: 0 }}, {Q + 0.5:.3f}, 0.3);
'''
    for i in range(6):
        d = 1 if i % 2 else -1
        f = 1 + (i >> 1) * 0.6
        js += (f'(function(){{var du = node("{p}_du{i}", {{ o: 0 }});'
               f'tl.fromTo(du, {{ x: {540 + d * 60}, y: {GY - 14}, s: 0.5, o: 1 }}, '
               f'{{ x: {540 + d * 230 * f:.0f}, y: {GY - 80 - 50 * f:.0f}, s: 2.4, o: 0, duration: 0.7, ease: "power2.out", immediateRender: false }}, {Q + 0.14:.3f});}})();\n')
    js += (f'var gp = pen("{p}_gp");\n'
           f'tl.to(gp, {{ d: 1, duration: 0.45, ease: "power1.inOut" }}, {Q + 0.5:.3f});\n')
    for i in range(3):
        js += f'tl.to(pen("{p}_gr{i}"), {{ d: 1, duration: 0.55, ease: "power1.inOut" }}, {Q + 0.64 + i * 0.16:.3f});\n'
    js += (f'tl.to(q, {{ y: -520, r: -16, duration: 0.42, ease: "power2.in" }}, {dive_at - 0.04:.3f});\n'
           f'tl.to(node("{p}_sky", {{}}), {{ o: 0, duration: 0.3, ease: "power2.in" }}, {dive_at + 0.12:.3f});\n'
           f'tl.to(cam, {{ dive: 1116, z: 0.95, duration: {max(0.2, slam_at + 0.1 - dive_at):.3f}, ease: "power2.inOut" }}, {dive_at:.3f});\n'
           f'tl.to(cam, {{ dive: 1210, duration: {max(0.1, t1 - slam_at - 0.1):.3f}, ease: "none" }}, {slam_at + 0.1:.3f});\n')
    ys = [880, 1032] if len(lines) > 1 else [940]
    for i, ln in enumerate(lines):
        js += (f'(function(){{var a = node("{p}_ask{i}", {{ x: 540, y: {ys[i]}, s: 0, o: 0, r: {-2 if i == 0 else 1.5} }});\n'
               f'slamIn(a, {slam_at + i * 0.14:.3f}, 1.9, 1, 0.22);\n'
               f'tl.to(a, {{ r: {1.5 if i == 0 else -1.5}, duration: 1.1, ease: "sine.inOut" }}, {slam_at + 0.4:.3f});}})();\n')
    js += f'shake(cam, {slam_at:.3f}, 26, 0.4);\n'
    return svg, js


# ================================================================== Z: uzatvaraci zaber slucky
def shot_loop_lead(p, c):
    body, hy, show, jter = hill_world(p, c["bob"], c["prop"], with_ghost=True, loop_cls=True,
                                      world=c.get("world"), hero=c.get("hero"))
    svg = svg_wrap(body)
    t0, total = c["t0"], c["total"]
    D = total - t0
    AV = 1200.0 / max(0.8, c["first_dur"])
    sea = W.world_kind(c.get("world")) == "sea"
    SH = f', "{p}_ship"' if sea else ""
    WALK = ("tl.set(rg, { w: 0, lean: 7 }, %.3f);\n"
            "setPose(rg, { aL: 118, aL2: 58, aR: -128, aR2: -60, head: 8 }, %.3f);\n" % (t0 - 0.01, t0 - 0.01)
            if sea else
            "tl.set(rg, { w: 1, wa: 1, lean: 7, ph: PH0 - OM * %.3f }, %.3f);\n"
            "tl.to(rg, { ph: PH0, duration: %.3f, ease: \"none\" }, %.3f);\n" % (D, t0 - 0.01, D, t0))
    js = f'''var H = HillShot("{p}", "{c['bob']}", function () {{ return (TM.total - CLK.t) * 22; }}, function (x) {{ return {jter}; }}{SH});
var rg = H.rig, cam = H.cam;
{WALK}tl.fromTo(cam, {{ bx: {100 - AV * D:.1f}, lead: 120, z: 1.68 }}, {{ bx: 100, lead: 120, z: 1.68, duration: {D:.3f}, ease: "none", immediateRender: false }}, {t0:.3f});
tl.set(H.ghost, {{ o: 0 }}, {t0 - 0.01:.3f});
tl.to(H.ghost, {{ o: 1, duration: 0.45, ease: "power2.out" }}, {t0 + 0.14:.3f});
'''
    k = 1
    while k <= 3 and not sea:
        tk = total - k * math.pi / (math.pi * 1.9)
        if tk <= t0 + 0.05:
            break
        x = 100 - AV * (total - tk) - 25
        js += (f'(function(){{var n = node("{p}_pf{k - 1}", {{ o: 0 }});'
               f'tl.fromTo(n, {{ x: {x:.0f}, y: {hy(x) - 8:.0f}, s: 0.35, o: 0.95 }}, '
               f'{{ x: {x - 46:.0f}, y: {hy(x) - 40:.0f}, s: 1.35, o: 0, duration: 0.5, ease: "power1.out", immediateRender: false }}, {tk:.3f});}})();\n')
        k += 1
    return svg, js


SHOTS = {
    "walk_in": shot_walk_in, "spot": shot_spot, "dig": shot_dig, "descend": shot_descend,
    "scale_measure": shot_scale, "human_stack": shot_stack, "wide_reveal": shot_wide,
    "timeline_compare": shot_timeline, "no_list": shot_no_list, "action_crowd": shot_crowd,
    "punch": shot_punch, "loop_close": shot_loop_close,
}


# ================================================================== 13) exhibit (era: modern)
def shot_exhibit(p, c):
    """Artefakt vo vitrine v galerii, navstevnici okolo, kamera obchadza a dojde na detail.
    Toto je odpoved na vety typu "fragments rest in the museum" - predtym z toho vysiel cintorin."""
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    base_y, cx = 1180, 560
    inner = fit_scale(pw, ph, 230, 280, 1.0)
    vis = "".join(W.crowd_rig(f"{p}v{i}", "modern", i) for i in range(2))
    body = (f'<g id="{p}_cam">{W.gallery(p)}'
            f'{W.plinth(cx, base_y, 300, 160)}'
            f'<g transform="translate({cx},{base_y - 22}) scale({inner:.3f})">{psvg}</g>'
            f'{W.glass_case(cx, base_y - 22, 340, 420)}'
            f'{W.placard(cx, base_y + 46, _last_noun(c["text"]))}'
            f'{vis}{W.hero_rig(c["bob"], c.get("hero"))}'
            f'<g id="{p}_spark" opacity="0">{SPARK}</g></g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    js = f'''var cam = ctl({{ x: 300, y: 900, z: 0.74, shx: 0, shy: 0 }}, function (st) {{ camSet("{p}_cam", st.x + st.shx, st.y + st.shy, st.z); }});
var rg = Rig("{c['bob']}", {{ s: 1.15, x: 170, y: {base_y + 150}, idle: 1, seed: 21, eye: 0.7 }});
var V0r = Rig("{p}v0", {{ s: 1.1, x: 950, y: {base_y + 150}, idle: 1, seed: 22, eye: 0.7, flip: -1 }});
var V1r = Rig("{p}v1", {{ s: 1.0, x: 1110, y: {base_y + 120}, idle: 1, seed: 23, eye: 0.6, flip: -1 }});
setPose(rg, POINT, {t0:.3f});
setPose(V0r, {{ lean: -4, aL: 40, aL2: 30, aR: -40, aR2: 20, head: -14 }}, {t0:.3f});
setPose(V1r, {{ lean: 2, aL: 120, aL2: 50, aR: -30, aR2: 20, head: -8 }}, {t0:.3f});
/* oblúk okolo vitriny: kamera sa presunie zlava na stred a pritom sa prisunie */
tl.fromTo(cam, {{ x: 300, y: 900, z: 0.74 }}, {{ x: {cx + 10}, y: 960, z: 1.06, duration: {t1 - t0:.3f}, ease: "power1.inOut", immediateRender: false }}, {t0:.3f});
var sp = node("{p}_spark", {{ x: {cx + 120}, y: {base_y - 320}, s: 0, o: 0 }});
pop(sp, {cu:.3f}, 0.22, 4);
tl.to(sp, {{ o: 0, r: 40, s: 1.5, duration: 0.3 }}, {cu + 0.26:.3f});
pose(rg, {{ head: -20, lean: -6, aL: 152, aL2: 20, eye: 1 }}, {cu:.3f}, 0.18);
pose(V0r, {{ head: -22, aL: 150, aL2: 24 }}, {cu + 0.12:.3f}, 0.2);
shake(cam, {cu:.3f}, 10, 0.24);
'''
    js += js_gold(p, c, cu, "cam", gy=440)
    return svg, js


# ================================================================== 14) detail_compare
def shot_detail(p, c):
    """Dve veci vedla seba: cely objekt + kruhova lupa s detailom, zlaty pocet nad lupou."""
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    lens_svg, _, _ = prop_svg(p + "_lens", c["prop"])
    scl = fit_scale(pw, ph, 460, 520, 1.5)
    lx, ly, R = 760, GY - 520, 250
    zoom = scl * 2.6
    body = (f'{sky(p, (200, 230), ((880, 300, 0.8),))}<g id="{p}_cam">{ground()}{dressing(44)}'
            f'<g transform="translate(300,{GY}) scale({scl:.3f})">{psvg}</g>'
            f'<defs><clipPath id="{p}_clip"><circle cx="{lx}" cy="{ly}" r="{R}"/></clipPath></defs>'
            f'<g id="{p}_lensg" opacity="0">'
            f'<circle cx="{lx}" cy="{ly}" r="{R}" fill="{PAPER}" stroke="none"/>'
            f'<g clip-path="url(#{p}_clip)"><g transform="translate({lx - pw * zoom * 0.30:.0f},{ly + ph * zoom * 0.52:.0f}) scale({zoom:.3f})">{lens_svg}</g></g>'
            f'<circle cx="{lx}" cy="{ly}" r="{R}" fill="none" stroke="{INK}" stroke-width="12"/>'
            f'<path id="{p}_link" class="pen" pathLength="1" d="M{300 + pw * scl * 0.3:.0f},{GY - ph * scl * 0.55:.0f} '
            f'L{lx - R * 0.78:.0f},{ly + R * 0.62:.0f}" fill="none" stroke="{INK}" stroke-width="8" stroke-linecap="round"/>'
            f'</g>{W.hero_rig(c["bob"], c.get("hero"))}</g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    js = f'''var cam = GCam("{p}_cam", {GY}, {{ x: 430, z: 0.9, up: 330 }});
var rg = Rig("{c['bob']}", {{ s: 1.15, x: 120, y: {GY}, idle: 1, seed: 24, eye: 0.7 }});
setPose(rg, POINT, {t0:.3f});
tl.fromTo(cam, {{ x: 470, z: 0.80 }}, {{ x: 560, z: 0.92, duration: {t1 - t0:.3f}, ease: "power1.inOut", immediateRender: false }}, {t0:.3f});
(function(){{
  var lens = cNode("{p}_lensg", {lx}, {ly}, {{ s: 0.2, o: 0 }});
  tl.set(lens, {{ o: 1 }}, {cu - 0.22:.3f});
  tl.fromTo(lens, {{ s: 0.2 }}, {{ s: 1, duration: 0.30, ease: "back.out(2.2)", immediateRender: false }}, {cu - 0.22:.3f});
  tl.to(pen("{p}_link"), {{ d: 1, duration: 0.24, ease: "power1.inOut" }}, {cu - 0.10:.3f});
}})();
pose(rg, {{ aL: 158, aL2: 16, head: -28, lean: -6, eye: 1 }}, {cu - 0.2:.3f}, 0.2);
shake(cam, {cu:.3f}, 14, 0.28);
'''
    js += js_gold(p, c, cu, "cam", gy=300)
    return svg, js


SHOTS["exhibit"] = shot_exhibit
SHOTS["detail_compare"] = shot_detail


# ---------------------------------------------------------------- scale_measure: viac rozmerov
def _dims(c):
    """[(cas, hodnota)] ked veta obsahuje viac cisel s jednotkou; inak []."""
    g = c.get("gold") or {}
    if "count" not in g:
        return []
    steps = list(c.get("steps") or [])
    if not steps:
        return []
    out = [(round(c["cue_t"], 3), float(g["count"]))]
    for t, v in steps[:2]:
        if v > 0:
            out.append((round(t, 3), float(v)))
    return out if len(out) > 1 else []


def _scale_multi(p, c, psvg, scl, ptop, ax, dims):
    unit = (c["gold"] or {}).get("unit", "")
    top = max(v for _, v in dims)
    H = GY - ptop
    arrows, labels = "", ""
    for i, (_, v) in enumerate(dims):
        x = ax + i * 150
        h = max(140.0, H * (v / top))
        arrows += (f'<g id="{p}_d{i}" opacity="0">'
                   f'<path id="{p}_da{i}" class="pen" pathLength="1" d="M{x:.0f},{GY - 6} V{GY - h:.0f}" '
                   f'fill="none" stroke="{RED}" stroke-width="10" stroke-linecap="round"/>'
                   f'<path d="M{x - 24:.0f},{GY - 34} L{x:.0f},{GY - 6} L{x + 24:.0f},{GY - 34} '
                   f'M{x - 24:.0f},{GY - h + 34:.0f} L{x:.0f},{GY - h:.0f} L{x + 24:.0f},{GY - h + 34:.0f}" '
                   f'fill="none" stroke="{RED}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/></g>')
        txt = (f"{v:g}" + (f" {unit}" if unit else ""))
        labels += f'<g id="{p}_dl{i}" opacity="0">{num3d(p + "_dn" + str(i), txt, 86)}</g>'
    body = (f'{sky(p, (200, 250), ((820, 300, 0.8),))}<g id="{p}_cam">{ground()}{dressing(12)}'
            f'<g transform="translate(620,{GY}) scale({scl:.3f})">{psvg}</g>'
            f'{arrows}{W.hero_rig(c["bob"], c.get("hero"))}</g>{labels}')
    svg = svg_wrap(body)
    t0, t1 = c["t0"], c["t1"]
    js = f'''var cam = GCam("{p}_cam", {GY}, {{ x: 660, z: 0.94, up: 330 }});
var rg = Rig("{c['bob']}", {{ s: 1.2, x: 150, y: {GY}, idle: 1, seed: 4, eye: 0.7 }});
tl.fromTo(cam, {{ z: 1.0, x: 630 }}, {{ z: 0.88, x: 700, duration: {t1 - t0:.3f}, ease: "power1.inOut", immediateRender: false }}, {t0:.3f});
setPose(rg, POINT, {t0:.3f});
'''
    for i, (t, v) in enumerate(dims):
        x = ax + i * 150
        h = max(140.0, H * (v / top))
        sx = 540 + (x - 700) * 0.9
        js += (f'(function(){{var d = node("{p}_d{i}", {{ o: 0 }});\n'
               f'tl.set(d, {{ o: 1 }}, {t - 0.001:.3f});\n'
               f'tl.to(pen("{p}_da{i}"), {{ d: 1, duration: 0.26, ease: "power2.out" }}, {t:.3f});\n'
               f'var l = node("{p}_dl{i}", {{ x: {min(980, max(120, sx)):.0f}, y: {max(300, 960 + (GY - h - 78 - 960) * 0.9):.0f}, s: 0, o: 0, r: {(i - 1) * 3} }});\n'
               f'slamIn(l, {t + 0.06:.3f}, 1.8, 1, 0.20);\n'
               f'shake(cam, {t:.3f}, {16 - i * 3}, 0.26);}})();\n')
    js += f'pose(rg, {{ aL: 166, aL2: 4, head: -30, lean: -6 }}, {dims[0][0]:.3f}, 0.2);\n'
    return svg, js


# ================================================================== 15) theory (spekulacie)
def _two_props(c):
    """Dve rozne rekvizity: prva z tejto vety, druha z tej druhej teorie (ked je parova),
    inak z tej istej vety. Ked veta ponuka len jednu, druha bublina je otaznik."""
    from props import rank_props
    def one(txt, fb):
        r = [k for k in rank_props(txt or "") if k != "object"]
        return (r[0] if r else None), (txt or fb)
    if c.get("pair") == 2:
        ka, la = one(c.get("prev_bubble"), c.get("prev_text"))
        kb, lb = one(c.get("bubble"), c.get("text"))
    else:
        ka, la = one(c.get("bubble"), c.get("text"))
        kb, lb = (None, None) if not c.get("bubble2") else one(c.get("bubble2"), "")
        if ka is None and not c.get("bubble"):
            ka = c["prop"]
    return (ka, la), (kb, lb)


def shot_theory(p, c):
    """Bob a dve myslienkove bubliny s dvoma verziami - na vety typu
    "Some think X, others suggest Y". Predtym na to padal punch a vyzeral ako vsetky ostatne."""
    (ka, la), (kb, lb) = _two_props(c)
    bub = []
    bubs = [(320, GY - 800, 215)] + ([(830, GY - 880, 235)] if (c.get("pair") or 0) != 1 else [])
    for i, (bx, by, R) in enumerate(bubs):
        key, lab = (ka, la) if i == 0 else (kb, lb)
        if key:
            ksvg, kw, kh = prop_svg(f"{p}_p{i}", key)
            sc = fit_scale(kw, kh, R * 1.5, R * 1.5, 1.0)
            inner = (f'<g transform="translate({bx},{by + kh * sc * 0.5:.0f}) scale({sc:.3f})">{ksvg}</g>')
        elif lab:
            # ked sa slovo neda nakreslit (fumes, waterspouts), napis ho - stale je to
            # konkretna verzia, nie prazdny otaznik
            wl = wrap2(str(lab).strip().rstrip(".!").upper(), per=9)[:2]
            fsz = fit_size(max(wl, key=len), 96, R * 1.7)
            inner = "".join(f'<text x="{bx}" y="{by - (len(wl) - 1) * fsz * 0.5 + k * fsz * 1.05 + fsz * 0.34:.0f}" '
                            f'class="hand" font-size="{fsz:.0f}" text-anchor="middle" fill="{INK}" '
                            f'stroke="none" data-layout-allow-overlap>{w_}</text>' for k, w_ in enumerate(wl))
        else:
            inner = (f'<text x="{bx}" y="{by + 92}" class="hand" font-size="250" text-anchor="middle" '
                     f'fill="{INK}" stroke="none">?</text>')
        tail = "".join(f'<circle cx="{bx + (540 - bx) * (0.42 + k * 0.2):.0f}" cy="{by + R + 70 + k * 62}" '
                       f'r="{26 - k * 7}" fill="{PAPER}" stroke="{INK}" stroke-width="7"/>' for k in range(3))
        bub.append(f'<g id="{p}_b{i}" opacity="0">'
                   f'<circle cx="{bx}" cy="{by}" r="{R}" fill="{PAPER}" stroke="{INK}" stroke-width="10"/>'
                   f'{inner}{tail}</g>')
    body = (f'{sky(p, (900, 240), ((210, 320, 0.85),))}<g id="{p}_cam">{ground()}{dressing(61)}'
            f'{W.hero_rig(c["bob"], c.get("hero"))}{"".join(bub)}</g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    t2 = min(t1 - 0.35, cu + max(0.55, (t1 - cu) * 0.45))
    pair = c.get("pair") or 0
    # parova teoria: prva veta otvori lavu bublinu, druha ju necha stat a prida pravu
    s0 = (t0 - 0.2) if pair == 2 else cu
    s1 = cu if pair == 2 else t2
    b0s, b0o = (1, 1) if pair == 2 else (0.3, 0)
    two = pair != 1
    B1 = ("" if not two else
          '  var b1 = cNode("%s_b1", 830, %d, { s: 0.3, o: 0 });\n'
          '  tl.set(b1, { o: 1 }, %.3f);\n'
          '  tl.fromTo(b1, { s: 0.3 }, { s: 1, duration: 0.30, ease: "back.out(2.2)", '
          'immediateRender: false }, %.3f);\n'
          '  tl.to(b1, { r: 2.5, duration: 1.2, ease: "sine.inOut" }, %.3f);'
          % (p, GY - 880, s1 - 0.001, s1, s1 + 0.3))
    B1P = ("" if not two else
           "pose(rg, { head: -24, lean: -4 }, %.3f, 0.18);\n"
           "pose(rg, SHRUG, %.3f, 0.22);\n"
           "shake(cam, %.3f, 10, 0.22);\n" % (s1, min(t1 - 0.25, s1 + 0.55), s1))
    js = f'''var cam = GCam("{p}_cam", {GY}, {{ x: 560, z: 0.82, up: 330 }});
var rg = Rig("{c['bob']}", {{ s: 1.2, x: 560, y: {GY}, idle: 1, seed: 31, eye: 0.7 }});
tl.fromTo(cam, {{ x: 560, z: 0.80 }}, {{ x: 566, z: 0.90, duration: {t1 - t0:.3f}, ease: "power1.inOut", immediateRender: false }}, {t0:.3f});
setPose(rg, {{ lean: 0, aL: 128, aL2: 74, aR: -128, aR2: -74, head: 4 }}, {t0:.3f});
(function(){{
  var b0 = cNode("{p}_b0", 320, {GY - 800}, {{ s: {b0s}, o: {b0o} }});
  tl.set(b0, {{ o: 1 }}, {max(t0, s0) - 0.001:.3f});
  tl.fromTo(b0, {{ s: {b0s} }}, {{ s: 1, duration: 0.30, ease: "back.out(2.2)", immediateRender: false }}, {max(t0, s0):.3f});
  tl.to(b0, {{ r: -2.5, duration: 1.2, ease: "sine.inOut" }}, {max(t0, s0) + 0.3:.3f});
{B1}
}})();
pose(rg, {{ head: {22 if pair != 2 else -6}, lean: {4 if pair != 2 else 0} }}, {cu:.3f}, 0.18);
tl.set(rg, {{ mo: 1, eye: 1 }}, {cu:.3f});
{B1P}shake(cam, {cu:.3f}, 10, 0.22);
'''
    js += js_gold(p, c, cu, "cam", gy=300)
    return svg, js


SHOTS["theory"] = shot_theory


# ================================================================== 16) object_reveal
def shot_object(p, c):
    """Cely objekt v zabere, odhaluje sa zdola nahor, Bob maly vedla neho.
    Na vety, ktore opisuju sam objekt - punch na ne bol prazdny (velky Bob, nulova lod)."""
    psvg, pw, ph = prop_svg(p + "_prop", pkey(c))
    scl = fit_scale(pw, ph, 820, 760, 2.2)
    ow, oh = pw * scl, ph * scl
    cx = 600
    sub = SUBM if SURFACE == "water" else 0
    basey = GY + sub
    k0 = 0.30            # zaber nezacina prazdnym obrazom, objekt je uz z tretiny vonku
    h0 = (oh + 90) * k0
    clip = (f'<clipPath id="{p}_clip"><rect id="{p}_clipr" x="{cx - ow / 2 - 80:.0f}" '
            f'y="{basey - h0:.0f}" width="{ow + 160:.0f}" height="{h0:.0f}"/></clipPath>')
    edge = (f'<path id="{p}_edge" d="M{cx - ow / 2 - 60:.0f},{basey} H{cx + ow / 2 + 60:.0f}" fill="none" '
            f'stroke="{INK}" stroke-width="7" opacity="0.5" stroke-linecap="round"/>')
    body = (f'<defs>{clip}</defs>{sky(p, (880, 260), ((230, 340, 0.85),))}'
            f'<g id="{p}_cam">{ground()}{dressing(23)}'
            f'<g clip-path="url(#{p}_clip)"><g transform="translate({cx},{basey}) scale({scl:.3f})">{psvg}</g></g>'
            + (water_front(cx - ow / 2 - 70, cx + ow / 2 + 70) if sub else "")
            + f'<g id="{p}_ew" opacity="0">{edge}</g>{W.hero_rig(c["bob"], c.get("hero"))}</g>')
    svg = svg_wrap(body + gold_layer(p, c["gold"], ""))
    t0, t1, cu = c["t0"], c["t1"], c["cue_t"]
    rev = max(0.42, min(0.8, (t1 - cu) * 0.55))
    bx = cx - ow / 2 - 150 if ow < 760 else 150
    js = f'''var cam = GCam("{p}_cam", {GY}, {{ x: {cx}, z: 1.08, up: 320 }});
var rg = Rig("{c['bob']}", {{ s: 0.92, x: {bx:.0f}, y: {GY}, idle: 1, seed: 8, eye: 0.7 }});
tl.fromTo(cam, {{ z: 1.14, x: {cx - 14} }}, {{ z: 0.94, x: {cx + 10}, duration: {t1 - t0:.3f}, ease: "power1.inOut", immediateRender: false }}, {t0:.3f});
setPose(rg, {{ lean: 4, aL: 150, aL2: 30, aR: -120, aR2: -50, head: -20 }}, {t0:.3f});
(function () {{
  var el = $("{p}_clipr"), H = {oh + 90:.0f};
  var cl = ctl({{ k: {k0} }}, function (st) {{
    var h = H * st.k;
    el.setAttribute("y", ({basey} - h).toFixed(1));
    el.setAttribute("height", h.toFixed(1));
  }});
  tl.fromTo(cl, {{ k: {k0} }}, {{ k: 1, duration: {rev:.3f}, ease: "power2.out", immediateRender: false }}, {cu:.3f});
  var ew = node("{p}_ew", {{ x: 0, y: 0, o: 0 }});
  var ec = ctl({{ k: {k0} }}, function (st) {{ ew.y = -H * st.k; }});
  tl.set(ew, {{ o: 1 }}, {cu - 0.001:.3f});
  tl.fromTo(ec, {{ k: {k0} }}, {{ k: 1, duration: {rev:.3f}, ease: "power2.out", immediateRender: false }}, {cu:.3f});
  tl.to(ew, {{ o: 0, duration: 0.16 }}, {cu + rev:.3f});
}})();
pose(rg, {{ head: -34, lean: -4, aL: 168, aL2: 12 }}, {cu + rev * 0.5:.3f}, 0.22);
tl.set(rg, {{ mo: 1, eye: 1 }}, {cu:.3f});
shake(cam, {cu + rev:.3f}, 14, 0.30);
'''
    js += js_gold(p, c, cu + rev * 0.7, "cam", gy=360)
    if c["gold"]:
        js += f'unpop(cnt, {min(t1 - 0.10, cu + rev + 1.1):.3f}, 0.18);\n'
    return svg, js


SHOTS["object_reveal"] = shot_object
