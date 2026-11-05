"""Config shared by run.py, judge.py and score.py."""
import os
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config(path=None, tasks_dir=None, runs_dir=None):
    if path is None:
        path = os.path.join(HERE, "config.toml")
        if not os.path.exists(path):
            path = os.path.join(HERE, "config.example.toml")
    with open(path, "rb") as fh:
        cfg = tomllib.load(fh)
    base = os.path.dirname(os.path.abspath(path))
    cfg["tasks_dir"] = os.path.abspath(tasks_dir or os.path.join(base, cfg["tasks_dir"]))
    cfg["runs_dir"] = os.path.abspath(runs_dir or os.path.join(base, cfg["runs_dir"]))
    cfg["config_path"] = path
    return cfg


def add_common_args(ap):
    ap.add_argument("--config", help="config file, default harness/config.toml or config.example.toml")
    ap.add_argument("--tasks-dir", help="overrides tasks_dir of the config")
    ap.add_argument("--runs-dir", help="overrides runs_dir of the config")


def task_ids(tasks_dir, only=""):
    names = only.split(",") if only else sorted(os.listdir(tasks_dir))
    return [t for t in names if not t.startswith("_") and os.path.isfile(os.path.join(tasks_dir, t, "prompt.md"))]
