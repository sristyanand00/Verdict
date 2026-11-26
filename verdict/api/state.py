"""What the API server knows about: databases, models, the app store.

Everything that changes between setups (laptop, college GPU, demo day) comes
from environment variables, so the same code runs everywhere:

    VERDICT_APP_DB          path of data/app.db
    VERDICT_OLIST_PATH      path of the Olist SQLite file
    VERDICT_DATABASES       databases offered, comma-separated ids (see KNOWN_DATABASES)
    VERDICT_QWEN_URL        OpenAI-compatible server, e.g. http://127.0.0.1:11434/v1
    VERDICT_QWEN_MODEL      model name on that server, e.g. verdict-qwen
    VERDICT_MODELS_FILE     optional JSON file listing models (replaces the defaults)
    VERDICT_ATTEMPTS        attempts per question (default 8)
    VERDICT_CORS_ORIGINS    comma-separated website addresses allowed to call the API
    GEMINI_API_KEY          only if Gemini is used

Accounts and credits:

    VERDICT_ADMIN_EMAIL, VERDICT_ADMIN_PASSWORD
                            the provider account, created on startup if missing
    VERDICT_SIGNUP_CREDITS  starting credits for a new account (default 20)
    VERDICT_PRICE_ASK       credits for one question (default 1)
    VERDICT_PRICE_ARENA_OUTSIDE_MODEL
                            credits per outside model in a live Arena run (default 1)
    VERDICT_AUTH_RATE       login and signup tries per minute per IP (default 10)
    VERDICT_CACHE           "off" answers every question fresh (default on)

Limits for a public server:

    VERDICT_UPLOADS         "off" turns file uploads off (default on)
    VERDICT_UPLOAD_TTL_HOURS
                            delete uploads older than this (default 0: keep)
    VERDICT_ASK_TIMEOUT_S   stop an ask after this many seconds (default 180)
    VERDICT_ASK_RATE        questions per user per minute (default 10)
    VERDICT_MAX_CONCURRENT_ASKS
                            fresh asks running at once (default 2)
    VERDICT_QUEUE_WAIT_S    how long an ask waits for a free slot (default 60)

Live Model Arena:

    VERDICT_ARENA_OUTSIDE   "on" lets the Arena call outside models such as Gemini
                            (default off, so no outside API quota is used)
    VERDICT_ARENA_OUTSIDE_ATTEMPTS
                            attempts asked of an outside model (default 8)
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from verdict.config import REPO_ROOT, data_root, db_path, results_root
from verdict.engine.llm import FixedWriter, GeminiWriter, OpenAICompatWriter, SQLWriter
from verdict.store.db import Store
from verdict.verifier.safety import read_only_uri

DEFAULT_ATTEMPTS = 8
DEFAULT_SIGNUP_CREDITS = 20
DEFAULT_PRICE_ASK = 1
DEFAULT_PRICE_ARENA = 1
DEFAULT_AUTH_RATE = 10
#: A whole ask (all attempts and queries) past this many seconds is stopped
#: and not charged.
DEFAULT_ASK_TIMEOUT_S = 180
#: Questions per user per minute.
DEFAULT_ASK_RATE = 10
#: Fresh asks running at the same time. A CPU model slows down for everyone
#: when more run at once, so the rest wait, up to DEFAULT_QUEUE_WAIT_S.
DEFAULT_MAX_CONCURRENT_ASKS = 2
DEFAULT_QUEUE_WAIT_S = 60


def _on(value: str) -> bool:
    return value.strip().lower() not in ("off", "0", "false", "no")


# -- databases ---------------------------------------------------------------

@dataclass(frozen=True)
class Database:
    id: str
    name: str
    path: Path
    source: str  # "preloaded" or "upload"
    #: who uploaded it; None for preloaded databases (everyone may use those)
    owner: str | None = None
    #: one line about the data, shown in the database picker
    description: str = ""

    def visible_to(self, user: dict | None) -> bool:
        """Preloaded databases are for everyone; an upload only for its owner
        and the provider. ``user`` None means a trusted internal caller."""
        if self.source != "upload" or user is None:
            return True
        return user.get("role") == "admin" or user.get("id") == self.owner

    @property
    def available(self) -> bool:
        return self.path.is_file()


#: Databases the server can offer: id -> (name, one line about it).
#: Olist is the demo's e-commerce data; the rest are BIRD dev databases, which
#: were not used in training (training used BIRD train).
KNOWN_DATABASES: dict[str, tuple[str, str]] = {
    "olist": ("Olist e-commerce", "Brazilian online shop: orders, items, payments, customers, sellers, reviews."),
    "financial": ("Czech bank", "Accounts, clients, loans, cards and transactions of a Czech bank. Coded values."),
    "formula_1": ("Formula 1", "Races, drivers, constructors, results, lap times and pit stops, 1950 onwards."),
    "european_football_2": ("European football", "Matches, teams, players and player ratings from European leagues."),
    "card_games": ("Magic: The Gathering cards", "Cards, sets, rulings, legalities and foreign names. Messy columns."),
    "california_schools": ("California schools", "Schools, SAT scores and free-meal numbers."),
    "codebase_community": ("Stats Q&A site", "Posts, users, comments, votes and badges of a Q&A site."),
    "debit_card_specializing": ("Fuel cards", "Customers, gas stations, products and monthly fuel spending."),
    "student_club": ("Student club", "Members, events, attendance, budget and expenses."),
    "superhero": ("Superheroes", "Superheroes, their powers, attributes and publishers."),
    "thrombosis_prediction": ("Thrombosis patients", "Patients, lab tests and examinations."),
    "toxicology": ("Toxicology molecules", "Molecules, atoms and bonds, with a carcinogenic label."),
}

#: Offered when VERDICT_DATABASES is not set: the demo data plus four hard databases.
DEFAULT_DATABASES = "olist,financial,formula_1,european_football_2,card_games"


def preloaded_databases() -> list[Database]:
    """The databases from VERDICT_DATABASES (comma-separated ids from KNOWN_DATABASES)."""
    ids = [i.strip() for i in os.environ.get("VERDICT_DATABASES", DEFAULT_DATABASES).split(",") if i.strip()]
    out = []
    for db_id in dict.fromkeys(ids):
        if db_id not in KNOWN_DATABASES:
            continue  # unknown ids are skipped; /api/health shows which are offered
        name, about = KNOWN_DATABASES[db_id]
        if db_id == "olist":
            olist = os.environ.get("VERDICT_OLIST_PATH")
            path = Path(olist) if olist else data_root() / "olist" / "olist.sqlite"
        else:
            path = db_path(db_id)
        out.append(Database(db_id, name, path, "preloaded", description=about))
    return out


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
    #: True for the user's own model (Qwen, any version). False for outside
    #: models (Gemini and the like), which are only for the Model Arena.
    own: bool = True
    #: True for a model shown only in the Model Arena, never used for Ask
    #: (the base Qwen, kept to show what training changed).
    arena_only: bool = False
    #: name of the environment variable holding this model's API key, if any
    api_key_env: str = ""

    @property
    def role(self) -> str:
        """"own" (answers analysts), "base" (untrained Qwen, Arena only) or "outside"."""
        if not self.own:
            return "outside"
        return "base" if self.arena_only else "own"


#: Outside models reached through an OpenAI-style API. Each one is offered in
#: the Model Arena only when its API key is set.
#: id -> (label, key variable, model variable, default model, base url)
OUTSIDE_OPENAI_MODELS = {
    "chatgpt": ("ChatGPT (cloud)", "OPENAI_API_KEY", "OPENAI_MODEL", "gpt-4o-mini",
                "https://api.openai.com/v1"),
    "groq-llama": ("Llama 3.3 70B (Groq cloud)", "GROQ_API_KEY", "GROQ_MODEL",
                   "llama-3.3-70b-versatile", "https://api.groq.com/openai/v1"),
}


def default_models() -> list[ModelEntry]:
    """The trained Qwen (answers analysts), the base Qwen and outside models (Arena only)."""
    qwen_url = os.environ.get("VERDICT_QWEN_URL", "http://127.0.0.1:11434/v1")
    out = [
        ModelEntry(
            "qwen", "Qwen 1.5B (trained), private", "openai", True,
            base_url=qwen_url, model=os.environ.get("VERDICT_QWEN_MODEL", "verdict-qwen"),
        ),
    ]
    base = os.environ.get("VERDICT_QWEN_BASE_MODEL", "qwen2.5-coder:1.5b")
    if base.lower() != "off":
        out.append(ModelEntry(
            "qwen-base", "Qwen 1.5B base (not trained)", "openai", True,
            base_url=qwen_url, model=base, arena_only=True,
        ))
    out.append(ModelEntry(
        "gemini", "Gemini (cloud)", "gemini", False,
        model=os.environ.get("GEMINI_MODEL", ""), own=False,
    ))
    for mid, (label, key_env, model_env, default_model, url) in OUTSIDE_OPENAI_MODELS.items():
        if os.environ.get(key_env):
            out.append(ModelEntry(
                mid, label, "openai", False, base_url=url,
                model=os.environ.get(model_env, default_model), own=False, api_key_env=key_env,
            ))
    return out


def load_models() -> list[ModelEntry]:
    """Models from VERDICT_MODELS_FILE if set, else the two defaults.

    File format: a JSON list of {"id", "label", "kind", "private", "base_url", "model", "own",
    "arena_only", "api_key_env"}. "own" defaults to true for kind "openai" (vLLM or Ollama
    serving Qwen) and false for kind "gemini".
    """
    path = os.environ.get("VERDICT_MODELS_FILE")
    if not path:
        return default_models()
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        ModelEntry(
            m["id"], m.get("label", m["id"]), m["kind"], bool(m.get("private", m["kind"] != "gemini")),
            base_url=m.get("base_url", ""), model=m.get("model", ""),
            own=bool(m.get("own", m["kind"] != "gemini")),
            arena_only=bool(m.get("arena_only", False)), api_key_env=m.get("api_key_env", ""),
        )
        for m in raw
    ]


def make_writer(m: ModelEntry) -> SQLWriter:
    if m.kind == "openai":
        key = os.environ.get(m.api_key_env) if m.api_key_env else None
        return OpenAICompatWriter(m.base_url, m.model, api_key=key)
    if m.kind == "gemini":
        return GeminiWriter(model=m.model or None)
    if m.kind == "fixed":
        return FixedWriter(list(m.replies))
    raise ValueError(f"unknown model kind: {m.kind}")


def model_reachable(m: ModelEntry) -> bool:
    if m.kind == "openai":
        return make_writer(m).reachable()
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
    # accounts and credits
    signup_credits: int = DEFAULT_SIGNUP_CREDITS
    price_ask: int = DEFAULT_PRICE_ASK
    price_arena_outside_model: int = DEFAULT_PRICE_ARENA
    admin_email: str | None = None
    admin_password: str | None = None
    auth_rate_per_minute: int = DEFAULT_AUTH_RATE
    #: repeated questions answered from the cache (VERDICT_CACHE=off turns it off)
    cache_enabled: bool = True
    # limits for a public server
    uploads_enabled: bool = True
    upload_ttl_hours: float = 0
    ask_timeout_s: float = DEFAULT_ASK_TIMEOUT_S
    ask_rate_per_minute: int = DEFAULT_ASK_RATE
    max_concurrent_asks: int = DEFAULT_MAX_CONCURRENT_ASKS
    queue_wait_s: float = DEFAULT_QUEUE_WAIT_S
    # live Model Arena
    arena_outside_enabled: bool = True
    arena_outside_attempts: int = DEFAULT_ATTEMPTS

    def __post_init__(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        from verdict.api.auth import RateLimiter

        self.ask_limiter = RateLimiter(
            self.ask_rate_per_minute,
            message="You are asking questions faster than this server allows. Wait a minute.",
        )
        self.ask_slots = threading.BoundedSemaphore(max(1, self.max_concurrent_asks))
        # Enough threads for running asks plus ones stopped by the time limit
        # that are still finishing.
        self.ask_pool = ThreadPoolExecutor(max_workers=max(1, self.max_concurrent_asks) * 4)
    # Credits held by asks that are still running, per user. See reserve_credits.
    _reserved: dict[str, int] = field(default_factory=dict)
    _reserve_lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def from_env(cls) -> "AppState":
        try:
            from dotenv import load_dotenv

            load_dotenv(REPO_ROOT / ".env")   # values already in the shell win
        except ImportError:
            pass
        env = os.environ.get
        return cls(
            store=Store(),
            models=load_models(),
            preloaded=preloaded_databases(),
            attempts=int(env("VERDICT_ATTEMPTS", DEFAULT_ATTEMPTS)),
            signup_credits=int(env("VERDICT_SIGNUP_CREDITS", DEFAULT_SIGNUP_CREDITS)),
            price_ask=int(env("VERDICT_PRICE_ASK", DEFAULT_PRICE_ASK)),
            price_arena_outside_model=int(env("VERDICT_PRICE_ARENA_OUTSIDE_MODEL", DEFAULT_PRICE_ARENA)),
            admin_email=env("VERDICT_ADMIN_EMAIL") or None,
            admin_password=env("VERDICT_ADMIN_PASSWORD") or None,
            auth_rate_per_minute=int(env("VERDICT_AUTH_RATE", DEFAULT_AUTH_RATE)),
            cache_enabled=_on(env("VERDICT_CACHE", "on")),
            uploads_enabled=_on(env("VERDICT_UPLOADS", "on")),
            upload_ttl_hours=float(env("VERDICT_UPLOAD_TTL_HOURS", 0)),
            ask_timeout_s=float(env("VERDICT_ASK_TIMEOUT_S", DEFAULT_ASK_TIMEOUT_S)),
            ask_rate_per_minute=int(env("VERDICT_ASK_RATE", DEFAULT_ASK_RATE)),
            max_concurrent_asks=int(env("VERDICT_MAX_CONCURRENT_ASKS", DEFAULT_MAX_CONCURRENT_ASKS)),
            queue_wait_s=float(env("VERDICT_QUEUE_WAIT_S", DEFAULT_QUEUE_WAIT_S)),
            arena_outside_enabled=_on(env("VERDICT_ARENA_OUTSIDE", "on")),
            arena_outside_attempts=int(env("VERDICT_ARENA_OUTSIDE_ATTEMPTS", DEFAULT_ATTEMPTS)),
        )

    def prices(self) -> dict[str, int]:
        return {"ask": self.price_ask, "arena_outside_model": self.price_arena_outside_model}

    # credits held while an ask runs

    def reserve_credits(self, user_id: str, amount: int) -> bool:
        """Hold ``amount`` credits for a running ask. False if the balance is too low.

        The charge itself happens when the ask is saved (Store.save_ask_and_charge,
        which also refuses to go below 0). Holding the credits first means two
        asks sent at the same time cannot both start on a balance that only
        pays for one. The hold is in memory, which is right for the single
        server process Verdict runs as.
        """
        if amount <= 0:
            return True
        with self._reserve_lock:
            held = self._reserved.get(user_id, 0)
            if self.store.balance(user_id) - held < amount:
                return False
            self._reserved[user_id] = held + amount
            return True

    def release_credits(self, user_id: str, amount: int) -> None:
        if amount <= 0:
            return
        with self._reserve_lock:
            left = self._reserved.get(user_id, 0) - amount
            if left > 0:
                self._reserved[user_id] = left
            else:
                self._reserved.pop(user_id, None)

    # databases

    def databases(self, user: dict | None = None) -> list[Database]:
        """Preloaded databases plus the uploads ``user`` may see."""
        self.remove_old_uploads()
        ups = [
            Database(d["id"], d["name"], Path(d["path"]), d["source"], d.get("user_id"))
            for d in self.store.list_databases()
        ]
        return self.preloaded + [d for d in ups if d.visible_to(user)]

    def database(self, db_id: str, user: dict | None = None) -> Database | None:
        return next((d for d in self.databases(user) if d.id == db_id), None)

    def remove_old_uploads(self) -> None:
        """Delete uploads older than upload_ttl_hours (0 keeps them)."""
        if self.upload_ttl_hours <= 0:
            return
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=self.upload_ttl_hours)).isoformat(
            timespec="seconds")
        for d in self.store.uploads_older_than(cutoff):
            try:
                Path(d["path"]).unlink(missing_ok=True)
            except OSError:
                continue  # still open somewhere; try again next time
            self.store.delete_database(d["id"])

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

    # precomputed proof files from the evaluation step

    def results_file(self, name: str) -> dict | None:
        p = self.results_dir / name
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
