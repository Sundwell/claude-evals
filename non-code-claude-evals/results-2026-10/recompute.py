#!/usr/bin/env python3
"""Recompute the numbers of the article https://sundwell.dev/ru/blog/eval-models from three files.

Reads only checklists.json, marks.json and runs.json next to this script. Python 3.9+, stdlib only.

An item counts as found when both judges marked it present. Per-task differences are the mean of the two
runs of each setting. Intervals are a percentile bootstrap over tasks (4000 resamples, seed 7), p-values a
sign-flip permutation over tasks (200000 rounds, seed 7) with Holm correction over the pairs of one measure.

  recompute.py           # the tables
  recompute.py --json    # the same values in the shape of the site's data file
"""
import argparse
import json
import os
import random
import statistics
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ["sonnet-medium", "sonnet-xhigh", "opus-high", "opus-xhigh", "fable-low", "fable-high"]
CATEGORIES = ["code-review", "fact-check", "intake", "plan", "recall", "turn"]
PAIRS = [("opus-xhigh", "opus-high"), ("fable-high", "opus-high"), ("fable-high", "opus-xhigh"),
         ("fable-high", "fable-low"), ("sonnet-xhigh", "sonnet-medium"), ("opus-high", "sonnet-xhigh"),
         ("opus-high", "sonnet-medium")]
# (model, two runs of this setting, against one run of this one, the two are neighbouring effort levels)
TWO_RUNS = [("Opus", "opus-high", "opus-xhigh", True), ("Fable", "fable-low", "fable-high", False),
            ("Sonnet", "sonnet-medium", "sonnet-xhigh", False)]
BOOT_N = 4000
PERM_ROUNDS = 200000
SEED = 7


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


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def load():
    tasks = {t["id"]: t for t in read("checklists.json")["tasks"]}
    answers = read("runs.json")["answers"]
    m = read("marks.json")
    marks = defaultdict(dict)
    for x in m["checklist"]:
        marks[x["answer"]][x["judge"]] = x
    extra = {x["answer"]: x for x in m["extra"]}
    return tasks, answers, marks, extra


def rows_of(tasks, answers, marks, judges=None):
    """One row per answer. The answer order of runs.json is kept: bootstrap and permutation results depend on it."""
    rows, agree = [], [0, 0]
    for c in answers:
        js = marks[c["answer"]]
        names = judges or sorted(js)
        t = tasks[c["task"]]
        ids = [i["id"] for i in t["items"]]
        core = {i["id"] for i in t["items"] if i["core"]}
        present = [{k for k, v in js[j]["items"].items() if v} for j in names]
        made = [{k for k, v in js[j]["traps"].items() if v} for j in names]
        if len(names) == 2:
            a, b = (js[j]["items"] for j in names)
            for i in ids:
                agree[0] += a[i] == b[i]
                agree[1] += 1
        both = set.intersection(*present)
        either = set.union(*present)
        errs = set.intersection(*made)
        rows.append({**c, "found": len(both) / len(ids), "found_either": len(either) / len(ids),
                     "core": (len(both & core) / len(core)) if core else None, "errors": len(errs),
                     "category": t["category"], "both": both, "n_items": len(ids)})
    return rows, agree


def group(rows):
    by = defaultdict(list)
    per = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[r["setting"]].append(r)
        per[r["task"]][r["setting"]].append(r)
    return by, per


