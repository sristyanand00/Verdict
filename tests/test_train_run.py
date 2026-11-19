"""The log runner must start Python children with the same interpreter (the venv)."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "train_run.py"


def test_python_child_uses_the_same_interpreter(tmp_path):
    log = tmp_path / "logs" / "check.log"
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(log), "python", "-c", "import sys; print(sys.executable)"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert str(Path(sys.executable)) in out
    assert str(Path(sys.executable)) in log.read_text(encoding="utf-8")


def test_exit_code_and_log_lines(tmp_path):
    log = tmp_path / "run.log"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(log), "python", "-c", "print('hello'); raise SystemExit(3)"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 3
    text = log.read_text(encoding="utf-8")
    assert "=== start" in text and "hello" in text and "exit code 3" in text
