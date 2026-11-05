#!/usr/bin/env python3
"""Tables from <runs>/secret-map.jsonl and <runs>/marks: found share per setting, paired differences, cost, time.

An item counts as found when every judge in use marks it present (with two judges, both). Paired differences
are per task (mean of the runs of each setting), with a bootstrap 95% interval over tasks (4000 resamples,
seed 7) and a sign-flip permutation p (200000 rounds, seed 7) with Holm correction over the pairs.
The same methods as results-2026-10/recompute.py, so numbers of your run mean what the article's mean.

  score.py
  score.py --judges sonnet     # count one judge's marks only
"""
import argparse
import json
import os
import random
import statistics
import sys
from collections import defaultdict

from common import add_common_args, load_config

BOOT_N = 4000
PERM_ROUNDS = 200000
SEED = 7


def load(cfg):
    cells = {}
    path = os.path.join(cfg["runs_dir"], "secret-map.jsonl")
    if not os.path.exists(path):
        sys.exit(f"no {path} yet, run run.py first")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            c = json.loads(line)
            cells[c["answer"][:-3]] = c
    keys = {}
    for t in os.listdir(cfg["tasks_dir"]):
        p = os.path.join(cfg["tasks_dir"], t, "key.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                keys[t] = json.load(fh)
    marks = defaultdict(dict)
    mdir = os.path.join(cfg["runs_dir"], "marks")
    for f in os.listdir(mdir) if os.path.isdir(mdir) else []:
        if f.endswith(".json"):
            with open(os.path.join(mdir, f), encoding="utf-8") as fh:
                m = json.load(fh)
            marks[m["answer"][:-3]][m["judge"]] = m
    return cells, keys, marks


def boot(diffs, n=BOOT_N):
    if len(diffs) < 2:
        return (float("nan"), float("nan"))
    rnd = random.Random(SEED)
    means = sorted(statistics.mean(rnd.choices(diffs, k=len(diffs))) for _ in range(n))
    return means[int(n * 0.025)], means[int(n * 0.975)]


def perm_p(d, rnd):
    obs = abs(sum(d))
    hit = sum(abs(sum(x if rnd.random() < 0.5 else -x for x in d)) >= obs - 1e-12 for _ in range(PERM_ROUNDS))
    return (hit + 1) / (PERM_ROUNDS + 1)


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out, run = [0.0] * len(ps), 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - k) * ps[i]))
        out[i] = run
    return out


