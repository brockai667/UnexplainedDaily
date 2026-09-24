# -*- coding: utf-8 -*-
"""Hlas (Kokoro am_michael) + skratenie pauz + zarovnanie slov (faster-whisper). Importuje ho build.py."""
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # tts_kokoro.py (modely v ../kokoro)

SR = 24000


def synth(text, wav, voice="am_michael", speed=1.08):
    import tts_kokoro as tts
    tts.load(voice, speed)
    a = tts.speak(text)
    sf.write(wav, a, SR)
    return a


def _silences(a, thr_db=-42.0, min_len=0.12):
    w = int(0.01 * SR)
    n = len(a) // w
    rms = np.sqrt((a[:n * w].reshape(n, w) ** 2).mean(1))
    sil = 20 * np.log10(rms + 1e-9) < thr_db
    out, i = [], 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            if (j - i) * 0.01 >= min_len:
                out.append((i * w, j * w))
            i = j
        else:
            i += 1
    return out


def tighten(a, gaps, lead=0.06, tail=0.10):
    """Pauzy > 0.3 s vnutri skrati na gaps[k] (v poradi viet); orez ticha na zaciatku/konci."""
    sils = _silences(a)
    n = len(a)
    keep, pos, k = [], 0, 0
    for s, e in sils:
        if s == 0:
            pos = max(0, e - int(lead * SR))
            continue
        if e >= n - int(0.02 * SR):
            keep.append(a[pos:min(n, s + int(tail * SR))])
            pos = n
            break
        if (e - s) / SR > 0.30:
            g = int(gaps[min(k, len(gaps) - 1)] * SR)
            k += 1
            if e - s > g:
                h = g // 2
                keep.append(a[pos:s + h])
                pos = e - (g - h)
    if pos < n:
        keep.append(a[pos:])
    out = np.concatenate(keep).astype(np.float32)
    f = int(0.01 * SR)
    out[:f] *= np.linspace(0, 1, f, dtype=np.float32)
    out[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
    return out


def align(wav):
    from faster_whisper import WhisperModel
    m = WhisperModel("base.en", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(wav, word_timestamps=True, language="en")
    return [{"w": w.word.strip(), "s": round(max(0.0, w.start), 3), "e": round(w.end, 3)}
            for seg in segs for w in (seg.words or [])]


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def map_tokens(tokens, words):
    """Priradi casy whisper slov k zobrazovanym tokenom (difflib; nespárovane interpoluje)."""
    import difflib
    A = [_norm(t) for t in tokens]
    B = [_norm(w["w"]) for w in words]
    alias = {"meters": "metres", "its": "its", "nineteen": "1994"}
    B = [alias.get(b, b) for b in B]
    sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
    res = [None] * len(A)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for d in range(i2 - i1):
                res[i1 + d] = (words[j1 + d]["s"], words[j1 + d]["e"])
        elif i2 > i1 and j2 > j1:
            s, e = words[j1]["s"], words[j2 - 1]["e"]
            n = i2 - i1
            for d in range(n):
                res[i1 + d] = (s + (e - s) * d / n, s + (e - s) * (d + 1) / n)
    for i, r in enumerate(res):
        if r is None:
            prev = res[i - 1][1] if i and res[i - 1] else 0.0
            nxt = next((x[0] for x in res[i + 1:] if x), prev + 0.25)
            res[i] = (prev, nxt)
    return [{"w": t, "s": round(r[0], 3), "e": round(r[1], 3)} for t, r in zip(tokens, res)]


def refine(words, a):
    """Whisper base ma nepresne hranice okolo pauz: prichyt k realnemu tichu + rozumne dlzky slov."""
    sils = [(s / SR, e / SR) for s, e in _silences(a, min_len=0.10)]
    for i, w in enumerate(words):
        for s, e in sils:                      # pauza vnutri slova -> slovo zacina az po nej
            if e - s >= 0.15 and s >= w["s"] - 0.03 and e <= w["e"] - 0.08:
                w["s"] = round(e, 3)
        n = len(_norm(w["w"]))
        mx = 1.15 if _norm(w["w"]).isdigit() else 0.12 + 0.085 * n
        if w["e"] - w["s"] > mx:
            w["s"] = round(w["e"] - mx, 3)
            if i and words[i - 1]["e"] > w["s"] - 0.4:
                words[i - 1]["e"] = w["s"]
        if w["e"] - w["s"] < 0.07:
            w["e"] = round(w["s"] + 0.08, 3)
            if i + 1 < len(words) and words[i + 1]["s"] < w["e"]:
                words[i + 1]["s"] = w["e"]
        for s, e in sils:                      # koniec vety dotiahni po zaciatok ticha
            nxt = words[i + 1]["s"] if i + 1 < len(words) else 1e9
            if 0 < s - w["e"] < 0.25 and e - s >= 0.10 and nxt >= s:
                w["e"] = round(s, 3)
    return words


def run(text, work, gaps, speed=1.08, voice="am_michael"):
    """Cache drzi VIAC zaznamov (jeden na kazdu rychlost), takze hladanie rychlosti
    nezahodi predchadzajuce syntezy - pri opakovanom builde to usetri vacsinu casu."""
    os.makedirs(work, exist_ok=True)
    import hashlib
    import shutil
    key = hashlib.sha1(json.dumps([text, gaps, speed, voice, "r4"]).encode("utf-8")).hexdigest()[:16]
    cf = os.path.join(work, "voice_cache.json")
    vw = os.path.join(work, "voice.wav")
    kw = os.path.join(work, f"voice_{key}.wav")
    cache = {}
    if os.path.exists(cf):
        try:
            cache = json.load(open(cf, encoding="utf-8"))
            if not isinstance(cache, dict) or "words" in cache:
                cache = {}                       # stary jednozaznamovy format
        except (ValueError, OSError):
            cache = {}
    if key in cache and os.path.exists(kw):
        if os.path.abspath(kw) != os.path.abspath(vw):
            shutil.copyfile(kw, vw)
        return cache[key]["words"], cache[key]["dur"]
    raw = synth(text, os.path.join(work, "raw.wav"), voice, speed)
    a = tighten(raw, gaps)
    sf.write(vw, a, SR)
    words = refine(map_tokens(text.split(), align(vw)), a)
    dur = round(len(a) / SR, 3)
    shutil.copyfile(vw, kw)
    cache[key] = {"words": words, "dur": dur, "speed": speed}
    json.dump(cache, open(cf, "w", encoding="utf-8"), indent=1)
    return words, dur


if __name__ == "__main__":
    T = ("In 1994, an archaeologist climbs a hill in southern Turkey and sees a stone poking out of the dirt. "
         "He digs. It keeps going down. It's a carved pillar, five and a half metres tall. "
         "That's three people standing on each other's shoulders.")
    ws, d = run(T, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"), [0.22, 0.34, 0.25, 0.25])
    print(d)
    for w in ws:
        print(f'{w["s"]:6.2f} {w["e"]:6.2f} {w["w"]}')
