# doodle/batch.py - topics in, checked episodes in the queue out

One command turns a list of topics into finished doodle episodes in `doodle/queue/` with no human in the loop
("100 scripts for 100 days": run it, then the cloud publishes one episode a day).

```
python doodle/batch.py --topics "Mary Celeste,Tunguska event" [--start 004]   # explicit topics (use ; if a name contains commas)
python doodle/batch.py --from-bank 100 [--start 004]                         # the next 100 unused topics of the bank
        [--backend cli|none|agentfile|api] [--model sonnet] [--no-review] [--keep] [--bank FILE]
```

Needs: the `claude` command logged in (the owner's subscription; not with `--backend agentfile`), `npx` (stills), the usual doodle engine
(TTS, whisper, ffmpeg, Chromium).
If the login has expired the batch stops at once with `Claude CLI needs login: run claude and /login` (exit code 3):
run `claude`, type `/login`, start the batch again.

## What happens per topic

| stage | what | model calls |
|---|---|---|
| facts | Wikipedia summary + intro + the article's sections (those about the disappearance / investigation / theories first, about 7000 chars; a thin lead such as Flannan Isles Lighthouse is no longer a problem; no key; search API once if the page is missing, else the topic is SKIPPED) | 0 |
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
  `author`, `fix1` ... `fixN` (accept.py problems; N = `--fix-rounds`, default 2), `review`, `fix<N+1>` (problems found by the review; `fix3`
  with the default, so resume a topic with the same `--fix-rounds`). Prompt:
  `doodle/episodes/<slug>/prompts/<stage>.md`, answer: `doodle/episodes/<slug>/answers/<stage>.txt` (empty = missing; code fences are
  stripped as with `cli`).
* Check stage, every backend: `accept.py` first scans the whole screenplay and prints EVERY problem the compiler would stop at (unknown drawing /
  pose / face / sfx, an action the object cannot do, a `word:` anchor not in the narration, unknown sentence key, `check:` word not in its scene ...)
  as `COMPILE ERROR: scene 'x' beat #n (...)` lines, exit code 1, nothing compiled; the fix prompt carries the whole list and a short reminder.
  `--fix-rounds N` = how many fix calls it gets. Backend api: brief + author + N fixes + review + review fix (+ retries) calls, so
  `--fix-rounds 4` needs `--api-cap 12` (the default cap stays 10). `--reasoning none` sends OpenRouter `{"reasoning": {"enabled": false,
  "exclude": true}}` (no `reasoning_effort`); the workflow default `extra` is `--reasoning none --max-tokens 32000 --fix-rounds 4 --api-cap 12`.
* Running the same command again resumes: the facts (`facts.json`), the validated brief (`brief.yaml`) and every answer are reused;
  `accept.py` runs again, the review stills are made only when the review prompt is written. Several topics are done in order, the
  first one that needs an answer stops the run; topics already in the queue are skipped. A topic that ended FAILED / SKIPPED is not
  tried again by the re-runs (`result.json` in its folder): delete `doodle/episodes/<slug>/` to start it over.
* `--from-bank N`: the pick of the first run is kept in `doodle/episodes/.agentfile_pick.json` until the command is finished, so every
  re-run works on the same N topics.
* Testing without a model: a Bash loop that, whenever the exit code is 10, copies a prepared answer to the answer path and runs the
  command again.

## Backend api (free OpenAI-compatible model, no login)

```
python doodle/batch.py --topics "Mary Celeste;Tunguska event" --backend api --provider openrouter --model nvidia/nemotron-3.5-super-vl:free [--start 004]
        [--review-model M] [--base-url URL] [--api-key-env VAR] [--max-tokens 16000] [--api-timeout 600] [--api-cap 10] [--no-review] [--keep]
```

No `claude` login, no agent, no human: a free model behind an OpenAI-compatible `POST <base-url>/chat/completions` is the author. It is the
`agentfile` flow (same stages, same `prompts/<stage>.md` and `answers/<stage>.txt`, same resume after a stop, same `QUEUED <queue folder>` /
`FAILED <slug>: <reason>` lines) except that a missing answer is fetched from the API and written to `answers/<stage>.txt`; the run never
ends with exit code 10. Re-run the same command after any stop: what is done is reused (an `ERROR` topic goes on where it stopped).

| `--provider` | base URL | key, read from the environment |
|---|---|---|
| `openrouter` (default) | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| `groq` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| `nim` | `https://integrate.api.nvidia.com/v1` | `NVIDIA_API_KEY` |
| `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY` |
| `custom` | `--base-url` (required) | `OPENAI_API_KEY` |

`--base-url` and `--api-key-env` replace the 2nd and 3rd column. The start prints `api key: <ENV NAME>, N chars` - the key itself is never printed
or stored. `--model` is the provider's model id for brief, author and fixes (the default `sonnet` is a CLI alias: always pass `--model`),
`--review-model` the one for the review (default `--model`).

* Request: `{model, messages, max_tokens, temperature: 0.4}`; system = "You are the author. Reply with the answer only ..." + the role rules of
  the stage, user = the stage prompt. `<think>` blocks of reasoning models are cut off the reply.
* Review: `review.jpg` goes along as an `image_url` part (base64 data URL) to `--review-model`. If the model refuses images (a 4xx about image
  input) the review counts as "no problems" and the topic's `review` is `skipped (no vision)`.
* Retries: 429, 5xx, timeouts and connection errors are tried 5 times in all, waiting for `Retry-After`, else 10, 20, 40, 80 s (at most 90).
  401/403 stop the batch (exit code 3, key rejected); 402 or a 429 that does not go away stop it with exit code 4 (run again later); another
  4xx makes the topic `ERROR` (3 in a row stop the batch).
* A reply cut off at `max_tokens` (`finish_reason: length`) or an empty one is asked again once with `max_tokens` doubled (up to 32000), then
  the topic is `FAILED: truncated reply`. More than `--api-cap` calls for a topic (all runs together) = `FAILED: api cap`.
* `calls.json` has one row per request (stage, model, status, seconds, prompt_tokens, completion_tokens, ...); `batch_log.jsonl` gets
  `backend: api`, calls, tokens in/out, `cost_usd` 0.
* Offline test (no key, no model; the real accept, qa render and queue still run, Wikipedia is still read):

  ```
  python doodle/tests/fake_openai.py --fail-first 1 --truncate-first 1 &     # fake API on http://127.0.0.1:8765/v1, POST /quit stops it
  OPENROUTER_API_KEY=offline-test python doodle/batch.py --topics "Mary Celeste" --backend api --provider openrouter --base-url http://127.0.0.1:8765/v1 --model fake --start 900 --no-review
  ```

  (Windows cmd: `set PYTHONIOENCODING=utf-8 && set OPENROUTER_API_KEY=offline-test && python doodle/batch.py ...`.) Afterwards delete
  `doodle/queue/900-*`, the Mary Celeste line of `doodle/batch_log.jsonl` and `doodle/episodes/mary-celeste/`.
* GitHub Actions: `.github/workflows/doodle-author.yml` (manual `workflow_dispatch`; the cron `15 2 * * *` is prepared but commented out).
  Inputs `provider`, `model`, `review_model`, `topics` (`;`-separated, empty = the next `from_bank` unused bank topics), `from_bank`, `start`,
  `commit`; the secret of the provider (`OPENROUTER_API_KEY`, `GROQ_API_KEY`, `NVIDIA_API_KEY` or `GEMINI_API_KEY`). It runs batch.py with
  `--backend api --keep` (limit 120 min) and always uploads the artifact `doodle-author` (review.jpg, accept.log, qa.log, calls.json,
  screenplay.yaml, renders/*.mp4, batch_log.jsonl). `commit` off = artifact only; on = `git add doodle/queue doodle/batch_log.jsonl`, commit
  "doodle-author: <topics>", push. A copy for a repo that holds the key secret: `doodle/tests/doodle-author-coldcase.yml` (checks out
  `brockai667/UnexplainedDaily` at the input `ref`); it is not run from here.
