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

import hashlib
import logging
import time
from concurrent.futures import TimeoutError as FutureTimeout

from fastapi import APIRouter, Depends, HTTPException, Request

from verdict.api.auth import current_user, is_admin
from verdict.api.deps import get_database, state, tested_trust
from verdict.api.present import ask_response
from verdict.api.routes.review import approve_with_sql
from verdict.api.schemas import AskRequest, ChooseRequest, FlagRequest
from verdict.engine.ask import ask as run_ask
from verdict.engine.knowledge import normalize
from verdict.engine.llm import LLMError
from verdict.store.db import NotEnoughCredits, new_id, now

router = APIRouter()
log = logging.getLogger("verdict.api")

NO_CREDITS = "You have no credits left. Ask the provider for more."


def cache_key(s, db_id: str, question: str, model_id: str, second_id: str, version: int | None = None) -> str:
    """Same database, same question (case and spacing ignored), same model and
    setup, same knowledge version: same key."""
    v = s.store.knowledge_version(db_id) if version is None else version
    parts = [db_id, normalize(question), model_id, second_id, str(s.attempts), str(v)]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def earlier_cached(s, db_id: str, key_for) -> dict | None:
    """The newest answer cached under an earlier knowledge version, or None.

    Used only when the model cannot answer right now: an answer checked before
    the last knowledge change is better than no answer, and it is marked
    ``cache_stale`` so the page can say so. ``key_for(version)`` builds the key.
    """
    for v in range(s.store.knowledge_version(db_id) - 1, -1, -1):
        hit = s.store.cache_get(key_for(v))
        if hit is not None:
            return hit
    return None


def perform_ask(
    s, user: dict, question: str, database_id: str | None, model_id: str | None, fresh: bool = False,
) -> dict:
    """Run one ask for ``user``, charge for it, and return the response.

    A repeated question is answered from the cache (``cache_hit: true``) when
    nothing that could change the answer has changed. It is still saved as the
    user's own ask and charged like any answer. The provider's own asks are free.
    ``fresh=True`` skips the cache (asking a saved question again).
    """
    settings = s.settings()
    db = get_database(s, database_id or settings["database_id"], user)
    model = s.model(model_id or settings["model"])
    if model is None:
        raise HTTPException(400, f"Unknown model: {model_id}")
    if model.arena_only:
        raise HTTPException(400, f"{model.label} is only for the Model Arena.")
    if not question or not question.strip():
        raise HTTPException(400, "The question is empty.")

    m2 = None
    if settings.get("second_model"):
        m2 = s.model(settings.get("second_model_id") or "")
        if m2 is not None and m2.id == model.id:
            m2 = None
    key = cache_key(s, db.id, question, model.id, m2.id if m2 else "")
    s.ask_limiter.check(user["id"])

    price = 0 if is_admin(user) else s.price_ask
    if not s.reserve_credits(user["id"], price):
        raise HTTPException(402, NO_CREDITS)
    try:
        start = time.perf_counter()
        cached = s.store.cache_get(key) if s.cache_enabled and not fresh else None
        stale = False
        if cached is None:
            try:
                resp = _run_fresh(s, db, model, m2, question, start)
            except HTTPException as e:
                log_failure(s, "ask", user, db.id, model.id, e, start)
                # The model is down or too slow: fall back to the answer saved
                # before the last knowledge change, if there is one.
                if s.cache_enabled and not fresh and outcome_of(e) in ("model_down", "timeout"):
                    cached = earlier_cached(
                        s, db.id, lambda v: cache_key(s, db.id, question, model.id, m2.id if m2 else "", v))
                if cached is None:
                    raise
                stale = True
            else:
                if s.cache_enabled:
                    s.store.cache_put(key, db.id, question, resp)
        if cached is not None:
            resp = dict(cached["response"])
            resp.update(
                ask_id=new_id("a"), question=question, created_at=now(),
                latency_ms=int((time.perf_counter() - start) * 1000),
                cache_hit=True, cached_at=cached["created_at"], cache_stale=stale,
                review_id=None, flagged=False, flag_note=None,
            )
            resp["usage"] = dict(NO_USAGE)
        try:
            s.store.save_ask_and_charge(resp, user["id"], price)
        except NotEnoughCredits:
            # Only if the provider took credits back while this ask ran.
            raise HTTPException(402, NO_CREDITS) from None
        log_success(s, "ask", user, db.id, model.id, resp)
    finally:
        s.release_credits(user["id"], price)

    # Everything that is not trusted goes to the review queue.
    if resp["level"] != "trusted":
        resp["review_id"] = s.store.add_review_item(resp["ask_id"], "auto")["id"]
    return resp


BUSY = "The server is busy with other questions. Try again in a minute. You were not charged."
TOO_SLOW = "The question took too long to answer, so it was stopped. You were not charged."
MODEL_DOWN = "The model is not reachable right now. Try again later. You were not charged."