def main():
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.add_argument("--judges", default="", help="comma-separated, default every judge enabled in the config")
    a = ap.parse_args()
    cfg = load_config(a.config, a.tasks_dir, a.runs_dir)
    judges = sorted(a.judges.split(",") if a.judges else [j for j, c in cfg["judges"].items() if c.get("enabled")])
    cells, keys, marks = load(cfg)
    rows = []
    agree = [0, 0]
    waiting = 0
    for stem, c in cells.items():
        js = marks.get(stem, {})
        if c["task"].startswith("_") or c["task"] not in keys:
            continue
        if any(j not in js for j in judges):
            waiting += 1
            continue
        k = keys[c["task"]]
        weight = {i["id"]: i["weight"] for i in k["items"]}
        present = [{i["id"] for i in js[j]["items"] if i["present"]} for j in judges]
        made = [{e["id"] for e in js[j].get("errors", []) if e.get("made")} for j in judges]
        both, either = set.intersection(*present), set.union(*present)
        if len(judges) == 2:
            for x, y in zip(js[judges[0]]["items"], js[judges[1]]["items"]):
                agree[0] += x["present"] == y["present"]
                agree[1] += 1
        core = [i for i in weight if weight[i] == "core"]
        rows.append({**c, "found": len(both) / len(weight), "found_either": len(either) / len(weight),
                     "core": (len(both & set(core)) / len(core)) if core else None,
                     "errors": len(set.intersection(*made)), "category": k["category"], "found_ids": sorted(both),
                     "n_items": len(weight)})
    if not rows:
        print(f"no judged cells yet ({waiting} answers wait for judges {','.join(judges)})")
        return
    head = f"cells judged {len(rows)} by {','.join(judges)}"
    if agree[1]:
        head += f", judge agreement {agree[0] / agree[1]:.1%} on {agree[1]} item marks"
    if waiting:
        head += f", {waiting} more wait for a judge"
    print(head + "\n")
    by = defaultdict(list)
    for r in rows:
        by[r["setting"]].append(r)
    found_label = "found (both judges)" if len(judges) == 2 else "found (all judges)"
    print(f"| setting | runs | {found_label} | found (either) | core found | wrong claims per run | $ per run | min per run |")
    print("|---|---|---|---|---|---|---|---|")
    for s, rs in sorted(by.items()):
        cores = [r["core"] for r in rs if r["core"] is not None]
        print(f"| {s} | {len(rs)} | {statistics.mean(r['found'] for r in rs):.0%} | "
              f"{statistics.mean(r['found_either'] for r in rs):.0%} | "
              f"{statistics.mean(cores) if cores else 0:.0%} | {statistics.mean(r['errors'] for r in rs):.2f} | "
              f"{statistics.mean(r['cost_usd'] or 0 for r in rs):.2f} | {statistics.mean(r['wall_s'] for r in rs) / 60:.1f} |")
    per = defaultdict(lambda: defaultdict(list))
    for r in rows:
        per[r["task"]][r["setting"]].append(r)

    print("\nFound share per setting, bootstrap 95% interval over the per-task means")
    for s, rs in sorted(by.items()):
        means = [statistics.mean(r["found"] for r in ss[s]) for ss in per.values() if s in ss]
        lo, hi = boot(means)
        ci = f"({lo:.1%} .. {hi:.1%})" if len(means) >= 2 else "(no interval from one task)"
        print(f"- {s}: {statistics.mean(r['found'] for r in rs):.1%} {ci} over {len(means)} tasks")

    pairs = [(A, B) for A, B in cfg["score"]["pairs"] if A in by and B in by]
    print("\nPaired by task, difference of found share (A minus B), mean and bootstrap 95% interval")
    print("| A vs B | tasks | mean diff | 95% interval | A better / equal / B better | cost ratio | time ratio |")
    print("|---|---|---|---|---|---|---|")
    diffs = []
    for A, B in pairs:
        d, cr, tr, wins = [], [], [], [0, 0, 0]
        for ss in per.values():
            if A in ss and B in ss:
                fa = statistics.mean(r["found"] for r in ss[A])
                fb = statistics.mean(r["found"] for r in ss[B])
                d.append(fa - fb)
                wins[0 if fa > fb else 1 if fa == fb else 2] += 1
                ca, cb = (statistics.mean(r["cost_usd"] or 0 for r in ss[x]) for x in (A, B))
                ta, tb = (statistics.mean(r["wall_s"] for r in ss[x]) for x in (A, B))
                if cb and tb:
                    cr.append(ca / cb)
                    tr.append(ta / tb)
        diffs.append((A, B, d))
        if d:
            lo, hi = boot(d)
            cost = f"{statistics.median(cr):.2f}" if cr else "-"
            time_ = f"{statistics.median(tr):.2f}" if tr else "-"
            print(f"| {A} vs {B} | {len(d)} | {statistics.mean(d):+.1%} | {lo:+.1%} .. {hi:+.1%} | "
                  f"{wins[0]} / {wins[1]} / {wins[2]} | {cost} | {time_} |")

    # One generator runs through the pairs in order, so a pair's p depends on its place in the config.
    tested = [(A, B, [100 * x for x in d]) for A, B, d in diffs if len(d) >= 2]
    if tested:
        rnd = random.Random(SEED)
        ps = [perm_p(d, rnd) for _, _, d in tested]
        print("\nPairs, sign-flip permutation p over tasks, Holm over the pairs")
        for (A, B, d), p, h in zip(tested, ps, holm(ps)):
            print(f"  {A} - {B}: {statistics.mean(d):+.2f} pp, p {p:.4f}, Holm {h:.4f}")

    cats = defaultdict(lambda: defaultdict(list))
    for r in rows:
        cats[r["category"]][r["setting"]].append(r["found"])
    print("\nFound share by category")
    sets = sorted(by)
    print("| category | " + " | ".join(sets) + " |")
    print("|---|" + "---|" * len(sets))
    for c, ss in sorted(cats.items()):
        print(f"| {c} | " + " | ".join(f"{statistics.mean(ss[s]):.0%}" if ss.get(s) else "-" for s in sets) + " |")

    print("\nEnsemble, share of key items found by the union of two runs of one setting")
    for s in sets:
        one, two = [], []
        for ss in per.values():
            rs = ss.get(s, [])
            if len(rs) >= 2:
                one.append(statistics.mean(len(r["found_ids"]) for r in rs) / rs[0]["n_items"])
                two.append(len(set(rs[0]["found_ids"]) | set(rs[1]["found_ids"])) / rs[0]["n_items"])
        if one:
            print(f"- {s}: one run {statistics.mean(one):.0%}, two runs together {statistics.mean(two):.0%}")

    compare = []
    for lo, hi in cfg["score"]["two_runs"]:
        d, w = [], [0, 0, 0]
        for ss in per.values():
            if len(ss.get(lo, [])) >= 2 and ss.get(hi):
                n = ss[lo][0]["n_items"]
                two = len(set(ss[lo][0]["found_ids"]) | set(ss[lo][1]["found_ids"])) / n
                one = statistics.mean(len(r["found_ids"]) for r in ss[hi]) / n
                d.append(100 * (two - one))
                w[0 if two > one else 1 if two == one else 2] += 1
        if len(d) >= 2:
            compare.append((lo, hi, d, w))
    if compare:
        rnd = random.Random(SEED)
        ps = [perm_p(d, rnd) for _, _, d, _ in compare]
        print("\nTwo runs of the first setting together against one run of the second, per task, Holm over the comparisons")
        for (lo, hi, d, w), p, h in zip(compare, ps, holm(ps)):
            b_lo, b_hi = boot(d)
            cost_two = 2 * statistics.mean(r["cost_usd"] or 0 for r in by[lo])
            cost_one = statistics.mean(r["cost_usd"] or 0 for r in by[hi])
            par = statistics.mean(max(r["wall_s"] for r in ss[lo]) for ss in per.values() if lo in ss) / 60
            one = statistics.mean(statistics.mean(r["wall_s"] for r in ss[hi]) for ss in per.values() if hi in ss) / 60
            print(f"{lo} x2 vs {hi} x1: {statistics.mean(d):+.1f} pp ({b_lo:+.1f} .. {b_hi:+.1f}), better/equal/worse "
                  f"{w[0]}/{w[1]}/{w[2]}, p {p:.4f}, Holm {h:.4f}, $ {cost_two:.2f} vs {cost_one:.2f}, "
                  f"min in parallel {par:.1f} vs {one:.1f}")


if __name__ == "__main__":
    main()
