# doodle/batch.py - topics in, checked episodes in the queue out

One command turns a list of topics into finished doodle episodes in `doodle/queue/` with no human in the loop
("100 scripts for 100 days": run it, then the cloud publishes one episode a day).

```
python doodle/batch.py --topics "Mary Celeste,Tunguska event" [--start 004]   # explicit topics (use ; if a name contains commas)
python doodle/batch.py --from-bank 100 [--start 004]                         # the next 100 unused topics of the bank
        [--backend cli|none|agentfile] [--model sonnet] [--no-review] [--keep] [--bank FILE]
```

Needs: the `claude` command logged in (the owner's subscription; not with `--backend agentfile`), `npx` (stills), the usual doodle engine
(TTS, whisper, ffmpeg, Chromium).
If the login has expired the batch stops at once with `Claude CLI needs login: run claude and /login` (exit code 3):
run `claude`, type `/login`, start the batch again.

## What happens per topic

| stage | what | model calls |
|---|---|---|
| facts | Wikipedia summary + intro (no key; search API once if the page is missing, else the topic is SKIPPED) | 0 |
| brief | brief YAML in the format of `briefs/celeste.yaml` + title / description / tags, validated (word count, gold words, scenes cover every sentence, title rules ...) | 1 (+1 retry with the errors) |
| author | `make_prompt.build()` brief -> complete `screenplay.yaml` (our validated header is put in front, so the narration cannot drift) | 1 |
| check | `accept.py`; its problems go back to the model | 0 if clean, else 1 per fix round, at most 2 rounds |
| review | `hyperframes snapshot` at 35 % and 75 % of every scene -> `review.jpg` -> a model that looks at it (`--tools Read`) | 1 (+1 fix call if it finds problems, then `accept.py` again) |
| render | `qa.py` must print `RESULT: PASS` | 0 |
| queue | `doodle/queue/<NNN>-<slug>/` with `screenplay.yaml` + `meta.json`, one line in `doodle/batch_log.jsonl` | 0 |

Typical topic: 3-4 model calls (brief, author, review, sometimes one fix), 10-20 minutes. Worst case 7 calls. A draft that
does not compile after 2 fix rounds, or a render that fails QA, is FAILED: the folder `doodle/episodes/<slug>/` stays for inspection
and the batch goes on. If the last fix made things worse, the best compiling draft is used.

## Results

* `doodle/queue/<NNN>-<slug>/` - NNN = next free number (queue and done), or from `--start`.
* `doodle/batch_log.jsonl` - one JSON line per topic: status (OK, FAILED, SKIPPED, ERROR), calls, tokens in/out, cost_usd
  (as the CLI reports it), seconds, fix_rounds, problems_first / problems_left (accept.py), review result.
* `doodle/episodes/<slug>/` - `brief.yaml`, `facts.txt`, `AUTHOR.md`, `screenplay.yaml`, `calls.json` (usage of every call),
  `accept.log`, `qa.log`, `review.jpg`. After a good run the heavy files (render, audio, stills) are deleted unless `--keep`.
* A one-line summary per topic while it runs and a table at the end. Exit code 0 = fine, 1 = a topic FAILED / ERROR,
  3 = login needed, 4 = usage limit, network or CLI keeps failing (nothing is lost: run again later),
  10 = `--backend agentfile`: an answer is needed (see the last section).

## Resuming and the bank

`--from-bank N` takes the first N topics of `stickman/topics_unexplained.json` (else `stickman/topics.json`; list `topics`) that are
not in its `used` / `auto` / `solved` lists, not in the queue or `done/`, and not already OK / FAILED / SKIPPED in `batch_log.jsonl`
(ERROR = the model call itself failed, tried again next time). So after a stop just run the same command again. Explicit
`--topics` are always tried, except those whose slug is already in the queue (shown as SKIPPED, not logged). Re-run one failed
topic with `--topics`. The bank in this branch (`stickman/topics.json`) has 80 unused topics: for 100 days add topics to it or pass `--bank FILE`.

When the queue is full: `git add doodle/queue doodle/batch_log.jsonl`, commit, push.

## Testing without the model

`--backend none` makes no model call: brief = `briefs/celeste.yaml`, screenplay = `episodes/celeste_sonnet/screenplay.yaml`,
no review; everything else (accept, qa render, queue, log) is real. Delete the test folder from the queue afterwards.
`CLAUDE_BIN="python path/to/fake.py"` replaces the `claude` command (forward slashes on Windows).

## Backend agentfile (a Claude Code agent is the model, no `claude` login)

```
python doodle/batch.py --topics "Mary Celeste;Tunguska event" --backend agentfile [--start 004] [--no-review]
```

**Instruction for the agent:** run the command. When it ends with exit code 10 and its last line is
`ANSWER NEEDED <stage> <prompt file> -> <answer file>`, read the prompt file (its first line repeats the command), write your complete
answer as plain text (no code fences) to the answer file and run the same command again. Repeat until the command no longer prints
ANSWER NEEDED: exit code 0 = no topic failed (each ended with a `QUEUED <queue folder>` line, or `SKIPPED <slug>: <reason>`),
1 = a topic ended with `FAILED <slug>: <reason>`.
In the `review` stage open the `review.jpg` named in the prompt with your Read tool and answer with the JSON only.

* Every place where `--backend cli` calls the model is a stage with a fixed name: `brief`, `brief-retry` (the brief was invalid),
  `author`, `fix1`, `fix2` (accept.py problems), `review`, `fix3` (problems found by the review). Prompt:
  `doodle/episodes/<slug>/prompts/<stage>.md`, answer: `doodle/episodes/<slug>/answers/<stage>.txt` (empty = missing; code fences are
  stripped as with `cli`).
* Running the same command again resumes: the facts (`facts.json`), the validated brief (`brief.yaml`) and every answer are reused;
  `accept.py` runs again, the review stills are made only when the review prompt is written. Several topics are done in order, the
  first one that needs an answer stops the run; topics already in the queue are skipped. A topic that ended FAILED / SKIPPED is not
  tried again by the re-runs (`result.json` in its folder): delete `doodle/episodes/<slug>/` to start it over.
* `--from-bank N`: the pick of the first run is kept in `doodle/episodes/.agentfile_pick.json` until the command is finished, so every
  re-run works on the same N topics.
* Testing without a model: a Bash loop that, whenever the exit code is 10, copies a prepared answer to the answer path and runs the
  command again.
