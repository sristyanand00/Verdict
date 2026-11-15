"""Execution accuracy of a model on a list of BIRD tasks.

    result = evaluate_tasks(model, tokenizer, prompts, tasks, reward_fn)
    result.accuracy, result.ran_rate, result.outcomes

One greedy answer (temperature 0) per question, so the score does not depend
on luck. Each answer is run on the question's database and its result is
compared with the gold result. The model is not changed.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from verdict.data.loaders import BirdTask
from verdict.train.reward import SQLRewardFunction, extract_sql
from verdict.train.rollout import GenerationConfig, generate_ids

OUTCOME = {"correct": "correct", "wrong": "ran, wrong", "failed": "failed"}


@dataclass
class EvalResult:
    texts: list[str]
    scores: list[float]
    outcomes: list[str]
    seconds: float
    by_difficulty: dict[str, dict[str, int]] = field(default_factory=dict)
    #: per question: why it failed (or why a right-looking answer was marked
    #: wrong); "" when there is nothing to report
    reasons: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def failure_counts(self) -> Counter:
        """How many failed answers had each reason, most common first."""
        return Counter(r for r, o in zip(self.reasons, self.outcomes) if o == OUTCOME["failed"] and r)

    def failure_summary(self, top: int = 4) -> str:
        counts = self.failure_counts()
        return ", ".join(f"{reason} {n}" for reason, n in counts.most_common(top))

    @property
    def accuracy(self) -> float:
        return self.outcomes.count(OUTCOME["correct"]) / max(len(self.outcomes), 1)

    @property
    def ran_rate(self) -> float:
        return sum(o != OUTCOME["failed"] for o in self.outcomes) / max(len(self.outcomes), 1)

    def rows(self, tasks: list[BirdTask]) -> list[dict]:
        """One record per question, for saving to a file."""
        return [
            {
                "question_id": t.question_id,
                "db_id": t.db_id,
                "difficulty": t.difficulty,
                "outcome": o,
                "reason": reason,
                "error": error[:300],
                "sql": extract_sql(text),
            }
            for t, text, o, reason, error in zip(
                tasks, self.texts, self.outcomes,
                self.reasons or [""] * len(tasks), self.errors or [""] * len(tasks),
            )
        ]


def evaluate_tasks(
    model,
    tokenizer,
    prompts: list[str],
    tasks: list[BirdTask],
    reward_fn: SQLRewardFunction,
    max_tokens: int = 256,
    amp: bool = True,
    chunk: int = 50,
    log=None,
) -> EvalResult:
    """Greedy answers for ``prompts`` scored against ``tasks``' gold SQL.

    ``log`` (a print-like function) gets a progress line every ``chunk``
    questions; long evaluations on Kaggle would otherwise look stuck.
    """
    t0 = time.time()
    config = GenerationConfig(temperature=0, max_tokens=max_tokens)
    texts: list[str] = []
    for i in range(0, len(prompts), chunk):
        rollouts = generate_ids(model, tokenizer, prompts[i : i + chunk], n_completions=1, amp=amp, config=config)
        texts.extend(r.texts[0] for r in rollouts)
        if log and len(prompts) > chunk:
            log(f"  answered {len(texts)}/{len(prompts)} ({time.time() - t0:.0f}s)")

    gold_sql = [t.gold_sql for t in tasks]
    db_id = [t.db_id for t in tasks]
    if hasattr(reward_fn, "details"):
        details = reward_fn.details(texts, gold_sql, db_id)
        scores = [d.reward for d in details]
        outcomes = [OUTCOME[d.outcome] for d in details]
        reasons = [d.reason for d in details]
        errors = [d.error for d in details]
    else:
        scores = reward_fn(prompts=prompts, completions=texts, gold_sql=gold_sql, db_id=db_id)
        names = {v: k for k, v in reward_fn.rewards.items()}
        outcomes = [OUTCOME[names[s]] for s in scores]
        reasons, errors = [""] * len(tasks), [""] * len(tasks)

    by_difficulty: dict[str, Counter] = {}
    for t, o in zip(tasks, outcomes):
        by_difficulty.setdefault(t.difficulty, Counter())[o] += 1
    return EvalResult(
        texts=texts,
        scores=list(scores),
        outcomes=outcomes,
        seconds=time.time() - t0,
        by_difficulty={d: dict(c) for d, c in by_difficulty.items()},
        reasons=reasons,
        errors=errors,
    )