def compute(tasks, answers, marks, extra):
    rows, agree = rows_of(tasks, answers, marks)
    by, per = group(rows)

    pairs = []
    for A, B in PAIRS:
        d, cr, tr, wins, ts = [], [], [], [0, 0, 0], []
        for t, ss in per.items():
            if A in ss and B in ss:
                fa = statistics.mean(r["found"] for r in ss[A])
                fb = statistics.mean(r["found"] for r in ss[B])
                d.append(fa - fb)
                ts.append(t)
                wins[0 if fa > fb else 1 if fa == fb else 2] += 1
                ca, cb = (statistics.mean(r["cost_usd"] or 0 for r in ss[x]) for x in (A, B))
                ta, tb = (statistics.mean(r["wall_s"] for r in ss[x]) for x in (A, B))
                if cb and tb:
                    cr.append(ca / cb)
                    tr.append(ta / tb)
        cost = {s: statistics.mean(r["cost_usd"] or 0 for r in by[s]) for s in (A, B)}
        wall = {s: statistics.mean(r["wall_s"] for r in by[s]) for s in (A, B)}
        pairs.append({"a": A, "b": B, "d": d, "tasks": ts, "ci": boot(d), "wins": wins,
                      "cost_median": statistics.median(cr), "time_median": statistics.median(tr),
                      "cost_ratio": cost[A] / cost[B], "time_ratio": wall[A] / wall[B]})

    # One generator runs through the seven pairs in order, so a pair's p depends on its place in PAIRS.
    pp = defaultdict(lambda: defaultdict(list))
    for r in rows:
        pp[r["task"]][r["setting"]].append(100 * len(r["both"]) / r["n_items"])
    rnd = random.Random(SEED)
    for p in pairs:
        dd = [statistics.mean(ss[p["a"]]) - statistics.mean(ss[p["b"]]) for ss in pp.values()
              if p["a"] in ss and p["b"] in ss]
        p["pp"], p["p"] = statistics.mean(dd), perm_p(dd, rnd)
    for p, h in zip(pairs, holm([p["p"] for p in pairs])):
        p["holm"] = h

    # Findings outside the checklist that the second-pass judge counted: useful plus minor.
    x_by = defaultdict(list)
    x_per = defaultdict(lambda: defaultdict(list))
    x_cls = defaultdict(lambda: defaultdict(list))
    x_cat = defaultdict(lambda: defaultdict(list))
    for c in answers:
        x = extra[c["answer"]]
        n = x["useful"] + x["minor"]
        x_by[c["setting"]].append(n)
        x_per[c["task"]][c["setting"]].append(n)
        x_cat[tasks[c["task"]]["category"]][c["setting"]].append(x["useful"])
        for k in ("useful", "minor", "false", "unverifiable"):
            x_cls[c["setting"]][k].append(x[k])
    rnd = random.Random(SEED)
    for p in pairs:
        dd = [statistics.mean(ss[p["a"]]) - statistics.mean(ss[p["b"]]) for ss in x_per.values()
              if p["a"] in ss and p["b"] in ss]
        p["x"] = {"d": dd, "mean": statistics.mean(dd), "ci": boot(dd), "p": perm_p(dd, rnd)}
    for p, h in zip(pairs, holm([p["x"]["p"] for p in pairs])):
        p["x"]["holm"] = h

    sets = defaultdict(lambda: defaultdict(list))
    cost = defaultdict(list)
    wall = defaultdict(lambda: defaultdict(list))
    for r in rows:
        sets[r["task"]][r["setting"]].append(r["both"])
        cost[r["setting"]].append(r["cost_usd"] or 0)
        wall[r["task"]][r["setting"]].append(r["wall_s"])
    rnd = random.Random(SEED)
    two = []
    for model, lo, hi, neighbour in TWO_RUNS:
        d, w, ts = [], [0, 0, 0], []
        for t, ss in sets.items():
            n = len(tasks[t]["items"])
            u = len(ss[lo][0] | ss[lo][1]) / n
            one = statistics.mean(len(x) for x in ss[hi]) / n
            d.append(100 * (u - one))
            ts.append(t)
            w[0 if u > one else 1 if u == one else 2] += 1
        two.append({"model": model, "low": lo, "high": hi, "neighbour": neighbour, "d": d, "tasks": ts,
                    "wins": w, "p": perm_p(d, rnd)})
    for x, h in zip(two, holm([x["p"] for x in two])):
        x["holm"] = h
        x["ci"] = boot(x["d"])
        x["par"] = statistics.mean(max(wall[t][x["low"]]) for t in wall) / 60
        x["one"] = statistics.mean(statistics.mean(wall[t][x["high"]]) for t in wall) / 60
        x["cost_two"] = 2 * statistics.mean(cost[x["low"]])
        x["cost_one"] = statistics.mean(cost[x["high"]])

    ens, found_ci = {}, {}
    for s in by:
        one, both2, means = [], [], []
        for t, ss in per.items():
            rs = ss.get(s, [])
            n = len(tasks[t]["items"])
            if len(rs) >= 2:
                one.append(statistics.mean(len(r["both"]) for r in rs) / n)
                both2.append(len(rs[0]["both"] | rs[1]["both"]) / n)
            if rs:
                means.append(statistics.mean(r["found"] for r in rs))
        ens[s] = (statistics.mean(one), statistics.mean(both2))
        found_ci[s] = boot(means)

    sol_rows, _ = rows_of(tasks, answers, marks, judges=["sol"])
    sol_by, _ = group(sol_rows)
    return {"rows": rows, "agree": agree, "by": by, "per": per, "pairs": pairs, "two": two, "ens": ens,
            "found_ci": found_ci, "x_by": x_by, "x_cls": x_cls, "x_cat": x_cat, "sol_by": sol_by}


