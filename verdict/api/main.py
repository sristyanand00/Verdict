"""The Verdict API server.

    uvicorn verdict.api.main:app --port 8000

All routes live under /api (contract: docs/API.md). The frontend never talks
to a model or a database directly; only this server does.

If the frontend has been built (frontend/dist), the server also serves it,
so on demo day one process on one address runs the whole product.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from verdict.api.auth import RateLimiter, current_user
from verdict.api.routes import accounts, ask, data, knowledge, models, results, review, saved
from verdict.api.routes.accounts import ensure_admin
from verdict.api.routes.models import models_json
from verdict.api.state import AppState
from verdict.config import REPO_ROOT
from verdict.engine.trust import THRESHOLDS_FILE

DEFAULT_CORS = "http://localhost:5173,http://127.0.0.1:5173"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def create_app(app_state: AppState | None = None, frontend_dist: Path | None = FRONTEND_DIST) -> FastAPI:
    app = FastAPI(title="Verdict API", version="0.1.0")
    app.state.verdict = app_state or AppState.from_env()
    app.state.auth_limiter = RateLimiter(app.state.verdict.auth_rate_per_minute)
    ensure_admin(app.state.verdict)

    origins = [o.strip() for o in os.environ.get("VERDICT_CORS_ORIGINS", DEFAULT_CORS).split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"],
    )

    # Login, signup and the account pages check the login themselves. Every
    # other /api route needs a logged-in, active account. /api/health and the
    # website files are open.
    app.include_router(accounts.router, prefix="/api")
    for r in (ask, review, knowledge, data, models, results, saved):
        app.include_router(r.router, prefix="/api", dependencies=[Depends(current_user)])

    @app.get("/api/health")
    def health(request: Request) -> dict:
        s: AppState = request.app.state.verdict
        try:
            source = json.loads(THRESHOLDS_FILE.read_text(encoding="utf-8")).get("source", "")
        except Exception:
            source = "unreadable"
        # Only the preloaded databases: uploads belong to their users.
        dbs = {d.id: d.available for d in s.preloaded}
        mods = {m["id"]: m["reachable"] for m in models_json(s)}
        return {
            "ok": s.store.ok(),
            "app_db": s.store.ok(),
            "databases": dbs,
            "models": mods,
            "attempts": s.attempts,
            # True until the evaluation step writes measured thresholds.
            "thresholds_placeholder": source.upper().startswith("PLACEHOLDER"),
            "results_ready": s.results_file("results.json") is not None,
        }

    if frontend_dist is not None and (frontend_dist / "index.html").is_file():
        _serve_frontend(app, frontend_dist)
    return app


def _serve_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built website, sending unknown paths to index.html so the
    frontend's own routes (/ask, /review, ...) work on reload."""
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = (root / path).resolve()
        if path and f.is_file() and f.is_relative_to(root):
            return FileResponse(f)
        return FileResponse(root / "index.html")


app = create_app()
