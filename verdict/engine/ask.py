"""Step 5 of the trust engine: one function that runs the whole pipeline.

    answer = ask("uploads/ab12cd.sqlite", "Total sales in Pune?")
    answer.verdict -> "trusted"
    answer.rows    -> ((150000.0,),)
    answer.sql     -> "SELECT SUM(amount) FROM sales WHERE city = 'Pune'"

The pipeline:

    describe_schema  ->  generate_attempts (n replies)  ->  run_and_group  ->  decide
       schema.py            generate.py + llm.py            group.py          trust.py

The writer is a parameter so the same pipeline can run Gemini today and Qwen
later, and so tests can pass a FixedWriter with known replies.

On top of agreement the product runs extra checks and gives one of three
levels (Trusted / Review / Reject):

    knowledge.py   saved meanings and similar approved examples go into the
                   prompt; near-identical approved answers are compared
    ambiguity.py   two big groups with different answers = two meanings
    second model   optional: one answer from another model must match
    checks.py      the check list for the evidence view
    trust.py       final_verdict combines all of it

``Answer.level`` keeps the agreement-only level (green / yellow / red /
unanswerable) for evaluation and scripts. ``Answer.verdict`` is the product
level.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from verdict.engine.ambiguity import find_split, label_meanings
from verdict.engine.checks import Check, build_checks
from verdict.engine.generate import CANNOT_ANSWER, Attempt, generate_attempts
from verdict.engine.group import AnswerGroup, Grouping, run_and_group
from verdict.engine.knowledge import PromptKnowledge, find_conflict, pick_knowledge, same_answer
from verdict.engine.llm import SQLWriter
from verdict.engine.schema import describe_schema
from verdict.engine.trust import Level, Reason, Verdict, decide, final_verdict, load_thresholds

DEFAULT_ATTEMPTS = 8

#: Attempts asked of the second model. One is enough to catch a disagreement
#: and keeps a cloud second model cheap.
SECOND_MODEL_ATTEMPTS = 1


@dataclass(frozen=True)
class MeaningOption:
    """One reading of a two-meaning question."""

    label: str
    sql: str
    columns: tuple[str, ...]
    rows: tuple[tuple, ...]
    size: int


@dataclass(frozen=True)
class Answer:
    question: str
    level: Level
    score: float
    reason: str
    #: the answer rows and column names; empty when nothing is shown
    rows: tuple[tuple, ...]
    columns: tuple[str, ...]
    #: one SQL from the winning group; "" when there is no answer
    sql: str
    #: everything underneath, kept for the evidence view and for evaluation
    schema: str
    attempts: list[Attempt]
    grouping: Grouping
    #: the product level and its reasons
    verdict: Verdict = "reject"
    reasons: list[Reason] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    #: the two readings when the question has two meanings, else None
    options: list[MeaningOption] | None = None
    #: what seems to be missing, when the data cannot answer
    missing: str | None = None
    tables: list[str] = field(default_factory=list)
    knowledge_used: list[str] = field(default_factory=list)

    @property
    def shown(self) -> bool:
        """Whether the agreement level alone would show an answer."""
        return self.level in ("green", "yellow")


def table_names(schema: str) -> list[str]:
    """Table names from describe_schema's ``table(col TYPE, ...)`` lines."""
    return [line.split("(", 1)[0].strip('"') for line in schema.splitlines() if "(" in line]


def missing_from_replies(attempts: list[Attempt]) -> str | None:
    """What the model said is missing, if it wrote anything after CANNOT_ANSWER.

    The prompt asks for the bare word, so this is often None. When a model
    does explain ("CANNOT_ANSWER: there is no advertising spend column"), the
    most common explanation is shown.
    """
    notes = []
    for a in attempts:
        if a.kind != "cannot_answer" or CANNOT_ANSWER not in a.raw:
            continue
        after = re.sub(r"^[\s:.\-]+", "", a.raw.split(CANNOT_ANSWER, 1)[1]).strip()
        if after:
            notes.append(after[:200])
    return Counter(notes).most_common(1)[0][0] if notes else None


