# -*- coding: utf-8 -*-
"""doodle/batch.py - a list of topics -> finished, checked doodle episodes in doodle/queue/, with no human in the loop.

    python doodle/batch.py --topics "Mary Celeste,Tunguska event" [--start 004]     # explicit topics (use ; when a name contains commas)
    python doodle/batch.py --from-bank 100 [--start 004]                            # the next 100 unused topics of the topic bank
    options: [--backend cli|none] [--model sonnet] [--no-review] [--keep] [--bank FILE]

Per topic (details in doodle/BATCH.md):
  1 facts   Wikipedia summary + intro (no key)
  2 brief   1 model call -> brief YAML (8-11 sentences, gold words, a scene paragraph per sentence) + title / description / tags;
            validated, one retry with the errors appended
  3 author  1 model call: make_prompt's author brief -> the complete screenplay.yaml
  4 check   doodle/accept.py; its problems go back to the model (fix call, at most 2 rounds); a draft that does not compile = FAILED
  5 review  stills (hyperframes snapshot) tiled into review.jpg, 1 model call that looks at it (+ 1 fix call if it finds problems)
  6 render  doodle/qa.py must print RESULT: PASS
  7 queue   doodle/queue/<NNN>-<slug>/ (screenplay.yaml + meta.json) and one line in doodle/batch_log.jsonl
The model is the installed `claude -p` command (the owner's subscription). --backend none = plumbing test without any model call
(brief = briefs/celeste.yaml, screenplay = episodes/celeste_sonnet/screenplay.yaml, no review).
Exit codes: 0 all fine, 1 a topic failed, 2 usage error, 3 Claude CLI needs login, 4 usage limit / network / the CLI keeps failing
(run again later: --from-bank skips what is done)."""
import argparse
import collections
import datetime
import json
import math
import os
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import textwrap
import time
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

import yaml
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import auto_writer as W    # noqa: E402  (strip_fences, load_patterns)
import make_prompt as MP   # noqa: E402  (build: the author brief)

for _stream in (sys.stdout, sys.stderr):      # Windows consoles default to cp1250: never die on a print
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

EPISODES, QUEUE, DONE = (os.path.join(HERE, d) for d in ("episodes", "queue", "done"))
LOG = os.path.join(HERE, "batch_log.jsonl")
SAMPLE_BRIEF = os.path.join(HERE, "briefs", "celeste.yaml")
SAMPLE_SCREENPLAY = os.path.join(EPISODES, "celeste_sonnet", "screenplay.yaml")
ACCEPT, QA = os.path.join(HERE, "accept.py"), os.path.join(HERE, "qa.py")
FONT = os.path.join(HERE, "anim_src", "assets", "fonts", "ComicNeue-Bold.ttf")
HF = "hyperframes@0.8.77"
MUSIC = "sneaky_snitch.mp3"
MUSIC_CREDIT = 'Music: "Sneaky Snitch" - Kevin MacLeod (incompetech.com), licensed under CC BY 4.0'
DEFAULT_TAGS = ["#unexplained", "#mystery", "#doodle", "#history", "#shorts"]
WIKI_UA = "UnexplainedDoodleBatch/1.0 (hand-drawn mystery shorts; python-urllib)"
LOGIN_MSG = "Claude CLI needs login: run `claude` and /login"
CALL_TIMEOUT, CALL_RETRIES = 600, 2          # seconds per `claude -p` call, retries after the first attempt
MAX_FIX_ROUNDS = 2
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)       # no console window pops up for child processes on Windows
KEEP_FILES = {"screenplay.yaml", "brief.yaml", "facts.txt", "AUTHOR.md", "calls.json", "review.jpg", "accept.log", "qa.log"}
STATE = {"dir": None, "calls": []}           # the topic being processed: its folder and the usage rows of its model calls


class StageFail(Exception):
    """this topic cannot be finished. status FAILED (content / qa), SKIPPED (no page, duplicate) or, with model=True, ERROR
    (the model call itself failed: --from-bank tries the topic again next time)"""

    def __init__(self, msg, status="FAILED", model=False):
        super().__init__(msg)
        self.status, self.model = status, model


class BatchAbort(Exception):
    """stop the whole batch (login needed, usage limit, CLI or network missing); code = process exit code"""

    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


class ClaudeError(Exception):
    pass


# ------------------------------------------------------------------------------------------ small helpers
def say(msg=""):
    print(msg, flush=True)


def short(s, n=160):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 3] + "..."


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def rel(path):
    try:
        return os.path.relpath(path, REPO).replace("\\", "/")
    except ValueError:                              # a path on another drive (Windows)
        return str(path).replace("\\", "/")


def slugify(text, maxlen=40):
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:maxlen].strip("-") or "topic"


def npx():
    p = shutil.which("npx") or shutil.which("npx.cmd")
    if not p:
        raise RuntimeError("npx not found")
    return p


def run_cmd(cmd, timeout):
    """-> (exit code, stdout + stderr)"""
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=timeout,
                       creationflags=NOWIN)
    return p.returncode, re.sub(r"\x1b\[[0-9;]*m", "", (p.stdout or "") + (p.stderr or ""))


def yaml_err(e):
    return short(str(e), 300)


def yaml_context(e, text):
    mark = getattr(e, "problem_mark", None)
    if mark is None:
        return ""
    lines = text.split("\n")
    a, b = max(0, mark.line - 2), min(len(lines), mark.line + 3)
    return "\n".join(f"{i + 1}: {lines[i]}" for i in range(a, b))


def trim_trailing_prose(text):
    """drop closing remarks of a model ('I hope this helps') after the last YAML line"""
    lines = text.rstrip().split("\n")
    while lines and (not lines[-1].strip() or not re.match(r"^(\s|-(\s|$)|#|[A-Za-z_][\w-]*\s*:)", lines[-1])):
        lines.pop()
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------ the model (claude -p)
def claude_cmd():
    parts = shlex.split(os.environ.get("CLAUDE_BIN") or "claude")      # CLAUDE_BIN: a stand-in for tests, forward slashes on Windows
    exe = shutil.which(parts[0])
    if not exe:
        raise BatchAbort(2, f"Claude CLI not found ({parts[0]}): install Claude Code, or set CLAUDE_BIN")
    return [exe] + parts[1:]


def record_call(row):
    STATE["calls"].append(row)
    if STATE["dir"]:
        write_text(os.path.join(STATE["dir"], "calls.json"), json.dumps(STATE["calls"], ensure_ascii=False, indent=1) + "\n")


def parse_cli_json(out):
    out = (out or "").strip()
    if not out:
        return None
    try:
        d = json.loads(out)
    except ValueError:
        i = out.rfind("\n{")
        try:
            d = json.loads(out[i + 1:]) if i >= 0 else None
        except ValueError:
            return None
    if isinstance(d, list):
        d = next((x for x in reversed(d) if isinstance(x, dict) and x.get("type") == "result"), None)
    return d if isinstance(d, dict) else None


def auth_error(d, msg):
    if d and d.get("api_error_status") == 401:
        return True
    return bool(re.search(r"oauth|not logged in|/login|authenticat|invalid (?:api )?key|token (?:has )?expired|expired token", msg, re.I))


def limit_error(d, msg):
    return bool((d or {}).get("api_error_status") in (429, 529) or
                re.search(r"usage limit|limit reached|rate.?limit|too many requests|overloaded|quota|credit balance", msg, re.I))