def print_tables(v, tasks):
    rows, agree, by = v["rows"], v["agree"], v["by"]
    print(f"cells judged {len(rows)}, judge agreement {agree[0] / agree[1]:.1%} on {agree[1]} item marks\n")
    print("| setting | runs | found (both judges) | found (either) | core found | wrong claims per run | $ per run | min per run |")
    print("|---|---|---|---|---|---|---|---|")
    for s, rs in sorted(by.items()):
        cores = [r["core"] for r in rs if r["core"] is not None]
        print(f"| {s} | {len(rs)} | {statistics.mean(r['found'] for r in rs):.0%} | "
              f"{statistics.mean(r['found_either'] for r in rs):.0%} | "
              f"{statistics.mean(cores):.0%} | {statistics.mean(r['errors'] for r in rs):.2f} | "
              f"{statistics.mean(r['cost_usd'] or 0 for r in rs):.2f} | {statistics.mean(r['wall_s'] for r in rs) / 60:.1f} |")
    print("\nPaired by task, difference of found share (A minus B), mean and bootstrap 95% interval")
    print("| A vs B | tasks | mean diff | 95% interval | A better / equal / B better | cost ratio | time ratio |")
    print("|---|---|---|---|---|---|---|")
    for p in v["pairs"]:
        lo, hi = p["ci"]
        w = p["wins"]
        print(f"| {p['a']} vs {p['b']} | {len(p['d'])} | {statistics.mean(p['d']):+.1%} | {lo:+.1%} .. {hi:+.1%} | "
              f"{w[0]} / {w[1]} / {w[2]} | {p['cost_median']:.2f} | {p['time_median']:.2f} |")
    cats = defaultdict(lambda: defaultdict(list))
    for r in rows:
        cats[r["category"]][r["setting"]].append(r["found"])
    print("\nFound share by category")
    sets = sorted(by)
    print("| category | " + " | ".join(sets) + " |")
    print("|---|" + "---|" * len(sets))
    for c, ss in sorted(cats.items()):
        print(f"| {c} | " + " | ".join(f"{statistics.mean(ss[s]):.0%}" if ss.get(s) else "-" for s in sets) + " |")
    print("\nEnsemble, share of key items found by the union of N runs of one setting (both judges)")
    for s in sets:
        one, two = v["ens"][s]
        print(f"- {s}: one run {one:.0%}, two runs together {two:.0%}")

    print("\n# Found share per setting with a bootstrap 95% interval over the per-task means")
    for s in ORDER:
        lo, hi = v["found_ci"][s]
        print(f"  {s}: {statistics.mean(r['found'] for r in by[s]):.1%} ({lo:.1%} .. {hi:.1%})")

    print("\n# Two runs of a lower effort together against one run of the higher effort")
    for x in v["two"]:
        d, (b_lo, b_hi), w = x["d"], x["ci"], x["wins"]
        print(f"{x['low']} x2 vs {x['high']} x1: {statistics.mean(d):+.1f} pp ({b_lo:+.1f} .. {b_hi:+.1f}), better/equal/worse "
              f"{w[0]}/{w[1]}/{w[2]}, p {x['p']:.4f}, Holm {x['holm']:.4f}, $ {x['cost_two']:.2f} vs "
              f"{x['cost_one']:.2f}, min in parallel {x['par']:.1f} vs {x['one']:.1f}")

    print("\n# Pairs, permutation p and Holm")
    print("Key recall, percentage points")
    for p in v["pairs"]:
        print(f"  {p['a']} - {p['b']}: {p['pp']:+.2f} pp, p {p['p']:.4f}, Holm {p['holm']:.4f}")
    print("Counted findings outside the key per answer, Sonnet A")
    for p in v["pairs"]:
        x = p["x"]
        print(f"  {p['a']} - {p['b']}: {x['mean']:+.2f}, p {x['p']:.4f}, Holm {x['holm']:.4f}")

    print("\n# Findings outside the checklist, useful plus minor, per answer, and paired with a bootstrap interval")
    print("xmarks-a", {s: f"{statistics.mean(n):.2f}" for s, n in sorted(v["x_by"].items())})
    for p in v["pairs"]:
        lo, hi = p["x"]["ci"]
        print(f"  {p['a']} - {p['b']}: {p['x']['mean']:+.2f} ({lo:+.2f} .. {hi:+.2f})")
    print("By class, per answer: useful / minor / false / unverifiable")
    for s in ORDER:
        c = v["x_cls"][s]
        print(f"  {s}: " + " / ".join(f"{statistics.mean(c[k]):.2f}" for k in ("useful", "minor", "false", "unverifiable")))
    print("Useful per answer by category")
    for cat in CATEGORIES:
        print(f"  {cat}: " + ", ".join(f"{s} {statistics.mean(v['x_cat'][cat][s]):.2f}" for s in ORDER))

    print("\n# Cost and time, ratio of means over all answers (the paired table above prints medians of per-task ratios)")
    for p in v["pairs"]:
        print(f"  {p['a']} / {p['b']}: cost {p['cost_ratio']:.2f}, time {p['time_ratio']:.2f}")
    print("Output tokens per answer")
    for s in ORDER:
        print(f"  {s}: {statistics.mean(r['tokens']['completion'] for r in by[s]):.0f}")
    print(f"API-price cost of all answers: ${sum(r['cost_usd'] or 0 for r in v['rows']):.2f}")

    print("\n# Found share by one judge, gpt-6.1-sol alone")
    sol = v["sol_by"]
    for s in sorted(ORDER, key=lambda s: -statistics.mean(r["found"] for r in sol[s])):
        print(f"  {s}: {statistics.mean(r['found'] for r in sol[s]):.1%}")


