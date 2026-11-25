"""/api/ask and /api/asks: ask a question, read past ones, flag, pick a meaning.

Asking costs credits (prices.ask, flat: 8 attempts are one question).
The balance is checked before anything runs (402 if too low), and the charge
is written in the same transaction that saves the ask. A server failure
(model unreachable, crash) is not charged. A Review or Reject verdict is a
real answer and is charged.

Every ask belongs to the user who asked it. Other users get 404, not 403, so
ask ids do not leak. The provider (admin) sees all.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from verdict.api.auth import current_user, is_admin
from verdict.api.deps import get_database, state, tested_trust
from verdict.api.present import ask_response
from verdict.api.routes.review import approve_with_sql
from verdict.api.schemas import AskRequest, ChooseRequest, FlagRequest
from verdict.engine.ask import ask as run_ask
from verdict.engine.llm import LLMError
from verdict.store.db import NotEnoughCredits, new_id, now

router = APIRouter()
log = logging.getLogger("verdict.api")

NO_CREDITS = "You have no credits left. Ask the provider for more."


def perform_ask(s, user: dict, question: str, database_id: str | None, model_id: str | None) -> dict:
    """Run one ask for ``user``, charge for it, and return the response."""
    settings = s.settings()
    db = get_database(s, database_id or settings["database_id"])
    model = s.model(model_id or settings["model"])
    if model is None:
        raise HTTPException(400, f"Unknown model: {model_id}")
    if not question or not question.strip():
        raise HTTPException(400, "The question is empty.")

    price = s.price_ask
    if not s.reserve_credits(user["id"], price):
        raise HTTPException(402, NO_CREDITS)
    try:
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
            raise HTTPException(503, f"The model is not available: {e}") from None

        start = time.perf_counter()
        try:
            answer = run_ask(
                db.path, question, writer=writer, n=s.attempts, thresholds=s.thresholds,
                knowledge=s.store.knowledge(db.id), second_writer=second,
            )
        except LLMError as e:
            raise HTTPException(503, f"The model is not reachable: {e}") from None
        except Exception:
            # Any other failure is the server's, not the question's.
            log.exception("ask failed")
            raise HTTPException(500, "Something went wrong on the server. You were not charged.") from None
        latency_ms = int((time.perf_counter() - start) * 1000)

        resp = ask_response(
            answer, ask_id=new_id("a"), database_id=db.id, model_id=model.id,
            model_label=model.label, latency_ms=latency_ms, created_at=now(),
            tested_trust=tested_trust(s),
        )
        try:
            s.store.save_ask_and_charge(resp, user["id"], price)
        except NotEnoughCredits:
            # Only if the provider took credits back while this ask ran.
            raise HTTPException(402, NO_CREDITS) from None
    finally:
        s.release_credits(user["id"], price)

    # Everything that is not trusted goes to the review queue.
    if resp["level"] != "trusted":
        resp["review_id"] = s.store.add_review_item(resp["ask_id"], "auto")["id"]
    return resp


@router.post("/ask")
def ask(body: AskRequest, request: Request, user: dict = Depends(current_user)) -> dict:
    return perform_ask(state(request), user, body.question, body.database_id, body.model)


@router.get("/asks")
def recent(
    request: Request, limit: int = 20, database_id: str | None = None,
    user: dict = Depends(current_user),
) -> list[dict]:
    owner = None if is_admin(user) else user["id"]
    return state(request).store.list_asks(min(max(limit, 1), 200), database_id, owner)


def own_ask_or_404(s, ask_id: str, user: dict) -> dict:
    """The ask, if it exists and belongs to ``user`` (or ``user`` is the provider)."""
    exists, owner = s.store.ask_owner(ask_id)
    if not exists or (not is_admin(user) and owner != user["id"]):
        raise HTTPException(404, f"Unknown ask: {ask_id}")
    a = s.store.get_ask(ask_id)
    item = s.store.open_item_for_ask(ask_id)
    a["review_id"] = item["id"] if item else a.get("review_id")
    return a


@router.get("/asks/{ask_id}")
def get_ask(ask_id: str, request: Request, user: dict = Depends(current_user)) -> dict:
    return own_ask_or_404(state(request), ask_id, user)


@router.get("/asks/{ask_id}/events")
def events(ask_id: str, request: Request, user: dict = Depends(current_user)) -> list[dict]:
    """The history of one ask: asked, flagged, chosen, approved, fixed, rejected."""
    s = state(request)
    own_ask_or_404(s, ask_id, user)
    return s.store.list_events(ask_id)


@router.post("/asks/{ask_id}/flag")
def flag(ask_id: str, body: FlagRequest, request: Request, user: dict = Depends(current_user)) -> dict:
    """The analyst says a Trusted answer is wrong. It goes to the review queue."""
    s = state(request)
    own_ask_or_404(s, ask_id, user)
    s.store.flag_ask(ask_id, body.note)
    s.store.add_event(ask_id, "analyst", "flagged", body.note or None)
    item = s.store.open_item_for_ask(ask_id) or s.store.add_review_item(ask_id, "flagged")
    return {"ok": True, "review_id": item["id"]}


@router.post("/asks/{ask_id}/choose")
def choose(ask_id: str, body: ChooseRequest, request: Request, user: dict = Depends(current_user)) -> dict:
    """Pick one reading of a two-meaning question. Approves it as the answer."""
    s = state(request)
    a = own_ask_or_404(s, ask_id, user)
    options = a.get("options") or []
    if body.option >= len(options):
        raise HTTPException(400, f"This question has {len(options)} options.")
    item = s.store.open_item_for_ask(ask_id) or s.store.add_review_item(ask_id, "auto")
    label = options[body.option]["label"]
    s.store.add_event(ask_id, "analyst", "chosen", label)
    return approve_with_sql(
        s, item, a, options[body.option]["sql"], "approved",
        note=f"Chose: {label}", meaning=body.save_meaning, known=None,
    )
