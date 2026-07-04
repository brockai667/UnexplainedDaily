#!/usr/bin/env python3
"""Doplni banku tem cez GitHub Models (zadarmo). Nika: ZAHADY / unexplained.
NOVY FORMAT (PRO engine, eerie dizajn): tema = mystery + place + country + 5-6 scen
(hook/map/fact/archive/callout/cta) s presnymi queries, sync chipmi, ARCHIVE scenou
(realna fotka artefaktu/miesta z Wikimedia) a popisom kde sa to stalo/naslo.
Stare temy bez 'scenes' sa vyradia az ked su aspon 3 nove (den nikdy neostane bez videi)."""
import json
import os
import re
import sys

import requests
try:
    import trends                      # trend scanner (Reddit + YouTube), volitelny
except Exception:
    trends = None

ROOT = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(ROOT, "topics_bank.json")
STATE = os.path.join(ROOT, "used_topics.json")

TARGET = int(os.environ.get("TOPICS_TARGET", "15"))
MODEL = os.environ.get("MODELS_MODEL", "openai/gpt-4o-mini")
BASE = os.environ.get("MODELS_BASE_URL", "https://models.github.ai/inference")
TOKEN = os.environ.get("MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN")

TREND_SUBREDDITS = ['UnresolvedMysteries', 'HighStrangeness', 'Paranormal', 'Glitch_in_the_Matrix', 'mystery']
TREND_YT_QUERIES = ['unexplained mysteries', 'strange phenomena', 'unsolved mysteries']

SYSTEM = ("You are a scriptwriter for a 'mysteries & unexplained' brand. You retell REAL, "
          "widely-documented mysteries: strange phenomena, unexplained discoveries, ancient artifacts, "
          "lost signals, places science still debates. STRICT SAFETY RULES: (1) ACCURACY IS SACRED - "
          "only real, widely-reported facts; never invent details, numbers or claims. (2) Be HONEST "
          "about the state of knowledge: if science has a leading explanation, present it as the "
          "accepted theory; what is unknown stays clearly unknown - never sell pseudoscience as fact. "
          "(3) No gore, nothing defamatory, no victim photos. (4) Eerie and fascinating, never "
          "misleading. You output strict JSON, nothing else.")

EXAMPLE = {
    "title": "The 2,000-Year-Old Computer",
    "place": "Antikythera",
    "country": "Greece",
    "scenes": [
        {"role": "hook", "text": "A machine two thousand years ahead of its time, found on a shipwreck.",
         "hook_top": "A 2,000 YEAR OLD COMPUTER", "query": "underwater shipwreck diver dark",
         "query2": "deep sea dark water"},
        {"role": "map", "text": "It was pulled from a Roman-era shipwreck off Antikythera, a tiny island in Greece."},
        {"role": "fact", "text": "Sponge divers found it in 1901. X-rays later revealed at least thirty interlocking bronze gears.",
         "query": "ancient bronze mechanism gears", "query2": "old gears macro dark",
         "chips": [{"t": "FOUND IN 1901", "on": "1901", "style": "white"}, {"t": "30 BRONZE GEARS", "on": "gears", "style": "accent"}],
         "punch": "gears"},
        {"role": "archive", "text": "Its corroded fragments are kept in Athens, still being decoded more than a century later.",
         "archive_query": "Antikythera mechanism fragment", "archive_label": "Antikythera mechanism"},
        {"role": "callout", "text": "It tracked the sun and the moon, and predicted eclipses, centuries before anything like it existed.",
         "query": "night sky stars moon timelapse", "query2": "solar eclipse dark sky",
         "label": "PREDICTED ECLIPSES", "sub": "centuries ahead of its time", "label_on": "eclipses", "punch": "eclipses"},
        {"role": "cta", "text": "Follow for a new mystery every day.",
         "query": "foggy forest night mist", "query2": "dark ocean night waves"}
    ],
    "description": "\U0001F4CD Antikythera, Greece - 1901. Sponge divers pulled a corroded machine from a Roman shipwreck: at least 30 bronze gears that tracked the sun and moon and predicted eclipses. Follow for daily mysteries!",
    "hashtags": ["#mystery", "#unexplained", "#antikythera", "#greece", "#ancienttech", "#history", "#shorts", "#fyp"],
}


import random  # CTAS_ROTATE

CTAS = [
    "Follow for a new mystery every day.",
    "Follow if you can't stop asking why.",
    "Follow for the cases no one can explain.",
    "Follow for daily unexplained mysteries.",
    "Follow if the unknown keeps you up at night.",
]


