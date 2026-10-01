# -*- coding: utf-8 -*-
"""Staticke SVG kusky v style 'hruba cierna linka, ploche farby' (pouzivaju ich epizody v episodes/<meno>/episode.py).
Vsetko vracia SVG retazce v suradniciach sveta sceny (720 siroky ramec, y dole)."""
import math

INK = "#1b1b1b"
S = f'stroke="{INK}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"'
T = f'stroke="{INK}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"'
FAR = 'stroke="#5f6f7c" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"'   # vzdialene hory


def f0(v):
    return f"{v:.0f}"


def house(x, base, w, h, wall, roof, gid):
    y = base - h
    return (f'<g id="{gid}">'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{wall}" {S}/>'
            f'<path d="M{x - 22},{y} L{f0(x + w / 2)},{f0(y - 0.6 * w)} L{x + w + 22},{y} Z" fill="{roof}" {S}/>'
            f'<rect x="{f0(x + w * 0.52)}" y="{base - 70}" width="{f0(w * 0.26)}" height="70" fill="#8d6e63" {S}/>'
            f'<rect x="{x + 18}" y="{y + 26}" width="36" height="36" fill="#8ecae6" {T}/>'
            f'<path d="M{x + 36},{y + 26} L{x + 36},{y + 62} M{x + 18},{y + 44} L{x + 54},{y + 44}" fill="none" {T}/>'
            '</g>')


def cloud(cx, cy, w, h, n=5, fill="#ffffff"):
    pts = [(cx + math.cos(math.pi - math.pi * i / n) * w / 2, cy - math.sin(math.pi - math.pi * i / n) * h) for i in range(n + 1)]
    d = f"M{f0(pts[0][0])},{f0(cy)}"
    for i in range(1, n + 1):
        (x, y), (px, py) = pts[i], pts[i - 1]
        r = math.hypot(x - px, y - py) * 0.62
        d += f" A{f0(r)},{f0(r)} 0 0 1 {f0(x)},{f0(cy if i == n else y)}"
    return f'<path d="{d} Z" fill="{fill}" {T}/>'


def star(n, R, r):
    pts = []
    for i in range(2 * n):
        a = math.pi * i / n - math.pi / 2
        rr = R if i % 2 == 0 else r
        pts.append(f"{math.cos(a) * rr:.0f},{math.sin(a) * rr:.0f}")
    return "M" + " L".join(pts) + " Z"


def snowcaps(peaks):
    return "".join(f'<path d="M{x - 24},{y + 24} L{x},{y} L{x + 24},{y + 24} L{x + 12},{y + 18} L{x + 2},{y + 28} L{x - 10},{y + 18} Z" '
                   f'fill="#ffffff" stroke="#5f6f7c" stroke-width="4" stroke-linejoin="round"/>' for x, y in peaks)


def mountains(ridge, base, peaks=()):
    """ridge = 'M.. L..' otvorena ciara hrebena; vyplni sa po base."""
    first = ridge.split("L")[0].replace("M", "").strip().split(",")
    last = ridge.split("L")[-1].strip().split(",")
    fill = f'{ridge} L{last[0]},{base} L{first[0]},{base} Z'
    return f'<path d="{fill}" fill="#dde5ea"/><path d="{ridge}" fill="none" {FAR}/>' + snowcaps(peaks)


def tufts(xs, y):
    return "".join(f'<path d="M{x},{y} l-5,-15 M{x + 7},{y} l1,-20 M{x + 14},{y} l6,-14" fill="none" stroke="{INK}" '
                   f'stroke-width="4" stroke-linecap="round"/>' for x in xs)


def red_cross(cx, cy, s, bg="#ffffff"):
    """biela tabulka s cervenym krizom (stred cx,cy, polovica velkosti s)"""
    a = s * 0.62
    return (f'<rect x="{f0(cx - s)}" y="{f0(cy - s)}" width="{f0(2 * s)}" height="{f0(2 * s)}" rx="6" fill="{bg}" {T}/>'
            f'<path d="M{f0(cx)},{f0(cy - a)} L{f0(cx)},{f0(cy + a)} M{f0(cx - a)},{f0(cy)} L{f0(cx + a)},{f0(cy)}" '
            f'fill="none" stroke="#e63946" stroke-width="{max(6, s * 0.42):.0f}" stroke-linecap="round"/>')


