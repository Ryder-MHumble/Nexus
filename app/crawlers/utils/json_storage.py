"""Save crawl results to local JSON files and upsert to Supabase articles table."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import BASE_DIR
from app.crawlers.utils.dedup import compute_url_hash

logger = logging.getLogger(__name__)

DATA_DIR = BASE_DIR / "data" / "raw"

LATEST_FILENAME = "latest.json"


def build_source_dir(dimension: str, group: str | None, source_id: str) -> Path:
    """Build the directory path for a source's JSON data.

    Convention: data/raw/{dimension}/{group}/{source_id}/
    or data/raw/{dimension}/{source_id}/ if group is None.

    Special case: scholars dimension stores in data/scholars/ instead of data/raw/scholars/
    """
    # Special handling for scholars dimension (stored directly in data/scholars/)
    if dimension == "scholars":
        base_dir = BASE_DIR / "data" / "scholars"
    else:
        base_dir = DATA_DIR / dimension

    if group:
        return base_dir / group / source_id
    return base_dir / source_id


def _serialize_item(item: Any, *, is_new: bool) -> dict[str, Any]:
    """Convert a CrawledItem to a JSON-serializable dict with is_new flag."""
    return {
        "title": item.title,
        "url": item.url,
        "url_hash": compute_url_hash(item.url),
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "author": item.author,
        "content": item.content,
        "content_html": item.content_html,
        "content_hash": item.content_hash,
        "source_id": item.source_id,
        "dimension": item.dimension,
        "tags": item.tags,
        "extra": item.extra,
        "is_new": is_new,
    }


def _load_previous_hashes(file_path: Path) -> tuple[set[str], str | None]:
    """Load url_hash set and crawled_at from previous latest.json.

    Returns (set_of_url_hashes, previous_crawled_at_str).
    """
    if not file_path.exists():
        return set(), None
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        hashes = {
            item["url_hash"]
            for item in data.get("items", [])
            if item.get("url_hash")
        }
        return hashes, data.get("crawled_at")
    except (json.JSONDecodeError, KeyError, OSError):
        logger.warning("Could not read previous %s, treating as first crawl", file_path)
        return set(), None


def _parse_published_at(value: str | None) -> datetime | None:
    """Parse an ISO datetime string to a timezone-aware datetime object."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


async def save_crawl_result_json(
    result: Any,
    source_config: dict[str, Any],
) -> Path | None:
    """Save all crawl result items to latest.json and upsert to Supabase.

    Output path: data/raw/{dimension}/{group}/{source_id}/latest.json

    All items from the crawl are saved (pre-dedup). Each item is annotated
    with is_new=true/false by comparing against existing DB records (or
    previous latest.json as fallback).

    Returns the path to the written file, or None if no items.
    """
    all_items = getattr(result, "items_all", None) or result.items
    if not all_items:
        return None

    dimension = source_config.get("dimension", "unknown")
    group = source_config.get("group")
    source_id = source_config.get("id", "unknown")

    output_dir = build_source_dir(dimension, group, source_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / LATEST_FILENAME

    # Try DB path first; fall back to JSON-based is_new detection
    db_available = False
    existing_hashes: set[str] = set()
    try:
        from app.db.client import get_client  # noqa: PLC0415

        client = get_client()  # raises RuntimeError if not initialized
        res = await client.table("articles").select("url_hash").eq("source_id", source_id).execute()
        existing_hashes = {row["url_hash"] for row in (res.data or [])}
        db_available = True
    except RuntimeError:
        # Client not initialized — fall back to JSON-based detection
        prev_hashes, prev_crawled_at_json = _load_previous_hashes(output_file)
        existing_hashes = prev_hashes
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB fetch existing hashes failed for %s: %s", source_id, exc)
        prev_hashes, prev_crawled_at_json = _load_previous_hashes(output_file)
        existing_hashes = prev_hashes

    # Also load previous crawled_at for JSON output
    prev_hashes_file, prev_crawled_at_json = _load_previous_hashes(output_file)

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    serialized_items = []
    new_count = 0

    for item in all_items:
        url_hash = compute_url_hash(item.url)
        is_new = url_hash not in existing_hashes
        if is_new:
            new_count += 1
        serialized = _serialize_item(item, is_new=is_new)
        serialized_items.append(serialized)

    # Write JSON file (always — serves as cache/backup)
    output_data = {
        "source_id": source_id,
        "dimension": dimension,
        "group": group,
        "source_name": source_config.get("name", source_id),
        "crawled_at": now_iso,
        "previous_crawled_at": prev_crawled_at_json,
        "item_count": len(serialized_items),
        "new_item_count": new_count,
        "items": serialized_items,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    logger.info(
        "Saved %d items (%d new) to %s",
        len(serialized_items),
        new_count,
        output_file,
    )

    # Upsert to Supabase
    if db_available and serialized_items:
        try:
            from app.db.client import get_client  # noqa: PLC0415

            client = get_client()
            upsert_data = []
            for item, s in zip(all_items, serialized_items):
                url_hash = compute_url_hash(item.url)
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
                    "is_new": s.get("is_new", False),
                })
            await client.table("articles").upsert(
                upsert_data,
                on_conflict="url_hash",
                ignore_duplicates=False,
            ).execute()
            logger.info("Upserted %d articles to DB for source %s", len(upsert_data), source_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DB upsert failed for %s, JSON file preserved: %s", source_id, exc)

    return output_file
