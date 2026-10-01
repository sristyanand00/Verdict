"""SQL execution reward for GRPO training.

    SQLRewardFunction(db_root)(prompts, completions, gold_sql=[...], db_id=[...]) -> list[float]

Takes a batch and returns one scalar per completion, matching the reward
function signature used by TRL and verl.

Reward scale:
  1.0  the query ran and its result matches the gold result
  0.1  the query ran but the result is wrong
  0.0  the query did not run (error, blocked, timeout)

The 0.1 tier keeps rewards from being identical when every completion in a
group is wrong. Without it, GRPO's group-relative advantage is zero and no
learning signal reaches the model early in training. The scale follows
Arctic-Text2SQL-R1 (arXiv:2505.20315).
"""

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from verdict.verifier.compare import compare_results
from verdict.verifier.execute import execute_query

_SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_sql(text: str) -> str:
    """Return the SQL from a model completion.

    Uses the last fenced code block, since models often draft a query and then
    restate the final answer at the end. Without a fence, the whole completion
    is treated as SQL.
    """
    blocks = _SQL_BLOCK.findall(text or "")
    if blocks:
        return blocks[-1].strip()
    return (text or "").strip()


class SQLRewardFunction:
    """Execution-based reward for text-to-SQL.

    Defined as a module-level class so it can be pickled and sent to worker
    processes; closures and nested functions cannot. Use functools.partial to
    pre-set arguments.
    """

    def __init__(self, db_root: str | Path, timeout_s: float = 5.0, workers: int = 8):
        self.db_root = Path(db_root)
        self.timeout_s = timeout_s
        self.workers = workers

    def db_path(self, db_id: str) -> Path:
        # BIRD layout: <root>/<db_id>/<db_id>.sqlite
        return self.db_root / db_id / f"{db_id}.sqlite"

    def _score_one(self, completion: str, gold_sql: str, db_id: str) -> float:
        db = self.db_path(db_id)
        cand = execute_query(extract_sql(completion), db, timeout_s=self.timeout_s)
        if not cand.ok:
            return 0.0
        # Gold SQL is trusted, so the keyword pre-filter is skipped for it.
        gold = execute_query(gold_sql, db, timeout_s=self.timeout_s, use_first_pass_filter=False)
        v = compare_results(cand, gold, gold_sql)
        return 1.0 if v.verdict == "correct" else 0.1

    def __call__(self, prompts, completions, **kwargs) -> list[float]:
        gold_sqls = kwargs["gold_sql"]
        db_ids = kwargs["db_id"]
        # Threads are sufficient here: sqlite3 releases the GIL while a query
        # executes, and threads are far cheaper to start than processes.
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(self._score_one, completions, gold_sqls, db_ids))
