"""Run a query in an isolated child process with a hard timeout.

The in-process deadline in safety.py cannot interrupt a hang inside SQLite's C
code. Killing a child process always works. Starting a process costs roughly
100 to 300 ms, so this path is used for auditing and evaluation, not training.

On timeout the child is asked to stop with terminate() and, if it is still
alive, removed with kill(). The SQLite connection is opened inside the child
because connections can be neither pickled nor shared between processes.
"""

import multiprocessing as mp
from pathlib import Path

from verdict.verifier.types import ExecutionResult

# spawn is the only start method on Windows. Using it everywhere also avoids
# fork copying open SQLite handles into the child on Linux.
_CTX = mp.get_context("spawn")


def _worker(sql: str, db_path: str, timeout_s: float, out) -> None:
    from verdict.verifier.execute import execute_query

    try:
        out.put(execute_query(sql, db_path, timeout_s=timeout_s))
    except Exception as e:
        out.put(ExecutionResult(status="crashed", error=f"{type(e).__name__}: {e}"))


def execute_isolated(
    sql: str, db_path: str | Path, timeout_s: float = 5.0, grace_s: float = 2.0
) -> ExecutionResult:
    """Run ``sql`` in a child process that is killed if it overruns.

    Never raises and never leaves a child process running.
    """
    out = _CTX.Queue()
    proc = _CTX.Process(target=_worker, args=(sql, str(db_path), timeout_s, out))
    proc.start()
    try:
        # Wait on the queue rather than the process: the result can be ready
        # while the child is still shutting down.
        try:
            result = out.get(timeout=timeout_s + grace_s)
        except Exception:
            result = None

        if result is not None:
            proc.join(1.0)
            return result

        if proc.is_alive():
            proc.terminate()
            proc.join(1.0)
            if proc.is_alive():
                proc.kill()
                proc.join(1.0)
            return ExecutionResult(status="timeout", error="worker killed after hard timeout")
        return ExecutionResult(status="crashed", error=f"worker exited with code {proc.exitcode}")
    finally:
        if proc.is_alive():
            proc.kill()
            proc.join(1.0)
        proc.close()
