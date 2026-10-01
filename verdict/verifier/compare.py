"""Result-set normalisation and equality.

Rules:
  * Row order matters only when the outermost gold query has ORDER BY.
  * Column order does not matter, but a reordering must apply to every row.
  * Numbers are compared after rounding, so 94 equals 94.0.
  * NULL is distinct from the empty string and from 0.
  * Duplicate rows are counted (multiset comparison).

This function decides the training reward, so a false "correct" trains the
model toward wrong answers.
"""

from collections import Counter
from itertools import permutations

import sqlglot

from verdict.verifier.types import ExecutionResult, VerificationResult

#: Decimal places kept when comparing numbers. Rounding, rather than a pairwise
#: tolerance, lets values be hashed into a Counter. Trade-off: two values on
#: either side of a rounding boundary compare as different.
FLOAT_PLACES = 4

#: Widest result for which every column order is tried (6! = 720). Wider
#: results are compared in the order given. BIRD answers rarely exceed 4 columns.
MAX_PERMUTED_COLS = 6


def gold_has_order_by(sql: str) -> bool:
    """True only if the outermost query has ORDER BY.

    The SQL is parsed rather than searched as text: 'order by' inside a string
    literal, or an ORDER BY inside a subquery or CTE, does not determine the
    order of the final result.
    """
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return "order by" in (sql or "").lower()
    if tree is None:
        return "order by" in (sql or "").lower()
    return tree.args.get("order") is not None


def _norm_value(v):
    # Values are tagged so that NULL can never equal "null", 0 or False.
    if v is None:
        return ("null",)
    # bool is checked before int because bool is a subclass of int.
    if isinstance(v, bool):
        return ("num", round(float(v), FLOAT_PLACES))
    if isinstance(v, (int, float)):
        if v != v:  # NaN
            return ("nan",)
        return ("num", round(float(v), FLOAT_PLACES))
    if isinstance(v, (bytes, bytearray)):
        return ("bytes", bytes(v))
    # Surrounding whitespace is treated as data-entry noise.
    return ("str", str(v).strip())


def _norm_row(row) -> tuple:
    return tuple(_norm_value(v) for v in row)


def _same_rows(cand: list[tuple], gold: list[tuple], ordered: bool) -> bool:
    if ordered:
        return cand == gold
    # Counter rather than set, so that [94, 94, 71] differs from [94, 71].
    return Counter(cand) == Counter(gold)


def _column_orders(n: int):
    """Candidate column orders, starting with the order as given."""
    if n > MAX_PERMUTED_COLS:
        return [tuple(range(n))]
    return permutations(range(n))


def _match_any_column_order(cand: list[tuple], gold: list[tuple], ordered: bool) -> bool:
    """True if some single column reordering, applied to every row, makes the results equal.

    Sorting the values inside each row independently is not sufficient: it
    treats [(1, 2), (2, 1)] as equal to [(1, 2), (1, 2)].
    """
    width = len(gold[0]) if gold else 0
    if any(len(r) != width for r in cand):
        return False

    # Candidate column i can only map to gold column j if both columns hold the
    # same multiset of values. This prunes nearly every permutation before any
    # rows are compared; without it a wrong 6 x 10,000 result took about 22 s.
    cand_cols = [Counter(r[i] for r in cand) for i in range(width)]
    gold_cols = [Counter(r[j] for r in gold) for j in range(width)]
    fits = [[cand_cols[i] == gold_cols[j] for j in range(width)] for i in range(width)]

    return any(
        _same_rows([tuple(r[i] for i in order) for r in cand], gold, ordered)
        for order in _column_orders(width)
        if all(fits[i][j] for j, i in enumerate(order))
    )


def compare_results(
    candidate: ExecutionResult, gold: ExecutionResult | None, gold_sql: str
) -> VerificationResult:
    """Judge a candidate result against the gold result."""
    if not candidate.ok:
        return VerificationResult(
            "invalid", candidate, gold, reason=f"candidate {candidate.status}: {candidate.error}"
        )
    if gold is None or not gold.ok:
        # A failing gold query is a benchmark defect, not a model error.
        g = gold.status if gold else "missing"
        return VerificationResult("invalid", candidate, gold, reason=f"GOLD FAILED ({g}): audit case")
    if len(candidate.rows) != len(gold.rows):
        return VerificationResult(
            "wrong", candidate, gold, reason=f"row count {len(candidate.rows)} vs {len(gold.rows)}"
        )

    cand = [_norm_row(r) for r in candidate.rows]
    goldr = [_norm_row(r) for r in gold.rows]

    ordered = gold_has_order_by(gold_sql)
    why = "ordered compare (gold has ORDER BY)" if ordered else "unordered compare (no ORDER BY)"
    same = _match_any_column_order(cand, goldr, ordered)

    return VerificationResult("correct" if same else "wrong", candidate, gold, reason=why)