def build_prompt(n, existing_titles, existing_places, trending=None):
    trend_block = ""
    if trending:
        joined = chr(10).join("- " + t for t in trending)
        trend_block = (
            " WHAT REAL PEOPLE DISCUSS AND WATCH THIS WEEK (live headlines from Reddit communities and "
            "top YouTube videos in this niche): " + joined +
            " Let at least HALF of the new topics be directly inspired by a SPECIFIC item above, turned "
            "into a strong hook that STILL follows all safety rules. Do NOT copy any headline "
            "word-for-word, and NEVER mention Reddit or YouTube. "
        )
    return (
        f"Generate {n} NEW faceless short-form video topics for a MYSTERIES & UNEXPLAINED brand. Each video "
        "is a cinematic MICRO-DOC of ONE real, widely-documented mystery (TikTok / Reels / Shorts).\n"
        "Return ONLY a JSON array (no markdown). Each item EXACTLY this schema:\n"
        f"{json.dumps(EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Rules (PRO editing pipeline depends on these):\n"
        "- Pick a REAL, widely-documented mystery: strange phenomena, unexplained discoveries, ancient "
        "artifacts, lost signals, mysterious places, historic enigmas. No invented mysteries, no creepypasta.\n"
        "- 'place' = where it happened / was found (city, island, region), 'country' = country (both REQUIRED - used for the "
        "map pin, must be findable on OpenStreetMap).\n"
        "- EXACTLY 5 or 6 scenes in this order: hook, map, fact, (optional archive), callout, cta. "
        "Each scene 'text' = 1-2 short spoken sentences (serious documentary voice, no gore).\n"
        "- hook: the most gripping TRUE detail, under 14 words. 'hook_top' = the same idea compressed "
        "to MAX 6 punchy words (big kinetic text). Never start with 'Did you know'.\n"
        "- map scene 'text' MUST say where it happened or was found, accurately.\n"
        "- fact scenes: 'chips' = 1-2 short TRUE fact-chips: {'t': 'MAX 22 CHARS', 'on': 'spoken trigger "
        "word', 'style': 'white'|'accent'}. ONLY widely-documented numbers/years (e.g. 'FOUND IN 1901', '30 BRONZE "
        "GEARS'); if no reliable number, use a word chip (e.g. 'STILL UNEXPLAINED').\n"
        "- archive scene (include ONLY if a real image almost certainly exists on Wikimedia "
        "Commons): 'archive_query' = precise Commons search (famous artifact, site, document - "
        "e.g. 'Antikythera mechanism fragment', 'Nazca lines aerial', 'Voynich manuscript page'), "
        "'archive_label' = short caption (max 26 chars). NEVER use photos of victims or private people.\n"
        "- callout scene: 'label' = 2-4 word on-screen label (e.g. 'NEVER RECOVERED'), 'sub' = short "
        "sub-line (max 34 chars), 'label_on' = spoken trigger word.\n"
        "- 'punch' (optional): ONE spoken word where the shot subtly zooms.\n"
        "- EVERY scene except map/archive needs 'query' = cinematic moody stock search (e.g. 'foggy forest "
        "night', 'deep ocean dark', 'ancient ruins mist', 'night sky stars timelapse') and 'query2' = "
        "alternative. Concrete, atmospheric, NEVER graphic or violent.\n"
        "- the LAST scene text MUST be exactly: 'Follow for a new mystery every day.'\n"
        "- HONESTY: if science has a leading explanation, include it as the accepted theory; what is "
        "unknown stays clearly unknown; never sell pseudoscience as fact; ACCURACY IS SACRED.\n"
        "- description: MUST begin with '\U0001F4CD <Place>, <Country> - <Year>.' then 1-2 gripping TRUE "
        "sentences about the mystery, then 'Follow for daily mysteries!'\n"
        "- hashtags: 6-9 tags: #mystery #unexplained #shorts #fyp + 2-3 specific to the case/place.\n"
        "- VARY THE TITLE FORMAT: mix a bold claim, a question and a curiosity gap; do NOT start more "
        "than one in five titles with a number; never clickbait that misleads.\n"
        f"- Do NOT reuse any of these existing titles: {existing_titles}\n"
        f"- Do NOT reuse any of these already-covered mysteries/places (no repeats, not even reworded): {existing_places}\n"
        + trend_block +
        "Return ONLY the JSON array."
    )


