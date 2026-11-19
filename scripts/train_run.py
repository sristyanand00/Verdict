#!/usr/bin/env python
"""Run a training or evaluation command, show its output live and save it to a log.

Usage (Windows PowerShell or Linux):
    python scripts/train_run.py E:\\verdict_runs\\logs\\sft_v2.log python scripts/train_sft.py --train-dir ...

Everything the command prints appears on screen as it happens and is also
written to the log file (appended, with a start and end line). Progress bars
that redraw one line (model downloads) work too. The child Python runs
unbuffered, so lines are not held back.

The exit code is the command's exit code. Closing the window stops the run,
so keep it open until the end line appears.
"""

import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    log_path = Path(sys.argv[1])
    command = sys.argv[2:]
    log_path.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    start = time.time()
    with open(log_path, "ab") as log:
        header = f"\n=== start {time.strftime('%Y-%m-%d %H:%M:%S')}: {' '.join(command)}\n".encode()
        log.write(header)
        sys.stdout.buffer.write(header)
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        try:
            while True:
                chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(1)
                if not chunk:
                    break
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
                log.write(chunk)
                log.flush()
        except KeyboardInterrupt:
            proc.terminate()
        code = proc.wait()
        minutes = (time.time() - start) / 60
        footer = f"\n=== end {time.strftime('%Y-%m-%d %H:%M:%S')}: exit code {code}, {minutes:.1f} minutes\n".encode()
        log.write(footer)
        sys.stdout.buffer.write(footer)
        sys.stdout.buffer.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
