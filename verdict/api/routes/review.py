"""/api/review: the analyst's review queue.

Every ask that is not Trusted lands here, and so does a Trusted answer the
analyst flags as wrong. Resolving an item:

    approve   the draft SQL is right (or the SQL sent with the request)
    fix       the analyst's edited SQL is right
    reject    it cannot be answered; the note says why

Approve and fix re-run the SQL through the verifier, then save it as an
approved example (used in future prompts and in the conflict check) and,
if asked, as a known number.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from verdict.api.deps import get_database, run_sql, state
from verdict.api.present import json_rows, result_json
from verdict.api.schemas import KnownNumberIn, MeaningIn, ResolveRequest

router = APIRouter()


def _summary(item: dict) -> dict:
    resp = item.get("response") or {}
    return {
        "review_id": item["id"],
        "ask_id": item["ask_id"],
        "question": item["question"],
        "database_id": item["database_id"],
        "level": item["level"],
        "reasons": resp.get("reasons", []),
        "source": item["source"],          # auto, or flagged by the analyst
        "status": item["status"],          # open, approved, fixed, rejected
        "created_at": item["created_at"],
        "resolved_at": item["resolved_at"],
    }


def _item_view(s, item: dict) -> dict:
    ask = s.store.get_ask(item["ask_id"])
    return {
        "review_id": item["id"],
        "source": item["source"],
        "status": item["status"],
        "final_sql": item["final_sql"],
        "final_columns": item["final_columns"],
        "final_rows": item["final_rows"],
        "note": item["note"],
        "created_at": item["created_at"],
        "resolved_at": item["resolved_at"],
        "ask": ask,
    }


@router.get("/review")
def list_items(
    request: Request, status: str | None = "open", level: str | None = None,
    database_id: str | None = None,
) -> dict:
    s = state(request)
    items = s.store.list_review_items(status or None, level, database_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    by_level = s.store.count_asks_since(today)
    asked = sum(by_level.values())
    return {
        "items": [_summary(i) for i in items],
        "open_counts": s.store.review_counts(),     # {"review": 4, "reject": 3}
        "today": {
            "asked": asked,
            "trusted": by_level.get("trusted", 0),
            "review": by_level.get("review", 0),
            "reject": by_level.get("reject", 0),
        },
    }


def _item_or_404(s, item_id: str) -> dict:
    item = s.store.get_review_item(item_id)
    if item is None:
        raise HTTPException(404, f"Unknown review item: {item_id}")
    return item


@router.get("/review/{item_id}")
def get_item(item_id: str, request: Request) -> dict:
    s = state(request)
    return _item_view(s, _item_or_404(s, item_id))


def approve_with_sql(
    s, item: dict, ask: dict, sql: str, status: str, note: str | None,
    meaning: MeaningIn | None, known: KnownNumberIn | None,
) -> dict:
    """Run ``sql``, save it as the approved answer, and close the item."""
    if item["status"] != "open":
        raise HTTPException(409, f"This item is already {item['status']}.")
    db = get_database(s, ask["database_id"])
    r = run_sql(db, sql)
    if not r.ok:
        raise HTTPException(400, {"message": "The SQL did not run.", "result": result_json(r)})

    cols, rows = list(r.columns), json_rows(r.rows, limit=10_000)
    s.store.add_example(db.id, ask["question"], sql, cols, rows, from_review_id=item["id"])
    if known is not None:
        s.store.add_known_number(db.id, known.name, ask["question"], sql, cols, rows)
    if meaning is not None:
        s.store.add_meaning(db.id, meaning.term, meaning.definition, meaning.sql_hint)
    updated = s.store.resolve_review_item(item["id"], status, sql, cols, rows, note)
    return _item_view(s, updated)


@router.post("/review/{item_id}/resolve")
def resolve(item_id: str, body: ResolveRequest, request: Request) -> dict:
    s = state(request)
    item = _item_or_404(s, item_id)
    ask = s.store.get_ask(item["ask_id"])

    if body.action == "reject":
        if item["status"] != "open":
            raise HTTPException(409, f"This item is already {item['status']}.")
        if body.save_meaning is not None:
            s.store.add_meaning(ask["database_id"], body.save_meaning.term,
                                body.save_meaning.definition, body.save_meaning.sql_hint)
        updated = s.store.resolve_review_item(item_id, "rejected", None, None, None, body.note)
        return _item_view(s, updated)

    if body.action == "fix":
        if not body.sql or not body.sql.strip():
            raise HTTPException(400, "A fix needs the corrected SQL.")
        sql, status = body.sql, "fixed"
    else:
        sql, status = (body.sql or ask.get("sql") or ""), "approved"
        if not sql.strip():
            raise HTTPException(400, "There is no draft SQL to approve. Send the SQL, or use fix.")
    return approve_with_sql(
        s, item, ask, sql, status, body.note, body.save_meaning, body.save_known_number
    )