#: "usage" of an answer that did not call a model (a cache hit).
NO_USAGE = {"model_ms": 0, "prompt_tokens": 0, "completion_tokens": 0}


def outcome_of(e: HTTPException) -> str:
    if e.status_code == 504:
        return "timeout"
    if e.status_code == 503:
        return "busy" if e.detail == BUSY else "model_down"
    return "error"


def log_success(s, kind: str, user: dict, db_id: str, model_id: str, resp: dict) -> None:
    usage = resp.get("usage") or NO_USAGE
    try:
        s.store.log_run(
            kind=kind, user_id=user["id"], database_id=db_id, model=model_id, outcome="ok",
            cache_hit=resp.get("cache_hit"), level=resp.get("level"),
            n_attempts=resp.get("n_attempts"), total_ms=resp.get("latency_ms"),
            model_ms=usage.get("model_ms"), prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"), ask_id=resp.get("ask_id"),
        )
    except Exception:
        log.exception("could not write the usage log")  # never fail an answer over statistics


def log_failure(s, kind: str, user: dict, db_id: str, model_id: str, e: HTTPException, start: float) -> None:
    try:
        s.store.log_run(
            kind=kind, user_id=user["id"], database_id=db_id, model=model_id,
            outcome=outcome_of(e), total_ms=int((time.perf_counter() - start) * 1000),
        )
    except Exception:
        log.exception("could not write the usage log")


class _Metered:
    """Wraps a writer to measure the time spent waiting for the model and the
    tokens it reports. Everything after that (running SQL, grouping, checks)
    is the rest of latency_ms."""

    def __init__(self, writer):
        self._w = writer
        self.ms = 0.0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def write(self, prompt: str, n: int) -> list[str]:
        t = time.perf_counter()
        try:
            return self._w.write(prompt, n)
        finally:
            self.ms += (time.perf_counter() - t) * 1000
            u = getattr(self._w, "last_usage", None) or {}
            self.prompt_tokens += int(u.get("prompt_tokens") or 0)
            self.completion_tokens += int(u.get("completion_tokens") or 0)

    def __getattr__(self, name):
        return getattr(self._w, name)


def _run_fresh(s, db, model, m2, question: str, start: float, n: int | None = None) -> dict:
    """Run the pipeline in a worker thread, at most max_concurrent_asks at a
    time, and stop waiting after ask_timeout_s.

    A stopped ask keeps its slot until its thread really ends, so a slow
    model cannot be flooded by retries.
    """
    if not s.ask_slots.acquire(timeout=s.queue_wait_s):
        raise HTTPException(503, BUSY)
    try:
        future = s.ask_pool.submit(_pipeline, s, db, model, m2, question, start, n)
    except Exception:
        s.ask_slots.release()
        raise
    future.add_done_callback(lambda _: s.ask_slots.release())
    try:
        return future.result(timeout=s.ask_timeout_s)
    except FutureTimeout:
        log.warning("ask stopped after %.0f s", s.ask_timeout_s)
        raise HTTPException(504, TOO_SLOW) from None


def _pipeline(s, db, model, m2, question: str, start: float, n: int | None = None) -> dict:
    second = None
    if m2 is not None:
        try:
            second = s.writer_factory(m2)
        except Exception:
            second = None  # optional; the check shows "off"
    try:
        writer = _Metered(s.writer_factory(model))
    except LLMError:
        log.exception("model not available")
        raise HTTPException(503, MODEL_DOWN) from None
    if second is not None:
        second = _Metered(second)
    try:
        answer = run_ask(
            db.path, question, writer=writer, n=n or s.attempts, thresholds=s.thresholds,
            knowledge=s.store.knowledge(db.id), second_writer=second,
        )
    except LLMError:
        # The details (server address, error) go to the log, not to the user.
        log.exception("model not reachable")
        raise HTTPException(503, MODEL_DOWN) from None
    except Exception:
        # Any other failure is the server's, not the question's.
        log.exception("ask failed")
        raise HTTPException(500, "Something went wrong on the server. You were not charged.") from None
    resp = ask_response(
        answer, ask_id=new_id("a"), database_id=db.id, model_id=model.id,
        model_label=model.label, latency_ms=int((time.perf_counter() - start) * 1000),
        created_at=now(), tested_trust=tested_trust(s),
    )
    resp["cache_hit"] = False
    resp["cached_at"] = None
    metered = [w for w in (writer, second) if w is not None]
    resp["usage"] = {
        "model_ms": int(sum(w.ms for w in metered)),
        "prompt_tokens": sum(w.prompt_tokens for w in metered),
        "completion_tokens": sum(w.completion_tokens for w in metered),
    }
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
