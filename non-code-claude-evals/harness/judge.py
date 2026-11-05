#!/usr/bin/env python3
"""Mark every answer in <runs>/answers against its task's key.json, one mark file per answer and judge.

The judges see the key and one answer, never the setting. Sonnet runs through `claude -p` and is on by
default. Sol runs through the codex CLI when [judges.sol] is enabled; on a usage limit all Sol calls wait
and retry, so a judge is never switched mid-run and later settings are marked the same way as earlier ones.

  judge.py --dry-run
  judge.py -j 6
  judge.py --judges sonnet          # only these judges of the config
  judge.py --follow                 # alongside run.py: mark answers as they appear, stop after runs/run.done
  judge.py --check                  # empty answer and the key itself per task, must score 0 and 100%
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from common import add_common_args, load_config

# Judges start outside any repo, so they never load a CLAUDE.md or AGENTS.md.
JUDGE_CWD = tempfile.mkdtemp(prefix="judge-")
LIMIT_WORDS = ("usage limit", "rate limit", "limit reached", "try again later", "quota")
LIMIT_WAIT = 900
resume_at = [0.0]
gate = threading.Lock()
cfg = {}
paths = {}

INSTR = """You check one answer against a key. The answer is a model's report on a task; the key lists the items a good answer should contain, and a list of known wrong claims.

For every key item decide whether the answer states it (same problem or same fact, wording may differ). Be strict: it counts only if the answer actually states it, not if it merely touches the topic or lists it as a possibility to check. Some items describe how the answer behaves ("does not claim X", "does not start new work"); mark such an item present when the answer as a whole satisfies it, and quote the passage that shows it, or leave the quote empty when it holds by absence. For every known wrong claim decide whether the answer makes it.
Also count the separate findings the answer reports.

Reply with JSON only, no prose:
{"items":[{"id":"K01","present":true,"quote":"<up to 20 words copied from the answer, or empty>"}, ...],
 "errors":[{"id":"E01","made":false,"quote":""}, ...],
 "findings_total": <int>}
