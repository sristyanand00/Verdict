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
    if not 0 < t["yellow"] <= t["green"] <= 1:
        raise ValueError(f"thresholds must satisfy 0 < yellow <= green <= 1, got {t}")
    return t


def decide(grouping: Grouping, thresholds: dict[str, float] | None = None) -> TrustDecision:
    t = thresholds or load_thresholds()
    n = grouping.n_attempts
    if n == 0:
        return TrustDecision("red", 0.0, None, "No attempts were made.")

    if grouping.n_cannot_answer / n > t["cannot_answer"]:
        return TrustDecision(
            "unanswerable", 0.0, None,
            f"{grouping.n_cannot_answer} of {n} attempts said this data cannot answer the question.",
        )

    top = grouping.top
    if top is None:
        return TrustDecision("red", 0.0, None, f"None of the {n} attempts produced a working query.")

    score = top.size / n
    agree = f"{top.size} of {n} attempts agree"

    if score >= t["green"] and not top.is_empty_answer:
        return TrustDecision("green", score, top, f"{agree}.")
    if score >= t["yellow"]:
        why = "the answer is empty" if top.is_empty_answer else "not enough agreement to be sure"
        return TrustDecision("yellow", score, top, f"{agree}, but {why}. Check before using.")
    if len(grouping.groups) == 1:
        why = f"Only {top.size} of {n} attempts produced a working query."
    else:
        why = f"Only {agree}; the attempts gave {len(grouping.groups)} different answers."
    return TrustDecision("red", score, None, why)