def call_claude(prompt, system, model="sonnet", tools="", label="call"):
    """One `claude -p` call (the owner's subscription): prompt on stdin, the answer text back. 600 s timeout, 2 retries; every attempt
    is logged (tokens, cost, seconds) into <episode>/calls.json. A CLI that needs a login stops the whole batch (exit code 3)."""
    cmd = claude_cmd() + ["-p", "--model", model, "--output-format", "json", "--system-prompt", system,
                          "--tools", tools, "--safe-mode", "--no-session-persistence"]
    if tools:
        cmd += ["--allowed-tools", tools]
    err, limited = "", False
    for attempt in range(1, CALL_RETRIES + 2):
        t0 = time.time()
        d, text, msg = None, "", ""
        try:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=CALL_TIMEOUT, cwd=REPO, creationflags=NOWIN)
            d = parse_cli_json(p.stdout)
            text = d.get("result") if d and isinstance(d.get("result"), str) else ""
            if d is None or d.get("is_error") or not text.strip():
                msg = (text or p.stderr or p.stdout or f"exit code {p.returncode}").strip()
        except subprocess.TimeoutExpired:
            msg = f"timeout after {CALL_TIMEOUT} s"
        except OSError as e:
            raise BatchAbort(2, f"cannot run the Claude CLI: {e}")
        u = (d or {}).get("usage") or {}
        row = {"n": len(STATE["calls"]) + 1, "label": label, "model": model, "tools": tools, "attempt": attempt,
               "ok": not msg, "seconds": round(time.time() - t0, 1), "duration_ms": (d or {}).get("duration_ms"),
               "prompt_chars": len(prompt), "reply_chars": len(text),
               "input_tokens": u.get("input_tokens") or 0, "cache_creation": u.get("cache_creation_input_tokens") or 0,
               "cache_read": u.get("cache_read_input_tokens") or 0, "output_tokens": u.get("output_tokens") or 0,
               "cost_usd": (d or {}).get("total_cost_usd") or 0}
        if msg:
            row["error"] = short(msg, 300)
        record_call(row)
        if not msg:
            return text
        if auth_error(d, msg):
            raise BatchAbort(3, LOGIN_MSG)
        err, limited = msg, limit_error(d, msg)
        if attempt <= CALL_RETRIES:
            time.sleep(10 * attempt if limited else 3)
    if limited:
        raise BatchAbort(4, f"Claude usage or rate limit ({short(err, 160)}) - run again later, finished topics are skipped")
    raise ClaudeError(short(err, 300))


def usage_totals(calls):
    tin = sum((c.get("input_tokens") or 0) + (c.get("cache_creation") or 0) + (c.get("cache_read") or 0) for c in calls)
    return len(calls), tin, sum(c.get("output_tokens") or 0 for c in calls), sum(c.get("cost_usd") or 0 for c in calls)


# ------------------------------------------------------------------------------------------ 1 facts (Wikipedia, no key)
_SSL = {"ctx": None, "certifi_tried": False}


