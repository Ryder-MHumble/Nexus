"""Manage mutable source runtime state — backed by Supabase SDK.

Falls back to the original local JSON file when the Supabase client is not
initialised (e.g. during unit-tests or when SUPABASE_DB_URL is empty).

DB table: source_states
  source_id VARCHAR(128) PRIMARY KEY
  last_crawl_at TIMESTAMPTZ
  last_success_at TIMESTAMPTZ
  consecutive_failures SMALLINT DEFAULT 0
  is_enabled_override BOOLEAN  -- NULL = no override
  updated_at TIMESTAMPTZ

State file (fallback): data/state/source_state.json
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

STATE_DIR = BASE_DIR / "data" / "state"
STATE_FILE = STATE_DIR / "source_state.json"

_lock = Lock()  # used only for JSON fallback path
DB_TIMEOUT_SECONDS = 2.0


# ---------------------------------------------------------------------------
# JSON fallback helpers
# ---------------------------------------------------------------------------

def _load_state() -> dict[str, dict[str, Any]]:
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupted source_state.json, starting fresh")
        return {}


def _save_state(state: dict[str, dict[str, Any]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(STATE_FILE)


def _get_client():
    from app.db.client import get_client  # noqa: PLC0415
    return get_client()


# ---------------------------------------------------------------------------
# Public API  (all async — callers must await)
# ---------------------------------------------------------------------------

async def get_source_state(source_id: str) -> dict[str, Any]:
    try:
        client = _get_client()
        res = await asyncio.wait_for(
            client.table("source_states").select("*").eq("source_id", source_id).execute(),
            timeout=DB_TIMEOUT_SECONDS,
        )
        if res.data:
            return res.data[0]
        return {}
    except RuntimeError:
        return _load_state().get(source_id, {})
    except Exception as exc:
        logger.warning("get_source_state DB failed, using JSON: %s", exc)
        return _load_state().get(source_id, {})


async def get_all_source_states() -> dict[str, dict[str, Any]]:
    try:
        client = _get_client()
        res = await asyncio.wait_for(
            client.table("source_states").select("*").execute(),
            timeout=DB_TIMEOUT_SECONDS,
        )
        return {row["source_id"]: row for row in (res.data or [])}
    except RuntimeError:
        return _load_state()
    except Exception as exc:
        logger.warning("get_all_source_states DB failed, using JSON: %s", exc)
        return _load_state()


async def update_source_state(
    source_id: str,
    *,
    last_crawl_at: datetime | None = None,
    last_success_at: datetime | None = None,
    consecutive_failures: int | None = None,
    reset_failures: bool = False,
) -> None:
    now = datetime.now(timezone.utc).isoformat()

    try:
        client = _get_client()

        # Read current failures to increment if needed
        res = await asyncio.wait_for(
            client.table("source_states").select("consecutive_failures").eq(
                "source_id", source_id
            ).execute(),
            timeout=DB_TIMEOUT_SECONDS,
        )
        current_failures: int = 0
        if res.data:
            current_failures = res.data[0].get("consecutive_failures") or 0

        if reset_failures:
            new_failures = 0
        elif consecutive_failures is not None:
            new_failures = consecutive_failures
        else:
            new_failures = current_failures + 1

        row: dict[str, Any] = {
            "source_id": source_id,
            "consecutive_failures": new_failures,
            "updated_at": now,
        }
        if last_crawl_at is not None:
            row["last_crawl_at"] = last_crawl_at.isoformat()
        if last_success_at is not None:
            row["last_success_at"] = last_success_at.isoformat()

        await asyncio.wait_for(
            client.table("source_states").upsert(row, on_conflict="source_id").execute(),
            timeout=DB_TIMEOUT_SECONDS,
        )
        return
    except RuntimeError:
        pass
    except Exception as exc:
        logger.warning("update_source_state DB failed, using JSON: %s", exc)

    # JSON fallback
    with _lock:
        state = _load_state()
        entry = state.setdefault(source_id, {})
        if last_crawl_at:
            entry["last_crawl_at"] = last_crawl_at.isoformat()
        if last_success_at:
            entry["last_success_at"] = last_success_at.isoformat()
        if reset_failures:
            entry["consecutive_failures"] = 0
        elif consecutive_failures is not None:
            entry["consecutive_failures"] = consecutive_failures
        else:
            entry["consecutive_failures"] = entry.get("consecutive_failures", 0) + 1
        _save_state(state)


async def set_enabled_override(source_id: str, is_enabled: bool) -> None:
    try:
        client = _get_client()
        row = {
            "source_id": source_id,
            "is_enabled_override": is_enabled,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await asyncio.wait_for(
            client.table("source_states").upsert(row, on_conflict="source_id").execute(),
            timeout=DB_TIMEOUT_SECONDS,
        )
        return
    except RuntimeError:
        pass
    except Exception as exc:
        logger.warning("set_enabled_override DB failed, using JSON: %s", exc)

    with _lock:
        state = _load_state()
        entry = state.setdefault(source_id, {})
        entry["is_enabled_override"] = is_enabled
        _save_state(state)


async def get_enabled_override(source_id: str) -> bool | None:
    try:
        client = _get_client()
        res = await asyncio.wait_for(
            client.table("source_states").select("is_enabled_override").eq(
                "source_id", source_id
            ).execute(),
            timeout=DB_TIMEOUT_SECONDS,
        )
        if res.data:
            return res.data[0].get("is_enabled_override")
        return None
    except RuntimeError:
        state = _load_state()
        return state.get(source_id, {}).get("is_enabled_override")
    except Exception as exc:
        logger.warning("get_enabled_override DB failed, using JSON: %s", exc)
        state = _load_state()
        return state.get(source_id, {}).get("is_enabled_override")
