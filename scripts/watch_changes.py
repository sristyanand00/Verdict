"""Watch the project and append every file change to CHANGES.log.

Logs files that are created, edited (with a line-by-line diff), or deleted.
Uses only the standard library: it checks the project every second.

Run from the project root:
    python scripts/watch_changes.py
Stop with Ctrl+C.
"""

import difflib
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "CHANGES.log"
POLL_SECONDS = 1.0
MAX_FILE_BYTES = 1_000_000  # skip diffing very large files

# Folders and files we never watch (tools, caches, data, the log itself).
SKIP_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", "datasets", "models", "scratch",
}
SKIP_FILES = {LOG_FILE.name}
SKIP_SUFFIXES = {".pyc", ".log", ".tmp", ".swp"}


def watched_files():
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if not path.is_file() or path.name in SKIP_FILES or path.suffix in SKIP_SUFFIXES:
            continue
        yield rel


def read_text(path):
    """Return the file's lines, or None if it is binary or too big."""
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8").splitlines(keepends=True)
    except (UnicodeDecodeError, OSError):
        return None


def snapshot():
    """Map each file to (modified time, size, contents)."""
    snap = {}
    for rel in watched_files():
        path = ROOT / rel
        try:
            stat = path.stat()
        except OSError:
            continue
        snap[rel] = (stat.st_mtime, stat.st_size, read_text(path))
    return snap


def log(entry):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n=== {stamp}  {entry}")
    print(f"{stamp}  {entry.splitlines()[0]}")


def diff(old, new, rel):
    lines = difflib.unified_diff(old, new, f"a/{rel.as_posix()}", f"b/{rel.as_posix()}")
    return "".join(line if line.endswith("\n") else line + "\n" for line in lines)


def main():
    print(f"Watching {ROOT}\nLogging to {LOG_FILE}\nPress Ctrl+C to stop.")
    before = snapshot()
    while True:
        time.sleep(POLL_SECONDS)
        after = snapshot()

        for rel in sorted(after.keys() - before.keys()):
            content = after[rel][2]
            added = diff([], content, rel) if content is not None else "(binary or large file)\n"
            log(f"CREATED  {rel.as_posix()}\n{added}")

        for rel in sorted(before.keys() - after.keys()):
            content = before[rel][2]
            removed = diff(content, [], rel) if content is not None else "(binary or large file)\n"
            log(f"DELETED  {rel.as_posix()}\n{removed}")

        for rel in sorted(before.keys() & after.keys()):
            if before[rel][:2] == after[rel][:2]:
                continue
            old, new = before[rel][2], after[rel][2]
            if old is None or new is None:
                log(f"MODIFIED {rel.as_posix()}\n(binary or large file)\n")
            elif old != new:
                log(f"MODIFIED {rel.as_posix()}\n{diff(old, new, rel)}")

        before = after


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
