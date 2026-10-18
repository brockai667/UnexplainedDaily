# -*- coding: utf-8 -*-
"""doodle/tests/fake_openai.py - an offline stand-in for an OpenAI-compatible API: tests `doodle/batch.py --backend api` end to end without a
key, a model or a network (only the facts stage still reads Wikipedia).

    python doodle/tests/fake_openai.py [--port 8765] [--fail-first N] [--truncate-first N]
    OPENROUTER_API_KEY=offline-test python doodle/batch.py --topics "Mary Celeste" --backend api --provider openrouter --base-url http://127.0.0.1:8765/v1 --model fake --start 900 --no-review
    (Windows cmd: set PYTHONIOENCODING=utf-8 && set OPENROUTER_API_KEY=offline-test && python doodle/batch.py ...)

POST /v1/chat/completions (and /chat/completions) is answered with canned text, chosen by the system message (else by the prompt):
  brief stage    -> doodle/briefs/celeste.yaml plus the title / description / tags lines the brief prompt asks for
  author / fix   -> doodle/episodes/celeste_sonnet/screenplay.yaml
  review         -> {"ok": true, "fixes": []}; a model whose name contains "novision" answers a request that carries an image with
                    400 "This model does not support image input"
Faults on demand: --fail-first N = the first N brief requests get 429 + Retry-After: 0 (the client must try again);
--truncate-first N = the first N author requests come back cut off (finish_reason length: the client must ask again with a bigger max_tokens).
The API key "bad-key" is answered with 401. POST /quit stops the server. Every request is one line on stdout (never the key)."""
import argparse
import base64
import collections
import http.server
import json
import os
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DOODLE = os.path.dirname(HERE)
BRIEF = os.path.join(DOODLE, "briefs", "celeste.yaml")
SCREENPLAY = os.path.join(DOODLE, "episodes", "celeste_sonnet", "screenplay.yaml")
META = ('title: "The Ship Found Without a Crew"\n'
        'description: "In December 1872 a ship was found drifting near the Azores with her cargo untouched and her lifeboat gone. '
        'Ten people were never seen again."\n'
        'tags: ["#unexplained", "#mystery", "#maryceleste", "#ghostship", "#shorts"]\n')
NO_PROBLEMS = '{"ok": true, "fixes": []}'
ARGS = None
COUNT = collections.Counter()
LOCK = threading.Lock()

for _stream in (sys.stdout, sys.stderr):      # Windows consoles default to cp1250: never die on a print
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read().replace("\r\n", "\n")


def brief_reply():
    """celeste.yaml with the title / description / tags lines right after `name:` (batch.py reads the reply from the `name:` line on)"""
    text = read(BRIEF)
    if re.search(r"^title\s*:", text, re.M):
        return text
    m = re.search(r"^name\s*:.*\n", text, re.M)
    return text[:m.end()] + META + text[m.end():] if m else "name: celeste_auto\n" + META + text


def text_of(message):
    """the text of a chat message (content is a string or a list of parts)"""
    c = message.get("content")
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return c if isinstance(c, str) else ""


def images_of(messages):
    """[(media type, decoded bytes)] of the image_url parts; ValueError when one is not a base64 data URL"""
    out = []
    for m in messages:
        for p in m.get("content") if isinstance(m.get("content"), list) else []:
            if isinstance(p, dict) and p.get("type") == "image_url":
                url = (p.get("image_url") or {}).get("url", "")
                mt = re.match(r"data:(image/[a-z+]+);base64,(.*)$", url, re.S)
                if not mt:
                    raise ValueError("image_url is not a base64 data URL")
                out.append((mt.group(1), base64.b64decode(mt.group(2), validate=True)))
    return out


def stage_of(messages, has_image):
    """brief / author / fix / review, from the system message (batch.py appends the role of the step) and, failing that, from the prompt"""
    system = " ".join(text_of(m) for m in messages if m.get("role") == "system")
    user = " ".join(text_of(m) for m in messages if m.get("role") == "user")
    if has_image or "reviewer" in system:
        return "review"
    if "story editor" in system:
        return "brief"
    if "screenplay author" in system:
        return "fix" if "YOUR SCREENPLAY:" in user else "author"
    if "Write the production brief" in user[:300]:
        return "brief"
    if "contact sheet" in user[:600]:
        return "review"
    return "fix" if "YOUR SCREENPLAY:" in user else "author"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):             # the default access log has no stage: do_POST prints its own line
        pass

    def reply(self, code, obj, headers=None):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def error(self, code, message, headers=None):
        self.reply(code, {"error": {"message": message, "code": code}}, headers)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if path == "/quit":
            self.reply(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if not path.endswith("/chat/completions"):
            return self.error(404, f"no such endpoint: {path}")
        auth = self.headers.get("Authorization") or ""
        key = auth[7:].strip() if auth.startswith("Bearer ") else ""
        if not key or key == "bad-key":
            return self.error(401, "invalid or missing API key")
        try:
            req = json.loads(raw.decode("utf-8"))
            msgs = req["messages"]
            images = images_of(msgs)
        except (ValueError, KeyError, TypeError) as e:
            return self.error(400, f"bad request: {e}")
        model, mt = str(req.get("model", "")), req.get("max_tokens")
        stage = stage_of(msgs, bool(images))
        with LOCK:
            COUNT[stage] += 1
            nth = COUNT[stage]
        info = f"[fake] {stage} #{nth} model={model} max_tokens={mt} temperature={req.get('temperature')}"
        if images:
            info += f" image={images[0][0]} {len(images[0][1])} bytes"
        if images and "novision" in model:
            print(info + " -> 400 no vision", flush=True)
            return self.error(400, "This model does not support image input")
        if stage == "brief" and nth <= ARGS.fail_first:
            print(info + " -> 429", flush=True)
            return self.error(429, "Rate limit exceeded (fake)", {"Retry-After": "0"})
        text, finish = (NO_PROBLEMS if stage == "review" else brief_reply() if stage == "brief" else read(SCREENPLAY)), "stop"
        if stage == "author" and nth <= ARGS.truncate_first:
            text, finish = text[:300], "length"
        print(info + f" -> {finish} {len(text)} chars", flush=True)
        n_in = sum(len(text_of(m)) for m in msgs) // 4
        self.reply(200, {"id": f"fake-{sum(COUNT.values())}", "object": "chat.completion", "created": int(time.time()), "model": model,
                         "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": finish}],
                         "usage": {"prompt_tokens": n_in, "completion_tokens": len(text) // 4, "total_tokens": n_in + len(text) // 4}})


def main():
    global ARGS
    ap = argparse.ArgumentParser(description="Offline fake of an OpenAI-compatible API for doodle/batch.py --backend api")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--fail-first", type=int, default=0, help="the first N brief requests answer 429 + Retry-After: 0")
    ap.add_argument("--truncate-first", type=int, default=0, help="the first N author requests come back cut off (finish_reason length)")
    ARGS = ap.parse_args()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler)
    print(f"fake OpenAI API on http://127.0.0.1:{ARGS.port}/v1 (fail-first {ARGS.fail_first}, truncate-first {ARGS.truncate_first}); "
          f"POST /quit stops it", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
