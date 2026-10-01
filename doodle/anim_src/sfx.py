# -*- coding: utf-8 -*-
"""Lacne deterministicke zvukove efekty (numpy, pevne seedy). Kazda funkcia vracia mono float32 pri SR.
Mixuju sa potichu pod hlas (build_anim.py). Druhy: whoosh, boom, thud, glass, bubbles, hiss, clatter, tick."""
import numpy as np

SR = 24000


def _env(n, a, d):
    """attack a s, potom exponencialny dozvuk d s"""
    t = np.arange(n) / SR
    e = np.minimum(1.0, t / max(a, 1e-4)) * np.exp(-np.maximum(0.0, t - a) / max(d, 1e-4))
    return e.astype(np.float32)


def _lowpass(x, fc):
    """jednopolovy dolny priepust s premenlivou frekvenciou (fc skalar alebo pole)"""
    fc = np.broadcast_to(np.asarray(fc, dtype=np.float64), x.shape)
    a = 1.0 - np.exp(-2 * np.pi * fc / SR)
    y = np.zeros_like(x, dtype=np.float64)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y.astype(np.float32)


def whoosh(dur=2.6, seed=1):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n).astype(np.float32)
    swell = (t / dur) ** 2.2                                   # nabieha k dopadu
    fc = 250 + 3200 * swell
    x = _lowpass(noise, fc) - _lowpass(noise, fc * 0.25)       # pasmovy sum, ktory stupa
    env = (0.15 + 0.85 * swell) * np.minimum(1, t / 0.25) * np.minimum(1, (dur - t) / 0.08)
    x = x * env
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def boom(dur=2.2, seed=2):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 32 + 38 * np.exp(-t * 5)                               # klesajuci ton
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(ph) * np.exp(-t / 0.65)
    rum = _lowpass(rng.standard_normal(n).astype(np.float32), 180) * np.exp(-t / 0.9) * 3.0
    crack = _lowpass(rng.standard_normal(n).astype(np.float32), 2500) * np.exp(-t / 0.05)
    x = tone + 0.8 * rum + 0.5 * crack
    x *= np.minimum(1, t / 0.006)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def thud(seed=3):
    rng = np.random.default_rng(seed)
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    f = 70 + 90 * np.exp(-t * 30)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.08)
    x += 0.35 * _lowpass(rng.standard_normal(n).astype(np.float32), 900) * np.exp(-t / 0.02)
    x *= np.minimum(1, t / 0.002)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def glass(dur=0.9, seed=4, pings=11):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n, np.float32)
    x += 0.5 * _lowpass(rng.standard_normal(n).astype(np.float32), 5000) * np.exp(-t / 0.06)     # prask
    for k in range(pings):
        t0 = rng.uniform(0.0, dur * 0.6) * (0.35 if k < 4 else 1.0)
        f = rng.uniform(2300, 5600)
        i0 = int(t0 * SR)
        tt = np.arange(n - i0) / SR
        x[i0:] += (rng.uniform(0.3, 1.0) * np.sin(2 * np.pi * f * tt) * np.exp(-tt / rng.uniform(0.04, 0.14))).astype(np.float32)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def bubbles(dur=2.0, seed=5, rate=16):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    x = np.zeros(n, np.float32)
    k = int(dur * rate)
    for _ in range(k):
        t0 = rng.uniform(0, dur - 0.06)
        ln = rng.uniform(0.025, 0.05)
        m = int(ln * SR)
        tt = np.arange(m) / SR
        f0 = rng.uniform(180, 380)
        f = f0 * (1 + 2.2 * tt / ln)                           # blip s rastucou vyskou = bublina
        b = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * tt / ln) * rng.uniform(0.3, 1.0)
        i0 = int(t0 * SR)
        x[i0:i0 + m] += b.astype(np.float32)
    x *= np.minimum(1, np.arange(n) / (0.2 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.3 * SR))
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def hiss(dur=1.2, seed=6):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    noise = rng.standard_normal(n).astype(np.float32)
    x = noise - _lowpass(noise, 2500)                          # vysoky sum = syk
    x *= _env(n, 0.03, dur / 3)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def clatter(seed=7):
    """bicykel spadne: niekolko kovovych tuknuti"""
    rng = np.random.default_rng(seed)
    n = int(0.6 * SR)
    x = np.zeros(n, np.float32)
    for k in range(5):
        t0 = [0.0, 0.05, 0.12, 0.2, 0.31][k]
        i0 = int(t0 * SR)
        tt = np.arange(n - i0) / SR
        f = rng.uniform(700, 1500)
        x[i0:] += (np.sin(2 * np.pi * f * tt) + 0.5 * np.sin(2 * np.pi * f * 2.76 * tt)).astype(np.float32) * np.exp(-tt / 0.05).astype(np.float32) * (1 - 0.15 * k)
    x += 0.4 * _lowpass(rng.standard_normal(n).astype(np.float32), 1200) * np.exp(-np.arange(n) / SR / 0.08).astype(np.float32)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def tick(seed=8):
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * 2400 * t) * np.exp(-t / 0.006)
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


MAKERS = {"whoosh": whoosh, "boom": boom, "thud": thud, "glass": glass, "bubbles": bubbles, "hiss": hiss, "clatter": clatter, "tick": tick}


def render(cues, total, sr=SR):
    """cues = [(t, kind, gain, kwargs)] -> mono stopa dlzky total"""
    out = np.zeros(int(total * sr) + 1, np.float32)
    cache = {}
    for c in cues:
        t, kind, gain = c[0], c[1], c[2]
        kw = c[3] if len(c) > 3 else {}
        key = (kind, tuple(sorted(kw.items())))
        if key not in cache:
            cache[key] = MAKERS[kind](**kw)
        x = cache[key]
        i0 = int(max(0.0, t) * sr)
        m = min(len(x), len(out) - i0)
        if m > 0:
            out[i0:i0 + m] += gain * x[:m]
    return out