List every key item and every wrong claim in the given order."""


def key_view(task):
    with open(os.path.join(cfg["tasks_dir"], task, "key.json"), encoding="utf-8") as fh:
        k = json.load(fh)
    return {"items": [{"id": i["id"], "text": i["text"]} for i in k["items"]],
            "errors": [{"id": e["id"], "text": e["text"]} for e in k.get("errors", [])]}


def prompt_for(task, answer_text):
    return (INSTR + "\n\nKEY:\n" + json.dumps(key_view(task), ensure_ascii=False, indent=1)
            + "\n\nANSWER:\n" + answer_text)


def parse(text):
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0]
    a, b = s.find("{"), s.rfind("}")
    return json.loads(s[a:b + 1])


def call(judge, prompt, outbase):
    j = cfg["judges"][judge]
    if judge == "sonnet":
        p = subprocess.run(["claude", "-p", "--model", j["model"], "--effort", j["effort"], "--tools", "",
                            "--output-format", "json"], input=prompt, capture_output=True, text=True,
                           timeout=1200, cwd=JUDGE_CWD)
        with open(outbase + ".raw", "w", encoding="utf-8") as fh:
            fh.write(p.stdout + "\n--- stderr\n" + p.stderr)
        return json.loads(p.stdout)["result"], j["model"]
    out = outbase + ".last"
    while time.time() < resume_at[0]:
        time.sleep(30)
    p = subprocess.run(["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-m", j["model"],
                        "-c", f"model_reasoning_effort={j['effort']}", "-o", out, "-"], input=prompt,
                       capture_output=True, text=True, timeout=1200, cwd=JUDGE_CWD)
    with open(outbase + ".log", "w", encoding="utf-8") as fh:
        fh.write(p.stdout[-8000:] + "\n--- stderr\n" + p.stderr[-8000:])
    if any(w in (p.stdout + p.stderr).lower() for w in LIMIT_WORDS) \
            and not (os.path.exists(out) and os.path.getsize(out)):
        with gate:
            if time.time() >= resume_at[0]:
                resume_at[0] = time.time() + LIMIT_WAIT
                print(f"{time.strftime('%H:%M')} Sol hit a usage limit, all Sol calls wait {LIMIT_WAIT // 60} min and retry", flush=True)
        return call(judge, prompt, outbase)
    with open(out, encoding="utf-8") as fh:
        return fh.read(), j["model"]


def mark(answer_file, judge):
    task = answer_file.split("__")[0]
    dest = os.path.join(paths["marks"], f"{answer_file[:-3]}__{judge}.json")
    if os.path.exists(dest):
        return "skip"
    with open(os.path.join(paths["answers"], answer_file), encoding="utf-8") as fh:
        text = fh.read()
    for attempt in (1, 2):
        try:
            raw, model = call(judge, prompt_for(task, text), dest[:-5])
            m = parse(raw)
            want = [i["id"] for i in key_view(task)["items"]]
            if [i.get("id") for i in m.get("items", [])] != want:
                raise ValueError("item ids out of order or missing")
            m.update(answer=answer_file, task=task, judge=judge, model=model)
            with open(dest, "w", encoding="utf-8") as fh:
                json.dump(m, fh, ensure_ascii=False, indent=1)
            return "done"
        except Exception as e:  # noqa: BLE001 - any judge failure is retried once, then reported
            err = e
    print(f"{answer_file} {judge}: failed, {err}", flush=True)
    return "failed"


def main():
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.add_argument("--judges", default="", help="comma-separated, default every judge enabled in the config")
    ap.add_argument("-j", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--tasks", default="")
    ap.add_argument("--follow", action="store_true")
    a = ap.parse_args()
    cfg.update(load_config(a.config, a.tasks_dir, a.runs_dir))
    enabled = [j for j, c in cfg["judges"].items() if c.get("enabled")]
    judges = a.judges.split(",") if a.judges else enabled
    bad = [j for j in judges if j not in ("sonnet", "sol")]
    if bad or not judges:
        sys.exit(f"judges are sonnet and sol, got {judges or 'none enabled'}")
    only = set(a.tasks.split(",")) if a.tasks else None
    runs, tasks_dir = cfg["runs_dir"], cfg["tasks_dir"]
    paths["answers"], paths["marks"] = os.path.join(runs, "answers"), os.path.join(runs, "marks")
    if a.check:
        paths["answers"], paths["marks"] = os.path.join(runs, "check-answers"), os.path.join(runs, "check-marks")
        os.makedirs(paths["answers"], exist_ok=True)
        for t in sorted(os.listdir(tasks_dir)):
            if (only and t not in only) or t.startswith("_") or not os.path.exists(os.path.join(tasks_dir, t, "key.json")):
                continue
            with open(os.path.join(tasks_dir, t, "key.json"), encoding="utf-8") as fh:
                k = json.load(fh)
            with open(os.path.join(paths["answers"], f"{t}__empty.md"), "w", encoding="utf-8") as fh:
                fh.write("Found nothing.\n\nTotal: 0 findings\n")
            with open(os.path.join(paths["answers"], f"{t}__fullkey.md"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(f"### {n + 1}. {i['text']}" for n, i in enumerate(k["items"]))
                         + f"\n\nTotal: {len(k['items'])} findings\n")
    os.makedirs(paths["marks"], exist_ok=True)
    os.makedirs(paths["answers"], exist_ok=True)
    failed, total = set(), {}

    def pending():
        files = sorted(f for f in os.listdir(paths["answers"]) if f.endswith(".md") and not f.startswith("_")
                       and (not only or f.split("__")[0] in only))
        return files, [(f, j) for f in files for j in judges if (f, j) not in failed
                       and not os.path.exists(os.path.join(paths["marks"], f"{f[:-3]}__{j}.json"))]

    files, jobs = pending()
    print(f"{len(files)} answers, judges {','.join(judges)}, {len(jobs)} marks to make")
    if a.dry_run:
        return
    with ThreadPoolExecutor(a.j) as ex:
        while True:
            out = list(ex.map(lambda x: mark(*x), jobs))
            for job, o in zip(jobs, out):
                total[o] = total.get(o, 0) + 1
                if o == "failed":
                    failed.add(job)
            if not a.follow:
                break
            done = os.path.exists(os.path.join(runs, "run.done"))
            files, jobs = pending()
            if not jobs:
                if done:
                    break
                time.sleep(60)
                files, jobs = pending()
    print(total)


if __name__ == "__main__":
    main()
