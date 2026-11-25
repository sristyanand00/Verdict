"""/api/databases: list, upload, and describe databases. Also /api/sql/run."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from verdict.api.auth import current_user

from verdict.api.deps import get_database, run_sql, state
from verdict.api.present import result_json
from verdict.api.schemas import SqlRunRequest
from verdict.api.state import table_counts
from verdict.engine.ingest import CSV_EXTS, EXCEL_EXTS, MAX_BYTES, SQLITE_EXTS, IngestError, ingest

router = APIRouter()


def _db_json(d) -> dict:
    out = {"id": d.id, "name": d.name, "source": d.source, "available": d.available,
           "tables_count": None}
    if d.available:
        try:
            out["tables_count"] = len(table_counts(d.path))
        except Exception:
            out["available"] = False
    return out


@router.get("/databases")
def list_databases(request: Request, user: dict = Depends(current_user)) -> list[dict]:
    return [_db_json(d) for d in state(request).databases(user)]


@router.get("/databases/{db_id}/schema")
def schema(db_id: str, request: Request, user: dict = Depends(current_user)) -> dict:
    import sqlite3
    from contextlib import closing

    from verdict.verifier.safety import read_only_uri

    db = get_database(state(request), db_id, user)
    counts = table_counts(db.path)
    tables = []
    with closing(sqlite3.connect(read_only_uri(db.path), uri=True)) as con:
        for name, n in counts.items():
            quoted = '"' + name.replace('"', '""') + '"'
            cols = con.execute(f"PRAGMA table_info({quoted})").fetchall()
            tables.append({
                "name": name, "row_count": n,
                "columns": [{"name": c[1], "type": c[2] or "TEXT"} for c in cols],
            })
    return {"id": db.id, "name": db.name, "tables": tables}


@router.post("/databases/upload")
def upload(request: Request, file: UploadFile = File(...), user: dict = Depends(current_user)) -> dict:
    s = state(request)
    if not s.uploads_enabled:
        raise HTTPException(403, "Uploads are turned off on this server. Use one of the provided databases.")
    name = Path(file.filename or "upload").name
    ext = Path(name).suffix.lower()
    if ext not in CSV_EXTS | EXCEL_EXTS | SQLITE_EXTS:
        raise HTTPException(400, "Upload a CSV, Excel (.xlsx) or SQLite file.")

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / name
        with src.open("wb") as out:
            shutil.copyfileobj(file.file, out, length=1024 * 1024)
        if src.stat().st_size > MAX_BYTES:
            raise HTTPException(413, f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
        try:
            result = ingest(src)
        except IngestError as e:
            raise HTTPException(400, str(e)) from None

    # Only the user who uploaded it (and the provider) can see or query it.
    row = s.store.add_database(
        Path(name).stem, str(result.db_path), "upload", len(result.tables), user_id=user["id"]
    )
    return {
        "id": row["id"], "name": row["name"], "source": "upload", "available": True,
        "tables_count": len(result.tables), "tables": result.tables, "columns": result.columns,
    }


@router.post("/sql/run")
def sql_run(body: SqlRunRequest, request: Request, user: dict = Depends(current_user)) -> dict:
    """Run the analyst's SQL through the same safe verifier as every attempt."""
    db = get_database(state(request), body.database_id, user)
    return result_json(run_sql(db, body.sql))
