"""/api/models and /api/settings."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Request

from verdict.api.auth import admin_user

from verdict.api.deps import state
from verdict.api.schemas import SettingsIn

router = APIRouter()


def models_json(s) -> list[dict]:
    # Reachability checks wait up to 2 s each; run them side by side.
    with ThreadPoolExecutor(max_workers=max(1, len(s.models))) as pool:
        reach = list(pool.map(s.reachable, s.models))
    # kind: "own" for the trained model that answers analysts; "base" for the
    # untrained Qwen and "outside" for Gemini and the like, both only in the
    # Arena. provider: how the server reaches it ("openai" covers vLLM, Ollama
    # and OpenAI-style cloud APIs).
    return [
        {"id": m.id, "label": m.label, "kind": m.role, "provider": m.kind,
         "private": m.private, "reachable": ok}
        for m, ok in zip(s.models, reach)
    ]


@router.get("/models")
def models(request: Request) -> list[dict]:
    return models_json(state(request))


@router.get("/settings")
def get_settings(request: Request) -> dict:
    return state(request).settings()


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request, _: dict = Depends(admin_user)) -> dict:
    """Settings (current database, model, second model) are shared by every
    user, so only the provider changes them."""
    s = state(request)
    values = body.model_dump(exclude_none=True)
    if "database_id" in values and s.database(values["database_id"]) is None:
        raise HTTPException(404, f"Unknown database: {values['database_id']}")
    for key in ("model", "second_model_id"):
        if key in values and values[key] and s.model(values[key]) is None:
            raise HTTPException(404, f"Unknown model: {values[key]}")
    s.store.put_settings(values)
    return s.settings()
