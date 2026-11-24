"""/api/ask and /api/asks: ask a question, read past ones, flag, pick a meaning."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from verdict.api.deps import get_database, state, tested_trust
from verdict.api.present import ask_response
from verdict.api.routes.review import approve_with_sql
from verdict.api.schemas import AskRequest, ChooseRequest, FlagRequest
from verdict.engine.ask import ask as run_ask
from verdict.engine.llm import LLMError
from verdict.store.db import new_id, now

router = APIRouter()


@router.post("/ask")
def ask(body: AskRequest, request: Request) -> dict:
    s = state(request)
    settings = s.settings()
    db = get_database(s, body.database_id or settings["database_id"])
    model = s.model(body.model or settings["model"])
    if model is None:
        raise HTTPException(400, f"Unknown model: {body.model}")

    second = None
    if settings.get("second_model"):
        m2 = s.model(settings.get("second_model_id") or "")
        if m2 is not None and m2.id != model.id:
            try:
                second = s.writer_factory(m2)
            except Exception:
                second = None  # optional; the check shows "off"

    try:
        writer = s.writer_factory(model)
    except LLMError as e:
        raise HTTPException(503, str(e)) from None

    start = time.perf_counter()
    try:
        answer = run_ask(
            db.path, body.question, writer=writer, n=s.attempts, thresholds=s.thresholds,
            knowledge=s.store.knowledge(db.id), second_writer=second,
        )
    except LLMError as e:
        raise HTTPException(503, f"The model is not reachable: {e}") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    latency_ms = int((time.perf_counter() - start) * 1000)

    resp = ask_response(
        answer, ask_id=new_id("a"), database_id=db.id, model_id=model.id,
        model_label=model.label, latency_ms=latency_ms, created_at=now(),
        tested_trust=tested_trust(s),
    )
    s.store.save_ask(resp)
    # Everything that is not trusted goes to the review queue.
    if resp["level"] != "trusted":
        resp["review_id"] = s.store.add_review_item(resp["ask_id"], "auto")["id"]
    return resp


@router.get("/asks")
def recent(request: Request, limit: int = 20, database_id: str | None = None) -> list[dict]:
    return state(request).store.list_asks(min(max(limit, 1), 200), database_id)


def _ask_or_404(s, ask_id: str) -> dict:
    a = s.store.get_ask(ask_id)
    if a is None:
        raise HTTPException(404, f"Unknown ask: {ask_id}")
    item = s.store.open_item_for_ask(ask_id)
    a["review_id"] = item["id"] if item else a.get("review_id")
    return a


@router.get("/asks/{ask_id}")
def get_ask(ask_id: str, request: Request) -> dict:
    return _ask_or_404(state(request), ask_id)


@router.post("/asks/{ask_id}/flag")
def flag(ask_id: str, body: FlagRequest, request: Request) -> dict:
    """The analyst says a Trusted answer is wrong. It goes to the review queue."""
    s = state(request)
    _ask_or_404(s, ask_id)
    s.store.flag_ask(ask_id, body.note)
    item = s.store.open_item_for_ask(ask_id) or s.store.add_review_item(ask_id, "flagged")
    return {"ok": True, "review_id": item["id"]}


@router.post("/asks/{ask_id}/choose")
def choose(ask_id: str, body: ChooseRequest, request: Request) -> dict:
    """Pick one reading of a two-meaning question. Approves it as the answer."""
    s = state(request)
    a = _ask_or_404(s, ask_id)
    options = a.get("options") or []
    if body.option >= len(options):
        raise HTTPException(400, f"This question has {len(options)} options.")
    item = s.store.open_item_for_ask(ask_id) or s.store.add_review_item(ask_id, "auto")
    return approve_with_sql(
        s, item, a, options[body.option]["sql"], "approved",
        note=f'Chose: {options[body.option]["label"]}', meaning=body.save_meaning, known=None,
    )
