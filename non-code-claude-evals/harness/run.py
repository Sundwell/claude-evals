#!/usr/bin/env python3
"""Run every (task, setting, repeat) cell through promptfoo's Claude Agent SDK provider.

Each cell is its own promptfoo eval with one provider and one test, so the queue stays flat and a cell that
hit a usage limit is simply put back. Done cells are skipped on a rerun, so a stopped run is resumed by
starting it again.

  run.py --dry-run                 # list the cells that would run
  run.py --tasks cr-x,plan-y       # only these tasks
  run.py --settings sonnet-medium --repeat 1
  run.py -j 10                     # parallel cells
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from common import HERE, add_common_args, load_config, task_ids

PROMPTFOO = os.path.join(HERE, "node_modules", ".bin", "promptfoo")
LIMIT_WORDS = ("usage limit", "rate limit", "rate_limit", "limit reached", "5-hour limit", "weekly limit", "overloaded")

cfg = {}
lock = threading.Lock()
gate = threading.Event()
gate.set()
stop_all = threading.Event()
reprobe = threading.Event()


def log(msg):
    line = f"{datetime.now().strftime('%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with lock, open(os.path.join(cfg["runs_dir"], "run.log"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def probe():
    """Live 5h and 7d utilization from a one-word Haiku call; only a subscription login reports it."""
    try:
        out = subprocess.run(
            ["claude", "-p", "say ok", "--model", "haiku", "--output-format", "stream-json", "--verbose"],
            capture_output=True, text=True, timeout=120, cwd=cfg["runs_dir"])
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    for line in out.stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "rate_limit_event":
            return (d.get("rate_limit_info") or {}).get("unifiedWindows") or None
    return None


def watch_limits():
    lim = cfg["limits"]
    while not stop_all.is_set():
        w = probe()
        if w is None:
            log("probe: no rate_limit_event, keeping the current state")
        else:
            five, week = w.get("five_hour") or {}, w.get("seven_day") or {}
            f, k = five.get("utilization", 0), week.get("utilization", 0)
            log(f"probe: 5h {f:.0%}, 7d {k:.0%}")
            if k >= lim["week_stop_at"]:
                log("weekly limit nearly gone, stopping; switch account or wait for the weekly reset")
                stop_all.set()
                gate.set()
                return
            if f >= lim["pause_at"]:
                until = (five.get("resetsAt") or time.time() + 1800) + 120
                gate.clear()
                log(f"pausing new cells until {datetime.fromtimestamp(until).strftime('%H:%M')}")
                while time.time() < until and not stop_all.is_set():
                    time.sleep(30)
                gate.set()
                continue
        reprobe.wait(lim["probe_every"])
        reprobe.clear()


def cell_dir(task, setting, rep):
    return os.path.join(cfg["runs_dir"], task, f"{setting}__r{rep}")


def done(task, setting, rep):
    return os.path.exists(os.path.join(cell_dir(task, setting, rep), "cell.json"))


def write_config(path, task, setting):
    s, agent = cfg["settings"][setting], cfg["agent"]
    q = json.dumps
    task_dir = os.path.join(cfg["tasks_dir"], task)
    text = f"""description: {q(f'{task} {setting}')}
prompts:
  - {q('file://' + os.path.join(task_dir, 'prompt.md'))}
providers:
  - id: anthropic:claude-agent-sdk
    label: {q(setting)}
    config:
      apiKeyRequired: false
      model: {q(s['model'])}
      effort: {q(s['effort'])}
      working_dir: {q(os.path.join(task_dir, 'src'))}
      copy_working_dir: true
      persist_session: false
      append_allowed_tools: {q(agent['allowed_tools'])}
      disallowed_tools: {q(agent['disallowed_tools'])}
