#!/usr/bin/env python3
"""
Doplni banku tem (topics_bank.json) cez GitHub Models (zadarmo) ak je malo nepouzitych.
Nika: ZAHADY / nevysvetlene / creepy (TRUE, siroko-uznavane javy; ziadne vymysly, ziaden gore).
Spusta sa v GitHub Actions (token z GITHUB_TOKEN, permission models: read).
"""
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

# Nika: ZAHADY / unexplained -> kde ludia realne diskutuju / co pozeraju
TREND_SUBREDDITS = ['UnresolvedMysteries', 'HighStrangeness', 'Paranormal', 'Glitch_in_the_Matrix', 'mystery']
TREND_YT_QUERIES = ['unexplained mysteries', 'strange phenomena', 'unsolved mysteries']

SYSTEM = ("You are a viral short-form scriptwriter for a 'mysteries & unexplained' brand. "
          "You ONLY use real, widely-reported phenomena and well-documented unsolved cases "
          "(no invented facts, no fake numbers, no gore, nothing defamatory). You make true "
          "things feel eerie and fascinating. You output strict JSON, nothing else. THE HOOK (the very first line / segment 1) is the single most important thing in the whole video: it MUST stop the scroll within 2 seconds. Make it concrete and specific (a number, a name, a vivid image, or a sharp contradiction) and open a curiosity gap that can ONLY be closed by watching to the end. Lead with the most shocking part FIRST, never a slow setup. Forbidden hook openers: 'Did you know', 'Have you ever', 'Imagine', 'Here are', 'In this video', 'Let me tell you'.")

EXAMPLE = {
    "title": "3 Mysteries Science Can't Explain",
    "segments": [
        {"text": "We've mapped less of the ocean than the surface of Mars.", "keywords": "deep ocean dark"},
        {"text": "And it only gets stranger from here.", "keywords": "dark underwater"},
        {"text": "First, the Bloop, a sound sensors caught deep underwater.", "keywords": "ocean waves night"},
        {"text": "It was heard across an entire ocean, and its source is still debated.", "keywords": "dark stormy sea"},
        {"text": "Next, creatures we've never seen drift in total darkness.", "keywords": "deep sea creature"},
        {"text": "Some glow with a light we still can't fully explain.", "keywords": "bioluminescent ocean"},
        {"text": "And most of the deep has never seen human eyes.", "keywords": "underwater dark blue"},
        {"text": "We truly don't know what is down there.", "keywords": "dark abyss"},
        {"text": "Follow for mysteries we still can't explain.", "keywords": "dark foggy forest"},
    ],
    "description": "We've explored more of space than our own oceans. Follow for daily mysteries!",
    "hashtags": ["#unexplained", "#mystery", "#ocean", "#creepy", "#strange", "#shorts", "#fyp", "#scary"],
}


import random  # CTAS_ROTATE

CTAS = [
    "Follow for a new mystery every day.",
    "Follow if you can't stop asking why.",
    "Follow for the cases no one can explain.",
    "Follow for daily unexplained mysteries.",
    "Follow if the unknown keeps you up at night.",
]


