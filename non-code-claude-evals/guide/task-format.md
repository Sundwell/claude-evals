# Task format

One task is one folder `tasks/<id>/`. `run.py` takes every folder that has a `prompt.md`, and skips folders whose name starts with `_` (a handy place for drafts and service files). A complete working example is in [../example-task/](../example-task/), and below it is taken apart file by file.

```
tasks/
  cr-shelf-renewals/
    prompt.md      # the task, the same for every model
    key.json       # checklist and traps, the model never sees it
    meta.json      # where the task came from and what you're unsure of, for you only
    src/           # material the model may read
      repo/
      change.diff
```

## id

A short kebab-case Latin id with a type prefix. I had six types.

- `cr-` code review. Read a change and find bugs without running anything outside
- `plan-` plan review. Find errors in a plan by checking it against the code, before anyone starts working from it
- `fc-` fact-checking. Check the claims of a report or research against the sources
- `intake-` intake of incoming messages. Material came in (a thread, a ticket, voice messages), decide what in it matters and what to do about it
- `recall-` recalling a detail from a session. Find what got lost from a long session in a note or documentation written from its results
- `turn-` the next turn in a session. Continue a session from the point where you once did not accept the agent's turn

The prefix is only for you, `score.py` takes the type from `category` in `key.json`.

## prompt.md

The task the model gets. The same for every model and every run, `run.py` passes it as is.

- Briefly, what the material is and where it lies (paths from the working folder, `./...`), what to find or decide and why
- No step lists, no "think carefully" and no hints that point at checklist items
- Where drafts may go. The agent works in a copy of `src/`, and my prompts always said "copies and check scripts only in `./work/`"
- At the end, the answer format. The answer as the final message, not a file, each finding with a heading, a location (file:line or a quote) and a weight "major" or "minor", the last line `Total: N findings`

The language of the prompt follows the material. My tasks were in Russian, and the judge had no trouble checking a Russian answer against a Russian checklist.

The full example is in [../example-task/prompt.md](../example-task/prompt.md). Note the "How to review" paragraph. It sets what counts as a bug and what as a minor issue, and cuts off defects of old code. Without such a paragraph models drown in style and tests, and the answer is harder to check.

## src/

A copy of exactly what the model may read, at the moment the task was set. Before each run `run.py` copies `src/` into a temporary folder, so the model can't spoil it.

- Only a copy, no symlinks
- Nothing that appeared after that moment. No later commits, no later messages of yours, no score files, no git history past that moment. The code tree at the right commit is easy to take with `git -C <repo> archive <rev> | tar -x -C tasks/<id>/src/repo`, don't copy the `.git` folder
- Under 30 MB. No `node_modules`, images or binaries unless the task is about them
- Before the run, search `src/` for the distinctive words of each checklist item, so the answer isn't lying ready in the material

In the example `src/repo/` is the project before the change, and `src/change.diff` is the change itself. So the model sees both the old code and the diff, and can apply it in its own `./work/`.

## key.json

The checklist. The model does not see it, only the judges do.

```json
{
 "task": "example-task",
 "category": "code-review",
 "key_source": "seeded",
 "items": [
  {"id": "K01", "weight": "core",
   "text": "The renewal limit check 'loan.renewals > MAX_RENEWALS' lets a third renewal through. On a loan already renewed twice (renewals == 2), renew() succeeds once more, while the README promises at most two. It should be '>='",
   "evidence": "seeded: shelf/loans.py renew(), README 'at most twice'"},
  {"id": "K05", "weight": "minor",
   "text": "The renew command prints 'Renewed until None', because renew() returns nothing and cli.py prints its result instead of loan.due",
   "evidence": "seeded: shelf/cli.py main(), shelf/loans.py renew() has no return"}
 ],
 "errors": [
  {"id": "E01",
   "text": "The claim that when a book is returned before the due date days_late() becomes negative and fine() gives a negative fine (in fact days_late() clamps the value with max(0, ...), and the change does not touch this code)",
   "evidence": "shelf/loans.py days_late() returns max(0, ...), unchanged by the diff"}
 ]
}
```

Fields.

- `task` - the same id as the folder
- `category` - the task type, `score.py` builds the per-type table from it. I had `code-review`, `plan`, `fact-check`, `intake`, `recall`, `turn`, but any of your own will do
- `key_source` - where the checklist came from, for you and for readers of the results. I had `later-outcome` (what broke later or what was fixed), `his-correction` (what I corrected by hand in an agent's answer), `scored-replay` (what was already checked in a past run), `verified-union` (a union of model findings, re-checked against the sources, the weakest option) and `seeded` (the error was planted on purpose)
- `items` - the items a good answer should find. 5 to 15 per task
  - `id` - `K01`, `K02` and so on in order. The judge must return all ids in the same order, otherwise `judge.py` treats the marks as broken and repeats the call
  - `text` - one checkable statement. The judge sees only the answer and this text, so the text must hold everything needed to recognize the finding, where, on what input, what goes wrong
  - `weight` - `core` if missing it costs something real, `minor` for everything else. `score.py` computes the share found over all items and separately over `core`
  - `evidence` - how you know the item is correct (file:line, a commit, your message with a date). Not shown to the judge
- `errors` - traps, optional. A wrong statement that looks true in the material. If the model repeated it, that is an error. The judge sees only `id` and `text`

The judge gets only `id` and `text` of items and traps from `key.json`. Everything else is for you.

## meta.json

For you, neither the model nor the judge reads it. It comes in handy a week later, when you have forgotten where the task came from.

```json
{
 "id": "example-task",
 "category": "code-review",
 "origin": ["invented for this repository: a fictional library project, the change and its defects are planted"],
 "moment": "the commit before the change; src/repo is the tree at that commit, src/change.diff the change",
 "why": "Shows the task format on material anyone may read; four planted bugs a reader of the diff can reproduce, one minor issue and one trap in unchanged code.",
 "key_doubts": ["K05 may be called a bug by some answers; it stays minor because the renewal itself works."],
 "est_minutes_opus_high": 3
}
```

- `origin` - where the material came from, paths and commits
- `moment` - the moment at which `src/` is frozen
- `why` - one line on why this is a fair test
- `key_doubts` - items you're unsure of, and why
- `est_minutes_opus_high` - roughly how long the task takes a strong model. My tasks took 3-12 minutes, and longer ones are better trimmed

## Check before the first run

```bash
python3 harness/judge.py --check --tasks <id>
```

For each task it writes two artificial answers, an empty one and one made of the checklist itself, to `runs/check-answers/` and marks them in `runs/check-marks/`. The empty one must have no items found, the full one all of them. An item the judge did not recognize in its own text is worded so that it can't be recognized in a real answer either.

## What run.py writes

```
runs/
  secret-map.jsonl                 # one line per answer: task, model, run number, cost, time, tokens
  answers/<task>__<hash>.md        # answers, the name does not give away the model
  marks/<task>__<hash>__sonnet.json
  <task>/<setting>__r<rep>/        # promptfoo config, result.json, log and cell.json of this cell
  run.log
```

Answers and marks quote your material, so `runs/` is in `.gitignore`, as is `tasks/`.
