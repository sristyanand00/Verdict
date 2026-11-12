"""Step 5 of the trust engine: one function that runs the whole pipeline.

    answer = ask("uploads/ab12cd.sqlite", "Total sales in Pune?")
    answer.level   -> "green"
    answer.rows    -> ((150000.0,),)
    answer.sql     -> "SELECT SUM(amount) FROM sales WHERE city = 'Pune'"

The pipeline:

    describe_schema  ->  generate_attempts (n replies)  ->  run_and_group  ->  decide
       schema.py            generate.py + llm.py            group.py          trust.py

The writer is a parameter so the same pipeline can run Gemini today and Qwen
later, and so tests can pass a FixedWriter with known replies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from verdict.engine.generate import Attempt, generate_attempts
from verdict.engine.group import Grouping, run_and_group
from verdict.engine.llm import SQLWriter
from verdict.engine.schema import describe_schema
from verdict.engine.trust import Level, decide

DEFAULT_ATTEMPTS = 8


@dataclass(frozen=True)
class Answer:
    question: str
    level: Level
    score: float
    reason: str
    #: the answer rows and column names; empty for red and unanswerable
    rows: tuple[tuple, ...]
    columns: tuple[str, ...]
    #: one SQL from the winning group; "" when there is no answer
    sql: str
    #: everything underneath, kept for the receipt page and for evaluation
    schema: str
    attempts: list[Attempt]
    grouping: Grouping

    @property
    def shown(self) -> bool:
        """Whether the product shows an answer at all."""
        return self.level in ("green", "yellow")


def ask(
    db_path: str | Path,
    question: str,
    writer: SQLWriter | None = None,
    n: int = DEFAULT_ATTEMPTS,
    thresholds: dict[str, float] | None = None,
) -> Answer:
    """Answer ``question`` from the database at ``db_path``, with a trust level."""
    if not question or not question.strip():
        raise ValueError("question is empty")
    if writer is None:
        from verdict.engine.llm import GeminiWriter

        writer = GeminiWriter()

    schema = describe_schema(db_path)
    attempts = generate_attempts(writer, schema, question, n)
    grouping = run_and_group(attempts, db_path)
    decision = decide(grouping, thresholds)

    top = decision.answer
    return Answer(
        question=question,
        level=decision.level,
        score=decision.score,
        reason=decision.reason,
        rows=top.result.rows if top else (),
        columns=top.result.columns if top else (),
        sql=top.sqls[0] if top else "",
        schema=schema,
        attempts=attempts,
        grouping=grouping,
    )
