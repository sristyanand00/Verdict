"""Spot questions that have two meanings, and label each meaning.

    find_split(grouping) -> [group_a, group_b] or None
    label_meanings(sql_a, sql_b) -> ("uses freight_value", "without freight_value")

"What was our revenue in 2017?" can mean product price only, or price plus
freight. When the attempts split into two big groups with different answers,
that is usually the question being read two ways, not the model being random.
Verdict then shows both answers and lets the analyst pick, instead of
choosing one silently.

The rule (plan section 7): the two largest groups each hold at least 3 of 8
attempts. With a different number of attempts the same share is used.

Labels come from comparing the two SQL queries, not from asking a model, so
they work offline and cannot invent anything: they only name columns,
conditions and functions that differ between the two queries.
"""

from __future__ import annotations

import math

from verdict.engine.group import AnswerGroup, Grouping

#: Share of attempts each of the two groups must hold to count as a split.
SPLIT_MIN_SHARE = 3 / 8

MAX_LABEL_CHARS = 80


def split_min_size(n: int) -> int:
    """Smallest group size that counts towards a split, for n attempts."""
    return max(2, math.ceil(SPLIT_MIN_SHARE * n - 1e-9))


def find_split(grouping: Grouping) -> list[AnswerGroup] | None:
    """Return the two big groups if the attempts split into two meanings."""
    groups = [g for g in grouping.groups if not g.is_empty_answer]
    if len(groups) < 2 or grouping.n_attempts == 0:
        return None
    need = split_min_size(grouping.n_attempts)
    a, b = groups[0], groups[1]
    if a.size >= need and b.size >= need:
        return [a, b]
    return None


def _features(sql: str) -> dict[str, set[str]] | None:
    """The parts of a query worth naming in a label. None if it cannot be read."""
    try:
        import sqlglot
        from sqlglot import exp

        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return None
    if tree is None:
        return None

    columns = {c.name for c in tree.find_all(exp.Column) if c.name}
    conditions: set[str] = set()
    for where in tree.find_all(exp.Where):
        cond = where.this
        parts = list(cond.flatten()) if isinstance(cond, exp.And) else [cond]
        for p in parts:
            conditions.add(p.sql(dialect="sqlite"))
    functions = {f.key.upper() for f in tree.find_all(exp.AggFunc)}
    if any(d for d in tree.find_all(exp.Distinct)):
        functions.add("DISTINCT")
    return {"columns": columns, "conditions": conditions, "functions": functions}


def _extra(own: dict[str, set[str]], other: dict[str, set[str]]) -> tuple[list, list, list]:
    """(columns, conditions, functions) that ``own`` has and ``other`` does not."""
    conds = sorted(own["conditions"] - other["conditions"])
    # A condition already names its columns; do not name them twice.
    cond_text = " ".join(conds).lower()
    cols = sorted(c for c in own["columns"] - other["columns"] if c.lower() not in cond_text)
    funcs = sorted(own["functions"] - other["functions"])
    return cols, conds, funcs


def _describe(own: dict[str, set[str]], other: dict[str, set[str]]) -> list[str]:
    """Plain phrases for what ``own`` has and ``other`` does not."""
    cols, conds, funcs = _extra(own, other)
    parts = []
    if cols:
        parts.append("uses " + ", ".join(cols))
    if conds:
        parts.append("only where " + " and ".join(conds))
    if funcs:
        parts.append("with " + ", ".join(funcs))
    return parts


def _describe_missing(own: dict[str, set[str]], other: dict[str, set[str]]) -> list[str]:
    """Plain phrases for the query that lacks what ``own`` has."""
    cols, conds, funcs = _extra(own, other)
    parts = []
    if cols:
        parts.append("without " + ", ".join(cols))
    if conds:
        parts.append("does not filter on " + " and ".join(conds))
    if funcs:
        parts.append("without " + ", ".join(funcs))
    return parts


def _short(text: str) -> str:
    text = text[0].upper() + text[1:] if text else text
    return text if len(text) <= MAX_LABEL_CHARS else text[: MAX_LABEL_CHARS - 3].rstrip() + "..."


def label_meanings(sql_a: str, sql_b: str) -> tuple[str, str]:
    """Short labels saying how the two queries differ."""
    fa, fb = _features(sql_a), _features(sql_b)
    if fa is None or fb is None:
        return "Meaning A", "Meaning B"

    a_parts, b_parts = _describe(fa, fb), _describe(fb, fa)
    if a_parts and b_parts:
        return _short("; ".join(a_parts)), _short("; ".join(b_parts))
    if a_parts:
        return _short("; ".join(a_parts)), _short("; ".join(_describe_missing(fa, fb)))
    if b_parts:
        return _short("; ".join(_describe_missing(fb, fa))), _short("; ".join(b_parts))
    return "Meaning A", "Meaning B"