def build_prompt(n, existing_titles, trending=None):
    trend_block = ""
    if trending:
        joined = chr(10).join("- " + t for t in trending)
        trend_block = (
            " WHAT REAL PEOPLE DISCUSS AND WATCH THIS WEEK (live headlines from Reddit communities and "
            "top YouTube videos in this niche - what the audience actually cares about right now): " + joined +
            " Let at least HALF of the new topics be directly inspired by a SPECIFIC item above, turned "
            "into a strong hook that STILL follows the style and safety rules described. Do NOT copy any "
            "headline word-for-word, and NEVER mention Reddit or YouTube. "
        )
    return (
        f"Generate {n} NEW faceless short-form video topics for a MYSTERIES & UNEXPLAINED brand "
        "(TikTok / Reels / YouTube Shorts).\n"
        "Niche: real unsolved mysteries, strange-but-true phenomena, eerie history, and things "
        "science can't fully explain (deep ocean, space signals, ancient sites, natural oddities).\n"
        "Return ONLY a JSON array (no markdown, no commentary). Each item EXACTLY this schema:\n"
        f"{json.dumps(EXAMPLE, ensure_ascii=False, indent=2)}\n\n"
        "Rules (make it feel PRO and VIRAL, eerie but trustworthy):\n"
        "- title: catchy, like '3 Mysteries Science Can't Explain' or 'Things That Shouldn't Exist'.\n"
        "- 8 to 11 segments. Segment 1 is THE HOOK: an unsettling, true fact under 12 words "
        "that makes a viewer think 'wait, that's real?'. Never start with 'Did you know'.\n"
        "- segment 2 is a short open-loop tease (e.g. 'And it only gets stranger.').\n"
        "- then present EACH point in TWO short lines: NAME the specific real thing (e.g. 'the Bloop', "
        "'fast radio bursts', 'the Antikythera mechanism', 'the sailing stones of Death Valley'), then "
        "EXPLAIN the real intriguing detail that makes it unexplained. Give a genuine 'whoa, I just "
        "learned something' payoff — go into the actual fact, do NOT just vaguely hint at it from a "
        "distance. ~30-40s total, not a rushed one-line list.\n"
        "- the SECOND-TO-LAST segment must LOOP BACK to the opening hook (re-pose the mystery you "
        "started with) so a rewatch feels seamless; the final segment is the fixed follow line below.\n"
        "- the LAST segment text MUST be exactly: 'Follow for mysteries we still can't explain.'\n"
        "- write for a slow, ominous SPOKEN voiceover: short, punchy, simple sentences.\n"
        "- USE ONLY REAL, widely-reported phenomena or genuine unsolved cases. NO invented facts, "
        "NO fake statistics, NO gore or graphic death, NO real named victims, nothing defamatory. "
        "Eerie and fascinating, never harmful misinformation.\n"
        "- each segment 'keywords': 1-3 ENGLISH words for real Pexels footage that VISUALLY MATCHES "
        "the specific thing named in that line, so viewers can picture it (line about a red lake -> "
        "'red lake', sailing stones -> 'desert cracked ground', a space signal -> 'radio telescope "
        "night'). Keep it dark/moody but CONCRETE, never abstract.\n"
        "- description: one intriguing sentence ending with 'Follow for daily mysteries!'.\n"
        "- About half the time, add ONE fitting emoji at the very END of the description (e.g. 🔍, 👁️, 🌑, ❓). "
        "Emoji ONLY in the description text, NEVER inside any segment 'text' (spoken captions).\n"
        "- hashtags: 6-8 tags including #unexplained #mystery #shorts #fyp.\n"
        "- VARY THE TITLE FORMAT: do NOT start more than one in five titles with a number "
        "(avoid the repetitive 'N things' pattern). Mix a bold claim, a question, a "
        "'why/how' angle and a curiosity gap so titles never look the same.\n"
        "- ACCURACY IS CRITICAL: use ONLY widely-documented, verifiable facts. NEVER invent or "
        "guess numbers, percentages, dates, amounts or statistics. If a specific figure is not "
        "universally established, say it generally instead of making one up. Wrong facts kill the "
        "channel's credibility, so double-check every claim.\n"
        "- BE SPECIFIC: name the ACTUAL subject of the video (the exact place, case, event, person "
        "or thing) so it is never vague. Viewers complain when the location or subject is not named.\n"
        f"- Do NOT reuse any of these existing titles: {existing_titles}\n"
        "- Do NOT repeat the same SUBJECT, fact or concept as any existing title above, even reworded, "
        "renumbered or from a different angle. Every topic must be a genuinely DIFFERENT idea.\n"
        + trend_block +
        "STORYBOARD (visual directing, IMPORTANT): to EVERY segment ADD a field 'visual' = an object choosing HOW to visualize exactly what that line SAYS (never generic): {\"type\":\"kenburns\",\"prompt\":\"LITERAL ENGLISH image prompt naming ONE concrete, instantly recognizable subject/scene that depicts exactly what the line says (a real thing a camera could photograph; NEVER abstract, NEVER metaphors)\"} for normal lines; {\"type\":\"counter\",\"target\":1000,\"suffix\":\"x\",\"label\":\"3-4 WORD CAPTION\"} when the line contains a big number; {\"type\":\"compare\",\"small_prompt\":\"...\",\"big_prompt\":\"...\",\"small_label\":\"X\",\"big_label\":\"Y\",\"stat\":\"300x\"} for size/amount comparisons; {\"type\":\"callouts\",\"prompt\":\"subject image\",\"labels\":[\"SHORT LABEL\"]} to point at parts of a subject; {\"type\":\"lineup\",\"items\":[{\"name\":\"A\",\"prompt\":\"...\"}]} for listing 3-5 things; {\"type\":\"arrow\",\"from_prompt\":\"...\",\"to_prompt\":\"...\",\"label\":\"WHAT MOVES\"} for movement/flow. First segment gets {\"type\":\"hook\",\"prompt\":\"dramatic scene image\",\"big\":\"SHORT PUNCHY QUESTION OR CLAIM (max 5 words)\"}; last segment {\"type\":\"cta\",\"prompt\":\"iconic subject of the video\"}. Labels MUST describe what the narration says at that moment - never invent unrelated text. Image prompts must describe 3D RENDERED CGI assets in a modern 3D-explainer style - NEVER photographs, NEVER photorealistic people; if a person is needed, describe an elegant dark silhouette with dramatic rim light, or the relevant anatomy/object instead - NEVER cartoon characters, NEVER toys; prefer objects, anatomy, environments, close-up details; the subject must FILL the frame and be well lit. Return ONLY the JSON array."
    )


