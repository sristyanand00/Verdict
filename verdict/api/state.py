"""What the API server knows about: databases, models, the app store.

Everything that changes between setups (laptop, college GPU, demo day) comes
from environment variables, so the same code runs everywhere:

    VERDICT_APP_DB          path of data/app.db
    VERDICT_OLIST_PATH      path of the Olist SQLite file
    VERDICT_QWEN_URL        OpenAI-compatible server, e.g. http://localhost:11434/v1
    VERDICT_QWEN_MODEL      model name on that server, e.g. verdict-qwen
    VERDICT_MODELS_FILE     optional JSON file listing models (replaces the defaults)
    VERDICT_ATTEMPTS        attempts per question (default 8)
    VERDICT_CORS_ORIGINS    comma-separated website addresses allowed to call the API
    GEMINI_API_KEY          only if Gemini is used
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from verdict.config import REPO_ROOT, data_root, db_path, results_root
from verdict.engine.llm import FixedWriter, GeminiWriter, OpenAICompatWriter, SQLWriter
from verdict.store.db import Store
from verdict.verifier.safety import read_only_uri

DEFAULT_ATTEMPTS = 8


# -- databases ---------------------------------------------------------------

@dataclass(frozen=True)
class Database:
    id: str
    name: str
    path: Path
    source: str  # "preloaded" or "upload"

    @property
    def available(self) -> bool:
        return self.path.is_file()


def preloaded_databases() -> list[Database]:
    olist = os.environ.get("VERDICT_OLIST_PATH")
    return [
        Database(
            "olist", "Olist e-commerce",
            Path(olist) if olist else data_root() / "olist" / "olist.sqlite", "preloaded",
        ),
        Database("financial", "BIRD financial (Czech bank)", db_path("financial"), "preloaded"),
        Database(
            "debit_card_specializing", "BIRD debit card (fuel cards)",
            db_path("debit_card_specializing"), "preloaded",
        ),
    ]


def table_counts(path: Path) -> dict[str, int]:
    """Table name -> row count, read-only."""
    with closing(sqlite3.connect(read_only_uri(path), uri=True)) as con:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        return {n: con.execute(f'SELECT COUNT(*) FROM "{n.replace(chr(34), chr(34) * 2)}"').fetchone()[0]
                for n in names}


# -- models ------------------------------------------------------------------

@dataclass(frozen=True)
class ModelEntry:
    id: str
    label: str
    kind: str              # "openai" (vLLM / Ollama), "gemini", or "fixed" (tests)
    private: bool          # True when the data never leaves this machine or network
    base_url: str = ""
    model: str = ""
    replies: tuple[str, ...] = ()   # only for kind "fixed"


def default_models() -> list[ModelEntry]:
    return [
        ModelEntry(
            "qwen", "Qwen 1.5B (trained), private", "openai", True,
            base_url=os.environ.get("VERDICT_QWEN_URL", "http://localhost:11434/v1"),
            model=os.environ.get("VERDICT_QWEN_MODEL", "verdict-qwen"),
        ),
        ModelEntry(
            "gemini", "Gemini (cloud)", "gemini", False,
            model=os.environ.get("GEMINI_MODEL", ""),
        ),
    ]


def load_models() -> list[ModelEntry]:
    """Models from VERDICT_MODELS_FILE if set, else the two defaults.

    File format: a JSON list of {"id", "label", "kind", "private", "base_url", "model"}.
    """
    path = os.environ.get("VERDICT_MODELS_FILE")
    if not path:
        return default_models()
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        ModelEntry(
            m["id"], m.get("label", m["id"]), m["kind"], bool(m.get("private", m["kind"] != "gemini")),
            base_url=m.get("base_url", ""), model=m.get("model", ""),
        )
        for m in raw
    ]


def make_writer(m: ModelEntry) -> SQLWriter:
    if m.kind == "openai":
        return OpenAICompatWriter(m.base_url, m.model)
    if m.kind == "gemini":
        return GeminiWriter(model=m.model or None)
    if m.kind == "fixed":
        return FixedWriter(list(m.replies))
    raise ValueError(f"unknown model kind: {m.kind}")


def model_reachable(m: ModelEntry) -> bool:
    if m.kind == "openai":
        return OpenAICompatWriter(m.base_url, m.model).reachable()
    if m.kind == "gemini":
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        return bool(os.environ.get("GEMINI_API_KEY"))
    return True


# -- the whole server state ----------------------------------------------------

@dataclass
class AppState:
    store: Store
    models: list[ModelEntry]
    preloaded: list[Database]
    results_dir: Path = field(default_factory=results_root)
    attempts: int = DEFAULT_ATTEMPTS
    thresholds: dict[str, float] | None = None   # None: read thresholds.json on every ask
    writer_factory: Callable[[ModelEntry], SQLWriter] = make_writer
    reachable: Callable[[ModelEntry], bool] = model_reachable

    @classmethod
    def from_env(cls) -> "AppState":
        return cls(
            store=Store(),
            models=load_models(),
            preloaded=preloaded_databases(),
            attempts=int(os.environ.get("VERDICT_ATTEMPTS", DEFAULT_ATTEMPTS)),
        )

    # databases

    def databases(self) -> list[Database]:
        ups = [
            Database(d["id"], d["name"], Path(d["path"]), d["source"])
            for d in self.store.list_databases()
        ]
        return self.preloaded + ups

    def database(self, db_id: str) -> Database | None:
        return next((d for d in self.databases() if d.id == db_id), None)

    # models

    def model(self, model_id: str) -> ModelEntry | None:
        return next((m for m in self.models if m.id == model_id), None)

    # settings, with defaults filled in

    def settings(self) -> dict:
        s = self.store.get_settings()
        first_db = next((d.id for d in self.preloaded if d.available), self.preloaded[0].id)
        s.setdefault("database_id", first_db)
        s.setdefault("model", self.models[0].id if self.models else "")
        s.setdefault("second_model", False)
        s.setdefault("second_model_id", next((m.id for m in self.models if m.kind == "gemini"), ""))
        return s

    # precomputed proof files from the Evaluation chat

    def results_file(self, name: str) -> dict | None:
        p = self.results_dir / name
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