def window(x, y, w, h, gid):
    """okno ktore sa da rozbit: <g id=gid_ok> cele sklo, <g id=gid_br> rozbite (JS prepina opacity)"""
    jag = (f"M{x},{y} L{x + w * 0.35:.0f},{y + h * 0.3:.0f} L{x + w * 0.2:.0f},{y + h * 0.55:.0f} L{x},{y + h * 0.7:.0f} Z "
           f"M{x + w},{y} L{x + w * 0.7:.0f},{y + h * 0.25:.0f} L{x + w},{y + h * 0.45:.0f} Z "
           f"M{x},{y + h} L{x + w * 0.3:.0f},{y + h * 0.78:.0f} L{x + w * 0.55:.0f},{y + h} Z "
           f"M{x + w},{y + h} L{x + w * 0.8:.0f},{y + h * 0.7:.0f} L{x + w * 0.62:.0f},{y + h} Z")
    return (f'<g id="{gid}_ok"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#8ecae6" {T}/>'
            f'<path d="M{x + 8},{y + h - 10} L{x + w * 0.45:.0f},{y + 8}" stroke="#ffffff" stroke-width="5" stroke-linecap="round"/></g>'
            f'<g id="{gid}_br" opacity="0"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#3d4f5c" {T}/>'
            f'<path d="{jag}" fill="#bfe6f7" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/></g>')


def health_centre(x, base, w=190, h=150, gid="hc"):
    """maly zdravotny domcek s cervenym krizom a dvomi oknami (okna: gid_w0, gid_w1)"""
    y = base - h
    ww, wh = 44, 44
    return (f'<g id="{gid}">'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#eef4f7" {S}/>'
            f'<path d="M{x - 10},{y} L{x + w + 10},{y}" fill="none" stroke="{INK}" stroke-width="12" stroke-linecap="round"/>'
            f'<rect x="{f0(x + w / 2 - 22)}" y="{base - 78}" width="44" height="78" fill="#8d6e63" {S}/>'
            f'{window(x + 18, y + 40, ww, wh, gid + "_w0")}{window(x + w - 18 - ww, y + 40, ww, wh, gid + "_w1")}'
            f'<path d="M{f0(x + w / 2)},{y} L{f0(x + w / 2)},{y - 30}" fill="none" {S}/>'
            f'{red_cross(x + w / 2, y - 52, 26)}'
            '</g>')


def hill(x0, x1, top_y, base, peak_x=None, fill="#a7c957"):
    px = peak_x if peak_x is not None else (x0 + x1) / 2
    d = f"M{x0},{base} Q{x0 + (px - x0) * 0.6:.0f},{top_y} {px:.0f},{top_y - 4} Q{px + (x1 - px) * 0.7:.0f},{top_y - 4} {x1},{top_y + 58}"
    return f'<path d="{d} L{x1},{base} Z" fill="{fill}"/><path d="{d}" fill="none" {S}/>'


def warning_sign(gid):
    """vystrazna tabula (lokalne suradnice: spodok stlpika = 0,0)"""
    return (f'<g id="{gid}"><path d="M0,0 L0,-120" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>'
            f'<path d="M-52,-112 L0,-200 L52,-112 Z" fill="#ffd166" {S}/>'
            f'<path d="M0,-176 L0,-140" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>'
            f'<circle cx="0" cy="-124" r="5.5" fill="{INK}"/></g>')


def tent(gid):
    """zdravotny stan (lokalne: stred spodku = 0,0)"""
    return (f'<g id="{gid}"><path d="M-96,0 L-70,-104 L70,-104 L96,0 Z" fill="#ffffff" {S}/>'
            f'<path d="M-70,-104 L-44,0 M70,-104 L44,0" fill="none" {T}/>'
            f'<path d="M-30,0 L0,-66 L30,0 Z" fill="#dfe7ee" {T}/>'
            f'<path d="M0,-104 L0,-150" fill="none" {T}/><path d="M0,-150 L34,-140 L0,-130 Z" fill="#e63946" {T}/>'
            f'{red_cross(0, -82, 16, "#ffffff")}</g>')
