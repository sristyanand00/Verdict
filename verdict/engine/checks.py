"""The check list shown in the evidence view.

    build_checks(...) -> [Check("safe", "Safe", "pass", "Read-only, nothing blocked"), ...]

Rule from the plan: only checks that actually ran are shown as pass or fail.
A check that did not run (the second model when it is switched off) is shown
as "off", never as pass.

Statuses:
    pass   the check ran and found nothing wrong
    fail   the check ran and found a problem
    off    the check did not run, with the detail saying why
    info   a fact worth showing that is not evidence about this answer

The receipt must not show more evidence than exists. So:
    safe           always "info": it describes the sandbox, which is the same
                   for every question, not the answer
    no_split       "info" when agreement already passed (a split is then
                   impossible, so the row would only repeat agreement);
                   "fail" on a split
    known_numbers  "off" when no approved answer was compared
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from verdict.engine.group import AnswerGroup, Grouping
from verdict.engine.trust import needed_for_green

Status = Literal["pass", "fail", "off", "info"]


@dataclass(frozen=True)
class Check:
    key: str
    name: str
    status: Status
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_checks(
    grouping: Grouping,
    thresholds: dict[str, float],
    split: list[AnswerGroup] | None,
    conflict: str | None,
    n_compared: int,
    second_model: tuple[Status, str],
) -> list[Check]:
    n = grouping.n_attempts
    top = grouping.top
    results = [r for r in grouping.results if r is not None]
    n_sql = len(results)
    blocked = sum(1 for r in results if r.status == "blocked")
    ran = sum(1 for r in results if r.ok)

    checks: list[Check] = []

    # Safe: every query went through the read-only verifier. Blocked queries
    # were refused and never touched the data. This is true of every answer,
    # so it is shown as information, never as a tick.
    if blocked:
        detail = f"Read-only sandbox. {blocked} attempt{'s' if blocked > 1 else ''} blocked as unsafe and not run."
    else:
        detail = "Read-only sandbox, nothing blocked."
    checks.append(Check("safe", "Safe", "info", detail))

    # Ran
    if n_sql == 0:
        checks.append(Check("ran", "Ran", "off", "No attempt wrote SQL to run."))
    else:
        status: Status = "pass" if ran > n // 2 else "fail"
        checks.append(Check("ran", "Ran", status, f"{ran} of {n_sql} queries ran without error or timeout."))

    # Agreement
    need = needed_for_green(n, thresholds) if n else 0
    agreement_passed = top is not None and top.size >= need
    if top is None:
        checks.append(Check("agreement", "Agreement", "fail", "No two attempts gave a usable answer."))
    else:
        status = "pass" if agreement_passed else "fail"
        checks.append(Check(
            "agreement", "Agreement", status, f"{top.size} of {n} give the same answer (trusted needs {need})."
        ))

    # Not empty
    if top is None:
        checks.append(Check("not_empty", "Not empty", "off", "There is no answer to check."))
    elif top.is_empty_answer:
        checks.append(Check("not_empty", "Not empty", "fail", "The answer is empty or only NULL."))
    else:
        checks.append(Check("not_empty", "Not empty", "pass", "The answer has values."))

    # No split
    if split:
        a, b = split
        checks.append(Check(
            "no_split", "No split", "fail",
            f"Attempts split into two answers ({a.size} and {b.size} of {n}).",
        ))
    elif top is None:
        checks.append(Check("no_split", "No split", "off", "There is no answer to check."))
    elif agreement_passed:
        # With enough agreement for trusted a split cannot happen, so a tick
        # here would count the agreement evidence twice.
        checks.append(Check("no_split", "No split", "info", "Follows from agreement; not separate evidence."))
    else:
        checks.append(Check("no_split", "No split", "pass", "Attempts did not split into two meanings."))

    # Matches approved answers
    if conflict:
        checks.append(Check("known_numbers", "Matches approved answers", "fail", conflict))
    elif top is None:
        checks.append(Check("known_numbers", "Matches approved answers", "off", "There is no answer to check."))
    elif n_compared:
        checks.append(Check(
            "known_numbers", "Matches approved answers", "pass",
            f"Same as {n_compared} approved answer{'s' if n_compared > 1 else ''} to this question.",
        ))
    else:
        checks.append(Check(
            "known_numbers", "Matches approved answers", "off",
            "No approved answer to a near-identical question yet, so nothing was compared.",
        ))

    status, detail = second_model
    checks.append(Check("second_model", "Second model", status, detail))
    return checks
