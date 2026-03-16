"""Raw data loading and annotation merging for scholar service."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.services.stores import scholar_annotation_store as annotation_store

logger = logging.getLogger(__name__)

SCHOLARS_FILE = Path("data/scholars/scholars.json")

_RELATION_FIELDS = [
    "is_advisor_committee",
    "adjunct_supervisor",
    "supervised_students",
    "joint_research_projects",
    "joint_management_roles",
    "academic_exchange_records",
    "is_potential_recruit",
    "institute_relation_notes",
    "relation_updated_by",
    "relation_updated_at",
]

_ACHIEVEMENT_FIELDS = [
    "representative_publications",
    "patents",
    "awards",
    "h_index",
    "citations_count",
    "publications_count",
]


async def _load_all_raw_async() -> list[dict[str, Any]]:
    """Load all scholar records from DB (async version).

    Uses paginated fetching to bypass Supabase's default 1000-row limit.
    """
    try:
        from app.db.client import get_client  # noqa: PLC0415
        client = get_client()

        batch_size = 1000
        all_rows: list[dict[str, Any]] = []
        offset = 0

        while True:
            res = await (
                client.table("scholars")
                .select("*")
                .range(offset, offset + batch_size - 1)
                .execute()
            )
            batch = res.data or []
            all_rows.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size

        if all_rows:
            # Normalize DB rows: map id → url_hash for compatibility
            for r in all_rows:
                if "url_hash" not in r:
                    r["url_hash"] = r.get("id", "")
                if "url" not in r:
                    r["url"] = r.get("source_url", "")
            return all_rows
    except Exception as exc:
        logger.warning("DB _load_all_raw_async failed: %s", exc)

    return []


def _load_all_raw() -> list[dict[str, Any]]:
    """Load all scholar records — DB preferred, JSON fallback.

    Note: This sync version tries to use asyncio.run() which may fail
    in some contexts. Prefer using _load_all_raw_async() in async contexts.
    """
    try:
        import asyncio  # noqa: PLC0415
        # Try to run async version
        try:
            return asyncio.run(_load_all_raw_async())
        except RuntimeError:
            # Already in event loop, try to get existing loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't use run_until_complete in running loop
                raise RuntimeError("Cannot call sync _load_all_raw from async context")
            return loop.run_until_complete(_load_all_raw_async())
    except Exception as exc:
        logger.warning("DB _load_all_raw failed, using JSON: %s", exc)

    if not SCHOLARS_FILE.exists():
        return []
    try:
        with open(SCHOLARS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load scholars file: %s", exc)
        return []
    return data.get("scholars", [])


def _merge_annotation(item: dict[str, Any], ann: dict[str, Any]) -> dict[str, Any]:
    """Overlay user annotation onto a scholar item (in-place, returns item)."""
    for field in _RELATION_FIELDS:
        if field in ann:
            item[field] = ann[field]
    for field in _ACHIEVEMENT_FIELDS:
        if field in ann:
            item[field] = ann[field]
    user_updates = ann.get("user_updates", [])
    if user_updates:
        existing = list(item.get("recent_updates") or [])
        item["recent_updates"] = existing + user_updates
    return item


async def _load_all_with_annotations_async() -> list[dict[str, Any]]:
    """Load scholar data and merge user annotations (async version)."""
    items = await _load_all_raw_async()
    if not items:
        return items
    all_annotations = annotation_store._load()
    if not all_annotations:
        return items
    for item in items:
        url_hash = item.get("url_hash", "")
        if url_hash in all_annotations:
            _merge_annotation(item, all_annotations[url_hash])
    return items


def _load_all_with_annotations() -> list[dict[str, Any]]:
    """Load scholar data and merge user annotations."""
    items = _load_all_raw()
    if not items:
        return items
    all_annotations = annotation_store._load()
    if not all_annotations:
        return items
    for item in items:
        url_hash = item.get("url_hash", "")
        if url_hash in all_annotations:
            _merge_annotation(item, all_annotations[url_hash])
    return items


def _find_raw_file_by_hash(url_hash: str) -> tuple[Path, int] | None:
    """Locate the scholar record index for a given url_hash.

    Returns (SCHOLARS_FILE, item_index) or None if not found.
    """
    if not SCHOLARS_FILE.exists():
        return None
    try:
        with open(SCHOLARS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    for idx, scholar in enumerate(data.get("scholars", [])):
        if scholar.get("url_hash") == url_hash:
            return SCHOLARS_FILE, idx
    return None
