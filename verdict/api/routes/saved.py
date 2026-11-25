"""/api/saved: answers the analyst keeps, and can ask again later.

Asking again is a normal ask (it costs prices.ask). The saved item then
points at the new ask, and ``changed`` says whether the answer or its level
differs from the previous run.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from verdict.api.auth import current_user, is_admin
from verdict.api.deps import state
from verdict.api.routes.ask import own_ask_or_404, perform_ask
from verdict.api.schemas import SaveRequest

router = APIRouter()


def _owner(user: dict) -> str | None:
    return None if is_admin(user) else user["id"]


def _saved_or_404(s, saved_id: str, user: dict) -> dict:
    item = s.store.get_saved(saved_id, _owner(user))
    if item is None:
        raise HTTPException(404, f"Unknown saved answer: {saved_id}")
    return item


@router.get("/saved")
def list_saved(request: Request, user: dict = Depends(current_user)) -> list[dict]:
    # The provider's Saved page shows their own items, like any analyst's.
    return state(request).store.list_saved(user["id"])


@router.post("/saved")
def save(body: SaveRequest, request: Request, user: dict = Depends(current_user)) -> dict:
    s = state(request)
    a = own_ask_or_404(s, body.ask_id, user)
    return s.store.add_saved(user["id"], a, body.name)


@router.delete("/saved/{saved_id}")
def delete(saved_id: str, request: Request, user: dict = Depends(current_user)) -> dict:
    s = state(request)
    _saved_or_404(s, saved_id, user)
    s.store.delete_saved(saved_id, _owner(user))
    return {"ok": True}


@router.post("/saved/{saved_id}/rerun")
def rerun(saved_id: str, request: Request, user: dict = Depends(current_user)) -> dict:
    s = state(request)
    _saved_or_404(s, saved_id, user)
    old = s.store.get_saved(saved_id)
    prev = s.store.get_ask(old["ask_id"]) or {}
    resp = perform_ask(s, user, prev.get("question") or old["name"], prev.get("database_id"), prev.get("model"))
    return s.store.update_saved_run(saved_id, resp)
