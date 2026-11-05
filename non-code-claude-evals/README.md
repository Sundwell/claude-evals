# non-code-claude-evals

An eval of Claude models on tasks that are not about writing code. In October 2026 I ran six models (Sonnet 5.5 medium and xhigh, Opus 5.5 high and xhigh, Fable 5.1 low and high) on 24 tasks from my own work, two runs per model and task, 288 answers. The tasks are of six types (code review, fact-checking, intake of incoming messages, plan review, recalling a detail from a session, and the next turn in a session). Results and conclusions are in the article (in Russian) [sundwell.dev/ru/blog/eval-models](https://sundwell.dev/ru/blog/eval-models).

Here is the code that ran it, the task format with a guide on how to build your own tasks, and the data from which every number in the article is recomputed.

## What is here

- [harness/](harness/) - `run.py` runs each (task, model) pair the required number of times, `judge.py` marks the answers against the checklists, `score.py` computes the tables. Settings are in `config.example.toml`
- [guide/task-format.md](guide/task-format.md) - the exact format of a task folder with a worked example
- [guide/collect-tasks.md](guide/collect-tasks.md) - how to build tasks from your own work, write a checklist and not step on what I stepped on
- [example-task/](example-task/) - one made-up code review task (a small library project, a change with planted bugs and one trap), to run the whole thing end to end in a couple of minutes
- [results-2026-10/](results-2026-10/) - the checklists of the 24 tasks, the judges' marks for every item, the cost and time of every answer, and `recompute.py`, which prints the article's numbers
- [AGENTS.md](AGENTS.md) - the same for an agent that helps you with the repo

## What is not here and why

The tasks themselves are not here. They are my real work material, correspondence with clients, code of client projects, transcripts of my sessions, and I can't publish them. So there are no task prompts, no model answers (the answers quote the material), no raw logs and no judges' reasoning (the judges quote it too).

What is left is a retelling of the checklist items (names of people and projects in them are replaced, as on the site), and for each answer only numbers and "found / not found" marks. That is enough to recompute every number in the article, but not enough to re-check the judges themselves. For your own tasks you will have everything, so you can repeat the whole eval on them.

The second pass over findings beyond the checklist (the judge checks every finding that is not in the checklist against the sources and rates it "correct and useful", "correct but minor" or "wrong") is not in `harness/`. Its final counts for each answer are in `results-2026-10/marks.json`, but the pass itself is not yet in a shape that runs without edits.

## Quick start on the example

You need Python 3.11+, Node.js 22.22+ and a logged-in Claude Code (a subscription or `ANTHROPIC_API_KEY`). On Linux also bubblewrap (`apt install bubblewrap`), since the agent in a task gets Bash and runs in a sandbox by default. The Claude Code login file is visible to the agent in the sandbox and open for writing, otherwise Claude Code can't save a refreshed login. So it is better to run other people's tasks on a separate account.

```bash
cd non-code-claude-evals
(cd harness && npm ci)
mkdir -p tasks && cp -r example-task tasks/
python3 harness/run.py --dry-run
python3 harness/run.py --settings sonnet-medium --repeat 1
python3 harness/judge.py
python3 harness/score.py
```

`run.py --dry-run` only prints what will be run. One Sonnet 5.5 medium cell on the example took me 20 seconds and cost $0.06 at API prices, and the judge found all 5 items in its answer. Scaled by the ratio of model prices in the article, all 12 cells of the example (6 models, 2 runs each) come to about $3-4. A judge call costs as much as the context of your Claude Code weighs (the judge runs as a plain `claude -p` under your name, with your global CLAUDE.md, skills and MCP), and with my heavy global config it was $0.89 per answer. On a subscription all of this goes into its limits; `run.py` itself pauses new cells when the 5-hour window is almost used up, and stops before the end of the weekly one.

The `tasks/` and `runs/` folders are in `.gitignore`. A stopped run continues with the same command, finished cells and marks are skipped.

## On your own tasks

1. Build 10-25 tasks following [guide/collect-tasks.md](guide/collect-tasks.md) and put them in `tasks/<id>/` in the format of [guide/task-format.md](guide/task-format.md)
2. If you want to change the models, effort, number of runs, or turn on a second judge, copy `harness/config.example.toml` to `harness/config.toml` and edit it. The scripts use `config.toml` when it exists
3. `python3 harness/judge.py --check` checks every checklist on two artificial answers, an empty one and one made of the checklist itself. The judge must give 0% and 100%, otherwise an item is written in a way that can't be recognized
4. Then `run.py`, `judge.py` (it can run alongside `run.py` with the `--follow` flag) and `score.py`

The second judge, GPT-6.1 Sol through the codex CLI, is turned on in the config (`[judges.sol] enabled = true`). With two judges an item counts only if both marked it, as in the article. With Sonnet alone the numbers come out a bit higher; for me "at least one judge" gave 6-10 p.p. more than "both".

## Recompute the article's numbers

```bash
python3 results-2026-10/recompute.py
```

It prints the share found for each model with a 95% interval, pairwise comparisons with p and Holm correction, the breakdown by task type, "two runs versus one", traps, findings beyond the checklist, and cost and time per answer. It reads nothing but the three JSON files next to it, and needs no network and no models. What is in which file is in [results-2026-10/README.md](results-2026-10/README.md).
