# Results of the 2026-10 run

The eval data from the article (in Russian) [sundwell.dev/ru/blog/eval-models](https://sundwell.dev/ru/blog/eval-models). 24 tasks, six models, two runs per model and task, 288 answers, two judges on every answer.

```bash
python3 recompute.py           # tables
python3 recompute.py --json    # the same values in the shape of the site's data
```

`recompute.py` reads only the three JSON files next to it, needs Python 3.9+ with no dependencies, and runs in a few seconds.

## Files

- `checklists.json` - for each task `id`, `category`, `title` and the checklist items (`id`, `core`, `text`) with traps (`id`, `text`). The texts are retold, and names of people and projects are replaced, exactly as on the site. The original wording quoted correspondence and code, so it is not here. The checklist texts in `checklists.json` are in Russian, as the tasks were
- `runs.json` - one line per answer, `answer` (an id of the form `<task>__<setting>__r<rep>`), `task`, `setting`, `rep`, `cost_usd` (the API price returned by the Agent SDK), `wall_s` (how long the whole cell took, in seconds), `latency_s` (the time of the model call itself), `tokens` and `finished`. The order of the lines is the order in which the runs went, and it matters, the bootstrap and the permutation test depend on it
- `marks.json` - the marks.
  - `checklist` - one line per answer and judge. `judge` is `sol` (GPT-6.1 Sol, effort high, through codex) or `sonnet` (Sonnet 5.5, effort high, through `claude -p`), `items` is the "found" mark for each checklist item, `traps` the "repeated the trap" mark for each trap, `findings_total` how many separate findings the judge counted in the answer
  - `extra` - the second pass over findings beyond the checklist, one line per answer, judge Sonnet 5.5. `units` is how many pieces of the answer it got, `useful` and `minor` how many of them are correct findings outside the checklist ("correct and useful" and "correct but minor"), `false` how many are wrong, `unverifiable` how many it could not check. The remaining pieces are repeats, checklist items or not findings
- `recompute.py` - the recomputation

There are no model answers here, and no quotes or reasoning of the judges, only ids, marks and numbers.

## How it is counted

- An item counts if both judges marked it. A trap counts if both marked that the model repeated it
- The share found for an answer is the counted items divided by all items of the task. For a model it is the mean over its 48 answers
- Pairs of models are compared per task. The difference on a task is the mean of two runs of one model minus the mean of two runs of the other. The interval is a percentile bootstrap over tasks, 4000 resamples, seed 7. p is a sign-flip permutation test over tasks, 200000 rounds, seed 7, with Holm correction over seven pairs
- "Two runs together" is the union of items found by at least one of a model's two runs
- Findings beyond the checklist per answer are `useful` + `minor`
- Cost and time per answer are the mean over a model's answers, and the ratio of cost and time in the article is the ratio of these means

## Checking that the numbers are the same

The output of `recompute.py` matches the site's data (`settings`, `categories`, `pairs`, `twoRuns`, `overview`, 0 mismatches) and contains verbatim three saved printouts of the eval's original scripts (the final tables, the pairs with p and Holm, "two runs versus one").

## Checksums

```
fad51dd6ccf2df7fc7ec90a9670eae9146f0214e1179f1784c8943cb8c71517f  checklists.json
9390849c6cf0af822bae24c911c25756a2e429763bc2e0ff69e06e14c5bb7dd9  marks.json
8b3dd7657e4f053a3c3b747813f31cf5a43766c03cfd2ddc1bd0d993e4c9612e  runs.json
```

Check with `sha256sum *.json`.

When the source files these JSON files were built from last changed, going by the modification times of the files themselves.

- Checklists, last edit on October 17, 2026 at 22:26
- Judges' marks against the checklists, from October 17 22:42 to October 18 12:32
- Runs, the last answer written on October 18 at 08:35
- The second pass over findings beyond the checklist, October 20 from 19:20 to 22:23

Local time, UTC+2.