def call_model(user_text):
    r = requests.post(
        BASE.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json={"model": MODEL, "temperature": 0.95,
              "messages": [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": user_text}]},
        timeout=180,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Models API {r.status_code}: {r.text[:500]}")
    return r.json()["choices"][0]["message"]["content"]


def extract_json(s):
    s = s.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    a, b = s.find("["), s.rfind("]")
    if a != -1 and b != -1:
        s = s[a:b + 1]
    return json.loads(s)


def valid(t):
    """Overi + doopravi NOVY format temy (scenes). Stare/nevalidne temy odmietne."""
    if not isinstance(t, dict) or not t.get("title") or not t.get("place") or not t.get("country"):
        return False
    scenes = t.get("scenes")
    if not isinstance(scenes, list) or not (4 <= len(scenes) <= 7):
        return False
    for sc in scenes:
        if not isinstance(sc, dict) or not sc.get("text"):
            return False
        sc.setdefault("role", "fact")
    roles = [sc["role"] for sc in scenes]
    scenes[0]["role"] = "hook"
    scenes[-1]["role"] = "cta"
    if "map" not in roles:
        return False
    for sc in scenes:
        if sc["role"] == "hook":
            top = re.sub(r"[^A-Za-z0-9' ]", "", str(sc.get("hook_top") or sc["text"]))
            sc["hook_top"] = " ".join(top.split()[:6]).upper()
        if sc["role"] == "archive" and not sc.get("archive_query"):
            sc["role"] = "fact"
        if sc["role"] not in ("map", "archive") and not sc.get("query"):
            sc["query"] = "foggy forest night mist"
        if sc["role"] not in ("map", "archive") and not sc.get("query2"):
            sc["query2"] = "dark ocean night waves"
        if sc["role"] == "fact":
            chips = [c for c in (sc.get("chips") or []) if isinstance(c, dict) and c.get("t")]
            for c in chips:
                c["t"] = str(c["t"])[:24]
            sc["chips"] = chips[:2]
    t.setdefault("description", f"\U0001F4CD {t['place']}, {t['country']}. " + t["title"] + " Follow for daily mysteries!")
    t.setdefault("hashtags", ["#mystery", "#unexplained", "#shorts", "#fyp"])
    return True


_STOP = {"why", "your", "the", "is", "a", "of", "you", "that", "are", "and", "to", "in",
         "on", "how", "this", "for", "with", "it", "its", "can", "cant", "not", "be", "do",
         "than", "them", "their", "own", "what", "when", "was", "were", "has", "have", "from",
         "more", "most", "just", "every", "an", "as", "or", "but", "so", "hidden", "secret",
         "surprising", "truth", "facts", "fact", "these", "there", "they"}


def _sig(title):
    return set(w for w in re.findall(r"[a-z]+", str(title).lower()) if len(w) > 2 and w not in _STOP)


def _too_similar(sig, existing_sigs):
    if not sig:
        return False
    for es in existing_sigs:
        if not es:
            continue
        inter = len(sig & es)
        if inter >= 3:
            return True
        if inter >= 2 and inter / (len(sig | es) or 1) >= 0.5:
            return True
    return False


def _place_key(t):
    """Normalizovany kluc zahady: titulok+miesto (ta ista zahada sa NIKDY neopakuje)."""
    if isinstance(t, dict):
        base = str(t.get("place", "")) + " " + str(t.get("title", ""))
    else:
        base = str(t)
    return re.sub(r"[^a-z0-9]+", "", base.lower())[:60]



# --- ANTI-OPAKOVANIE (dedup): po behu odstrani z banky NEPOUZITE temy, ktore su subjektom
# prilis podobne inej teme. Signatura = title+description+hook + cisla/roky; caste niche-slova
# sa auto-ignoruju cez frekvenciu (df). Duale pravidlo: rovnaky ROK + prekrytie = dup;
# rozne roky = rozne pripady; bezrocnove niky -> silna slovna zhoda. Publikovane sa NIKDY nemazu.
_DD_STOP = set("""a an the this that these those and or but so of to in on for with at by from as is are was
were be been being it its you your they them their our we he she his her my me i do does did not no can cant
will just every most more than then there here what when why how who which while into over out up down off only
also very much many some any all if thing things way ways get make made youre follow daily wisdom mindset day
today need needs about like want wants nobody tells tell told never ever still story people world reveal
revealed discover""".split())


def _dd_sig(t):
    first = ""
    if t.get("scenes"):
        first = t["scenes"][0].get("text", "")
    elif t.get("segments"):
        first = t["segments"][0].get("text", "")
    txt = (str(t.get("title", "")) + " " + str(t.get("place", "")) + " "
           + str(t.get("description", "")) + " " + str(first))
    low = txt.lower()
    toks = set(w for w in re.findall(r"[a-z]+", low) if len(w) > 2 and w not in _DD_STOP)
    toks |= set("#" + n for n in re.findall(r"\d{2,}", low))
    return toks


def _dd_years(s):
    return set(w for w in s if len(w) == 5 and w[0] == "#" and w[1] in "12")


def _dd_dup(si, sj):
    common = si & sj
    if len(common) < 3:
        return False
    yi, yj = _dd_years(si), _dd_years(sj)
    yc = yi & yj
    if yi and yj and not yc:
        return False                                   # rozne roky = rozne pripady
    jac = len(common) / (len(si | sj) or 1)
    if yc and len(common) >= 3:
        return True                                    # spolocny rok + prekrytie
    if not (yi or yj) and len(common) >= 4 and jac >= 0.5:
        return True                                    # bezrocnove niky -> silna slovna zhoda
    return False


def _clean_bank():
    """Odstrani NEPOUZITE temy prilis podobne inej teme (ziadne opakovanie videi).
    Publikovane (used_topics) sa nikdy nemazu. Best-effort, nikdy nezhodi denny beh."""
    from collections import Counter
    bank = json.load(open(BANK, encoding="utf-8"))
    used = set(json.load(open(STATE, encoding="utf-8"))) if os.path.exists(STATE) else set()
    raws = [_dd_sig(t) for t in bank]
    df = Counter()
    for s in raws:
        for w in s:
            df[w] += 1
    cutoff = max(2, int(len(bank) * 0.25))             # slovo vo >25% tem = niche-filler -> ignoruj
    sigs = [set(w for w in s if df[w] <= cutoff) for s in raws]
    ks = [s for t, s in zip(bank, sigs) if t.get("title") in used]   # seed: vsetky publikovane
    kept, removed = [], 0
    for t, s in zip(bank, sigs):
        if t.get("title") in used:
            kept.append(t)
            continue
        if s and any(_dd_dup(s, k) for k in ks):
            removed += 1
            continue
        kept.append(t)
        ks.append(s)
    if removed:
        json.dump(kept, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("Dedup: odstranenych %d podobnych nepouzitych tem (ziadne opakovanie)." % removed)
    else:
        print("Dedup: ziadne podobne nepouzite temy.")



def main():
    if not TOKEN:
        print("CHYBA: chyba MODELS_TOKEN/GITHUB_TOKEN"); sys.exit(1)
    bank = json.load(open(BANK, encoding="utf-8"))
    used = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else []
    # MIGRACIA na PRO format: nepouzite temy STAREHO formatu (bez 'scenes') vyrad -
    # ale LEN ak uz mame aspon 3 nove PRO temy (den nikdy neostane bez videi)
    old = [t for t in bank if not t.get("scenes") and t["title"] not in used]
    new_unused = [t for t in bank if t.get("scenes") and t["title"] not in used]
    if old and len(new_unused) >= 3:
        bank = [t for t in bank if t.get("scenes") or t["title"] in used]
        print(f"Migracia: vyradenych {len(old)} nepouzitych tem stareho formatu.")
    titles = {t["title"] for t in bank}
    unused = [t for t in bank if t["title"] not in used]
    need = TARGET - len(unused)
    if need <= 0:
        json.dump(bank, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"Banka OK: {len(unused)} nepouzitych tem."); return
    print(f"Generujem ~{need} novych tem cez {MODEL}...")
    trending = []
    if trends is not None:
        try:
            trending, meta = trends.gather(TREND_SUBREDDITS, TREND_YT_QUERIES, top=18, return_meta=True)
            if trending:
                print(f"Trendy: {len(trending)} titulkov (Reddit={meta['reddit']}, YouTube={meta['youtube']}) -> temy z realneho dopytu.")
        except Exception as e:
            print("Trendy preskocene:", str(e)[:120])
    places = sorted({_place_key(t) for t in bank})
    items = extract_json(call_model(build_prompt(need + 3, sorted(titles), places, trending)))
    added = 0
    existing_sigs = [_sig(x) for x in titles]
    existing_places = {_place_key(t) for t in bank}
    for t in items:
        if not valid(t) or t["title"] in titles:
            continue
        _s = _sig(t["title"])
        if _too_similar(_s, existing_sigs):   # ta ista TEMA (iny nazov) -> preskoc (ziadne opakovanie)
            print("  preskocene (podobna tema):", t["title"]); continue
        pk = _place_key(t)
        if pk and pk in existing_places:
            print("  preskocene (zahada uz bola):", t["title"]); continue
        if t.get("scenes"):
            t["scenes"][-1]["text"] = random.choice(CTAS)  # CTAS_ROTATE: nie vzdy rovnaka veta
        bank.append(t); titles.add(t["title"]); existing_sigs.append(_s); added += 1
        if pk:
            existing_places.add(pk)
    json.dump(bank, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Pridanych {added} tem. Banka ma {len(bank)} tem.")


if __name__ == "__main__":
    main()
    try:
        _clean_bank()
    except Exception as _e:
        print("Dedup preskoceny:", str(_e)[:150])
