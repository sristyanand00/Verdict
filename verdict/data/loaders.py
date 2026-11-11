"""Load BIRD dev questions into typed task records.

    load_bird_dev() -> list[BirdTask]

Paths come from verdict.config, so the data can move (VERDICT_DATA_ROOT)
without code changes. Unlike the verifier, the loader raises on bad input:
a malformed or incomplete dataset should stop a run before it starts, not
surface as thousands of silently failing queries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from verdict import config

Difficulty = Literal["simple", "moderate", "challenging"]
DIFFICULTIES: tuple[str, ...] = ("simple", "moderate", "challenging")
_REQUIRED = ("question_id", "db_id", "question", "evidence", "SQL", "difficulty")


@dataclass(frozen=True)
class BirdTask:
    """One BIRD question with its gold SQL and database location."""

    question_id: int
    db_id: str
    question: str
    evidence: str  # BIRD's hint; empty for some questions
    gold_sql: str
    difficulty: Difficulty
    db_path: Path


def load_bird_dev(
    path: str | Path | None = None,
    data_root: str | Path | None = None,
    check_db: bool = True,
) -> list[BirdTask]:
    """Read BIRD dev questions.

    ``path`` defaults to ``config.dev_json()``. ``data_root`` is the folder
    holding ``dev_databases/`` and defaults to ``config.data_root()``; pass a
    different root to point the same questions at perturbed database copies.
    With ``check_db`` every referenced database file must exist.
    """
    path = Path(path) if path else config.dev_json()
    root = Path(data_root) if data_root else config.data_root()

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a JSON list of questions")

    tasks: list[BirdTask] = []
    seen: set[int] = set()
    missing_dbs: set[str] = set()

    for i, item in enumerate(raw):
        absent = [k for k in _REQUIRED if k not in item]
        if absent:
            raise ValueError(f"{path}: item {i} is missing {absent}")
        if item["difficulty"] not in DIFFICULTIES:
            raise ValueError(f"{path}: item {i} has unknown difficulty {item['difficulty']!r}")
        qid = int(item["question_id"])
        if qid in seen:
            raise ValueError(f"{path}: duplicate question_id {qid}")
        seen.add(qid)

        db = config.db_path(item["db_id"], root)
        if check_db and not db.exists():
            missing_dbs.add(item["db_id"])

        tasks.append(
            BirdTask(
                question_id=qid,
                db_id=item["db_id"],
                question=item["question"].strip(),
                evidence=(item["evidence"] or "").strip(),
                gold_sql=item["SQL"].strip(),
                difficulty=item["difficulty"],
                db_path=db,
            )
        )

    # Report every missing database at once rather than one per run.
    if missing_dbs:
        raise FileNotFoundError(
            f"databases not found under {root / 'dev_databases'}: {sorted(missing_dbs)}"
        )
    return tasks