def r2(x):
    return round(x, 2) + 0.0


def r3(x):
    return round(x, 3) + 0.0


def r6(x):
    return round(x, 6) + 0.0


def to_json(v, tasks):
    rows, by = v["rows"], v["by"]
    settings = []
    for s in ORDER:
        rs = by[s]
        settings.append({
            "id": s, "answers": len(rs),
            "found": r6(statistics.mean(r["found"] for r in rs)),
            "foundCi": [r6(x) for x in v["found_ci"][s]],
            "foundEither": r6(statistics.mean(r["found_either"] for r in rs)),
            "core": r6(statistics.mean(r["core"] for r in rs if r["core"] is not None)),
            "trapsPerAnswer": r6(statistics.mean(r["errors"] for r in rs)),
            "costPerAnswer": r2(statistics.mean(r["cost_usd"] or 0 for r in rs)),
            "minutesPerAnswer": r2(statistics.mean(r["wall_s"] for r in rs) / 60),
            "extraPerAnswer": r2(statistics.mean(v["x_by"][s])),
            "twoRunsFound": r6(v["ens"][s][1]),
        })
    categories = []
    for c in CATEGORIES:
        rs = [r for r in rows if r["category"] == c]
        categories.append({"id": c, "tasks": len({r["task"] for r in rs}),
                           "found": {s: r6(statistics.mean(r["found"] for r in rs if r["setting"] == s)) for s in ORDER}})
    pairs = []
    for p in v["pairs"]:
        x = p["x"]
        pairs.append({
            "a": p["a"], "b": p["b"], "tasks": len(p["d"]),
            "diff": r6(statistics.mean(p["d"])), "ci": [r6(y) for y in p["ci"]],
            "better": p["wins"][0], "equal": p["wins"][1], "worse": p["wins"][2],
            "p": r3(p["p"]), "holm": r3(p["holm"]),
            "costRatio": r3(p["cost_ratio"]), "timeRatio": r3(p["time_ratio"]),
            "perTask": [{"task": t, "diff": r6(d)} for t, d in zip(p["tasks"], p["d"])],
            "extra": {"diff": r2(x["mean"]), "ci": [r2(y) for y in x["ci"]], "holm": r3(x["holm"])},
        })
    two = []
    for x in v["two"]:
        w = x["wins"]
        two.append({
            "model": x["model"], "low": x["low"], "high": x["high"], "neighbour": x["neighbour"],
            "diff": r6(statistics.mean(x["d"]) / 100), "ci": [r6(y / 100) for y in x["ci"]],
            "better": w[0], "equal": w[1], "worse": w[2], "p": r3(x["p"]), "holm": r3(x["holm"]),
            "costTwo": r2(x["cost_two"]), "costOne": r2(x["cost_one"]),
            "minutesParallel": r2(x["par"]), "minutesOne": r2(x["one"]),
            "perTask": [{"task": t, "diff": r6(d / 100)} for t, d in zip(x["tasks"], x["d"])],
        })
    return {
        "overview": {"tasks": len(v["per"]), "answers": len(rows),
                     "judgeAgreement": r6(v["agree"][0] / v["agree"][1]), "judgeMarks": v["agree"][1],
                     "apiCostTotal": r2(sum(r["cost_usd"] or 0 for r in rows))},
        "settings": settings, "categories": categories, "pairs": pairs, "twoRuns": two,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    tasks, answers, marks, extra = load()
    v = compute(tasks, answers, marks, extra)
    if a.json:
        print(json.dumps(to_json(v, tasks), ensure_ascii=False, indent=1))
    else:
        print_tables(v, tasks)


if __name__ == "__main__":
    main()
