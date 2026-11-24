"""Small helpers shared by the routes."""

from __future__ import annotations

from fastapi import HTTPException, Request

from verdict.api.state import AppState, Database
from verdict.engine.group import QUERY_TIMEOUT_S
from verdict.verifier.pool import execute_isolated
from verdict.verifier.types import ExecutionResult


def state(request: Request) -> AppState:
    return request.app.state.verdict


def get_database(s: AppState, db_id: str) -> Database:
    db = s.database(db_id)
    if db is None:
        raise HTTPException(404, f"Unknown database: {db_id}")
    if not db.available:
        raise HTTPException(409, f"Database file is missing: {db.name}")
    return db


def run_sql(db: Database, sql: str) -> ExecutionResult:
    """Every query from the API goes through the same isolated, read-only verifier."""
    return execute_isolated(sql, db.path, QUERY_TIMEOUT_S)


def tested_trust(s: AppState) -> dict | None:
    """The tested-trust line, from results.json once the Evaluation chat writes it."""
    results = s.results_file("results.json")
    return results.get("tested_trust") if isinstance(results, dict) else None
