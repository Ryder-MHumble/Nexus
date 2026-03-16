"""Page snapshot storage — backed by Supabase SDK.

Falls back to local JSON files when the Supabase client is not initialised.

DB table: snapshots
  source_id VARCHAR(128) PRIMARY KEY
  data JSONB DEFAULT '{}'
  updated_at TIMESTAMPTZ

JSON fallback: data/state/snapshots/{source_id}.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

SNAPSHOTS_DIR = BASE_DIR / "data" / "state" / "snapshots"


# ---------------------------------------------------------------------------
# JSON fallback helpers
# ---------------------------------------------------------------------------

def _snapshot_path(source_id: str):
    return SNAPSHOTS_DIR / f"{source_id}.json"


def _load_snapshot_json(source_id: str) -> dict[str, Any] | None:
    path = _snapshot_path(source_id)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_snapshot_json(source_id: str, data: dict[str, Any]) -> None:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _snapshot_path(source_id)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _get_client():
    from app.db.client import get_client  # noqa: PLC0415
    return get_client()


# ---------------------------------------------------------------------------
# Public API  (all async — callers must await)
# ---------------------------------------------------------------------------

async def get_last_snapshot(source_id: str) -> dict[str, Any] | None:
    try:
        client = _get_client()
        res = await client.table("snapshots").select("data").eq("source_id", source_id).execute()
        if res.data:
            return res.data[0].get("data")
        return None
    except RuntimeError:
        pass
    except Exception as exc:
        logger.warning("get_last_snapshot DB failed, using JSON: %s", exc)

    return _load_snapshot_json(source_id)


async def save_snapshot(
    source_id: str,
    content_hash: str,
    content_text: str,
    diff_text: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "content_hash": content_hash,
        "content_text": content_text,
        "diff_text": diff_text,
        "captured_at": now,
    }
    try:
        client = _get_client()
        await client.table("snapshots").upsert(
            {"source_id": source_id, "data": payload, "updated_at": now},
            on_conflict="source_id",
        ).execute()
        return
    except RuntimeError:
        pass
    except Exception as exc:
        logger.warning("save_snapshot DB failed, using JSON: %s", exc)

    _save_snapshot_json(source_id, {"source_id": source_id, **payload})
