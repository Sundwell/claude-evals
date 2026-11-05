# How to build tasks from your own work

The most expensive part of an eval is not the run but the tasks. The run goes by itself, while the checklist for a task has to be written so that it is correct, checkable and does not give away the answer. Below is how I built my 24 tasks and what I stepped on along the way. The file format is in [task-format.md](task-format.md).

## Where to get tasks

Take past episodes of your work where you already know the right answer, and know it not from a model's words. In order of decreasing reliability.

1. **What broke later or what was fixed later.** A change that was followed an hour or a day later by a commit with a fix. The checklist is the bugs that were fixed, and the material is the code at the commit before the fix. That is how all my code review tasks were built (`key_source: later-outcome`)
2. **What you corrected by hand.** A turn of an agent in a long session that you did not accept and redid. The material is the session before that turn, the checklist is what you said or did yourself afterwards (`his-correction`)
3. **What was already checked before.** Findings of a past plan review that were later confirmed in the code (`scored-replay`)
4. **Planted errors.** You take real material and put defects into it yourself (`seeded`). The checklist is then correct by construction, but such errors are usually cleaner than real ones, and the task comes out easier
5. **A union of model findings, re-checked against the sources** (`verified-union`). The weakest option, because the checklist is born from the opinion of the same models you then compare. I had this in only two tasks

My task types were code review, plan review, fact-checking of research, intake of incoming messages, recalling a detail from a session and the next turn in a session. Take the ones you actually have. 3-5 tasks per type is the minimum to get at least some direction per type, and even then a difference under 5-7 p.p. within a type is noise.

Make sure the tasks don't all come from one place. 10 of my 24 tasks come from one project, and all 4 next-turn tasks come from one session, so on other material the numbers may come out different.

## Freeze the material

The model must see exactly what was at hand at the moment of the task, and nothing later.

- Take the code at the right commit with `git archive`, without the `.git` folder, otherwise the fix sits in the history
- Cut correspondence and transcripts at the moment of the task. None of your later messages, no next rounds
- No score files, no notes on "what is wrong here", no reports of past reviews
- Trim the material so that a strong model spends 3-12 minutes on the task. A 40-minute task eats limits and adds almost nothing
- At the end, search the material for the distinctive words of each checklist item. If an item is written there in plain text, any model will find it, and the task measures nothing

Drop an item whose knowledge is not in the material. I had an item about a library that the material never mentioned, it was only in my later messages, and it could not be found in principle.

## Write the checklist

- **One item, one problem or one fact.** "The limit lets a third renewal through" and "the limit is not saved between calls" are two items, not one
- **An item is checkable from the answer text alone.** The judge sees only the answer and the item text, it does not see the sources. So the item must say where, on what input and what goes wrong, not just "a bug in renew()"
- **`core` and `minor`.** `core` if missing it costs something real (a lost order, a wrong sum, a broken main scenario). Everything else is `minor`. Without this split, easy small things pull the share found up for a model that misses the main thing
- **Items about how the answer behaves are fine too.** For example, "does not propose to start new work" or "does not claim that X is already done" for next-turn tasks. The judge marks them when the answer as a whole behaves that way
- **Traps.** If the material has a statement that looks true but is wrong (an old README, an outdated comment, a false hypothesis in a report), put it in `errors`. Repeating a trap counts as a model's error
- **Only about what changed.** In a review of a change, an item about old code that the change does not touch is not a review finding. I removed those
- **No hints in the prompt.** An example of a trigger in the prompt ("for example, if the response comes back with an error") points at a specific item. I cleaned them out after the first check

5-15 items per task. With fewer than five, a single task starts jumping by 20-25 p.p. on one item.

## Check the checklist before the run

An error in the checklist can't be told apart from a model's error later, so the check comes before the first run.

- **An independent check against the sources.** A separate agent that did not write the checklist checks each item against `src/` and says whether it is correct and findable from the material. After such a check three of my code review tasks were dropped entirely, because not enough correct items were left in them, new ones came in their place, and a few items left other tasks
- **A human.** I checked half of the checklists myself, in two rounds each. The checklists of plans and of other people's code I honestly could not check ("I never even looked at that code"), so only checker agents checked them. Write down for yourself who checked each task, you will need it later to describe the result honestly
- **`judge.py --check`.** An empty answer must give 0%, an answer made of the checklist itself 100%. If the judge did not recognize an item in its own text, rewrite the item
- **Freezing.** After the first marking the checklists do not change. My last checklist edit was on October 17 at 22:26, the judge's first marking at 22:42. If you still had to fix an item, that task's marks have to be deleted and made again

## Judges

- **Pick the judge on answers with known marks.** I took 4 reports with marks against a 27-item checklist known in advance and ran three GPT candidates. GPT-6.1 Sol agreed with me in 98.1%, the others in 94-95%
- **Two judges from different families.** An item counts only if both marked it. That way one judge model can't favor its own. The check is simple, compute everything with one judge from the other family and see whether the order of the models held (for me it held)
- **The judge does not know whose answer it is.** `run.py` names answer files by a hash, and the model and setting are kept separately in `secret-map.jsonl`
- **A broken judge answer.** Sometimes a judge returns the wrong JSON or loses an item. `judge.py` checks that all ids came back in order, and repeats the call once. That happened to me five times
- **Check the judges by hand.** Take 50-60 verdicts blind, without looking at the judge's answer, and compare. It is the only way to know whether its thousand marks can be trusted

## What I did not account for at first

- **A sandbox from the first run.** The agent in a task has Bash. On the first day my eval agents, without a sandbox, found and killed live processes on my machine. After that everything ran in bubblewrap, and `run.py` does so by default
- **Findings beyond the checklist.** At first everything a model found beyond the checklist was simply thrown away, and a model that found something else that was correct looked worse than it is. It was not me who noticed this but a colleague I showed the first numbers to. If this matters to you, plan a second pass in advance, where the judge checks each such finding against the sources and rates it "correct and useful", "correct but minor" or "wrong". The line between "useful" and "minor" is blurry even for me, and the judge agreed with me on it in 72% of cases
- **The ceiling.** If no model found a `core` item in any run, check that it is findable from the material at all. If it is, that is just the ceiling of the task, but it is worth knowing about
- **A cut-off answer.** Check that no run stopped on a turn or budget limit, and look at the shortest answer of each model. A truncated answer looks like a bad one
- **Two runs at least.** A second run of the same model added 7-11 p.p. to what each model found, and a single run is noticeably noisy. With one run per cell, comparing models on a task is close to impossible
