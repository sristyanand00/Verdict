"""Turn BIRD tasks into chat-format training examples.

Each example holds the prompt (system instruction, schema, question, optional
hint) and the metadata the reward function needs (gold SQL, db_id).
"""

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from verdict.data.loaders import BirdTask
from verdict.data.schema import get_schema_cached

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are an expert SQL assistant. Given a database schema and a question, write a single SQLite SELECT query that answers the question.

Rules:
- Use ONLY the tables and columns shown in the schema
- Return ONLY the SQL query inside a ```sql code block
- Do not include explanations or comments
- Make sure the query is syntactically correct"""


@dataclass
class TrainingExample:
    """One prompt plus the metadata the reward function needs."""

    prompt: list[dict]  # chat messages: [{"role": "system", ...}, {"role": "user", ...}]
    gold_sql: str
    db_id: str
    question_id: int
    difficulty: str


def build_prompt(task: BirdTask, schema: str, include_evidence: bool = True) -> list[dict]:
    """Chat messages for one task: system instruction, then schema + question (+ hint)."""
    user = f"### Database Schema\n{schema}\n\n### Question\n{task.question}"
    if include_evidence and task.evidence:
        user += f"\n\n### Hint\n{task.evidence}"
    user += "\n\nWrite a SQL query to answer this question."
    return [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": user},
    ]


def prepare_training_data(
    tasks: list[BirdTask],
    db_root: Path,
    cache_dir: Path | None = None,
    include_evidence: bool = True,
) -> list[TrainingExample]:
    """Build one example per task. ``db_root`` is the folder holding ``<db_id>/<db_id>.sqlite``.

    Tasks whose database is missing or unreadable are skipped with a warning.
    """
    examples = []
    for task in tasks:
        db_path = Path(db_root) / task.db_id / f"{task.db_id}.sqlite"
        try:
            schema = get_schema_cached(db_path, cache_dir=cache_dir)
        except (FileNotFoundError, sqlite3.Error) as e:
            logger.warning("skipping task %s: %s", task.question_id, e)
            continue
        examples.append(
            TrainingExample(
                prompt=build_prompt(task, schema, include_evidence),
                gold_sql=task.gold_sql,
                db_id=task.db_id,
                question_id=task.question_id,
                difficulty=task.difficulty,
            )
        )
    return examples


def save_examples(examples: list[TrainingExample], output_path: Path) -> None:
    """Write examples as a JSON list, ready for ``datasets.Dataset.from_list``."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([asdict(ex) for ex in examples], f, indent=2, ensure_ascii=False)


def load_examples(input_path: Path) -> list[dict]:
    with open(input_path, encoding="utf-8") as f:
        return json.load(f)
