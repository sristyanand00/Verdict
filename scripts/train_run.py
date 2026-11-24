#!/usr/bin/env python
"""Run a training or evaluation command, show its output live and save it to a log.

Usage (Windows PowerShell or Linux):
    python scripts/train_run.py E:\\verdict_runs\\logs\\sft_v2.log python scripts/train_sft.py --train-dir ...

Everything the command prints appears on screen as it happens and is also
written to the log file (appended, with a start and end line). Progress bars
that redraw one line (model downloads) work too. The child Python runs
unbuffered, so lines are not held back.

If the command starts with ``python``, it is run with the same Python as
this script (the active venv). On Windows a bare ``python`` started from a
venv is otherwise found next to the base interpreter, which lacks the
project's packages.

Ctrl+C: one press only prints a warning and the run keeps going (in a
terminal, Ctrl+C without selected text is easy to press by accident while
copying). Press it twice within 5 seconds to stop the run.

The exit code is the command's exit code. Closing the window stops the run,
so keep it open until the end line appears.
"""

import os
import subprocess
import sys
import time
from pathlib import Path


PYTHON_NAMES = {"python", "python3", "python.exe", "python3.exe"}
CONFIRM_SECONDS = 5.0


def resolve_command(command: list[str]) -> list[str]:
    """Run a leading ``python`` with this script's own interpreter."""
    if command and command[0].lower() in PYTHON_NAMES:
        return [sys.executable, *command[1:]]
    return command


class StopGuard:
    """A single Ctrl+C only warns; a second one within ``window`` seconds means stop."""

    def __init__(self, window: float = CONFIRM_SECONDS):
        self.window = window
        self.last: float | None = None

    def press(self, now: float) -> bool:
        if self.last is not None and now - self.last <= self.window:
            return True
        self.last = now
        return False


def child_options() -> dict:
    """Start the child in its own process group so Ctrl+C reaches only this script."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    log_path = Path(sys.argv[1])
    command = resolve_command(sys.argv[2:])
    log_path.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    start = time.time()
    with open(log_path, "ab") as log:

        def write(data: bytes) -> None:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            log.write(data)
            log.flush()

        write(f"\n=== start {time.strftime('%Y-%m-%d %H:%M:%S')}: {' '.join(command)}\n".encode())
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                **child_options())
        guard = StopGuard()
        stopped = False
        while True:
            try:
                chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(1)
            except KeyboardInterrupt:
                if stopped:
                    continue
                if guard.press(time.monotonic()):
                    write(b"\n=== Ctrl+C pressed twice: stopping the run\n")
                    proc.terminate()
                    stopped = True
                else:
                    write(f"\n=== Ctrl+C pressed. The run keeps going. Press Ctrl+C again within "
                          f"{CONFIRM_SECONDS:.0f} seconds to stop it.\n".encode())
                continue
            if not chunk:
                break
            write(chunk)
        code = proc.wait()
        minutes = (time.time() - start) / 60
        note = " (stopped with Ctrl+C)" if stopped else ""
        write(f"\n=== end {time.strftime('%Y-%m-%d %H:%M:%S')}: exit code {code}, {minutes:.1f} minutes{note}\n"
              .encode())
    return code


if __name__ == "__main__":
    sys.exit(main())
