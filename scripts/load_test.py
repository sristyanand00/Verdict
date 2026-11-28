"""Load test: several users asking at the same time, against a running server.

    python scripts/load_test.py --base https://139-84-142-13.sslip.io/api --users 1 5 10
    python scripts/load_test.py --users 1 5 --per-user 2 --out data/load_test.json

For each level (1, 5, 10 users) that many users start together and each runs
``--per-user`` questions one after another. Every question is a fresh run of
the full pipeline (model, SQL, checks) through the provider's Model Arena with
the own model only, so the test leaves no asks, no review items, no credit
charges and no changes to the answer cache behind. It logs in as the provider
from .env (VERDICT_ADMIN_EMAIL and VERDICT_ADMIN_PASSWORD).

Questions come from the demo question files, a different one for each run, so
the model writes them all from scratch. Each result is one of:

    ok          an answer (Trusted, Review or Reject)
    busy        no free slot within the server's queue wait (503)
    timeout     stopped at the server's time limit (504)
    error       anything else (model down, HTTP error, network)

The run also reads /api/admin/stats once at the end, for the machine's load.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_QUESTIONS = REPO / "demos" / "questions"


def call(base: str, path: str, body: dict | None = None, token: str | None = None,
         timeout: float = 900, method: str | None = None) -> tuple[int, dict | str]:
    headers = {"Content-Type": "application/json", "User-Agent": "verdict-load-test"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        base.rstrip("/") + path, data=None if body is None else json.dumps(body).encode("utf-8"),
        headers=headers, method=method or ("GET" if body is None else "POST"),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:  # network
        return 0, f"{type(e).__name__}: {e}"


def load_questions(folder: Path) -> list[tuple[str, str]]:
    """(database id, question) pairs from <db>.txt files, interleaved across databases."""
    per_db = {}
    for f in sorted(folder.glob("*.txt")):
        qs = [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()
              if ln.strip() and not ln.strip().startswith("#")]
        if qs:
            per_db[f.stem] = qs
    out, i = [], 0
    while any(i < len(qs) for qs in per_db.values()):
        out += [(db, qs[i]) for db, qs in per_db.items() if i < len(qs)]
        i += 1
    return out


def outcome(status: int, data) -> tuple[str, str | None]:
    if status != 200 or not isinstance(data, dict):
        return {503: "busy", 504: "timeout"}.get(status, "error"), None
    r = data["results"][0]
    if r["status"] == "ok":
        return "ok", r["level"]
    err = (r.get("error") or "").lower()
    if "busy" in err:
        return "busy", None
    if "too long" in err:
        return "timeout", None
    return "error", None


def run_level(base: str, token: str, model: str, users: int, per_user: int,
              questions: list[tuple[str, str]], offset: int) -> dict:
    results: list[dict] = []
    lock = threading.Lock()

    def user(u: int) -> None:
        for k in range(per_user):
            db, q = questions[(offset + u * per_user + k) % len(questions)]
            t = time.perf_counter()
            status, data = call(base, "/arena/run", {
                "question": q, "database_id": db, "models": [model], "fresh": True}, token)
            took = time.perf_counter() - t
            out, level = outcome(status, data)
            with lock:
                results.append({"user": u, "database_id": db, "question": q, "outcome": out,
                                "level": level, "seconds": round(took, 1)})

    start = time.perf_counter()
    threads = [threading.Thread(target=user, args=(u,)) for u in range(users)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - start

    ok = [r["seconds"] for r in results if r["outcome"] == "ok"]
    counts = {o: sum(1 for r in results if r["outcome"] == o) for o in ("ok", "busy", "timeout", "error")}
    return {
        "users": users, "questions": len(results), "wall_seconds": round(wall, 1),
        "outcomes": counts,
        "answered_per_minute": round(60 * counts["ok"] / wall, 1) if wall else None,
        "seconds_avg": round(statistics.mean(ok), 1) if ok else None,
        "seconds_median": round(statistics.median(ok), 1) if ok else None,
        "seconds_max": max(ok) if ok else None,
        "runs": sorted(results, key=lambda r: (r["user"], r["question"])),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8000/api")
    ap.add_argument("--users", type=int, nargs="+", default=[1, 5, 10])
    ap.add_argument("--per-user", type=int, default=2)
    ap.add_argument("--model", default="qwen")
    ap.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS, help="folder of <db>.txt files")
    ap.add_argument("--out", type=Path, default=REPO / "data" / "load_test.json")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env")
    except ImportError:
        pass
    email, password = os.environ.get("VERDICT_ADMIN_EMAIL"), os.environ.get("VERDICT_ADMIN_PASSWORD")
    if not email or not password:
        sys.exit("Set VERDICT_ADMIN_EMAIL and VERDICT_ADMIN_PASSWORD (the provider account).")
    status, data = call(args.base, "/auth/login", {"email": email, "password": password})
    if status != 200:
        sys.exit(f"login failed: HTTP {status}: {data}")
    token = data["token"]

    questions = load_questions(args.questions)
    if not questions:
        sys.exit(f"no questions in {args.questions}")
    print(f"{len(questions)} questions; model {args.model}; {args.per_user} per user; server {args.base}")

    levels, offset = [], 0
    for n in args.users:
        print(f"\n{n} user(s) at the same time ...", flush=True)
        lv = run_level(args.base, token, args.model, n, args.per_user, questions, offset)
        offset += n * args.per_user
        levels.append(lv)
        o = lv["outcomes"]
        print(f"  {lv['questions']} questions in {lv['wall_seconds']} s: ok {o['ok']}, busy {o['busy']},"
              f" timeout {o['timeout']}, error {o['error']}; answered/min {lv['answered_per_minute']};"
              f" seconds avg {lv['seconds_avg']}, median {lv['seconds_median']}, max {lv['seconds_max']}")

    status, stats = call(args.base, "/admin/stats", token=token)
    report = {
        "server": args.base, "model": args.model, "per_user": args.per_user,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "server_settings": stats.get("settings") if status == 200 else None,
        "machine_after": stats.get("machine") if status == 200 else None,
        "levels": levels,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nsaved {args.out}")


if __name__ == "__main__":
    main()