def _urlopen(url):
    """urllib with the system CA store; if that fails on a certificate (an expired root in the Windows store makes
    en.wikipedia.org fail on some PCs) once more with the certifi bundle, which is then used for all later requests"""
    req = urllib.request.Request(url, headers={"User-Agent": WIKI_UA, "Accept": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=30, context=_SSL["ctx"])
    except urllib.error.URLError as e:
        if not isinstance(e.reason, ssl.SSLCertVerificationError) or _SSL["certifi_tried"]:
            raise
        _SSL["certifi_tried"] = True
        try:
            import certifi
            _SSL["ctx"] = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            raise e
        return urllib.request.urlopen(req, timeout=30, context=_SSL["ctx"])


def http_json(url):
    """GET -> parsed JSON; None for 404; BatchAbort(4) when Wikipedia stays unreachable"""
    last = None
    for i in range(3):
        try:
            with _urlopen(url) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = e
        time.sleep(2 * (i + 1))
    raise BatchAbort(4, f"Wikipedia is not reachable ({last}) - check the network and run again")


def wiki_page(title):
    """-> (canonical title, summary, intro extract) or None when there is no usable article"""
    s = http_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"), safe=""))
    if not s or s.get("type") == "disambiguation":
        return None
    canon = s.get("title") or title
    d = http_json("https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&format=json&redirects=1&titles="
                  + urllib.parse.quote(canon, safe=""))
    pages = ((d or {}).get("query") or {}).get("pages") or {}
    extract = next((p.get("extract") or "" for p in pages.values() if "missing" not in p), "").strip()
    summary = (s.get("extract") or "").strip()
    return (canon, summary, extract) if (summary or extract) else None


def fetch_facts(topic):
    """-> {"title", "text", "note"} or None (no page, also not through the search API)"""
    page, note = wiki_page(topic), ""
    if not page:
        d = http_json("https://en.wikipedia.org/w/api.php?action=query&list=search&srlimit=1&format=json&srsearch="
                      + urllib.parse.quote(topic))
        hits = ((d or {}).get("query") or {}).get("search") or []
        if hits:
            page, note = wiki_page(hits[0]["title"]), f" (found by search: {hits[0]['title']})"
    if not page:
        return None
    canon, summary, extract = page
    parts = [f"WIKIPEDIA ARTICLE: {canon}"]
    if summary:
        parts.append("SUMMARY:\n" + summary)
    if extract and extract != summary:
        parts.append("INTRO:\n" + extract[:6000])
    return {"title": canon, "text": "\n\n".join(parts), "note": note}


# ------------------------------------------------------------------------------------------ 2 brief
BRIEF_SYSTEM = ("You are a story editor for short documentary doodle videos. Reply with ONE YAML document only: "
                "no prose before or after it, no code fences.")

BRIEF_PROMPT = """Write the production brief for ONE short vertical video (about 40 seconds) about a real, documented mystery.
A narrator reads 8-11 short sentences; afterwards a hand-drawn animation is built scene by scene from your `must` paragraphs.

TOPIC: @@TOPIC@@

FACTS: the Wikipedia text below is your ONLY source. Do not add any fact, name, number or date that is not in it.
-----
@@FACTS@@
-----

Reply with ONE YAML document and nothing else, in exactly the format of the EXAMPLE at the end (same keys in the same order:
name, title, description, tags, header, scenes; `header` is a literal block). Your reply starts with the line `name: ...`. Rules:

NARRATION (`sentences:` inside `header`)
- 8 to 11 sentences with the keys s1, s2, ... in order; at most 105 words in total; present tense; short, concrete, easy to hear.
- s1 is a hook that names the place and the time. The last sentence leaves the mystery open (what nobody knows or ever found).
- Numbers are written as words ("seventeen hundred", "nine days"); only years stay digits ("1872"). No abbreviations, symbols or brackets.
- Put EVERY sentence in double quotes and use no other double quotes inside it.
- Every sentence must be drawable. If people died or vanished and the facts say so, you may say it in the narration, but the
  pictures (the `must` texts) never show blood, bodies, injuries or violence: show the empty place, objects, traces and reactions.

GOLD (`gold:` inside `header`): 3 to 5 big yellow words that slam onto the screen on key words
- Copy the syntax of the example: kind stamp (a label) or kind counter (counts up to a number; its label is digits only).
- `word` = a word exactly as written in one sentence (case and punctuation ignored); if it occurs in several sentences write
  sentence/word, e.g. s10/ever. `label` = what is shown, at most 12 characters (a year, "9 DAYS", "NEVER FOUND").
- `until` ends the gold: "word:X", "s5.end" or "s10.end+0.6", inside the same scene. Each gold must end before the next one starts.
- Keep voice, tail and music exactly as in the example; loop.at is "<last sentence key>.end+0.55".

SCENES
- One scene per sentence (or per two neighbouring sentences). `sents` lists their keys; every sentence belongs to exactly one scene,
  in order. `id` = one short lowercase word (letters and digits).
- `must` = ONE vivid paragraph (25-60 words): what the viewer sees and what moves - the setting, the main thing BIG in the picture,
  who does what, one camera move. Only things that can be drawn in ink: stick-figure people, buildings, ships, animals, objects,
  weather, maps. Everything the sentence names is visible. No written text on screen.

TITLE, DESCRIPTION, TAGS (for the video platform)
- title: at most 6 words, no digits, no dash or hyphen, not the word "you", no "$". Curious, not clickbait.
- description: 1-2 sentences that tell the hook, using only the facts above.
- tags: exactly 5, lowercase, each starting with #; the first two are #unexplained and #mystery, then two specific to the topic, then #shorts.
- name: @@SLUG@@

EXAMPLE (a finished brief about the Mary Celeste; write yours for the TOPIC above and copy only its structure and level of detail):
@@EXAMPLE@@"""

VIOLENCE_RE = re.compile(r"\b(blood\w*|bleed\w*|gore|gory|corpses?|dead bod\w+|stabb\w*|murder\w*|kill\w*|wounds?|wounded|mutilat\w*|"
                         r"decapitat\w*|severed|gunshots?|hanged|lynch\w*)\b", re.I)
EXAMPLE_META = {"title": "The Ship Found Without a Crew",
                "description": "In December 1872 a ship was found drifting near the Azores with her cargo untouched and her lifeboat gone. "
                               "Ten people were never seen again.",
                "tags": ["#unexplained", "#mystery", "#maryceleste", "#ghostship", "#shorts"]}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


class Narration:
    """the sentences the way sp.py reads them: words = text.split(), compared with case and punctuation ignored"""

    def __init__(self, sents):
        self.keys = list(sents)
        self.words = [(k, _norm(w)) for k in self.keys for w in str(sents[k]).split()]

    def find(self, spec):
        """index of the word named by a gold `word` (word, sK/word, word#2, optional word: prefix), or None"""
        spec = str(spec).strip()
        if spec.startswith("word:"):
            spec = spec[5:]
        if spec.endswith(".end"):
            spec = spec[:-4]
        nth = 0
        if "#" in spec:
            spec, n = spec.split("#", 1)
            if not n.isdigit() or int(n) < 1:
                return None
            nth = int(n) - 1
        key = None
        if "/" in spec:
            key, spec = spec.split("/", 1)
        if not _norm(spec):
            return None
        hits = [i for i, (k, w) in enumerate(self.words) if w == _norm(spec) and (key is None or k == key)]
        return hits[nth] if len(hits) > nth else None

    def until(self, expr):
        """word index where a gold `until` ends; None = cannot compare (seconds), False = not understood"""
        base = re.sub(r"(?:\s*[+-]\s*\d+(?:\.\d+)?)+\s*$", "", str(expr).strip()).strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", base) or base in ("scene", "scene.end", "prev", "prev.end"):
            return None
        if base.startswith("word:"):
            i = self.find(base)
            return False if i is None else i
        k = base[:-4] if base.endswith(".end") else base
        idx = [i for i, (kk, _) in enumerate(self.words) if kk == k]
        if not idx:
            return False
        return idx[-1] if base.endswith(".end") else idx[0]


def num(v, default, lo=None, hi=None):
    try:
        x = float(v)
    except (TypeError, ValueError):
        x = float(default)
    if lo is not None:
        x = max(lo, x)
    if hi is not None:
        x = min(hi, x)
    return int(x) if x == int(x) else round(x, 2)


def yflow(v):
    """a value as a YAML flow item (strings always double-quoted)"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {yflow(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(yflow(x) for x in v) + "]"
    s = str(v)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s) and s.lower() not in ("y", "n", "yes", "no", "on", "off", "true", "false", "null"):
        return s                                   # a plain word (kind: stamp, word: seventeen) - YAML 1.1 booleans stay quoted
    return json.dumps(s, ensure_ascii=False)


def header_text(title, sents, golds):
    """the canonical episode header (title ... gold) that the author copies verbatim into the screenplay"""
    last = list(sents)[-1]
    lines = [f"title: {json.dumps(title, ensure_ascii=False)}",
             "voice: {voice: am_michael, speed: 1.10, pause: 0.30}", "tail: 2.0", f"music: {MUSIC}",
             f'loop: {{at: "{last}.end+0.55", dur: 1.3}}', "sentences:"]
    lines += [f"  {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in sents.items()]
    lines.append("gold:")
    lines += ["  - " + yflow(g) for g in golds]
    return "\n".join(lines) + "\n"


def title_problems(t):
    if not t:
        return ["title is missing"]
    out = []
    if len(t.split()) > 6:
        out.append(f"title has {len(t.split())} words: at most 6")
    if re.search(r"\d", t):
        out.append("title must not contain digits (write numbers as words or leave them out)")
    if re.search(r"[-‐-―−]", t):
        out.append("title must not contain a dash or hyphen")
    if re.search(r"\byou(?:r|rs|rself|'re|'ll|'ve|'d)?\b", t, re.I):
        out.append('title must not contain "you"')
    if "$" in t:
        out.append("title must not contain $")
    return out


def norm_tags(tags):
    """-> 5 clean tags (lowercase, #...), #unexplained #mystery first; fewer than 5 usable ones -> []"""
    if isinstance(tags, str):
        tags = re.split(r"[\s,]+", tags)
    out = ["#unexplained", "#mystery"]
    for t in tags if isinstance(tags, list) else []:
        t = "#" + re.sub(r"[^a-z0-9_]", "", str(t).lower())
        if len(t) > 1 and t not in out:
            out.append(t)
    return out[:5] if len(out) >= 5 else []


def validate_brief(B, slug, need_meta=True):
    """-> (errors, brief). brief = the normalised dict {name, title, description, tags, header (text), scenes} or None.
    Constants (voice, tail, music, loop) are forced to the example's values; the rest is checked the way sp.py will read it."""
    if not isinstance(B, dict):
        return ["the answer is not a YAML mapping with the keys name, title, description, tags, header, scenes"], None
    head = B.get("header")
    if isinstance(head, str):
        try:
            head = yaml.safe_load(head)
        except yaml.YAMLError as e:
            return [f"`header` is not valid YAML ({yaml_err(e)}); put every sentence in double quotes"], None
    if not isinstance(head, dict):
        return ["`header` must be a literal block (header: |) holding title, voice, tail, music, loop, sentences and gold"], None
    errs, sents = [], {}
    raw = head.get("sentences")
    if not isinstance(raw, dict) or not raw:
        errs.append("header.sentences must be a mapping s1, s2, ...")
    else:
        for k, v in raw.items():
            if v is None or isinstance(v, (dict, list)) or not str(v).strip():
                errs.append(f"sentence {k} is not a plain text line (put it in double quotes)")
            else:
                sents[str(k)] = " ".join(str(v).split())
        keys = list(sents)
        if keys != [f"s{i}" for i in range(1, len(keys) + 1)]:
            errs.append("sentence keys must be s1, s2, s3, ... in order, without gaps")
        if not 8 <= len(keys) <= 11:
            errs.append(f"{len(keys)} sentences: write 8 to 11")
        words = sum(len(v.split()) for v in sents.values())
        if words > 110:
            errs.append(f"the narration has {words} words: at most 105 (shorten sentences, keep 8-11 of them)")
    nar = Narration(sents)
    golds, spans = [], []
    gl = head.get("gold")
    if not isinstance(gl, list) or not 2 <= len(gl) <= 6:
        errs.append("header.gold must be a list of 3 to 5 entries")
        gl = [] if not isinstance(gl, list) else gl
    for n, g in enumerate(gl, 1):
        if not isinstance(g, dict):
            errs.append(f"gold #{n} is not a mapping like {{word: ..., label: ..., kind: stamp, ...}}")
            continue
        word, kind = g.get("word"), g.get("kind", "stamp")
        label = " ".join(str(g.get("label", "")).split())
        pos = nar.find(word) if word is not None else None
        if pos is None:
            errs.append(f"gold #{n}: word {word!r} is not a word of the sentences (copy it exactly; sK/word if it occurs twice)")
        if not label:
            errs.append(f"gold #{n}: label is missing")
        if kind not in ("stamp", "counter"):
            errs.append(f"gold #{n}: kind must be stamp or counter")
        if kind == "counter" and not re.fullmatch(r"\d+", label):
            errs.append(f"gold #{n}: a counter label must be digits only (use kind stamp for text)")
        end = nar.until(g["until"]) if g.get("until") is not None else False
        if end is False:
            errs.append(f'gold #{n}: until must be "word:X", "sK.end" or "sK.end+0.6"')
        elif end is not None and pos is not None and end < pos:
            errs.append(f"gold #{n}: until ends before its own word")
        longest = max([len(p) for p in label.split("|")] or [1]) or 1
        item = {"word": str(word), "label": label, "kind": kind, "top": num(g.get("top"), 120, 100, 150),
                "size": num(g.get("size"), 110, 60, max(60, min(120, int(600 / (0.62 * longest)))))}
        if kind == "counter":
            item["dur"] = num(g.get("dur"), 0.9, 0.4, 2.0)
        item["until"] = str(g.get("until"))
        if kind == "stamp":
            st = g.get("stamp") if isinstance(g.get("stamp"), dict) else {}
            item["stamp"] = {"from": num(st.get("from"), 2.4), "r0": num(st.get("r0"), -12), "r1": num(st.get("r1"), -4)}
        golds.append(item)
        spans.append((pos, end, n))
    ordered = sorted((s for s in spans if s[0] is not None), key=lambda s: s[0])
    for a, b in zip(ordered, ordered[1:]):
        if a[1] not in (None, False) and a[1] >= b[0]:
            errs.append(f"gold #{a[2]} is still on screen when gold #{b[2]} stamps: end it earlier with until")
    scenes, order = [], []
    sc_list = B.get("scenes")
    if not isinstance(sc_list, list) or not sc_list:
        errs.append("scenes must be a list of {id, sents, must}")
        sc_list = []
    ids = set()
    for n, sc in enumerate(sc_list, 1):
        if not isinstance(sc, dict):
            errs.append(f"scene #{n} is not a mapping")
            continue
        sid, ks = str(sc.get("id", "")).strip(), sc.get("sents")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", sid):
            errs.append(f"scene #{n}: id must be one lowercase word (letters, digits, _)")
        elif sid in ids:
            errs.append(f"scene id {sid} is used twice")
        ids.add(sid)
        if isinstance(ks, str):
            ks = [x for x in re.split(r"[\s,\[\]]+", ks) if x]
        if not isinstance(ks, list) or not ks:
            errs.append(f"scene {sid}: sents must list sentence keys like [s1, s2]")
            ks = []
        ks = [str(k) for k in ks]
        order += ks
        must = " ".join(str(sc.get("must") or "").split())
        if len(must.split()) < 12:
            errs.append(f"scene {sid}: `must` needs a vivid paragraph of what is seen and what moves")
        m = VIOLENCE_RE.search(must)
        if m:
            errs.append(f"scene {sid}: `must` mentions '{m.group(0)}': pictures show no violence, blood or bodies - show the empty place, objects or reactions")
        scenes.append({"id": sid, "sents": ks, "must": must})
    if sents and order != list(sents):
        missing = [k for k in sents if k not in order]
        extra = [k for k in order if k not in sents]
        if missing:
            errs.append(f"sentences without a scene: {missing} (every sentence belongs to exactly one scene)")
        if extra:
            errs.append(f"scenes name sentences that do not exist: {extra}")
        if not missing and not extra:
            errs.append("scenes must list the sentences in order, each exactly once")
    title = " ".join(str(B.get("title") or "").split())
    desc = " ".join(str(B.get("description") or "").split())
    tags = norm_tags(B.get("tags"))
    if need_meta:
        errs += title_problems(title)
        if not desc:
            errs.append("description is missing (1-2 sentences)")
        desc = " ".join(s.strip() for s in re.findall(r"[^.!?]+[.!?]+(?:\s|$)|[^.!?]+$", desc)[:2])[:300]
        if not tags:
            errs.append("tags must be 5 lowercase #tags, the first two #unexplained #mystery")
    if errs:
        return errs, None
    htitle = " ".join(str(head.get("title") or title or slug.replace("-", " ").title()).split())
    return [], {"name": slug, "title": title, "description": desc, "tags": tags,
                "header": header_text(htitle, sents, golds), "scenes": scenes}


def parse_brief(reply):
    txt = W.strip_fences(reply).replace("\r\n", "\n")
    m = re.search(r"^name\s*:", txt, re.M)
    txt = trim_trailing_prose(txt[m.start():] if m else txt)
    try:
        return yaml.safe_load(txt), []
    except yaml.YAMLError as e:
        return None, [f"the answer is not valid YAML ({yaml_err(e)}); check indentation and quote the sentences"]


def brief_yaml(b):
    """a brief in the format of doodle/briefs/celeste.yaml (header as a literal block, must as folded blocks)"""
    out = [f"name: {b['name']}"]
    for k in ("title", "description"):
        if b.get(k):
            out.append(f"{k}: {json.dumps(b[k], ensure_ascii=False)}")
    if b.get("tags"):
        out.append(f"tags: {json.dumps(b['tags'], ensure_ascii=False)}")
    out.append("header: |")
    out += [("  " + ln) if ln else "" for ln in b["header"].rstrip("\n").split("\n")]
    out.append("scenes:")
    for sc in b["scenes"]:
        out += [f"  - id: {sc['id']}", f"    sents: [{', '.join(sc['sents'])}]", "    must: >-"]
        out += ["      " + ln for ln in textwrap.wrap(sc["must"], 118, break_long_words=False, break_on_hyphens=False)]
    return "\n".join(out) + "\n"


def sample_brief(slug, need_meta=False):
    errs, b = validate_brief(yaml.safe_load(read_text(SAMPLE_BRIEF)), slug, need_meta=need_meta)
    if errs:
        raise StageFail("the sample brief doodle/briefs/celeste.yaml is invalid: " + "; ".join(errs[:3]))
    return b


def example_text():
    b = dict(sample_brief("mary-celeste"), **EXAMPLE_META)
    return brief_yaml(b)


def meta_from_brief(b):
    head = yaml.safe_load(b["header"])
    return {"title": b.get("title") or str(head.get("title") or b["name"]),
            "description": b.get("description") or " ".join(list(head["sentences"].values())[:2]),
            "tags": b.get("tags") or DEFAULT_TAGS, "music_credit": MUSIC_CREDIT}


# ------------------------------------------------------------------------------------------ 3 author, 4 check
AUTHOR_SYSTEM = ("You are an expert animation screenplay author. Output ONLY the complete screenplay.yaml content: the header "
                 "verbatim first, then styles, shapes, scenes. No prose, no explanations, no code fences.")
FIX_TAIL = """

Fix every problem listed under PROBLEMS: and change nothing else that already works. The header (title ... gold) stays exactly as it is.
Reply with the COMPLETE corrected file - header first, then styles, shapes, scenes - as plain text: no diff, no commentary, no code fences."""
STOP = set("a an the and or of to in on at by with from into over under is are was were be been it its his her their this that these those "
           "as up down out off then while one two three each all no not only more most some who what which when where how".split())


def choose_patterns(brief, n=4):
    """pattern scenes for the author: the two that suit every story (close-up of a small thing, quiet ending) + the ones whose
    description shares most words with the scene paragraphs"""
    pats = W.load_patterns([])
    if not pats:
        return []
    mine = set(re.findall(r"[a-z]+", " ".join(sc["must"] for sc in brief["scenes"]).lower())) - STOP
    docs = {k: set(re.findall(r"[a-z]+", p["use"].lower())) - STOP for k, p in pats.items()}
    df = collections.Counter(w for d in docs.values() for w in d)
    score = {k: sum(math.log(1 + len(docs) / df[w]) for w in d & mine) for k, d in docs.items()}
    chosen = [k for k in ("devon.measure", "devon.dusk") if k in pats]
    for k in sorted(pats, key=lambda k: (-score[k], k)):
        if len(chosen) < n and k not in chosen and score[k] > 0:
            chosen.append(k)
    for k in ("devon.night", "carancas.village", "devon.yard", "milky.night"):
        if len(chosen) < n and k in pats and k not in chosen:
            chosen.append(k)
    return chosen[:n]


def clean_screenplay(reply, header):
    """the model's answer -> file text: fences and prose around it removed, our canonical header put in front of
    styles / shapes / scenes (so the narration and gold words are exactly the validated ones), #rrggbb colours quoted"""
    txt = W.strip_fences(reply).replace("\r\n", "\n")
    m = re.search(r"^(styles|shapes|scenes|sfx)\s*:", txt, re.M)
    body = trim_trailing_prose(txt[m.start():] if m else txt)
    body = re.sub(r"(:\s*)(#[0-9a-fA-F]{3,8})\b", r'\1"\2"', body)
    body = re.sub(r"(\[\s*|,\s*)(#[0-9a-fA-F]{6})\b", r'\1"\2"', body)
    return header.rstrip() + "\n" + body.strip() + "\n"


class Ctx:
    """everything one topic needs on its way through the stages"""

    def __init__(self, topic, slug, args):
        self.topic, self.slug, self.args = topic, slug, args
        self.ep = os.path.join(EPISODES, slug)
        self.sp = os.path.join(self.ep, "screenplay.yaml")
        self.t0 = time.time()
        self.facts = self.brief = None
        self.author_md = ""
        self.queue = ""
        self.fix_rounds, self.problems_first, self.problems_left, self.review = 0, None, None, "skipped"

    def say(self, msg):
        say(f"[{self.slug} +{time.time() - self.t0:.0f}s] {msg}")

    def ask(self, prompt, system, label, tools=""):
        try:
            return call_claude(prompt, system, self.args.model, tools=tools, label=label)
        except ClaudeError as e:
            raise StageFail(f"model call failed ({label}): {e}", model=True)

    def write_screenplay(self, reply):
        write_text(self.sp, clean_screenplay(reply, self.brief["header"]))


def fresh_dir(path):
    """an empty work folder for the topic; an earlier run of this script is wiped, a folder somebody else made is not touched"""
    if os.path.isdir(path):
        if os.listdir(path) and not any(os.path.exists(os.path.join(path, m)) for m in ("brief.yaml", "facts.txt", "calls.json", "AUTHOR.md")):
            raise StageFail(f"{rel(path)} exists and was not made by batch.py: rename or delete it")
        shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
    STATE["dir"], STATE["calls"] = path, []


def stage_facts(c):
    try:
        f = fetch_facts(c.topic)
    except BatchAbort as e:
        if c.args.backend != "none":
            raise
        c.say(f"facts: skipped ({e}); not needed for backend none")
        c.facts = ""
        return
    if not f:
        if c.args.backend == "none":
            c.say("facts: no Wikipedia page (not needed for backend none)")
            c.facts = ""
            return
        raise StageFail("no Wikipedia page for this topic (search found nothing either)", status="SKIPPED")
    c.facts = f["text"]
    write_text(os.path.join(c.ep, "facts.txt"), c.facts + "\n")
    c.say(f"facts: {f['title']}{f['note']}, {len(c.facts)} chars")


def stage_brief(c):
    if c.args.backend == "none":
        c.brief = sample_brief(c.slug)
        c.say("brief: briefs/celeste.yaml (backend none)")
    else:
        prompt = (BRIEF_PROMPT.replace("@@TOPIC@@", c.topic).replace("@@FACTS@@", c.facts[:7000])
                  .replace("@@SLUG@@", c.slug).replace("@@EXAMPLE@@", example_text()))
        c.say("brief: model call")
        reply = c.ask(prompt, BRIEF_SYSTEM, "brief")
        B, errs = parse_brief(reply)
        if not errs:
            errs, c.brief = validate_brief(B, c.slug)
        if errs:
            c.say("brief: invalid, one retry: " + short("; ".join(errs), 200))
            retry = (prompt + "\n\nYOUR PREVIOUS ANSWER:\n" + reply + "\n\nPROBLEMS - fix all of them and reply with the complete "
                     "corrected YAML document only:\n" + "\n".join("- " + e for e in errs))
            reply = c.ask(retry, BRIEF_SYSTEM, "brief-retry")
            B, errs = parse_brief(reply)
            if not errs:
                errs, c.brief = validate_brief(B, c.slug)
            if errs:
                raise StageFail("brief invalid after one retry: " + short("; ".join(errs), 300))
    write_text(os.path.join(c.ep, "brief.yaml"), brief_yaml(c.brief))
    head = yaml.safe_load(c.brief["header"])
    c.say(f"brief: {len(head['sentences'])} sentences, {len(head['gold'])} gold words, {len(c.brief['scenes'])} scenes"
          + (f", title \"{c.brief['title']}\"" if c.brief.get("title") else ""))


def stage_author(c):
    c.author_md = MP.build(c.brief, c.ep, choose_patterns(c.brief), text_only=True)
    write_text(os.path.join(c.ep, "AUTHOR.md"), c.author_md)
    if c.args.backend == "none":
        if not os.path.isfile(SAMPLE_SCREENPLAY):
            raise StageFail(f"backend none needs {rel(SAMPLE_SCREENPLAY)}")
        reply = read_text(SAMPLE_SCREENPLAY)
        c.say("author: episodes/celeste_sonnet/screenplay.yaml (backend none)")
    else:
        c.say(f"author: model call ({len(c.author_md) // 1024} kB brief, answer takes a few minutes)")
        reply = c.ask(c.author_md, AUTHOR_SYSTEM, "author")
    c.write_screenplay(reply)


def fix_screenplay(c, problems, label):
    prompt = (c.author_md + "\n\nYOUR SCREENPLAY:\n" + read_text(c.sp) + "\n\nPROBLEMS:\n" + problems.strip()[:8000] + FIX_TAIL)
    c.write_screenplay(c.ask(prompt, AUTHOR_SYSTEM, label))


def precheck(c):
    """cheap structural check before accept.py (which would only crash on broken YAML) -> problem text or ''"""
    text = read_text(c.sp)
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return ("COMPILE ERROR: the file is not valid YAML: " + yaml_err(e) + "\nLines around the error (line number: text):\n"
                + yaml_context(e, text))
    if not isinstance(doc, dict) or not isinstance(doc.get("scenes"), list) or not doc["scenes"]:
        return "COMPILE ERROR: the file has no top-level `scenes:` list (header, then styles, shapes, scenes)"
    return ""


def accept_step(c):
    """-> (exit code, output, number of problems, compiled?)"""
    pre = precheck(c)
    if pre:
        return 1, pre, 1, False
    try:
        code, out = run_cmd([sys.executable, ACCEPT, c.ep], 1800)
    except subprocess.TimeoutExpired:
        code, out = 1, "COMPILE ERROR: accept.py timed out after 1800 s"
    write_text(os.path.join(c.ep, "accept.log"), out)
    m = re.search(r"RESULT: (\d+) problems", out)
    n = int(m.group(1)) if m else (0 if code == 0 else 1)
    return code, out, n, "COMPILE OK" in out


def accept_line(out, n, ok):
    if not ok:
        m = re.search(r"(?:COMPILE ERROR|PROBLEM):.*", out)
        return short(m.group(0) if m else out, 150)
    return "compile ok, " + (f"{n} problem(s)" if n else "no problems")


def stage_check(c):
    code, out, n, ok = accept_step(c)
    c.problems_first = n if ok else max(n, 1)
    best = (read_text(c.sp), n) if ok else None
    rounds = 0
    while code != 0 and rounds < MAX_FIX_ROUNDS and c.args.backend != "none":
        c.say(f"accept: {accept_line(out, n, ok)} -> fix round {rounds + 1}/{MAX_FIX_ROUNDS}")
        try:
            fix_screenplay(c, out, f"fix{rounds + 1}")
        except StageFail as e:
            if not e.model:
                raise
            c.say(f"fix call failed ({e}); going on with what we have")
            break
        rounds += 1
        code, out, n, ok = accept_step(c)
        if ok and (best is None or n <= best[1]):
            best = (read_text(c.sp), n)
    c.fix_rounds = rounds
    if best is None:
        raise StageFail(f"does not compile after {rounds} fix round(s): {accept_line(out, n, ok)}")
    if read_text(c.sp) != best[0]:          # the last draft is worse than an earlier one that compiled: go back and recompile it
        write_text(c.sp, best[0])
        code, out, n, ok = accept_step(c)
        if not ok:
            raise StageFail("the best draft no longer compiles: " + accept_line(out, n, ok))
    c.problems_left = n
    c.say(f"accept: {accept_line(out, n, ok)}" + (f" after {rounds} fix round(s)" if rounds else ""))


# ------------------------------------------------------------------------------------------ 5 review
REVIEW_SYSTEM = "You are a strict animation reviewer. You judge finished frames against the narration. Answer with the JSON only."


def review_times(ep):
    """(time, scene id) pairs at 35 % and 75 % of every scene window, ascending. A scene lasts from its start to `end` in
    work/timing.json (t1 of the first scene is the loop seam = whole video, so t1 is not used)."""
    t = json.loads(read_text(os.path.join(ep, "work", "timing.json")))
    total, out = float(t["total"]), []
    limit = min(total, float((t.get("loop") or {}).get("t0", total))) - 0.1      # the loop seam (page lifts back to scene 1) is no scene
    for s in t["scenes"]:
        a, b = float(s["t0"]) + 0.1, float(s.get("end") or s["t1"])
        if b - a < 0.6:
            a, b = float(s["t0"]), max(b, float(s["t0"]) + 0.6)
        for frac in (0.35, 0.75):
            out.append((round(min(a + frac * (b - a), limit), 2), s["id"]))
    return sorted(out)


def snapshots(c, times):
    """hyperframes snapshot at the given times -> [(png path, label)]"""
    out_dir = os.path.join(c.ep, "review")
    shutil.rmtree(out_dir, ignore_errors=True)
    code, log = run_cmd([npx(), "--yes", HF, "snapshot", c.ep, "-o", out_dir, "--at", ",".join(f"{t:g}" for t, _ in times),
                         "--no-end", "--describe", "false"], 900)
    files = sorted((f for f in (os.listdir(out_dir) if os.path.isdir(out_dir) else []) if re.fullmatch(r"frame-\d+-at-.*\.png", f)),
                   key=lambda f: int(re.match(r"frame-(\d+)", f).group(1)))
    if len(files) < len(times):
        raise RuntimeError(f"snapshot gave {len(files)} of {len(times)} frames (exit {code}): {short(log, 200)}")
    return [(os.path.join(out_dir, f), f"{sid} {t:.1f}s") for f, (t, sid) in zip(files, times)]


def _font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def tile_sheet(frames, out_path):
    """[(png, label)] -> ONE jpeg, tiles in reading order (the two stills of a scene next to each other), label under each tile.
    The grid is the one with the biggest tiles inside 1568 px (the size a model looks at without shrinking it)."""
    n, side, label_h = len(frames), 1568, 30
    best = None
    for cols in range(1, n + 1):
        tw = min(side // cols, 360)
        th, rows = round(tw * 1280 / 720), math.ceil(n / cols)
        if rows * (th + label_h) <= side and (best is None or tw >= best[1]):
            best = (cols, tw, th, rows)
    if best is None:
        cols = max(1, math.ceil(n / 3))
        tw = side // cols
        best = (cols, tw, round(tw * 1280 / 720), math.ceil(n / cols))
    cols, tw, th, rows = best
    sheet = Image.new("RGB", (cols * tw, rows * (th + label_h)), "white")
    d = ImageDraw.Draw(sheet)
    for i, (path, label) in enumerate(frames):
        x, y = (i % cols) * tw, (i // cols) * (th + label_h)
        with Image.open(path) as im:
            sheet.paste(im.convert("RGB").resize((tw - 4, th), Image.LANCZOS), (x + 2, y))
        d.rectangle([x + 1, y, x + tw - 2, y + th + label_h - 1], outline=(190, 190, 190))
        size = 20
        font = _font(size)
        while size > 10 and d.textlength(label, font=font) > tw - 8:
            size -= 1
            font = _font(size)
        d.text((x + 5, y + th + 4), label, fill="black", font=font)
    sheet.save(out_path, "JPEG", quality=88)


def review_prompt(c, sheet):
    doc = yaml.safe_load(read_text(c.sp))
    sents = doc.get("sentences") or {}
    intended = {s["id"]: s["must"] for s in c.brief["scenes"]}
    lines = []
    for sc in doc.get("scenes") or []:
        sid = sc.get("id")
        line = f"- scene `{sid}`: the narrator says \"{' '.join(str(sents.get(k, '')) for k in sc.get('sents') or [])}\""
        if sid in intended:
            line += f"\n  intended picture: {intended[sid]}"
        lines.append(line)
    return (f"A 40-second vertical doodle animation (720x1280, ink on paper, stick figures) is finished and about to be published.\n"
            f"Look at its contact sheet: use the Read tool on exactly this file: {sheet.replace(os.sep, '/')}\n"
            f"Every tile is one full frame of the video (captions sit at the bottom), labelled with the scene id and the time in seconds; "
            f"each scene has two tiles, one early and one late in the scene.\n\nNARRATION AND SCENES\n" + "\n".join(lines) + "\n\n"
            "Judge ONLY these three things:\n"
            "1. Does each picture show what its sentence says (everything the sentence names is on screen, nothing contradicts it)?\n"
            "2. Is the main subject big and readable on a phone (about a third of the frame height; small things in close-up)?\n"
            "3. Is anything missing or wrong (floating or tiny objects, a person standing on water, empty paper, wrong proportions)?\n"
            "Ignore taste, colours, line quality, captions and the big gold words.\n\n"
            'Answer with ONLY this JSON, no prose, no code fences:\n'
            '{"ok": true, "fixes": []}  or  {"ok": false, "fixes": [{"scene": "<scene id>", "problem": "<what is wrong, one sentence>", '
            '"fix": "<the concrete change to make in the screenplay, one sentence>"}]}\n'
            'Use "ok": true when nothing important is wrong. List at most 6 fixes, real problems only, the most important first.')


def parse_verdict(reply):
    txt = W.strip_fences(reply)
    i, j = txt.find("{"), txt.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(txt[i:j + 1])
    except ValueError:
        return None
    if not isinstance(d, dict) or "ok" not in d:
        return None
    fixes = [{"scene": str(f.get("scene", "?")), "problem": short(f.get("problem", ""), 300), "fix": short(f.get("fix", ""), 300)}
             for f in (d.get("fixes") or []) if isinstance(f, dict) and (f.get("problem") or f.get("fix"))]
    return bool(d["ok"]), fixes[:6]


def stage_review(c):
    if c.args.no_review or c.args.backend == "none":
        c.review = "skipped"
        return
    sheet = os.path.join(c.ep, "review.jpg")
    try:
        frames = snapshots(c, review_times(c.ep))
        tile_sheet(frames, sheet)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as e:
        c.review = f"skipped ({short(e, 100)})"
        c.say("review: " + c.review)
        return
    c.say(f"review: {len(frames)} stills -> review.jpg, model call")
    try:
        reply = c.ask(review_prompt(c, sheet), REVIEW_SYSTEM, "review", tools="Read")
    except StageFail as e:
        if not e.model:
            raise
        c.review = "skipped (model call failed)"
        c.say("review: " + c.review)
        return
    verdict = parse_verdict(reply)
    if verdict is None:
        c.review = "skipped (answer was not the JSON verdict)"
        c.say("review: " + c.review)
        return
    ok, fixes = verdict
    if ok or not fixes:
        c.review = "ok"
        c.say("review: ok")
        return
    c.say(f"review: {len(fixes)} problem(s) -> fix call")
    before = read_text(c.sp)
    problems = ("A reviewer looked at stills of the rendered video and found these problems (scene id: problem -> what to change):\n"
                + "\n".join(f"- {f['scene']}: {f['problem']} -> {f['fix']}" for f in fixes))
    try:
        fix_screenplay(c, problems, "review-fix")
    except StageFail as e:
        if not e.model:
            raise
        c.review = "fix call failed"
        return
    code, out, n, ok = accept_step(c)
    if not ok:                                  # the repair broke the compile: back to the draft that worked (and recompile it)
        write_text(c.sp, before)
        accept_step(c)
        c.review = f"{len(fixes)} problem(s) found, fix broke the compile: reverted"
    else:
        c.review, c.problems_left = f"fixed {len(fixes)} problem(s)", n
    c.say("review: " + c.review)


# ------------------------------------------------------------------------------------------ 6 render, 7 queue
def stage_render(c):
    c.say("qa: render + checks (a few minutes)")
    try:
        code, out = run_cmd([sys.executable, QA, c.ep], 2400)
    except subprocess.TimeoutExpired:
        code, out = 1, "RESULT: FAIL (qa.py timed out)"
    write_text(os.path.join(c.ep, "qa.log"), out)
    verdict = (re.findall(r"^RESULT:.*$", out, re.M) or ["no RESULT line"])[-1]
    if code != 0 or "RESULT: PASS" not in out:
        fails = [l.strip() for l in out.splitlines() if re.search(r"\bFAIL\b", l)][:3]
        raise StageFail("qa.py: " + short(verdict + " | " + " | ".join(fails), 300))
    c.say("qa: " + verdict)


def queue_numbers():
    nums = set()
    for d in (QUEUE, DONE):
        for name in os.listdir(d) if os.path.isdir(d) else []:
            m = re.match(r"(\d+)-", name)
            if m:
                nums.add(int(m.group(1)))
    return nums


def next_number(start):
    used = queue_numbers()
    n = start if start is not None else (max(used) + 1 if used else 1)
    while n in used:
        n += 1
    return n


def stage_queue(c):
    meta = meta_from_brief(c.brief)
    name = f"{next_number(c.args.start):03d}-{c.slug}"
    qdir = os.path.join(QUEUE, name)
    os.makedirs(qdir)
    shutil.copyfile(c.sp, os.path.join(qdir, "screenplay.yaml"))
    dumps = lambda v: json.dumps(v, ensure_ascii=False)       # noqa: E731
    write_text(os.path.join(qdir, "meta.json"),
               "{\n" + ",\n".join(f'  "{k}": {dumps(meta[k])}' for k in ("title", "description", "tags", "music_credit")) + "\n}\n")
    try:
        import factory
        factory.load_meta(name)                                # the same validation the daily factory will apply
    except Exception as e:                                     # noqa: BLE001
        shutil.rmtree(qdir, ignore_errors=True)
        raise StageFail(f"meta.json of {name} is not valid for factory.py: {e}")
    c.queue = name
    c.say(f"queue: {rel(qdir)}  \"{meta['title']}\"")


# ------------------------------------------------------------------------------------------ topics, log, summary
def queued_slugs():
    out = set()
    for d in (QUEUE, DONE):
        for name in os.listdir(d) if os.path.isdir(d) else []:
            m = re.match(r"\d+-(.+)$", name)
            if m:
                out.add(m.group(1))
    return out


def logged_slugs(statuses):
    out = set()
    for line in read_text(LOG).splitlines() if os.path.isfile(LOG) else []:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("status") in statuses and r.get("slug"):
            out.add(r["slug"])
    return out


def bank_topics(a):
    """the next N topics of the bank that are not used / solved / already made, tried or queued"""
    path = a.bank or next((p for p in (os.path.join(REPO, "stickman", "topics_unexplained.json"),
                                       os.path.join(REPO, "stickman", "topics.json")) if os.path.isfile(p)), None)
    if not path or not os.path.isfile(path):
        raise BatchAbort(2, "no topic bank found (stickman/topics_unexplained.json or stickman/topics.json): use --bank FILE or --topics")
    d = json.loads(read_text(path))
    items = d.get("topics", []) if isinstance(d, dict) else d
    skip = queued_slugs() | logged_slugs({"OK", "FAILED", "SKIPPED"})
    for key in ("used", "auto", "solved"):
        skip |= {slugify(t) for t in (d.get(key) or [] if isinstance(d, dict) else []) if isinstance(t, str)}
    out = []
    for t in items:
        name = t if isinstance(t, str) else (t.get("title") or t.get("topic") or t.get("name") or "")
        if name and slugify(name) not in skip and slugify(name) not in {slugify(x) for x in out}:
            out.append(name)
        if len(out) >= a.from_bank:
            break
    say(f"bank {rel(path)}: {len(out)} topic(s) selected" + ("" if len(out) >= a.from_bank else f" (only {len(out)} unused left)"))
    return out


def pick_topics(a):
    if a.topics is not None:
        names = [t.strip() for t in a.topics.split(";" if ";" in a.topics else ",") if t.strip()]
    else:
        names = bank_topics(a)
    seen, out = set(), []
    for t in names:
        if slugify(t) not in seen:
            seen.add(slugify(t))
            out.append(t)
    return out


def cleanup(ep):
    """after a good run: drop the heavy generated files (render, audio, voice cache, stills), keep the small text files"""
    for name in os.listdir(ep):
        if name not in KEEP_FILES:
            p = os.path.join(ep, name)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except OSError:
                    pass


def process_topic(topic, a):
    slug = slugify(topic)
    c = Ctx(topic, slug, a)
    STATE["dir"], STATE["calls"] = None, []
    status, reason, dup = "OK", "", False
    try:
        if slug in queued_slugs():
            dup = True                               # shown, but not logged (the queue entry says it all)
            raise StageFail(f"already in the queue ({slug})", status="SKIPPED")
        fresh_dir(c.ep)
        stage_facts(c)
        stage_brief(c)
        stage_author(c)
        stage_check(c)
        stage_review(c)
        stage_render(c)
        stage_queue(c)
    except StageFail as e:
        status, reason = ("ERROR" if e.model else e.status), str(e)
    except (BatchAbort, KeyboardInterrupt):
        raise
    except Exception as e:                       # noqa: BLE001  a bug in one topic must not stop a run of 100
        traceback.print_exc()
        status, reason = "FAILED", f"internal error: {type(e).__name__}: {short(e, 200)}"
    calls, tin, tout, cost = usage_totals(STATE["calls"])
    row = {"ts": utc_now(), "topic": topic, "slug": slug, "status": status, "reason": reason, "queue": c.queue, "backend": a.backend,
           "model": a.model if a.backend == "cli" else "", "calls": calls, "tokens_in": tin, "tokens_out": tout,
           "cost_usd": round(cost, 4), "seconds": round(time.time() - c.t0), "fix_rounds": c.fix_rounds,
           "problems_first": c.problems_first, "problems_left": c.problems_left, "review": c.review}
    if not dup:
        with open(LOG, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if status == "OK" and not a.keep:
        cleanup(c.ep)
    fixed = max(0, (c.problems_first or 0) - (c.problems_left or 0)) if status == "OK" else 0
    say(f"--> {topic}: {status}" + (f"  {c.queue}" if c.queue else f"  ({short(reason, 200)})")
        + f"  calls {calls}, tokens {tin // 1000}k/{tout // 1000}k, ${cost:.2f}, {row['seconds']} s"
        + (f", {c.fix_rounds} fix round(s), {fixed} problem(s) fixed, {c.problems_left} left" if status == "OK" else ""))
    return row


def fmt_time(sec):
    return f"{sec // 60}m{sec % 60:02d}s" if sec >= 60 else f"{sec}s"


def summary(rows):
    if not rows:
        return
    say("\n=== SUMMARY")
    say(f"{'#':>3}  {'topic':<30} {'status':<8} {'queue folder':<30} {'calls':>5} {'in':>6} {'out':>6} {'cost':>7} {'time':>7}")
    for i, r in enumerate(rows, 1):
        say(f"{i:>3}  {short(r['topic'], 30):<30} {r['status']:<8} {(r['queue'] or '-'):<30} {r['calls']:>5} "
            f"{str(r['tokens_in'] // 1000) + 'k':>6} {str(r['tokens_out'] // 1000) + 'k':>6} {'$%.2f' % r['cost_usd']:>7} {fmt_time(r['seconds']):>7}")
    ok = [r for r in rows if r["status"] == "OK"]
    say(f"{len(ok)} of {len(rows)} topic(s) OK; {sum(r['calls'] for r in rows)} model calls, ${sum(r['cost_usd'] for r in rows):.2f}, "
        f"{fmt_time(sum(r['seconds'] for r in rows))}")
    for r in rows:
        if r["status"] != "OK":
            say(f"  {r['status']}: {r['topic']}: {short(r['reason'], 200)}")
    if ok:
        say("Next: git add doodle/queue doodle/batch_log.jsonl && git commit && git push  (the cloud publishes one episode a day)")


def main():
    ap = argparse.ArgumentParser(description="Topics -> finished, checked doodle episodes in doodle/queue/ (no human in the loop).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--topics", help='topic names separated by commas (or by ; if a name has commas), e.g. "Mary Celeste,Tunguska event"')
    g.add_argument("--from-bank", type=int, metavar="N", help="the next N unused topics of the topic bank")
    ap.add_argument("--bank", help="topic bank JSON (default: stickman/topics_unexplained.json, else stickman/topics.json)")
    ap.add_argument("--start", type=int, help="first queue number NNN (default: after the highest in queue/ and done/)")
    ap.add_argument("--backend", choices=("cli", "none"), default="cli", help="cli = claude -p; none = plumbing test without any model call")
    ap.add_argument("--model", default="sonnet", help="model alias for every call (default sonnet)")
    ap.add_argument("--no-review", action="store_true", help="skip the look at stills (saves 1-2 model calls per topic)")
    ap.add_argument("--keep", action="store_true", help="keep the whole episode work folder after a good run (default: only the small text files)")
    a = ap.parse_args()
    rows, abort, streak = [], None, 0
    try:
        if a.backend == "cli":
            claude_cmd()
        topics = pick_topics(a)
        if not topics:
            say("no topics to do")
        for i, topic in enumerate(topics, 1):
            say(f"\n=== [{i}/{len(topics)}] {topic}")
            row = process_topic(topic, a)
            rows.append(row)
            streak = streak + 1 if row["status"] == "ERROR" else 0
            if streak >= 3:
                raise BatchAbort(4, "the Claude CLI failed on 3 topics in a row - stopping (run again later)")
    except BatchAbort as e:
        abort = e
    except KeyboardInterrupt:
        abort = BatchAbort(130, "interrupted")
    summary(rows)
    if abort:
        say(("\n" if rows else "") + str(abort))
        return abort.code
    return 1 if any(r["status"] in ("FAILED", "ERROR") for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