tests:
  - description: {q(task)}
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def sandbox(cmd, task, cell, node):
    # The agent has Bash. In the first run it found and killed live processes of the host, so promptfoo and
    # the agent run in bwrap: own pid namespace, home, /tmp, /run and /mnt hidden, only node, the harness's
    # node_modules, the task's prompt and src, the cell folder and the credentials file bound back.
    home = os.path.expanduser("~")
    node_dir = os.path.dirname(os.path.dirname(node))
    task_dir = os.path.join(cfg["tasks_dir"], task)
    hidden = (home, "/tmp", "/run", "/mnt", "/var/tmp")
    ro = [node_dir, os.path.join(task_dir, "prompt.md"), os.path.join(task_dir, "src")]
    # WSL and systemd-resolved keep resolv.conf behind a symlink into /mnt or /run, which the tmpfs would hide.
    resolv = os.path.realpath("/etc/resolv.conf")
    if resolv.startswith(hidden) and os.path.exists(resolv):
        ro.append(resolv)
    args = ["bwrap", "--ro-bind", "/", "/"]
    for h in hidden:
        args += ["--tmpfs", h]
    args += ["--proc", "/proc", "--dev", "/dev"]
    for p in ro:
        args += ["--ro-bind", p, p]
    # A symlink runs_dir/node_modules under a hidden folder is hidden too, so the packages are bound there themselves.
    mods = [os.path.join(HERE, "node_modules")]
    if cfg["runs_dir"].startswith(hidden):
        mods.append(os.path.join(cfg["runs_dir"], "node_modules"))
    for p in mods:
        args += ["--ro-bind", os.path.join(HERE, "node_modules"), p]
    args += ["--bind", cell, cell]
    creds = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude"), ".credentials.json")
    if os.path.exists(creds):
        args += ["--bind", creds, creds]
    args += ["--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup-try",
             "--die-with-parent", "--new-session",
             "--unsetenv", "XDG_RUNTIME_DIR", "--unsetenv", "DBUS_SESSION_BUS_ADDRESS",
             "--setenv", "HOME", home, "--setenv", "PATH", f"{node_dir}/bin:/usr/bin:/bin",
             "--chdir", cell]
    return args + cmd


