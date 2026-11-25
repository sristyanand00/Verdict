"""execute_isolated must return the result even if the child is slow to exit.

On a busy machine (GitHub CI) the child can still be shutting down after the
result arrives. close() then raises ValueError, which used to escape and turn
a good answer into an error.
"""

import queue

from verdict.verifier import pool
from verdict.verifier.types import ExecutionResult


class SlowToExit:
    """A process that has sent its result but keeps 'running' a little longer."""

    def __init__(self, target, args):
        self.out = args[-1]
        self.alive = True
        self.exitcode = None

    def start(self):
        self.out.put(ExecutionResult(status="ok", rows=((1,),), columns=("x",)))

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        if timeout is None:   # only an unlimited wait sees it exit
            self.alive = False

    def kill(self):
        pass

    def terminate(self):
        pass

    def close(self):
        if self.alive:
            raise ValueError("Cannot close a process while it is still running.")


class Ctx:
    def Queue(self):
        return queue.Queue()

    def Process(self, target, args):
        return SlowToExit(target, args)


def test_result_survives_a_slow_child_exit(monkeypatch):
    monkeypatch.setattr(pool, "_CTX", Ctx())
    r = pool.execute_isolated("SELECT 1", "unused.sqlite")
    assert r.status == "ok" and r.rows == ((1,),)


def test_close_error_is_never_raised(monkeypatch):
    class NeverDies(SlowToExit):
        def join(self, timeout=None):
            pass

    class Ctx2(Ctx):
        def Process(self, target, args):
            return NeverDies(target, args)

    monkeypatch.setattr(pool, "_CTX", Ctx2())
    assert pool.execute_isolated("SELECT 1", "unused.sqlite").status == "ok"
