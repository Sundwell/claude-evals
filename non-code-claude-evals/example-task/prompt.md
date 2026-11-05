Task: review a finished change before it is committed. You only read and check, you don't write code and don't edit files in ./repo.

Material in the working folder.
- ./repo/ - a small project called shelf (Python 3.11, no dependencies) at the commit before the change. It tracks book loans at a district library, due dates and late fines, with a command line `python3 -m shelf.cli`.
- ./change.diff - the change. It adds loan renewals and a cap on fines. What is intended is written in the "Renewals" section of the README inside this same change. It applies to ./repo with `git apply`.

Find the defects of this change.

How to review.
- A bug is only reproducible behavior that breaks what this change is for. Name the concrete input or state and what goes wrong.
- Everything else (style, names, structure, texts, tests, cases with no reachable trigger) is minor issues, in a separate section.
- Don't include defects of old code that the change does not touch.

There is no network. You may copy ./repo to ./work/, apply the change there and run functions and tests (`python3 -m unittest`). Copies, drafts and check scripts go only in ./work/.

Answer format - as the final message, not a file. Two sections, `## Bugs` and `## Minor issues`. Each finding like this.

### N. <one line on what is wrong>
- Where: file:line or a quote from the change.
- Trigger: input or state (required for a bug).
- What is wrong: what happens and what should happen.
- Weight: "major" or "minor".

The last line is `Total: N findings, B of them bugs`.