def run_cell(task, setting, rep, node, attempt=1):
    hits = 0
    runs = cfg["runs_dir"]
    while True:
        gate.wait()
        if stop_all.is_set():
            return "stopped"
        d = cell_dir(task, setting, rep)
        os.makedirs(d, exist_ok=True)
        conf, out = os.path.join(d, "promptfooconfig.yaml"), os.path.join(d, "result.json")
        write_config(conf, task, setting)
        t0 = time.time()
        env = dict(os.environ, PROMPTFOO_DISABLE_TELEMETRY="1", PROMPTFOO_DISABLE_UPDATE="1")
        cmd = [node, os.path.realpath(PROMPTFOO), "eval", "-c", conf, "-o", out, "--no-cache", "--no-table",
               "--no-progress-bar", "-j", "1"]
        if cfg["agent"]["sandbox"] == "bwrap":
            cmd = sandbox(cmd, task, d, node)
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=d, env=env)
        with open(os.path.join(d, "promptfoo.log"), "w", encoding="utf-8") as fh:
            fh.write(p.stdout[-20000:] + "\n--- stderr\n" + p.stderr[-20000:])
        r = None
        try:
            with open(out, encoding="utf-8") as fh:
                res = json.load(fh)["results"]
            r = (res["results"] if isinstance(res, dict) else res)[0]
        except (OSError, ValueError, KeyError, IndexError):
            pass
        text = ((r or {}).get("response") or {}).get("output") or ""
        err = ((r or {}).get("response") or {}).get("error") or (r or {}).get("error") or ""
        blob = (str(err) + p.stderr[-4000:]).lower()
        if (not text or err) and any(w in blob for w in LIMIT_WORDS):
            hits += 1
            log(f"{task} {setting} r{rep}: hit a limit ({hits}), waiting for the limit watcher")
            reprobe.set()
            time.sleep(min(1800, 120 * hits))
            continue
        if not text:
            if attempt < 2:
                log(f"{task} {setting} r{rep}: empty answer, one retry ({str(err)[:120]})")
                attempt += 1
                continue
            log(f"{task} {setting} r{rep}: failed twice, left out ({str(err)[:200]}); see {d}/promptfoo.log")
            return "failed"
        # The answer file name carries no setting, so the judges cannot tell whose answer they mark.
        h = hashlib.sha256(f"{task}|{setting}|{rep}|{t0}".encode()).hexdigest()[:10]
        ans_dir = os.path.join(runs, "answers")
        os.makedirs(ans_dir, exist_ok=True)
        with open(os.path.join(ans_dir, f"{task}__{h}.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        tu = r.get("tokenUsage") or {}
        cell = {"task": task, "setting": setting, "rep": rep, "answer": f"{task}__{h}.md",
                "cost_usd": r.get("cost"), "latency_s": round((r.get("latencyMs") or 0) / 1000),
                "wall_s": round(time.time() - t0), "tokens": tu,
                "session": (r.get("response") or {}).get("sessionId"),
                "finished": datetime.now().isoformat(timespec="seconds")}
        with open(os.path.join(d, "cell.json"), "w", encoding="utf-8") as fh:
            json.dump(cell, fh, ensure_ascii=False, indent=1)
        with lock, open(os.path.join(runs, "secret-map.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(cell, ensure_ascii=False) + "\n")
        log(f"{task} {setting} r{rep}: done, ${cell['cost_usd'] or 0:.2f}, {cell['wall_s'] // 60} min")
        return "done"


def main():
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.add_argument("--tasks", default="", help="comma-separated task ids, default every task with a prompt.md")
    ap.add_argument("--settings", default="", help="comma-separated setting names, default all of the config")
    ap.add_argument("--repeat", type=int, help="runs per (task, setting), default repeats of the config")
    ap.add_argument("-j", type=int, help="parallel cells, default jobs of the config")
    ap.add_argument("--no-limit-watch", action="store_true", help="skip the usage probe even if the config has it on")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg.update(load_config(a.config, a.tasks_dir, a.runs_dir))
    tasks = task_ids(cfg["tasks_dir"], a.tasks)
    settings = a.settings.split(",") if a.settings else list(cfg["settings"])
    bad = [s for s in settings if s not in cfg["settings"]]
    if bad:
        sys.exit(f"unknown settings {bad}, the config has {list(cfg['settings'])}")
    repeat = a.repeat or cfg["repeats"]
    jobs = a.j or cfg["jobs"]
    # Interleave settings and tasks so a pause or a stop leaves every setting about equally covered.
    cells = [(t, s, r) for r in range(1, repeat + 1) for t in tasks for s in settings if not done(t, s, r)]
    print(f"{len(tasks)} tasks in {cfg['tasks_dir']}, {len(settings)} settings, {repeat} repeats, "
          f"{len(cells)} cells to run")
    if a.dry_run:
        for c in cells:
            print(*c)
        return
    node = shutil.which("node")
    if not node or not os.path.exists(PROMPTFOO):
        sys.exit(f"needs node on PATH and promptfoo in {HERE}/node_modules: run `npm ci` in {HERE}")
    # Version managers put a shim on PATH that dispatches by its own name; the sandbox needs the real binary.
    node = subprocess.run([node, "-p", "process.execPath"], capture_output=True, text=True, check=True).stdout.strip()
    if cfg["agent"]["sandbox"] == "bwrap" and not shutil.which("bwrap"):
        sys.exit('sandbox = "bwrap" needs bubblewrap (apt install bubblewrap); or set sandbox = "none" in config.toml')
    runs = cfg["runs_dir"]
    os.makedirs(runs, exist_ok=True)
    # promptfoo resolves the Agent SDK from the folder of each cell's config, which lies under runs_dir.
    link = os.path.join(runs, "node_modules")
    if not os.path.lexists(link):
        os.symlink(os.path.join(HERE, "node_modules"), link)
    if os.path.exists(os.path.join(runs, "run.done")):
        os.remove(os.path.join(runs, "run.done"))
    log(f"start, {len(cells)} cells, -j {jobs}")
    if cfg["limits"]["watch"] and not a.no_limit_watch:
        threading.Thread(target=watch_limits, daemon=True).start()
    with ThreadPoolExecutor(jobs) as ex:
        outcomes = list(ex.map(lambda c: run_cell(*c, node), cells))
    stop_all.set()
    log("end, " + ", ".join(f"{k} {outcomes.count(k)}" for k in sorted(set(outcomes))))
    # judge.py --follow stops once this exists and nothing is left to mark.
    with open(os.path.join(runs, "run.done"), "w", encoding="utf-8") as fh:
        fh.write(datetime.now().isoformat(timespec="seconds"))


if __name__ == "__main__":
    main()
