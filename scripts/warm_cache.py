"""Answer the demo questions once, so on stage they come from the cache.

    python scripts/warm_cache.py --db olist questions.txt
    python scripts/warm_cache.py --db financial "How many accounts are there?" "How many loans?"

Each question is asked through the running server as the provider (the
admin account from .env), so the answers are exactly what an analyst gets,
and the provider's asks cost no credits. Asking a question that is already
cached is instant and changes nothing.

questions.txt: one question per line; empty lines and lines starting with #
are skipped. The server must be running (uvicorn verdict.api.main:app).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def call(base: str, path: str, body: dict | None = None, token: str | None = None, timeout: float = 600) -> dict:
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
        method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{path}: HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from None


def load_questions(items: list[str]) -> list[str]:
    out = []
    for item in items:
        p = Path(item)
        if p.suffix == ".txt" and p.is_file():
            out += [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.strip().startswith("#")]
        else:
            out.append(item)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("questions", nargs="+", help="questions, or .txt files with one question per line")
    ap.add_argument("--db", required=True, help="database id, e.g. olist or financial")
    ap.add_argument("--model", default=None, help="model id (default: the server's current model)")
    ap.add_argument("--base", default="http://127.0.0.1:8000/api")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env")
    except ImportError:
        pass
    email, password = os.environ.get("VERDICT_ADMIN_EMAIL"), os.environ.get("VERDICT_ADMIN_PASSWORD")
    if not (email and password):
        sys.exit("Set VERDICT_ADMIN_EMAIL and VERDICT_ADMIN_PASSWORD in .env first.")
    token = call(args.base, "/auth/login", {"email": email, "password": password})["token"]

    questions = load_questions(args.questions)
    print(f"{len(questions)} questions on {args.db}")
    for q in questions:
        t = time.perf_counter()
        body = {"question": q, "database_id": args.db, **({"model": args.model} if args.model else {})}
        r = call(args.base, "/ask", body, token)
        took = time.perf_counter() - t
        where = "cache" if r.get("cache_hit") else "fresh"
        print(f"  {r['level']:<8} {where:<5} {took:6.1f}s  {r.get('answer_text') or '-'}  | {q}")


if __name__ == "__main__":
    main()
