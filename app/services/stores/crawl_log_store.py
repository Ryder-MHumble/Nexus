"""Append-only crawl log storage — backed by Supabase SDK.

Falls back to local JSON files when the Supabase client is not initialised.

DB table: crawl_logs
  id BIGSERIAL PRIMARY KEY
  source_id VARCHAR(128) NOT NULL
  status VARCHAR(32) NOT NULL
  items_total INT DEFAULT 0
  items_new INT DEFAULT 0
  error_message TEXT
  started_at TIMESTAMPTZ
  finished_at TIMESTAMPTZ
  duration_seconds FLOAT

JSON fallback: data/logs/{source_id}/crawl_logs.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

LOGS_DIR = BASE_DIR / "data" / "logs"
MAX_LOGS_PER_SOURCE = 100


# ---------------------------------------------------------------------------
# JSON fallback helpers
# ---------------------------------------------------------------------------

def _log_file(source_id: str) -> Path:
    return LOGS_DIR / source_id / "crawl_logs.json"


def _load_logs(source_id: str) -> list[dict[str, Any]]:
    path = _log_file(source_id)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_logs(source_id: str, logs: list[dict[str, Any]]) -> None:
    path = _log_file(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2, default=str)


def _get_client():
    from app.db.client import get_client  # noqa: PLC0415
    return get_client()


# ---------------------------------------------------------------------------
# Public API  (all async — callers must await)
# ---------------------------------------------------------------------------

async def append_crawl_log(
    source_id: str,
    *,
    status: str,
    items_total: int = 0,
    items_new: int = 0,
    error_message: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    duration_seconds: float = 0.0,
) -> None:
    row: dict[str, Any] = {
        "source_id": source_id,
        "status": status,
        "items_total": items_total,
        "items_new": items_new,
        "error_message": error_message,
        "started_at": started_at.isoformat() if started_at else None,
        "finished_at": finished_at.isoformat() if finished_at else None,
        "duration_seconds": duration_seconds,
    }
    try:
        client = _get_client()
        await client.table("crawl_logs").insert(row).execute()
        return
    except RuntimeError:
        pass
    except Exception as exc:
        logger.warning("append_crawl_log DB failed, using JSON: %s", exc)

    # JSON fallback
    logs = _load_logs(source_id)
    row["created_at"] = datetime.now(timezone.utc).isoformat()
    logs.append(row)
    if len(logs) > MAX_LOGS_PER_SOURCE:
        logs = logs[-MAX_LOGS_PER_SOURCE:]
    _save_logs(source_id, logs)


async def get_crawl_logs(
    source_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    try:
        client = _get_client()
        query = client.table("crawl_logs").select("*").order(
            "started_at", desc=True
        ).limit(limit)
        if source_id:
            query = query.eq("source_id", source_id)
        res = await query.execute()
        return res.data or []
    except RuntimeError:
        pass
    except Exception as exc:
        logger.warning("get_crawl_logs DB failed, using JSON: %s", exc)

    # JSON fallback
    if source_id:
        logs = _load_logs(source_id)
        logs.sort(key=lambda x: x.get("started_at") or "", reverse=True)
        return logs[:limit]

    all_logs: list[dict[str, Any]] = []
    if LOGS_DIR.exists():
        for source_dir in LOGS_DIR.iterdir():
            if source_dir.is_dir():
                all_logs.extend(_load_logs(source_dir.name))
    all_logs.sort(key=lambda x: x.get("started_at") or "", reverse=True)
    return all_logs[:limit]


async def get_recent_log_stats(hours: int = 24) -> dict[str, int]:
    """Get crawl and article counts from the last N hours."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        client = _get_client()
        res = await client.table("crawl_logs").select(
            "items_new"
        ).gte("started_at", cutoff).execute()
        rows = res.data or []
        return {
            "crawls": len(rows),
            "new_articles": sum(r.get("items_new", 0) or 0 for r in rows),
        }
    except RuntimeError:
        pass
    except Exception as exc:
        logger.warning("get_recent_log_stats DB failed, using JSON: %s", exc)

    # JSON fallback
    total_crawls = 0
    total_new_articles = 0
    if not LOGS_DIR.exists():
        return {"crawls": 0, "new_articles": 0}
    for source_dir in LOGS_DIR.iterdir():
        if not source_dir.is_dir():
            continue
        for log in _load_logs(source_dir.name):
            started = log.get("started_at") or ""
            if started >= cutoff:
                total_crawls += 1
                total_new_articles += log.get("items_new", 0)
    return {"crawls": total_crawls, "new_articles": total_new_articles}
