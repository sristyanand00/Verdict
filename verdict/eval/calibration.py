"""How far can agreement be trusted? Measure it, then pick thresholds.

    agreement_table(records)             accuracy for each "k of n agree"
    choose_thresholds(records, ...)      thresholds.json values from data
    summarize(records, unanswerable, t)  the headline numbers

Input is the records written by eval/harness.py. The trust rules come from
engine/trust.py (level_for), so the numbers here describe exactly what the
product would have shown.

Thresholds are fitted on one half of the questions (the "calibration" split)
and the headline is reported on the other half (the "test" split). Fitting
and reporting on the same questions would make the result look better than
it will be on new questions.

Terms used in reports:
  single     one attempt, always shown: what a plain "ask the AI" app does
  vote       the largest group's answer, always shown
  coverage   share of questions where Verdict shows an answer
  accuracy   share of shown answers that are right
"""

from __future__ import annotations

import random

from verdict.engine.trust import NEVER, level_for
from verdict.eval.metrics import rate


def split(records: list[dict], seed: int = 0) -> tuple[list[dict], list[dict]]:
    """Deterministic 50/50 split into (calibration, test)."""
    keys = sorted(r["key"] for r in records)
    random.Random(seed).shuffle(keys)
    calib = set(keys[: len(keys) // 2])
    return [r for r in records if r["key"] in calib], [r for r in records if r["key"] not in calib]


def usable(records: list[dict]) -> list[dict]:
    """Answerable records whose gold query ran (a failed gold cannot score anything)."""
    return [r for r in records if r["answerable"] and r["gold_status"] == "ok"]


def top_size(r: dict) -> int:
    return r["group_sizes"][0] if r["group_sizes"] else 0


def vote_correct(r: dict) -> bool:
    return bool(r["group_correct"] and r["group_correct"][0])


def single_correct(r: dict) -> bool:
    return r["attempt_correct"][0] is True


def level(r: dict, t: dict[str, float]) -> str:
    return level_for(r["n"], r["n_cannot"], top_size(r), r["top_empty"], t)


# --------------------------------------------------------------------------


def agreement_table(records: list[dict]) -> list[dict]:
    """For each k: how many questions had k of n attempts in the largest
    group, and how often that group's answer was right."""
    recs = usable(records)
    n = max((r["n"] for r in recs), default=8)
    rows = []
    for k in range(n, -1, -1):
        at_k = [r for r in recs if top_size(r) == k]
        if not at_k:
            continue
        right = sum(vote_correct(r) for r in at_k)
        empty = sum(r["top_empty"] for r in at_k)
        rows.append({"agree": k, "of": n, "empty": empty, **rate(right, len(at_k))})
    return rows


def choose_thresholds(
    records: list[dict],
    green_target: float = 0.85,
    yellow_target: float = 0.60,
    min_support: int = 10,
) -> dict:
    """Pick the lowest agreement levels that still meet the accuracy targets.

    green: smallest k such that answers with >= k agreeing (and not empty)
           are right at least ``green_target`` of the time.
    yellow: same with ``yellow_target``, empty answers included.
    cannot_answer: kept from the current file; reported, not fitted, because
           answerable and unanswerable questions come from different runs.

    Lower k means more questions get an answer, so the smallest k that meets
    the target gives the most coverage at that accuracy. ``min_support``
    stops a threshold being set from a handful of questions.
    """
    recs = usable(records)
    n = max((r["n"] for r in recs), default=8)

    def acc_at(k: int, allow_empty: bool) -> tuple[float, int]:
        s = [r for r in recs if top_size(r) >= k and (allow_empty or not r["top_empty"])]
        return (sum(vote_correct(r) for r in s) / len(s) if s else 0.0), len(s)

    def lowest(target: float, allow_empty: bool) -> tuple[int | None, float, int]:
        for k in range(1, n + 1):
            acc, support = acc_at(k, allow_empty)
            if support >= min_support and acc >= target:
                return k, acc, support
        return None, 0.0, 0

    gk, gacc, gsup = lowest(green_target, allow_empty=False)
    yk, yacc, ysup = lowest(yellow_target, allow_empty=True)
    green = gk / n if gk else NEVER
    yellow = min(yk / n if yk else NEVER, green)
    return {
        "green": green,
        "yellow": yellow,
        "fit": {
            "n": n, "questions": len(recs),
            "green_target": green_target, "green_k": gk, "green_fit_accuracy": gacc, "green_support": gsup,
            "yellow_target": yellow_target, "yellow_k": yk, "yellow_fit_accuracy": yacc, "yellow_support": ysup,
            "green_target_met": gk is not None,
        },
    }


def summarize(records: list[dict], unanswerable: list[dict], t: dict[str, float]) -> dict:
    """Headline numbers for answerable and unanswerable questions under ``t``."""
    recs = usable(records)
    N = len(recs)
    by_level: dict[str, list[dict]] = {"green": [], "yellow": [], "red": [], "unanswerable": []}
    for r in recs:
        by_level[level(r, t)].append(r)

    green, yellow = by_level["green"], by_level["yellow"]
    shown = green + yellow
    single_right = sum(single_correct(r) for r in recs)

    out = {
        "thresholds": {k: t[k] for k in ("green", "yellow", "cannot_answer")},
        "answerable": {
            "questions": N,
            "single": rate(single_right, N),
            "vote": rate(sum(vote_correct(r) for r in recs), N),
            "green": {"coverage": rate(len(green), N), "accuracy": rate(sum(map(vote_correct, green)), len(green))},
            "shown": {"coverage": rate(len(shown), N), "accuracy": rate(sum(map(vote_correct, shown)), len(shown))},
            "levels": {lv: len(v) for lv, v in by_level.items()},
            # Wrong answers a user would take as reliable.
            "confident_wrong": {
                "single_app": N - single_right,
                "verdict_green": sum(not vote_correct(r) for r in green),
            },
            # Right answers Verdict held back (the cost of caution).
            "withheld_but_right": sum(vote_correct(r) for r in by_level["red"] + by_level["unanswerable"]),
            "by_difficulty": {},
        },
    }
    for d in ("simple", "moderate", "challenging"):
        sub = [r for r in recs if r["difficulty"] == d]
        if sub:
            g = [r for r in sub if level(r, t) == "green"]
            out["answerable"]["by_difficulty"][d] = {
                "questions": len(sub),
                "single": rate(sum(map(single_correct, sub)), len(sub)),
                "green_coverage": rate(len(g), len(sub)),
                "green_accuracy": rate(sum(map(vote_correct, g)), len(g)),
            }

    U = len(unanswerable)
    if U:
        lv = [level(r, t) for r in unanswerable]
        out["unanswerable"] = {
            "questions": U,
            "refused": rate(lv.count("unanswerable"), U),
            "green": rate(lv.count("green"), U),
            "yellow": rate(lv.count("yellow"), U),
            "red": rate(lv.count("red"), U),
            # A plain app always shows an answer unless the model refuses.
            "single_app_answered": rate(sum(r["sqls"][0] not in ("cannot_answer", "empty") for r in unanswerable), U),
        }
    return out


def cannot_answer_sweep(records: list[dict], unanswerable: list[dict], t: dict[str, float]) -> list[dict]:
    """How the refusal threshold trades caught unanswerables against
    wrongly refused answerable questions."""
    recs = usable(records)
    rows = []
    for c in (0.25, 0.375, 0.5, 0.625, 0.75):
        tt = {**t, "cannot_answer": c}
        caught = sum(level(r, tt) == "unanswerable" for r in unanswerable)
        false_refusal = sum(level(r, tt) == "unanswerable" for r in recs)
        rows.append({"cannot_answer": c,
                     "unanswerable_caught": rate(caught, len(unanswerable)),
                     "answerable_refused": rate(false_refusal, len(recs))})
    return rows
