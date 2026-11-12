"""Turn an uploaded file into a SQLite database the verifier can query.

Accepted inputs:
  * CSV               -> one table, named after the file
  * Excel (.xlsx)     -> one table per non-empty sheet, named after the sheet
  * SQLite            -> copied as-is

Every upload becomes a new file in the uploads folder, so the original is never
touched and the verifier can open the copy read-only.

Column names are cleaned because the AI writes SQL against them. A header like
"Order Date" forces the model to quote the name correctly every time, and a
column called "order" collides with the SQL keyword. Clean names remove both
failure modes. The mapping back to the original headers is returned so the UI
and the receipt can show users the names they recognise.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from verdict.config import uploads_root

#: Largest upload accepted. Big enough for a real business spreadsheet, small
#: enough that the free-tier backend does not run out of memory.
MAX_BYTES = 50 * 1024 * 1024

CSV_EXTS = {".csv"}
EXCEL_EXTS = {".xlsx", ".xlsm"}
SQLITE_EXTS = {".sqlite", ".sqlite3", ".db"}

#: Encodings tried in order. utf-8-sig drops the BOM Excel adds when it saves
#: CSV; cp1252 covers files saved by older Windows tools.
CSV_ENCODINGS = ("utf-8-sig", "cp1252")

#: Words that would have to be quoted if used as a name. A name in this set
#: gets a trailing underscore. Not exhaustive: these are the ones that occur
#: as spreadsheet headers in practice.
SQL_KEYWORDS = {
    "all", "and", "as", "asc", "between", "by", "case", "check", "column",
    "create", "default", "delete", "desc", "distinct", "drop", "else", "end",
    "exists", "from", "group", "having", "in", "index", "insert", "into",
    "is", "join", "key", "like", "limit", "not", "null", "offset", "on", "or",
    "order", "primary", "references", "select", "set", "table", "then",
    "to", "union", "update", "values", "when", "where",
}

_SQLITE_MAGIC = b"SQLite format 3\x00"


class IngestError(ValueError):
    """The upload cannot be turned into a database. The message is shown to the user."""


@dataclass(frozen=True)
class IngestResult:
    """What was built from one upload."""

    db_path: Path
    #: table name -> number of rows
    tables: dict[str, int]
    #: table name -> {clean column name: original header}
    columns: dict[str, dict[str, str]] = field(default_factory=dict)


def clean_name(raw: object, fallback: str) -> str:
    """Make a safe, lowercase SQL identifier from a header or sheet name.

    "Order Date" -> "order_date", "2024 Sales" -> "col_2024_sales",
    "order" -> "order_", "" -> fallback.
    """
    name = re.sub(r"[^0-9a-zA-Z]+", "_", str(raw)).strip("_").lower()
    if not name or name.startswith("unnamed"):
        # pandas names blank headers "Unnamed: 3".
        name = fallback
    if name[0].isdigit():
        name = "col_" + name
    if name in SQL_KEYWORDS:
        name += "_"
    return name


def _dedupe(names: list[str]) -> list[str]:
    """Make names unique: amount, amount -> amount, amount_2."""
    seen: dict[str, int] = {}
    out = []
    for n in names:
        if n in seen:
            seen[n] += 1
            candidate = f"{n}_{seen[n]}"
            while candidate in seen:
                seen[n] += 1
                candidate = f"{n}_{seen[n]}"
            n = candidate
        seen[n] = 1
        out.append(n)
    return out


def _read_csv(path: Path) -> pd.DataFrame:
    for enc in CSV_ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            raise IngestError(f"{path.name} is empty.") from None
        except pd.errors.ParserError as e:
            raise IngestError(f"{path.name} is not a valid CSV file: {e}") from None
    raise IngestError(f"Could not read {path.name}: unknown text encoding.")


def _read_excel(path: Path) -> dict[str, pd.DataFrame]:
    try:
        return pd.read_excel(path, sheet_name=None)
    except Exception as e:
        raise IngestError(f"Could not read {path.name} as an Excel file: {e}") from None


def _write_tables(frames: dict[str, pd.DataFrame], db_path: Path) -> IngestResult:
    """Clean the names and write each non-empty frame as a table."""
    frames = {k: v for k, v in frames.items() if not v.dropna(how="all").empty}
    if not frames:
        raise IngestError("The file has no data rows.")

    table_names = _dedupe([clean_name(k, f"table_{i + 1}") for i, k in enumerate(frames)])
    tables: dict[str, int] = {}
    columns: dict[str, dict[str, str]] = {}

    con = sqlite3.connect(db_path)
    try:
        for table, df in zip(table_names, frames.values()):
            df = df.dropna(how="all")
            originals = [str(c) for c in df.columns]
            clean = _dedupe([clean_name(c, f"column_{i + 1}") for i, c in enumerate(originals)])
            df.columns = clean
            df.to_sql(table, con, index=False)
            tables[table] = len(df)
            columns[table] = dict(zip(clean, originals))
        con.commit()
    finally:
        con.close()
    return IngestResult(db_path=db_path, tables=tables, columns=columns)


def _copy_sqlite(src: Path, db_path: Path) -> IngestResult:
    with open(src, "rb") as f:
        if f.read(len(_SQLITE_MAGIC)) != _SQLITE_MAGIC:
            raise IngestError(f"{src.name} is not a SQLite database.")
    shutil.copyfile(src, db_path)

    con = sqlite3.connect(db_path)
    try:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]
        tables = {n: con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
        columns = {
            n: {row[1]: row[1] for row in con.execute(f'PRAGMA table_info("{n}")')}
            for n in names
        }
    finally:
        con.close()
    if not tables:
        db_path.unlink()
        raise IngestError(f"{src.name} has no tables.")
    return IngestResult(db_path=db_path, tables=tables, columns=columns)


def ingest(src: str | Path, out_dir: str | Path | None = None) -> IngestResult:
    """Build a new SQLite database from ``src`` and return what was created.

    The database is written to ``out_dir`` (default: the uploads folder) under a
    random name, so two uploads of the same file never collide. Raises
    IngestError with a user-facing message if the file cannot be used.
    """
    src = Path(src)
    if not src.is_file():
        raise IngestError(f"File not found: {src.name}")
    if src.stat().st_size > MAX_BYTES:
        raise IngestError(f"{src.name} is larger than {MAX_BYTES // (1024 * 1024)} MB.")

    out = Path(out_dir) if out_dir else uploads_root()
    out.mkdir(parents=True, exist_ok=True)
    db_path = out / f"{uuid.uuid4().hex[:12]}.sqlite"

    ext = src.suffix.lower()
    try:
        if ext in CSV_EXTS:
            return _write_tables({src.stem: _read_csv(src)}, db_path)
        if ext in EXCEL_EXTS:
            return _write_tables(_read_excel(src), db_path)
        if ext in SQLITE_EXTS:
            return _copy_sqlite(src, db_path)
    except IngestError:
        db_path.unlink(missing_ok=True)
        raise
    if ext == ".xls":
        raise IngestError("Old .xls files are not supported. Save the file as .xlsx and upload again.")
    raise IngestError(f"Unsupported file type '{ext}'. Upload a CSV, Excel (.xlsx) or SQLite file.")
