"""Run a query in an isolated child process with a hard timeout.

The in-process deadline in safety.py cannot interrupt a hang inside SQLite's C
code. Killing a child process always works. Starting a process costs roughly
100 to 300 ms, so this path is used for auditing and evaluation, not training.

On timeout the child is asked to stop with terminate() and, if it is still
alive, removed with kill(). The SQLite connection is opened inside the child
because connections can be neither pickled nor shared between processes.
"""

import multiprocessing as mp
import time
from pathlib import Path

from verdict.verifier.types import ExecutionResult

# spawn is the only start method on Windows. Using it everywhere also avoids
# fork copying open SQLite handles into the child on Linux.
_CTX = mp.get_context("spawn")

#: Tries to start the worker process before giving up with "crashed".
START_RETRIES = 4


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
    proc = None
    # Windows can refuse to create a process for a moment ("Access is
    # denied") when many start at once. That says nothing about the query,
    # so retry briefly; if it keeps failing, return "crashed" as promised.
    for attempt in range(START_RETRIES):
        proc = _CTX.Process(target=_worker, args=(sql, str(db_path), timeout_s, out))
        try:
            proc.start()
            break
        except OSError as e:
            proc = None
            if attempt == START_RETRIES - 1:
                return ExecutionResult(status="crashed", error=f"could not start worker: {e}")
            time.sleep(0.2 * (attempt + 1))
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
            # After kill the child always exits, so waiting without a limit is
            # safe. A short wait could end first on a busy machine.
            proc.join()
        try:
            proc.close()
        except ValueError:
            # Still shutting down; the OS reaps it. The result is already in
            # hand, and this function promises never to raise.
            pass
