r"""Path configuration — the one place that knows where data lives.

Nothing else in the package should hardcode a data path. The reason is
deployment: the same code runs in three places with the data mounted
differently each time.

    local dev   datasets/  ->  junction  ->  C:erdict-data\datasets
    training    /mnt/bird                    (GPU host scratch disk)
    container   /data                        (volume mount, per the
                                              Deployment Architecture:
                                              "SQLite benchmark corpora and
                                              the experiment store mounted
                                              as files")

Set VERDICT_DATA_ROOT to move the data without touching code. Unset, it
falls back to `datasets/` next to the repo root, which is what the Week 1
plan builds and what tests/test_loaders.py assumes.

The benchmark corpora are NEVER deployed as part of the product. The demo
serves a precomputed results.json with no GPU and no network (see I.27).
These paths exist for training and evaluation, not for the shipped app.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Repo root — this file is at <root>/verdict/config.py
REPO_ROOT = Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """Where the benchmark corpora live.

    Honours ``VERDICT_DATA_ROOT``; defaults to ``<repo>/datasets``.
    """
    env = os.environ.get("VERDICT_DATA_ROOT")
    return Path(env).expanduser().resolve() if env else REPO_ROOT / "datasets"


def results_root() -> Path:
    """Where run artifacts (results.json) are written and read."""
    env = os.environ.get("VERDICT_RESULTS_ROOT")
    return Path(env).expanduser().resolve() if env else REPO_ROOT / "results"


def dev_json() -> Path:
    """BIRD dev questions — 1534 tasks."""
    return data_root() / "dev.json"


def db_path(db_id: str, root: Path | None = None) -> Path:
    """Resolve a benchmark database by its ``db_id``.

    ``root`` is overridable so perturbed copies (anti-reward-hacking) can be
    verified against the same code path as the originals.
    """
    return (root or data_root()) / "dev_databases" / db_id / f"{db_id}.sqlite"


def readonly_uri(path: Path, immutable: bool = True) -> str:
    """Driver-level read-only handle — the real write-prevention control.

    A keyword blacklist is not the control (writes hide in CTEs and
    subqueries); this is. ``immutable=1`` is safe for the static benchmark
    corpora but must be False for anything being written concurrently.
    """
    uri = f"file:{path.as_posix()}?mode=ro"
    if immutable:
        uri += "&immutable=1"
    return uri


def check() -> None:
    """Fail loudly and early if the data is not where we think it is."""
    root = data_root()
    problems = []
    if not root.exists():
        problems.append(f"data root missing: {root}")
    if not dev_json().exists():
        problems.append(f"dev.json missing: {dev_json()}")
    dbs = root / "dev_databases"
    if not dbs.exists():
        problems.append(f"dev_databases missing: {dbs}")
    if problems:
        raise FileNotFoundError(
            "BIRD dev set not found.\n  "
            + "\n  ".join(problems)
            + "\n\nRun: powershell -ExecutionPolicy Bypass -File scripts\fetch_bird.ps1"
        )


if __name__ == "__main__":
    print(f"REPO_ROOT    {REPO_ROOT}")
    print(f"data_root    {data_root()}")
    print(f"results_root {results_root()}")
    print(f"dev_json     {dev_json()}")
    print(f"example db   {db_path('california_schools')}")
    check()
    print("\nOK - data is where it should be.")
