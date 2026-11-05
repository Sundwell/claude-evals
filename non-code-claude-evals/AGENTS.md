# AGENTS.md

Guide for a coding agent helping someone run this eval on their own tasks. The human-facing docs are in Russian (README.md, guide/); this file says the same for you.

## What this is

An eval of Claude models on judgment work that is not code writing: code and plan review by reading, fact-checking, intake of raw material, recalling details of a long session, choosing the next turn of a session. Each task has a frozen copy of its material, a prompt, and a checklist written before any run. Every (task, setting) cell runs N times through promptfoo's Claude Agent SDK provider with read-and-run tools only; judges mark each checklist item found or not found in each answer; `score.py` compares settings per task with a bootstrap interval and a permutation test.

## Layout

- `harness/run.py` - runs the cells. One promptfoo eval per cell, config generated into `runs/<task>/<setting>__r<rep>/`. Answers go to `runs/answers/<task>__<hash>.md` (the name hides the setting from the judges), the mapping to `runs/secret-map.jsonl`.
- `harness/judge.py` - one mark file per answer and judge in `runs/marks/`. Sonnet via `claude -p` is the default judge; Sol via the codex CLI is optional (`[judges.sol] enabled = true`).
- `harness/score.py` - tables from `runs/secret-map.jsonl`, `runs/marks/` and the tasks' `key.json`.
- `harness/common.py` - config loading shared by the three scripts.
- `harness/config.example.toml` - defaults. A `harness/config.toml`, when present, is used instead (gitignored).
- `harness/package.json` - promptfoo and `@anthropic-ai/claude-agent-sdk`, pinned to the versions of the 2026-10 run.
- `guide/task-format.md`, `guide/collect-tasks.md` - task format and how to build tasks (Russian).
- `example-task/` - one invented code-review task, safe to publish.
- `results-2026-10/` - the published results of the 2026-10 run and `recompute.py`.
- `tasks/`, `runs/` - the user's own tasks and outputs. Both are gitignored and must stay that way.

## Commands

All from `non-code-claude-evals/`. Python 3.11+ (stdlib only), Node 22.22+.

```bash
(cd harness && npm ci)                       # once
mkdir -p tasks && cp -r example-task tasks/  # the demo task
python3 harness/run.py --dry-run             # list cells, spends nothing
python3 harness/run.py --settings sonnet-medium --repeat 1
python3 harness/run.py                       # every task x setting x repeat; rerun resumes
python3 harness/judge.py --dry-run
python3 harness/judge.py --check             # empty and full-key answers per task, expect 0% and 100%
python3 harness/judge.py                     # or --follow next to a running run.py
python3 harness/score.py
python3 results-2026-10/recompute.py         # the article's numbers, offline
```

`--tasks`, `--settings`, `--repeat`, `-j`, `--config`, `--tasks-dir`, `--runs-dir` narrow or redirect any run. Everything except `--dry-run`, `score.py` and `recompute.py` spends model usage; ask the user before starting a full run and tell them the cell count from `--dry-run` first.

## Auth and sandbox

- The agent under test and the Sonnet judge use the user's own Claude Code login (subscription credentials in `~/.claude/.credentials.json` or `$CLAUDE_CONFIG_DIR`) or `ANTHROPIC_API_KEY` from the environment. Never write a key into a file of this repo.
- With `sandbox = "bwrap"` (default) promptfoo and the agent run in bubblewrap: own pid namespace, empty home, /tmp, /run and /mnt; only node, `harness/node_modules`, the task's `prompt.md` and `src/`, the cell folder and the credentials file are visible. The agent has Bash, and without this it once found and killed live processes on the host. `sandbox = "none"` is for a disposable machine or container only. macOS has no bwrap; there, run inside a Linux container or VM.
- `[limits] watch = true` probes usage with a one-word Haiku call every 10 minutes and pauses new cells near the 5-hour limit. It only gets a reading on a subscription login; `--no-limit-watch` turns it off for one run.
- Judges run `claude -p` / `codex exec` from a temporary empty folder, so no project CLAUDE.md or AGENTS.md reaches them; the user's global Claude Code config still does.

## Invariants

- Never commit `tasks/`, `runs/`, any `prompt.md`, `src/`, model answer, judge output or log of a real task. Real tasks hold other people's messages and code. `example-task/` is the only task in the repo, and it is invented.
- Never edit `results-2026-10/*.json`. They are the published data; their sha256 is in `results-2026-10/README.md`. `recompute.py` must keep printing the article's numbers from them.
- Keep the judge prompt (`INSTR` in `judge.py`), the found rule (an item counts when every judge in use marked it), the bootstrap (4000 resamples, seed 7, percentile 2.5/97.5 over per-task differences) and the permutation test (200000 sign flips, seed 7, Holm over the pairs) as they are. Results computed otherwise do not compare with the article's.
- A checklist is frozen before the first run. Changing `key.json` after answers exist means deleting that task's `runs/marks/*` and judging again, and saying so in any published result.
- Settings are compared only on tasks where both have answers; a task with a failed cell drops out of that pair.

## Adding a task

1. Create `tasks/<id>/` with a category prefix in the id (`cr-`, `plan-`, `fc-`, `intake-`, `recall-`, `turn-`). Format in `guide/task-format.md`, `example-task/` is a complete instance.
2. `src/` is a copy of exactly what the model may read, frozen at the moment the task was set: no later commits, no later messages, no score files, no `.git`. Export a tree with `git -C <repo> archive <rev> | tar -x -C tasks/<id>/src/repo`.
3. `prompt.md` is the same for every setting and ends with the answer format. No hints that point at checklist items.
4. `key.json` has 5-15 atomic items, each checkable from the answer text alone, with `weight` "core" or "minor", and optional `errors` (traps: false claims the material makes look true).
5. Grep `src/` for distinctive words of each item to make sure the answer is not lying in the material.
6. Run `judge.py --check --tasks <id>` (the empty answer must score 0 items, the full-key answer all items) before the first real run.

## Before publishing results of your own run

- Publish only numbers and ids: per answer the task id, setting, repeat, cost, time, tokens, and per judge and item a boolean. That is the shape of `results-2026-10/`.
- Checklist texts are retold, not copied, whenever they quote the material; replace names of people, clients, employers and projects.
- Scan everything you publish for names, emails, hostnames, home paths, account names, tokens and keys, and for any passage longer than about 200 characters that also appears in a `prompt.md`, `src/` file or answer.
