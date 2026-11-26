"""/api/results and /api/arena: precomputed proof for the Trust Report and
Model Arena pages.

Both read files the evaluation step writes into results/, so the proof pages
work with no GPU and no internet:

    results/results.json   the Trust Report numbers (and "tested_trust")
    results/arena.json     {question_key: cached 4-model answers}
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from verdict.api.auth import admin_user
from verdict.api.deps import state

router = APIRouter()


@router.get("/results")
def results(request: Request) -> dict:
    data = state(request).results_file("results.json")
    if data is None:
        raise HTTPException(404, "results.json has not been made yet.")
    return data


#: Fields of one scoreboard row. A field missing from results.json is null
#: ("not measured yet"); the server never fills in a number.
ARENA_MODEL_FIELDS = ("model_id", "label", "kind", "benchmark", "n_questions", "accuracy", "measured_at")


@router.get("/arena/models")
def arena_models(request: Request, _: dict = Depends(admin_user)) -> list[dict]:
    """One scoreboard row per model, from results.json "arena_models".

    An empty list until the evaluation step writes that list.
    """
    data = state(request).results_file("results.json") or {}
    rows = data.get("arena_models") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    return [{k: r.get(k) for k in ARENA_MODEL_FIELDS} for r in rows if isinstance(r, dict)]


@router.get("/arena")
def arena_keys(request: Request, _: dict = Depends(admin_user)) -> list[str]:
    data = state(request).results_file("arena.json") or {}
    return sorted(data)


@router.get("/arena/{question_key}")
def arena(question_key: str, request: Request, _: dict = Depends(admin_user)) -> dict:
    data = state(request).results_file("arena.json")
    if data is None:
        raise HTTPException(404, "arena.json has not been made yet.")
    if question_key not in data:
        raise HTTPException(404, f"No cached arena answers for: {question_key}")
    return data[question_key]
