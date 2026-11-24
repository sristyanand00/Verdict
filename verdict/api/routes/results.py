"""/api/results and /api/arena: precomputed proof for the Trust Report and
Model Arena pages.

Both read files the Evaluation chat writes into results/, so the proof pages
work with no GPU and no internet:

    results/results.json   the Trust Report numbers (and "tested_trust")
    results/arena.json     {question_key: cached 4-model answers}
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from verdict.api.deps import state

router = APIRouter()


@router.get("/results")
def results(request: Request) -> dict:
    data = state(request).results_file("results.json")
    if data is None:
        raise HTTPException(404, "results.json has not been made yet.")
    return data


@router.get("/arena")
def arena_keys(request: Request) -> list[str]:
    data = state(request).results_file("arena.json") or {}
    return sorted(data)


@router.get("/arena/{question_key}")
def arena(question_key: str, request: Request) -> dict:
    data = state(request).results_file("arena.json")
    if data is None:
        raise HTTPException(404, "arena.json has not been made yet.")
    if question_key not in data:
        raise HTTPException(404, f"No cached arena answers for: {question_key}")
    return data[question_key]