def call_model(user_text):
    r = requests.post(
        BASE.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "temperature": 0.95,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_text},
            ],
        },
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
    if not isinstance(t, dict):
        return False
    if "title" not in t or "segments" not in t:
        return False
    if not isinstance(t["segments"], list) or len(t["segments"]) < 4:
        return False
    for seg in t["segments"]:
        if "text" not in seg or "keywords" not in seg:
            return False
    t.setdefault("description", t["title"] + " Follow for daily mysteries!")
    t.setdefault("hashtags", ["#unexplained", "#mystery", "#shorts", "#fyp"])
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


def main():
    if not TOKEN:
        print("CHYBA: chyba MODELS_TOKEN/GITHUB_TOKEN")
        sys.exit(1)
    bank = json.load(open(BANK, encoding="utf-8"))
    used = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else []
    titles = {t["title"] for t in bank}
    unused = [t for t in bank if t["title"] not in used]
    need = TARGET - len(unused)
    if need <= 0:
        print(f"Banka OK: {len(unused)} nepouzitych tem (>= {TARGET}), netreba dopnat.")
        return
    print(f"Nepouzitych {len(unused)} < {TARGET} -> generujem ~{need} novych tem cez {MODEL}...")
    trending = []
    if trends is not None:
        try:
            trending, meta = trends.gather(TREND_SUBREDDITS, TREND_YT_QUERIES, top=18, return_meta=True)
            if trending:
                print(f"Trendy: {len(trending)} titulkov (Reddit={meta['reddit']}, YouTube={meta['youtube']}) -> temy z realneho dopytu.")
        except Exception as e:
            print("Trendy preskocene:", str(e)[:120])
    raw = call_model(build_prompt(need + 3, sorted(titles), trending))
    items = extract_json(raw)
    added = 0
    existing_sigs = [_sig(x) for x in titles]
    for t in items:
        if not valid(t) or t["title"] in titles:
            continue
        _s = _sig(t["title"])
        if _too_similar(_s, existing_sigs):   # ta ista TEMA (iny nazov) -> preskoc (ziadne opakovanie)
            print("  preskocene (podobna tema):", t["title"]); continue
        if t.get("segments"):
            t["segments"][-1]["text"] = random.choice(CTAS)  # CTAS_ROTATE: nie vzdy rovnaka veta
        bank.append(t)
        titles.add(t["title"])
        existing_sigs.append(_s)
        added += 1
    json.dump(bank, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Pridanych {added} novych tem. Banka ma teraz {len(bank)} tem.")


if __name__ == "__main__":
    main()
