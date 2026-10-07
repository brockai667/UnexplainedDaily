# -*- coding: utf-8 -*-
"""Zadanie pre autora epizody v JEDNOM subore (uspornа vyroba: autor precita jeden subor, napise scenar, spusti jednu kontrolu).
  python doodle/make_prompt.py doodle/briefs/celeste.yaml --name celeste_sonnet --patterns milky.night,milky.cargo,devon.measure,devon.dusk
-> doodle/episodes/<name>/AUTHOR.md   (autor potom pise doodle/episodes/<name>/screenplay.yaml)"""
import argparse
import os
import re
import sys

import yaml

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import auto_writer as W   # noqa: E402

RULES = """# You are the director and animator of ONE short doodle episode

Write the complete file `{sp}` (720x1280 vertical video, about 35-45 s, hand-drawn ink on paper, stick-figure people).
A narrator reads the sentences; captions and the gold words are added automatically. Your job: for every sentence the viewer
SEES exactly what it says, big, and something moves all the time.

## How to work (strict budget: at most 14 tool calls in total)
1. This file is all you need. Do NOT open any other file, do not look at images, do not spawn agents.
2. Write `{sp}`: start with the HEADER below copied verbatim, then `styles:`, `shapes:` (only your NEW drawings),
   then `scenes:`. Use the Write tool for the first part (header + shapes + first 3-4 scenes) and append the remaining scenes
   with 1-2 Edit calls. Keep `scenes:` the last top-level key.
3. Run once:  `python doodle/accept.py {ep}`   (from the repository root {root}). It compiles the episode and prints, per
   scene, compiler errors, directing problems and ON-SCREEN MEASUREMENTS (is each `check` thing visible and big enough when its
   word is spoken). Fix what it reports with Edit calls and run it again. At most 3 runs of accept.py.
4. Finish with:  `python doodle/qa.py {ep}`   (renders the video and prints a verdict). Do not fix anything after it.
5. Reply with 5 lines: duration, accept.py result, qa.py verdict, number of tool calls you used, what you could not do.

## Rules for every scene
- Every sentence belongs to exactly one scene, in order (a scene may take two sentences).
- First object of `set` is the backdrop (library backdrop shape at x 0, y 0, or kind sky), then a ground / sea / floor.
  Interiors: draw the room as shapes (wall rect, floor line) so the frame is never empty paper.
- People are `cast` entries and always stand ON something (ground, deck, floor: their `gy` = that line). Never floating, never
  standing on water. Animals and things are shapes (library name, or drawn by you), never cast entries.
- Sizes make sense: person k 1.3 = about 310 px; a sailing ship next to people is at least 2x a person. Buildings and ships are
  never smaller than the people next to them.
- BIG: the main subject fills at least a third of the frame height. A small thing the sentence is about (a book, a footprint,
  a coin) gets a close-up: camera zoom 1.6-2.2 centred on it, so it is at least 100 px on screen.
- Something moves all the time: at least 10 beats per scene, at least 4 tied to spoken words (`at: "word:..."`, only words of
  that scene's sentences). People walk in (enter), react (face, pose, point, look, startle), things pop up one after another
  (`repeat`), and the camera works: a start `camera:` plus at least one push / pan / follow beat.
- Each scene ends with `check:` - 2 to 4 entries, one per thing the sentence names:
  `- {{thing: "the logbook", ids: [book], word: "logbook"}}`  (ids = the object ids that draw it; word = an exact spoken word of
  the scene at which it must be clearly visible). accept.py measures exactly these.
- Library drawings are used by name with no definition. New drawings: thick black outline (width 5-7), flat fills, 4-14 items,
  around their own origin (0,0 = bottom centre for things standing on the ground), at least 80 px for anything that matters.
- Keep the action between y 280 and y 900 (captions are below y 926, gold words sit at y 100-260). Quote "#rrggbb" colours
  and "word:..." strings. Use only kinds, verbs, poses, faces, emitters and sfx that the documentation lists.
- PATTERN SCENES below were made by a professional for other stories. Where a scene of yours does something similar, start
  from the pattern: keep its structure, timing style (word anchors, `prev` chains, `repeat`) and camera work, and replace
  every object, drawing, position and word.
"""


# "How to work" for an author that has NO tools (batch.py: `claude -p --tools ""`): the whole reply is the file
HOW_TEXT = """## How to work (you have NO tools: your whole reply is the file)
1. This brief is all you need. There are no files to open and nothing to run; nobody answers questions.
2. Reply with the complete file `{sp}` as plain text and nothing else: the HEADER below copied verbatim, then `styles:`,
   `shapes:` (only your NEW drawings), then `scenes:` as the last top-level key. No prose, no explanations, no code fences.
3. Afterwards a program compiles the file and measures every `check:` entry on screen (is the thing visible and big enough when
   its word is spoken). What it finds is sent back to you and you may repair the file at most twice - so get the structure,
   the ids and the word anchors right the first time.

"""


def build(B, ep_dir, patterns=(), text_only=False):
    """Text of the author brief (AUTHOR.md) for the brief dict B (name, header, scenes) and the absolute episode folder ep_dir.
    patterns = keys of lib/patterns.yaml to include. text_only=True: the reader has no tools, so the "How to work" section
    says "reply with the file" instead of "write it with Write/Edit and run accept.py" (batch.py)."""
    root = os.path.dirname(HERE)
    ep_rel = os.path.relpath(ep_dir, root).replace("\\", "/")
    lib, pats = W.load_lib([]), W.load_patterns([])
    sp = ep_rel + "/screenplay.yaml"
    rules = RULES.format(sp=sp, ep=ep_rel, root=root.replace("\\", "/"))
    if text_only:
        rules = re.sub(r"## How to work.*?(?=## Rules for every scene)", lambda m: HOW_TEXT.format(sp=sp), rules, flags=re.S)
    out = [rules]
    out.append("## HEADER (copy verbatim as the start of the file)\n```yaml\n" + B["header"].rstrip() + "\n```\n")
    out.append("## SCENES THE PRODUCER WANTS (you may merge two neighbours or split one if it reads better)\n" +
               "\n".join(f"- `{p['id']}` {p['sents']}: {p['must']}" for p in B["scenes"]) + "\n")
    out.append("## " + W.catalog(lib) + "\n")
    chosen = [k for k in patterns if k in pats]
    if chosen:
        out.append("## PATTERN SCENES\n" + "\n".join(
            f"### {k} - {pats[k]['use']}\n(its sentences: {pats[k]['words']})\n```yaml\n" + W.dump({"scenes": [pats[k]["scene"]]}) + "```\n" for k in chosen))
    out.append("## ENGINE DOCUMENTATION\n" + W.api_doc())
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("brief")
    ap.add_argument("--name", required=True)
    ap.add_argument("--patterns", default="")
    a = ap.parse_args()
    B = yaml.safe_load(open(a.brief, encoding="utf-8"))
    ep_dir = os.path.join(HERE, "episodes", a.name)
    os.makedirs(ep_dir, exist_ok=True)
    path = os.path.join(ep_dir, "AUTHOR.md")
    open(path, "w", encoding="utf-8").write(build(B, ep_dir, a.patterns.split(",")))
    print(path, f"({os.path.getsize(path) // 1024} kB, ~{os.path.getsize(path) // 3500} tis. tokenov)")


if __name__ == "__main__":
    main()
