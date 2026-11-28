"""GET /api/admin/stats: how the service is used and how it performs.

For the provider only. Every question run (asks and Arena runs, answered,
from the cache, or failed) is written to the usage log in the app database;
this page sums it up, next to the review queue and the machine's load.

Times are in milliseconds. "model" time is waiting for the model; the rest of
a fresh answer's time is running the SQL and the checks. Averages and p95 use
fresh answers only, because a cache hit takes no time. Days are UTC days.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request

from verdict.api.auth import admin_user
from verdict.api.deps import state

router = APIRouter()
log = logging.getLogger("verdict.api")

LEVELS = ("trusted", "review", "reject")
OUTCOMES = ("ok", "busy", "timeout", "model_down", "error")
DAYS_SHOWN = 14
RECENT_FAILURES = 10


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    v = sorted(values)
    return v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))]


def _avg(values: list[int]) -> int | None:
    return int(sum(values) / len(values)) if values else None


def summarize(rows: list[dict]) -> dict:
    """Totals for one stretch of time."""
    fresh = [r for r in rows if r["outcome"] == "ok" and not r["cache_hit"]]
    outcomes = Counter(r["outcome"] for r in rows)
    levels = Counter(r["level"] for r in rows if r["outcome"] == "ok")
    return {
        "runs": len(rows),
        "asks": sum(1 for r in rows if r["kind"] == "ask"),
        "arena_runs": sum(1 for r in rows if r["kind"] == "arena"),
        "answered": outcomes["ok"],
        "from_cache": sum(1 for r in rows if r["outcome"] == "ok" and r["cache_hit"]),
        "failed": {o: outcomes[o] for o in OUTCOMES if o != "ok"},
        "levels": {lv: levels[lv] for lv in LEVELS},
        "avg_ms": _avg([r["total_ms"] for r in fresh if r["total_ms"] is not None]),
        "p95_ms": _p95([r["total_ms"] for r in fresh if r["total_ms"] is not None]),
        "avg_model_ms": _avg([r["model_ms"] for r in fresh if r["model_ms"] is not None]),
        "prompt_tokens": sum(r["prompt_tokens"] or 0 for r in rows),
        "completion_tokens": sum(r["completion_tokens"] or 0 for r in rows),
        "active_users": len({r["user_id"] for r in rows if r["user_id"]}),
    }


def per_day(rows: list[dict], today: datetime) -> list[dict]:
    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_day[r["created_at"][:10]].append(r)
    out = []
    for i in range(DAYS_SHOWN - 1, -1, -1):
        day = (today - timedelta(days=i)).date().isoformat()
        d = by_day.get(day, [])
        fresh = [r["total_ms"] for r in d if r["outcome"] == "ok" and not r["cache_hit"] and r["total_ms"] is not None]
        out.append({
            "day": day, "runs": len(d), "answered": sum(1 for r in d if r["outcome"] == "ok"),
            "failed": sum(1 for r in d if r["outcome"] != "ok"),
            "avg_ms": _avg(fresh), "p95_ms": _p95(fresh),
        })
    return out


def by_model(rows: list[dict], labels: dict[str, str]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["model"] or "?"].append(r)
    out = []
    for model_id, rs in sorted(groups.items()):
        s = summarize(rs)
        out.append({
            "model": model_id, "label": labels.get(model_id, model_id), "runs": s["runs"],
            "answered": s["answered"], "failed": sum(s["failed"].values()),
            "avg_ms": s["avg_ms"], "p95_ms": s["p95_ms"],
            "prompt_tokens": s["prompt_tokens"], "completion_tokens": s["completion_tokens"],
        })
    return out


def machine(app_db_path) -> dict:
    """CPU, memory, disk and GPU. A figure that cannot be read is null."""
    out: dict = {"cpu_count": os.cpu_count(), "cpu_percent": None, "load_avg": None,
                 "ram_total_mb": None, "ram_used_mb": None, "ram_percent": None,
                 "disk_total_gb": None, "disk_free_gb": None, "app_db_mb": None, "gpus": []}
    try:
        import psutil

        out["cpu_percent"] = psutil.cpu_percent(interval=0.2)
        vm = psutil.virtual_memory()
        out.update(ram_total_mb=vm.total // 2**20, ram_used_mb=(vm.total - vm.available) // 2**20,
                   ram_percent=vm.percent)
    except Exception:
        pass
    try:
        out["load_avg"] = [round(x, 2) for x in os.getloadavg()]
    except (AttributeError, OSError):
        pass  # not on Windows
    try:
        du = shutil.disk_usage(app_db_path.parent)
        out.update(disk_total_gb=round(du.total / 2**30, 1), disk_free_gb=round(du.free / 2**30, 1))
        out["app_db_mb"] = round(app_db_path.stat().st_size / 2**20, 2)
    except OSError:
        pass
    if shutil.which("nvidia-smi"):
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            for line in res.stdout.strip().splitlines():
                name, util, used, total = [x.strip() for x in line.split(",")]
                out["gpus"].append({"name": name, "util_percent": int(util),
                                    "mem_used_mb": int(used), "mem_total_mb": int(total)})
        except Exception:
            log.exception("nvidia-smi failed")
    return out


@router.get("/admin/stats")
def stats(request: Request, _: dict = Depends(admin_user)) -> dict:
    s = state(request)
    now = datetime.now(timezone.utc)
    rows = s.store.run_log()
    today = now.date().isoformat()
    week_ago = (now - timedelta(days=7)).isoformat(timespec="seconds")
    days_ago = (now - timedelta(days=DAYS_SHOWN)).isoformat(timespec="seconds")
    counts = s.store.stats_counts()
    labels = {m.id: m.label for m in s.models}
    failures = [r for r in rows if r["outcome"] != "ok"][-RECENT_FAILURES:]
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "totals": {
            "today": summarize([r for r in rows if r["created_at"][:10] == today]),
            "last_7_days": summarize([r for r in rows if r["created_at"] >= week_ago]),
            "all_time": summarize(rows),
        },
        "per_day": per_day([r for r in rows if r["created_at"] >= days_ago], now),
        "by_model": by_model(rows, labels),
        "recent_failures": [
            {k: r[k] for k in ("created_at", "kind", "database_id", "model", "outcome", "total_ms")}
            for r in reversed(failures)
        ],
        "users": {"total": counts["users"],
                  "active_7_days": summarize([r for r in rows if r["created_at"] >= week_ago])["active_users"]},
        "review": {"open": counts["review_open"], "resolved": counts["review_done"],
                   "flagged_trusted": counts["flagged_trusted"]},
        "settings": {"attempts": s.attempts, "max_concurrent_asks": s.max_concurrent_asks,
                     "ask_timeout_s": s.ask_timeout_s, "cache": s.cache_enabled},
        "machine": machine(s.store.path),
    }
