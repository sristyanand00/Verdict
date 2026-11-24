"""/api/knowledge: meanings, approved examples and known numbers."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from verdict.api.deps import get_database, run_sql, state
from verdict.api.present import json_rows, result_json
from verdict.api.schemas import NewMeaningRequest
from verdict.engine.knowledge import same_answer

router = APIRouter()


@router.get("/knowledge")
def get_knowledge(database_id: str, request: Request) -> dict:
    return state(request).store.knowledge(database_id)


@router.post("/knowledge/meanings")
def add_meaning(body: NewMeaningRequest, request: Request) -> dict:
    s = state(request)
    if s.database(body.database_id) is None:
        raise HTTPException(404, f"Unknown database: {body.database_id}")
    return s.store.add_meaning(body.database_id, body.term, body.definition, body.sql_hint)


@router.delete("/knowledge/{kind}/{item_id}")
def delete(kind: str, item_id: str, request: Request) -> dict:
    try:
        deleted = state(request).store.delete_knowledge(kind, item_id)
    except ValueError:
        raise HTTPException(400, "kind must be meanings, examples or known") from None
    if not deleted:
        raise HTTPException(404, f"Not found: {kind}/{item_id}")
    return {"ok": True}


@router.post("/knowledge/known/{item_id}/recheck")
def recheck(item_id: str, request: Request) -> dict:
    """Run a known number's SQL again and say whether the answer changed."""
    s = state(request)
    k = s.store.get_known_number(item_id)
    if k is None:
        raise HTTPException(404, f"Unknown known number: {item_id}")
    r = run_sql(get_database(s, k["database_id"]), k["sql"])
    unchanged = r.ok and same_answer(r, k["columns"], k["value"], k["sql"])
    s.store.mark_known_checked(item_id, unchanged)
    return {
        "ok": unchanged,
        "changed": r.ok and not unchanged,
        "saved_value": k["value"],
        "value_now": json_rows(r.rows) if r.ok else None,
        "result": result_json(r),
    }
