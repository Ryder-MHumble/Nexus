"""Persist crawl results to database (DB-only storage path)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import BASE_DIR
from app.crawlers.utils.dedup import compute_url_hash

logger = logging.getLogger(__name__)

DATA_DIR = BASE_DIR / "data" / "raw"

LATEST_FILENAME = "latest.json"

async def save_crawl_result_json(
    result: Any,
    source_config: dict[str, Any],
) -> None:
    """Persist crawl items to DB.

    NOTE: Function name kept for backward compatibility with existing call-sites.
    No local JSON files are written.
    """
    all_items = getattr(result, "items_all", None) or result.items
    if not all_items:
        return None

    dimension = source_config.get("dimension", "unknown")
    group = source_config.get("group")
    source_id = source_config.get("id", "unknown")

    # DB-only path
    existing_hashes: set[str] = set()
    try:
        from app.db.client import get_client  # noqa: PLC0415

        client = get_client()
        res = await client.table("articles").select("url_hash").eq("source_id", source_id).execute()
        existing_hashes = {row["url_hash"] for row in (res.data or [])}
    except RuntimeError:
        logger.warning("DB client not initialized; skip persisting source %s", source_id)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB fetch existing hashes failed for %s, skip persisting: %s", source_id, exc)
        return None

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    try:
        from app.db.client import get_client  # noqa: PLC0415

        client = get_client()
        upsert_data = []
        seen_hashes: set[str] = set()
        new_count = 0
        for item in all_items:
            url_hash = compute_url_hash(item.url)
            # Guard against duplicate hashes in the same batch, which can
            # break a single Postgres upsert statement.
            if url_hash in seen_hashes:
                continue
            seen_hashes.add(url_hash)
            is_new = url_hash not in existing_hashes
            if is_new:
                new_count += 1
            pub_at = item.published_at.isoformat() if item.published_at else None
            upsert_data.append({
                "url_hash": url_hash,
                "source_id": source_id,
                "dimension": dimension,
                "group_name": group,
                "url": item.url,
                "title": item.title,
                "author": item.author,
                "published_at": pub_at,
                "content": item.content,
                "content_html": item.content_html,
                "content_hash": item.content_hash,
                "tags": item.tags or [],
                "extra": item.extra or {},
                "crawled_at": now_iso,
                "is_new": is_new,
            })
        if upsert_data:
            await client.table("articles").upsert(
                upsert_data,
                on_conflict="url_hash",
                ignore_duplicates=False,
            ).execute()
        logger.info(
            "Upserted %d items (%d new) to DB for source %s",
            len(upsert_data),
            new_count,
            source_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB upsert failed for %s: %s", source_id, exc)

    return None
