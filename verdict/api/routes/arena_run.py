"""POST /api/arena/run: one question, several models, side by side.

Only the provider (admin) uses the Arena: it shows how good the product is,
by putting the trained Qwen next to the base Qwen and outside models
(Gemini, ChatGPT and the like). Analysts do not see it.

Outside models run only when the server allows it (VERDICT_ARENA_OUTSIDE,
on by default), because each call uses the provider's API quota or money.
Arena runs use no credits.

Every model gets the same question, database and knowledge, and its attempts
go through the same verifier and trust rules as a normal ask. Arena runs are
comparisons: they are not saved as asks and do not enter the review queue.
"""

from __future__ import annotations

import hashlib
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from verdict.api.auth import admin_user
from verdict.api.deps import get_database, state
from verdict.api.routes.ask import _run_fresh
from verdict.engine.knowledge import normalize

router = APIRouter()
log = logging.getLogger("verdict.api")

MAX_MODELS = 4
ROWS_SHOWN = 20
OUTSIDE_OFF = "Outside models are turned off on this server."


class ArenaRunRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    database_id: str
    models: list[str] = Field(min_length=1, max_length=MAX_MODELS)


def _key(s, db_id: str, question: str, model_id: str, n: int) -> str:
    parts = ["arena", db_id, normalize(question), model_id, str(n), str(s.store.knowledge_version(db_id))]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _summary(m, resp: dict, cache_hit: bool) -> dict:
    groups = resp.get("groups") or []
    return {
        "model_id": m.id, "label": m.label, "kind": m.role, "provider": m.kind,
        "status": "ok",
        "level": resp["level"],
        "reasons": resp["reasons"],
        "answer_text": resp.get("answer_text"),
        "sql": resp.get("sql") or (groups[0]["sql"] if groups else None),
        "columns": resp.get("columns") or [],
        "rows": (resp.get("rows") or [])[:ROWS_SHOWN],
        "n_attempts": resp["n_attempts"],
        "agree": groups[0]["size"] if groups else 0,
        "latency_ms": resp["latency_ms"],
        "cache_hit": cache_hit,
        "error": None,
    }


def _not_run(m, status: str, error: str) -> dict:
    return {
        "model_id": m.id, "label": m.label, "kind": m.role, "provider": m.kind,
        "status": status, "level": None, "reasons": [], "answer_text": None, "sql": None,
        "columns": [], "rows": [], "n_attempts": 0, "agree": 0, "latency_ms": 0,
        "cache_hit": False, "error": error,
    }


@router.post("/arena/run")
def arena_run(body: ArenaRunRequest, request: Request, user: dict = Depends(admin_user)) -> dict:
    s = state(request)
    if not body.question.strip():
        raise HTTPException(400, "The question is empty.")
    db = get_database(s, body.database_id, user)

    models = []
    for mid in dict.fromkeys(body.models):   # keep order, drop repeats
        m = s.model(mid)
        if m is None:
            raise HTTPException(400, f"Unknown model: {mid}")
        models.append(m)

    results = []
    for m in models:
        if not m.own and not s.arena_outside_enabled:
            results.append(_not_run(m, "off", OUTSIDE_OFF))
            continue
        n = s.attempts if m.own else s.arena_outside_attempts
        key = _key(s, db.id, body.question, m.id, n)
        cached = s.store.cache_get(key) if s.cache_enabled else None
        if cached is not None:
            results.append(_summary(m, cached["response"], True))
            continue
        try:
            resp = _run_fresh(s, db, m, None, body.question, time.perf_counter(), n=n)
        except HTTPException as e:
            # One model failing (quota, timeout) does not stop the others.
            results.append(_not_run(m, "error", str(e.detail)))
            continue
        if s.cache_enabled:
            s.store.cache_put(key, db.id, body.question, resp)
        results.append(_summary(m, resp, False))

    return {
        "question": body.question,
        "database_id": db.id,
        "results": results,
        "credits_charged": 0,   # kept for the page; Arena runs use no credits
    }