def _second_opinion(
    second_writer: SQLWriter, schema: str, question: str, knowledge_block: str,
    db_path: str | Path, top: AnswerGroup | None,
) -> tuple[bool | None, tuple[str, str]]:
    """Run the second model once and compare with the top answer.

    Returns (agrees, or None if it gave no usable answer; (check status, detail)).
    """
    if top is None:
        return None, ("off", "There is no answer to compare.")
    try:
        attempts = generate_attempts(
            second_writer, schema, question, SECOND_MODEL_ATTEMPTS, knowledge=knowledge_block
        )
    except Exception as e:  # the second model is optional; its outage must not stop the answer
        return None, ("off", f"Second model unavailable ({type(e).__name__}).")
    second = run_and_group(attempts, db_path).top
    if second is None:
        return None, ("off", "Second model gave no usable answer.")
    agrees = same_answer(
        second.result, list(top.result.columns), [list(r) for r in top.result.rows], top.sqls[0]
    )
    if agrees:
        return True, ("pass", "The second model gives the same answer.")
    return False, ("fail", "The second model gives a different answer.")


def ask(
    db_path: str | Path,
    question: str,
    writer: SQLWriter | None = None,
    n: int = DEFAULT_ATTEMPTS,
    thresholds: dict[str, float] | None = None,
    knowledge: dict[str, list[dict]] | None = None,
    second_writer: SQLWriter | None = None,
) -> Answer:
    """Answer ``question`` from the database at ``db_path``, with a trust level.

    ``knowledge``: {"meanings": [...], "examples": [...], "known_numbers": [...]}
    as saved by the store. ``second_writer``: optional second model.
    """
    if not question or not question.strip():
        raise ValueError("question is empty")
    if writer is None:
        from verdict.engine.llm import GeminiWriter

        writer = GeminiWriter()
    t = thresholds or load_thresholds()
    kn = knowledge or {}

    schema = describe_schema(db_path)
    picked: PromptKnowledge = pick_knowledge(question, kn.get("meanings", []), kn.get("examples", []))
    block = picked.prompt_block()
    attempts = generate_attempts(writer, schema, question, n, knowledge=block)
    grouping = run_and_group(attempts, db_path)
    decision = decide(grouping, t)
    top = grouping.top

    split = find_split(grouping)
    conflict, n_compared = find_conflict(
        question, top.result if top and not split else None,
        kn.get("examples", []), kn.get("known_numbers", []),
    )
    conflict_text = conflict.text if conflict else None

    second_agrees: bool | None = None
    second_check: tuple[str, str] = ("off", "Off.")
    if second_writer is not None and not split:
        second_agrees, second_check = _second_opinion(second_writer, schema, question, block, db_path, top)

    final = final_verdict(grouping, t, split, conflict_text, second_agrees)
    checks = build_checks(grouping, t, split, conflict_text, n_compared, second_check)

    options = None
    if split:
        labels = label_meanings(split[0].sqls[0], split[1].sqls[0])
        options = [
            MeaningOption(label, g.sqls[0], g.result.columns, g.result.rows, g.size)
            for label, g in zip(labels, split)
        ]

    # Show the top answer unless the verdict is reject. A review answer is a
    # draft for the analyst to check. With two meanings the options carry the
    # answers instead, so neither is shown as "the" answer.
    show = final.level != "reject" and top is not None and not split
    not_in_data = any(r.code == "not_in_data" for r in final.reasons)
    return Answer(
        question=question,
        level=decision.level,
        score=decision.score,
        reason=decision.reason,
        rows=top.result.rows if show else (),
        columns=top.result.columns if show else (),
        sql=top.sqls[0] if show else "",
        schema=schema,
        attempts=attempts,
        grouping=grouping,
        verdict=final.level,
        reasons=final.reasons,
        checks=checks,
        options=options,
        missing=missing_from_replies(attempts) if not_in_data else None,
        tables=table_names(schema),
        knowledge_used=picked.used,
    )
