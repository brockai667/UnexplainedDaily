# -*- coding: utf-8 -*-
"""LLM volanie pre storyboard.py (Groq / OpenAI-kompatibilny provider).

Prebrate 1:1 zo ScienceFactory/explainer/common.py, aby stickman fabrika
nezavisela od ineho repozitara. Kluc: MODELS_TOKEN (Actions) alebo GROQ_API_KEY.
"""
import json
import os
import re
import time

import requests

MODEL = os.environ.get("MODELS_MODEL", "openai/gpt-oss-120b")
MODEL_FALLBACK = os.environ.get("MODELS_FALLBACK", "openai/gpt-oss-20b")
BASE = os.environ.get("MODELS_BASE_URL", "https://api.groq.com/openai/v1")
TOKEN = os.environ.get("MODELS_TOKEN") or os.environ.get("GROQ_API_KEY") or os.environ.get("GITHUB_TOKEN")
# zalozny provider (OpenAI-kompatibilny), napr. Cerebras (gpt-oss-120b, 1M tokenov/den zadarmo) alebo Gemini
BASE2 = os.environ.get("MODELS2_BASE_URL", "")
TOKEN2 = os.environ.get("MODELS2_TOKEN", "")
MODEL2 = os.environ.get("MODELS2_MODEL", "gpt-oss-120b")


def _extract_json(txt):
    txt = txt.strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.S)
    try:
        return json.loads(txt)
    except Exception:
        pass
    # najdi prvy { ... } alebo [ ... ] blok
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = txt.find(opener), txt.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(txt[i:j + 1])
            except Exception:
                continue
    raise ValueError("LLM nevratil validny JSON: " + txt[:200])


def _providers():
    out = [(BASE, TOKEN, MODEL, 8), (BASE, TOKEN, MODEL_FALLBACK, 1)]
    if BASE2 and TOKEN2:
        out.insert(1, (BASE2, TOKEN2, MODEL2, 3))   # zaloha hned po hlavnom modeli, pred slabsim 20b
    return out


def llm_json(prompt, system, temperature=0.7, max_tokens=6000, tries=10):
    """Zavolaj chat model, vrat parsovany JSON. Poradie: hlavny model (Groq 120b, trpezlive retry na 429),
    zalozny provider (MODELS2_*), az nakoniec slabsi 20b (horsie fakty)."""
    if not TOKEN:
        raise RuntimeError("Chyba MODELS_TOKEN (Groq) v prostredi.")
    last = None
    for base, token, model, n_tries in _providers():
        for att in range(n_tries):
            try:
                r = requests.post(
                    base.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"model": model, "temperature": temperature, "max_tokens": max_tokens,
                          "reasoning_effort": "low",            # gpt-oss: inak minie tokeny na reasoning a vrati prazdno
                          "response_format": {"type": "json_object"},
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}]},
                    timeout=180)
                if r.status_code == 429:
                    why = re.sub(r"\s+", " ", r.text)[:140]
                    # denny limit (TPD) -> cakanie nepomoze, skoc na dalsieho providera
                    if "per day" in why or "TPD" in why:
                        print(f"   [llm] 429 DENNY limit ({model}): {why}")
                        break
                    ra = r.headers.get("retry-after")
                    try:
                        wait = min(300, max(5, float(ra) + 3)) if ra else min(240, 30 + 40 * att)
                    except ValueError:
                        wait = min(240, 30 + 40 * att)
                    print(f"   [llm] 429 rate limit ({model}) - cakam {wait:.0f}s (retry-after={ra}): {why}")
                    time.sleep(wait)
                    continue
                if r.status_code in (401, 402, 403):
                    print(f"   [llm] {model} @ {base}: HTTP {r.status_code} - provider nepouzitelny, preskakujem: {r.text[:160]}")
                    break
                if r.status_code >= 400 and "reasoning_effort" not in r.text:
                    print(f"   [llm] {model} HTTP {r.status_code}: {re.sub(r'\s+', ' ', r.text)[:200]}")
                if r.status_code == 400 and "reasoning_effort" in r.text:
                    # model bez podpory reasoning_effort -> bez neho
                    r = requests.post(base.rstrip("/") + "/chat/completions",
                                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                      json={"model": model, "temperature": temperature, "max_tokens": max_tokens,
                                            "response_format": {"type": "json_object"},
                                            "messages": [{"role": "system", "content": system},
                                                         {"role": "user", "content": prompt}]}, timeout=180)
                r.raise_for_status()
                txt = r.json()["choices"][0]["message"]["content"] or ""
                if not txt.strip():
                    raise ValueError("prazdny obsah (reasoning zjedol tokeny?)")
                return _extract_json(txt)
            except Exception as e:
                last = e
                print(f"   [llm] {model} pokus {att + 1}/{n_tries}: {str(e)[:120]}")
                time.sleep(3 + 4 * att)
    raise RuntimeError(f"LLM zlyhalo: {last}")
