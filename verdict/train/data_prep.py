"""Turn BIRD tasks into chat-format training examples.

Each example holds the prompt (system instruction, schema, question, optional
hint) and the metadata the reward function needs (gold SQL, db_id).
"""

import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from verdict.data.loaders import BirdTask
from verdict.data.schema import get_schema, get_schema_cached

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


def shorten_schema(with_rows: str, without_rows: str | Callable[[], str], limit: int) -> str:
    """Fit a schema into ``limit`` characters.

    Sample rows are dropped first. If the schema is still too long it is cut
    at a line break and marked. The prompt itself is never cut, because the
    question sits at its end.
    """
    schema = with_rows
    if len(schema) > limit:
        schema = without_rows() if callable(without_rows) else without_rows
    if len(schema) > limit:
        cut = schema.rfind("\n", 0, limit)
        schema = schema[: cut if cut > 0 else limit] + "\n-- (schema truncated)"
    return schema


class SchemaStore:
    """Schema text per database, shortened to ``max_chars``.

    Reads the database when ``<db_root>/<db_id>/<db_id>.sqlite`` exists.
    Otherwise uses ``schemas_file``: a JSON object written on Kaggle when
    BIRD train was prepared, ``{db_id: {"with_rows": ..., "no_rows": ...}}``,
    made with ``get_schema(num_samples=2)`` and ``num_samples=0``. This lets
    supervised fine-tuning use questions whose (very large) database was not
    kept. Both sources give the same text when ``sample_rows`` is 2.
    """

    def __init__(
        self,
        db_root: Path | str | None = None,
        schemas_file: Path | str | None = None,
        sample_rows: int = 2,
        max_chars: int = 6000,
    ):
        self.db_root = Path(db_root) if db_root else None
        self.sample_rows = sample_rows
        self.max_chars = max_chars
        self._saved: dict = {}
        if schemas_file:
            with open(schemas_file, encoding="utf-8") as f:
                self._saved = json.load(f)
        self._cache: dict[str, str] = {}

    def __call__(self, db_id: str) -> str:
        if db_id not in self._cache:
            self._cache[db_id] = self._build(db_id)
        return self._cache[db_id]

    def _build(self, db_id: str) -> str:
        db = self.db_root / db_id / f"{db_id}.sqlite" if self.db_root else None
        if db is not None and db.exists():
            return shorten_schema(
                get_schema(db, num_samples=self.sample_rows),
                lambda: get_schema(db, num_samples=0),
                self.max_chars,
            )
        if db_id in self._saved:
            saved = self._saved[db_id]
            first = saved["with_rows"] if self.sample_rows > 0 else saved["no_rows"]
            return shorten_schema(first, saved["no_rows"], self.max_chars)
        raise FileNotFoundError(f"no database and no saved schema for {db_id!r} (looked in {db})")


def render_prompt(tokenizer, task: BirdTask, schema: str, include_evidence: bool = True) -> str:
    """The exact prompt text the model sees: chat template plus generation marker."""
    messages = build_prompt(task, schema, include_evidence)
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return "\n\n".join(m["content"] for m in messages) + "\n\n```sql\n"


def sql_answer(gold_sql: str) -> str:
    """The answer format the system instruction asks for: one fenced SQL block."""
    return f"```sql\n{gold_sql.strip()}\n```"


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
