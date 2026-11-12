"""Step 4 of the trust engine: decide how much to trust the answer.

    decide(grouping) -> TrustDecision(level="green", score=0.875, reason="7 of 8 attempts agree")

The signal is agreement: the share of the n attempts that landed in the
largest answer group. Levels, checked in this order:

    unanswerable  more than half the attempts said CANNOT_ANSWER
    green         agreement >= thresholds["green"]   (show the answer)
    yellow        agreement >= thresholds["yellow"]  (show it, with a warning)
    red           otherwise                          (do not show an answer)

Two extra rules:
  * An empty answer (no rows, or only NULL) is never green. Eight attempts
    that all filter on a misspelled value agree perfectly and are all wrong.
  * The thresholds live in thresholds.json, not in this code. They are
    placeholders until Phase 2 measures, on BIRD dev, how often each level of
    agreement is actually correct. Agreement is not correctness: attempts
    from one model can share the same mistake.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from verdict.engine.group import AnswerGroup, Grouping

THRESHOLDS_FILE = Path(__file__).with_name("thresholds.json")

Level = Literal["green", "yellow", "red", "unanswerable"]

#: A threshold above 1 can never be reached: calibration writes it when no
#: agreement level met the accuracy target, which turns that level off.
NEVER = 1.01


@dataclass(frozen=True)
class TrustDecision:
    level: Level
    #: share of attempts in the largest group, 0.0 to 1.0
    score: float
    #: the answer to show; None for red and unanswerable
    answer: AnswerGroup | None
    #: one sentence a user can read
    reason: str


def load_thresholds(path: str | Path = THRESHOLDS_FILE) -> dict[str, float]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    t = {k: float(data[k]) for k in ("green", "yellow", "cannot_answer")}
    if not 0 < t["yellow"] <= t["green"] <= NEVER:
        raise ValueError(f"thresholds must satisfy 0 < yellow <= green <= {NEVER}, got {t}")
    return t


def level_for(
    n: int, n_cannot_answer: int, top_size: int, top_is_empty: bool, thresholds: dict[str, float]
) -> Level:
    """The trust rules on plain counts.

    decide() uses this for live answers, and eval/calibration.py uses it on
    saved evaluation records, so both always apply exactly the same rules.
    """
    t = thresholds
    if n == 0:
        return "red"
    if n_cannot_answer / n > t["cannot_answer"]:
        return "unanswerable"
    score = top_size / n
    if top_size and score >= t["green"] and not top_is_empty:
        return "green"
    if top_size and score >= t["yellow"]:
        return "yellow"
    return "red"


def decide(grouping: Grouping, thresholds: dict[str, float] | None = None) -> TrustDecision:
    t = thresholds or load_thresholds()
    n = grouping.n_attempts
    top = grouping.top
    level = level_for(
        n, grouping.n_cannot_answer, top.size if top else 0, bool(top and top.is_empty_answer), t
    )

    if n == 0:
        return TrustDecision("red", 0.0, None, "No attempts were made.")
    if level == "unanswerable":
        return TrustDecision(
            "unanswerable", 0.0, None,
            f"{grouping.n_cannot_answer} of {n} attempts said this data cannot answer the question.",
        )
    if top is None:
        return TrustDecision("red", 0.0, None, f"None of the {n} attempts produced a working query.")

    score = top.size / n
    agree = f"{top.size} of {n} attempts agree"
    if level == "green":
        return TrustDecision("green", score, top, f"{agree}.")
    if level == "yellow":
        why = "the answer is empty" if top.is_empty_answer else "not enough agreement to be sure"
        return TrustDecision("yellow", score, top, f"{agree}, but {why}. Check before using.")
    if len(grouping.groups) == 1:
        why = f"Only {top.size} of {n} attempts produced a working query."
    else:
        why = f"Only {agree}; the attempts gave {len(grouping.groups)} different answers."
    return TrustDecision("red", score, None, why)
