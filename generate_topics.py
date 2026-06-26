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

ROOT = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(ROOT, "topics_bank.json")
STATE = os.path.join(ROOT, "used_topics.json")

TARGET = int(os.environ.get("TOPICS_TARGET", "15"))
MODEL = os.environ.get("MODELS_MODEL", "openai/gpt-4o-mini")
BASE = os.environ.get("MODELS_BASE_URL", "https://models.github.ai/inference")
TOKEN = os.environ.get("MODELS_TOKEN") or os.environ.get("GITHUB_TOKEN")

SYSTEM = ("You are a viral short-form scriptwriter for a 'mysteries & unexplained' brand. "
          "You ONLY use real, widely-reported phenomena and well-documented unsolved cases "
          "(no invented facts, no fake numbers, no gore, nothing defamatory). You make true "
          "things feel eerie and fascinating. You output strict JSON, nothing else.")

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


def build_prompt(n, existing_titles):
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
        "- hashtags: 6-8 tags including #unexplained #mystery #shorts #fyp.\n"
        f"- Do NOT reuse any of these existing titles: {existing_titles}\n"
        "Return ONLY the JSON array."
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
    raw = call_model(build_prompt(need + 3, sorted(titles)))
    items = extract_json(raw)
    added = 0
    for t in items:
        if not valid(t) or t["title"] in titles:
            continue
        bank.append(t)
        titles.add(t["title"])
        added += 1
    json.dump(bank, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Pridanych {added} novych tem. Banka ma teraz {len(bank)} tem.")


if __name__ == "__main__":
    main()
