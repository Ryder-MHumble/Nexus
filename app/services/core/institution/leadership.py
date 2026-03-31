"""University leadership data service.

Provides:
1) Monthly full-crawl sync into dedicated leadership table
2) Current/history-compatible query APIs for institution pages
3) Manual institution people configuration from scholar DB
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import BASE_DIR
from app.crawlers.base import CrawledItem
from app.crawlers.registry import CrawlerRegistry
from app.crawlers.utils.json_storage import save_crawl_result_json
from app.db.pool import get_pool
from app.scheduler.manager import load_all_source_configs
from app.services.core.institution.detail_query import get_institution_detail
from app.services.core.institution.storage import (
    fetch_all_institutions,
    fetch_institution_by_id,
    upsert_institution,
)

logger = logging.getLogger(__name__)

_CURRENT_TABLE = "university_leadership_current"

_TABLES_READY = False
_TABLES_LOCK = asyncio.Lock()

_ROLE_PRIORITY = {
    "党委书记": 5,
    "校长": 4,
    "常务副校长": 3,
    "副校长": 2,
}


def _extract_university_name(source_name: str, source_id: str) -> str:
    if source_name:
        return source_name.split("-", 1)[0].strip() or source_id
    return source_id


def _normalize_str(value: Any) -> str:
    return str(value or "").strip()


def _ensure_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _json_load_maybe(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        token = _normalize_str(value)
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def _leader_sort_key(leader: dict[str, Any]) -> tuple[int, str, str]:
    role = _normalize_str(leader.get("role"))
    name = _normalize_str(leader.get("name"))
    return (_ROLE_PRIORITY.get(role, 0), role, name)


def _normalize_leader_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = _normalize_str(raw.get("name"))
    role = _normalize_str(raw.get("role"))
    if not name or not role:
        return None

    return {
        "name": name,
        "role": role,
        "profile_url": _normalize_str(raw.get("profile_url")) or None,
        "avatar_url": _normalize_str(raw.get("avatar_url")) or None,
        "bio": _normalize_str(raw.get("bio")) or None,
        "intro_lines": _ensure_str_list(raw.get("intro_lines")),
        "source_page_url": _normalize_str(raw.get("source_page_url")) or None,
        "detail_name_text": _normalize_str(raw.get("detail_name_text")) or None,
    }


def _extract_leader_from_crawled_item(item: CrawledItem) -> dict[str, Any] | None:
    extra = item.extra or {}
    raw = {
        "name": extra.get("name") or item.author,
        "role": extra.get("position") or extra.get("role"),
        "profile_url": extra.get("profile_url"),
        "avatar_url": extra.get("avatar_url"),
        "bio": extra.get("personal_intro") or item.content,
        "intro_lines": extra.get("intro_lines"),
        "source_page_url": extra.get("source_page_url"),
        "detail_name_text": extra.get("detail_name_text"),
    }
    return _normalize_leader_entry(raw)


def _normalize_leaders(leaders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for leader in leaders:
        normalized = _normalize_leader_entry(leader)
        if not normalized:
            continue
        key = (
            _normalize_str(normalized.get("name")),
            _normalize_str(normalized.get("role")),
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = normalized
            continue
        # Keep richer record when duplicate appears.
        if len(_normalize_str(normalized.get("bio"))) > len(_normalize_str(existing.get("bio"))):
            deduped[key] = normalized

    ordered = list(deduped.values())
    ordered.sort(key=_leader_sort_key, reverse=True)
    return ordered


def _compute_role_counts(leaders: list[dict[str, Any]]) -> dict[str, int]:
    role_counts: dict[str, int] = {}
    for leader in leaders:
        role = _normalize_str(leader.get("role"))
        if not role:
            continue
        role_counts[role] = role_counts.get(role, 0) + 1
    return role_counts


def _compute_data_hash(leaders: list[dict[str, Any]], role_counts: dict[str, int]) -> str:
    payload = {
        "leaders": leaders,
        "role_counts": role_counts,
        "leader_count": len(leaders),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _compute_change_summary(
    previous_leaders: list[dict[str, Any]],
    current_leaders: list[dict[str, Any]],
) -> dict[str, Any]:
    prev_by_name = {
        _normalize_str(item.get("name")): _normalize_str(item.get("role"))
        for item in previous_leaders
        if _normalize_str(item.get("name"))
    }
    cur_by_name = {
        _normalize_str(item.get("name")): _normalize_str(item.get("role"))
        for item in current_leaders
        if _normalize_str(item.get("name"))
    }

    added = sorted([name for name in cur_by_name if name and name not in prev_by_name])
    removed = sorted([name for name in prev_by_name if name and name not in cur_by_name])

    role_changed = []
    for name in sorted(set(prev_by_name) & set(cur_by_name)):
        if prev_by_name[name] != cur_by_name[name]:
            role_changed.append(
                {
                    "name": name,
                    "from_role": prev_by_name[name],
                    "to_role": cur_by_name[name],
                }
            )

    changed = bool(added or removed or role_changed)

    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "role_changed": role_changed,
        "added_count": len(added),
        "removed_count": len(removed),
        "role_changed_count": len(role_changed),
    }


async def _ensure_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return

    async with _TABLES_LOCK:
        if _TABLES_READY:
            return

        pool = get_pool()

        await pool.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_CURRENT_TABLE} (
              source_id VARCHAR(128) PRIMARY KEY,
              institution_id VARCHAR(128) NULL,
              university_name VARCHAR(256) NOT NULL,
              source_name VARCHAR(256) NULL,
              source_url TEXT NULL,
              dimension VARCHAR(64) NULL,
              group_name VARCHAR(128) NULL,
              crawled_at TIMESTAMPTZ NOT NULL,
              previous_crawled_at TIMESTAMPTZ NULL,
              leader_count INTEGER NOT NULL DEFAULT 0,
              new_leader_count INTEGER NOT NULL DEFAULT 0,
              role_counts JSONB NOT NULL DEFAULT '{{}}'::jsonb,
              leaders JSONB NOT NULL DEFAULT '[]'::jsonb,
              data_hash VARCHAR(64) NOT NULL,
              change_version INTEGER NOT NULL DEFAULT 1,
              last_changed_at TIMESTAMPTZ NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await pool.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_CURRENT_TABLE}_institution_id ON {_CURRENT_TABLE}(institution_id)"
        )
        await pool.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_CURRENT_TABLE}_university_name ON {_CURRENT_TABLE}(university_name)"
        )
        await pool.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_CURRENT_TABLE}_crawled_at ON {_CURRENT_TABLE}(crawled_at DESC)"
        )

        _TABLES_READY = True


async def _load_institution_name_map() -> dict[str, str]:
    records = await fetch_all_institutions()
    mapping: dict[str, str] = {}
    for row in records:
        if row.get("entity_type") != "organization":
            continue
        name = _normalize_str(row.get("name"))
        row_id = _normalize_str(row.get("id"))
        if name and row_id:
            mapping[name] = row_id
    return mapping


def _build_payload_from_crawl(
    source_config: dict[str, Any],
    raw_items: list[CrawledItem],
    *,
    crawled_at: datetime,
    institution_name_map: dict[str, str],
) -> dict[str, Any]:
    source_id = _normalize_str(source_config.get("id"))
    source_name = _normalize_str(source_config.get("name"))
    university_name = _extract_university_name(source_name, source_id)

    leaders = _normalize_leaders(
        [
            leader
            for item in raw_items
            if (leader := _extract_leader_from_crawled_item(item)) is not None
        ]
    )
    role_counts = _compute_role_counts(leaders)

    return {
        "source_id": source_id,
        "institution_id": institution_name_map.get(university_name),
        "university_name": university_name,
        "source_name": source_name or None,
        "source_url": _normalize_str(source_config.get("url")) or None,
        "dimension": _normalize_str(source_config.get("dimension")) or None,
        "group_name": _normalize_str(source_config.get("group")) or None,
        "crawled_at": crawled_at,
        "leader_count": len(leaders),
        "role_counts": role_counts,
        "leaders": leaders,
        "data_hash": _compute_data_hash(leaders, role_counts),
    }


def _parse_iso_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = _normalize_str(value)
        if not text:
            dt = datetime.now(timezone.utc)
        else:
            dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _build_payload_from_json_doc(
    doc: dict[str, Any],
    *,
    institution_name_map: dict[str, str],
) -> dict[str, Any]:
    source_id = _normalize_str(doc.get("source_id"))
    source_name = _normalize_str(doc.get("source_name"))
    university_name = _normalize_str(doc.get("university_name")) or _extract_university_name(
        source_name,
        source_id,
    )

    leaders = _normalize_leaders(doc.get("leaders") or [])
    role_counts = doc.get("role_counts")
    if not isinstance(role_counts, dict):
        role_counts = _compute_role_counts(leaders)

    crawled_at = _parse_iso_datetime(doc.get("crawled_at"))

    return {
        "source_id": source_id,
        "institution_id": institution_name_map.get(university_name),
        "university_name": university_name,
        "source_name": source_name or None,
        "source_url": _normalize_str(doc.get("source_url")) or None,
        "dimension": _normalize_str(doc.get("dimension")) or None,
        "group_name": _normalize_str(doc.get("group")) or None,
        "crawled_at": crawled_at,
        "leader_count": len(leaders),
        "role_counts": role_counts,
        "leaders": leaders,
        "data_hash": _compute_data_hash(leaders, role_counts),
    }


async def _upsert_current(payload: dict[str, Any]) -> dict[str, Any]:
    await _ensure_tables()
    pool = get_pool()

    source_id = payload["source_id"]
    crawled_at: datetime = payload["crawled_at"]
    current_row = await pool.fetchrow(
        f"""
        SELECT
          source_id,
          institution_id,
          university_name,
          crawled_at,
          leader_count,
          new_leader_count,
          role_counts,
          leaders,
          data_hash,
          change_version,
          last_changed_at
        FROM {_CURRENT_TABLE}
        WHERE source_id = $1
        """,
        source_id,
    )

    new_leaders = payload["leaders"]
    new_role_counts = payload["role_counts"]
    new_leader_count = int(payload["leader_count"])
    new_hash = payload["data_hash"]

    changed = True
    change_version = 1
    last_changed_at = crawled_at
    previous_crawled_at: datetime | None = None
    delta_new_count = new_leader_count
    change_summary = _compute_change_summary([], new_leaders)

    leaders_to_store = new_leaders
    role_counts_to_store = new_role_counts
    leader_count_to_store = new_leader_count
    data_hash_to_store = new_hash

    institution_id = payload.get("institution_id")

    if current_row:
        previous_crawled_at = current_row["crawled_at"]
        old_leaders = _json_load_maybe(current_row["leaders"], [])
        old_role_counts = _json_load_maybe(current_row["role_counts"], {})
        old_hash = _normalize_str(current_row["data_hash"])

        if old_hash == new_hash:
            changed = False
            leaders_to_store = old_leaders
            role_counts_to_store = old_role_counts
            leader_count_to_store = int(current_row["leader_count"] or len(old_leaders))
            data_hash_to_store = old_hash
            change_version = int(current_row["change_version"] or 1)
            last_changed_at = current_row["last_changed_at"] or crawled_at
            delta_new_count = 0
            change_summary = {
                "changed": False,
                "added": [],
                "removed": [],
                "role_changed": [],
                "added_count": 0,
                "removed_count": 0,
                "role_changed_count": 0,
            }
        else:
            changed = True
            change_version = int(current_row["change_version"] or 1) + 1
            last_changed_at = crawled_at
            change_summary = _compute_change_summary(old_leaders, new_leaders)
            delta_new_count = int(change_summary.get("added_count", 0))

        institution_id = institution_id or _normalize_str(current_row["institution_id"]) or None

    await pool.execute(
        f"""
        INSERT INTO {_CURRENT_TABLE} (
          source_id,
          institution_id,
          university_name,
          source_name,
          source_url,
          dimension,
          group_name,
          crawled_at,
          previous_crawled_at,
          leader_count,
          new_leader_count,
          role_counts,
          leaders,
          data_hash,
          change_version,
          last_changed_at,
          created_at,
          updated_at
        )
        VALUES (
          $1,
          $2,
          $3,
          $4,
          $5,
          $6,
          $7,
          $8,
          $9,
          $10,
          $11,
          $12::jsonb,
          $13::jsonb,
          $14,
          $15,
          $16,
          NOW(),
          NOW()
        )
        ON CONFLICT (source_id) DO UPDATE SET
          institution_id = EXCLUDED.institution_id,
          university_name = EXCLUDED.university_name,
          source_name = EXCLUDED.source_name,
          source_url = EXCLUDED.source_url,
          dimension = EXCLUDED.dimension,
          group_name = EXCLUDED.group_name,
          crawled_at = EXCLUDED.crawled_at,
          previous_crawled_at = EXCLUDED.previous_crawled_at,
          leader_count = EXCLUDED.leader_count,
          new_leader_count = EXCLUDED.new_leader_count,
          role_counts = EXCLUDED.role_counts,
          leaders = EXCLUDED.leaders,
          data_hash = EXCLUDED.data_hash,
          change_version = EXCLUDED.change_version,
          last_changed_at = EXCLUDED.last_changed_at,
          updated_at = NOW()
        """,
        source_id,
        institution_id,
        payload["university_name"],
        payload.get("source_name"),
        payload.get("source_url"),
        payload.get("dimension"),
        payload.get("group_name"),
        crawled_at,
        previous_crawled_at,
        leader_count_to_store,
        delta_new_count,
        json.dumps(role_counts_to_store, ensure_ascii=False),
        json.dumps(leaders_to_store, ensure_ascii=False),
        data_hash_to_store,
        change_version,
        last_changed_at,
    )

    return {
        "source_id": source_id,
        "changed": changed,
        "new_leader_count": int(change_summary.get("added_count", 0)) if changed else 0,
        "change_version": change_version,
        "change_summary": change_summary,
    }


def _serialize_current_row(row: dict[str, Any]) -> dict[str, Any]:
    role_counts = _json_load_maybe(row.get("role_counts"), {})
    leaders = _json_load_maybe(row.get("leaders"), [])
    return {
        "source_id": row.get("source_id"),
        "institution_id": row.get("institution_id"),
        "university_name": row.get("university_name"),
        "source_name": row.get("source_name"),
        "source_url": row.get("source_url"),
        "dimension": row.get("dimension"),
        "group": row.get("group_name"),
        "crawled_at": row.get("crawled_at"),
        "previous_crawled_at": row.get("previous_crawled_at"),
        "leader_count": int(row.get("leader_count") or 0),
        "new_leader_count": int(row.get("new_leader_count") or 0),
        "role_counts": role_counts if isinstance(role_counts, dict) else {},
        "leaders": leaders if isinstance(leaders, list) else [],
        "data_hash": row.get("data_hash"),
        "change_version": int(row.get("change_version") or 1),
        "last_changed_at": row.get("last_changed_at"),
        "updated_at": row.get("updated_at"),
    }


async def get_university_leadership_current(institution_id: str) -> dict[str, Any] | None:
    await _ensure_tables()
    institution = await fetch_institution_by_id(institution_id)
    if not institution:
        return None

    pool = get_pool()
    row = await pool.fetchrow(
        f"""
        SELECT *
        FROM {_CURRENT_TABLE}
        WHERE institution_id = $1
        ORDER BY crawled_at DESC
        LIMIT 1
        """,
        institution_id,
    )

    if not row:
        university_name = _normalize_str(institution.get("name"))
        if university_name:
            row = await pool.fetchrow(
                f"""
                SELECT *
                FROM {_CURRENT_TABLE}
                WHERE university_name = $1
                ORDER BY crawled_at DESC
                LIMIT 1
                """,
                university_name,
            )

    if not row:
        return None

    return _serialize_current_row(dict(row))


async def list_university_leadership_current(
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    await _ensure_tables()

    safe_page = max(1, int(page))
    safe_page_size = max(1, min(int(page_size), 100))
    offset = (safe_page - 1) * safe_page_size

    conditions: list[str] = []
    params: list[Any] = []

    query = _normalize_str(keyword)
    if query:
        params.append(f"%{query}%")
        p = len(params)
        conditions.append(
            f"(university_name ILIKE ${p} OR COALESCE(source_name, '') ILIKE ${p} OR COALESCE(source_id, '') ILIKE ${p})"
        )

    where_sql = ""
    if conditions:
        where_sql = " WHERE " + " AND ".join(conditions)

    pool = get_pool()
    total = await pool.fetchval(
        f"SELECT COUNT(*) FROM {_CURRENT_TABLE}{where_sql}",
        *params,
    )

    params.extend([safe_page_size, offset])
    p_limit = len(params) - 1
    p_offset = len(params)

    rows = await pool.fetch(
        f"""
        SELECT *
        FROM {_CURRENT_TABLE}
        {where_sql}
        ORDER BY crawled_at DESC, university_name ASC
        LIMIT ${p_limit} OFFSET ${p_offset}
        """,
        *params,
    )

    return {
        "total": int(total or 0),
        "page": safe_page,
        "page_size": safe_page_size,
        "items": [_serialize_current_row(dict(row)) for row in rows],
    }


async def get_all_university_leadership_current(
    *,
    keyword: str | None = None,
) -> dict[str, Any]:
    await _ensure_tables()

    conditions: list[str] = []
    params: list[Any] = []

    query = _normalize_str(keyword)
    if query:
        params.append(f"%{query}%")
        p = len(params)
        conditions.append(
            f"(university_name ILIKE ${p} OR COALESCE(source_name, '') ILIKE ${p} OR COALESCE(source_id, '') ILIKE ${p})"
        )

    where_sql = ""
    if conditions:
        where_sql = " WHERE " + " AND ".join(conditions)

    pool = get_pool()
    rows = await pool.fetch(
        f"""
        SELECT *
        FROM {_CURRENT_TABLE}
        {where_sql}
        ORDER BY crawled_at DESC, university_name ASC
        """,
        *params,
    )

    return {
        "total": len(rows),
        "items": [_serialize_current_row(dict(row)) for row in rows],
    }


async def get_university_leadership_history(
    institution_id: str,
    *,
    limit: int = 12,
) -> dict[str, Any] | None:
    await _ensure_tables()

    institution = await fetch_institution_by_id(institution_id)
    if not institution:
        return None

    university_name = _normalize_str(institution.get("name"))

    row = await get_university_leadership_current(institution_id)
    if not row:
        return {
            "institution_id": institution_id,
            "university_name": university_name,
            "total": 0,
            "items": [],
        }

    crawled_at = row.get("crawled_at")
    crawl_month = None
    if isinstance(crawled_at, datetime):
        crawl_month = crawled_at.date().replace(day=1)

    item = {
        "snapshot_id": None,
        "source_id": row.get("source_id"),
        "institution_id": row.get("institution_id"),
        "university_name": row.get("university_name"),
        "source_name": row.get("source_name"),
        "source_url": row.get("source_url"),
        "crawl_month": crawl_month,
        "crawled_at": row.get("crawled_at"),
        "previous_crawled_at": row.get("previous_crawled_at"),
        "leader_count": row.get("leader_count", 0),
        "new_leader_count": row.get("new_leader_count", 0),
        "role_counts": row.get("role_counts", {}),
        "leaders": row.get("leaders", []),
        "data_hash": row.get("data_hash"),
        "changed": int(row.get("change_version") or 1) > 1,
        "change_summary": {},
        "updated_at": row.get("updated_at"),
    }

    return {
        "institution_id": institution_id,
        "university_name": university_name,
        "total": 1,
        "items": [item][: max(1, min(limit, 60))],
    }


async def run_university_leadership_full_crawl(
    *,
    max_concurrency: int = 4,
    include_disabled: bool = False,
) -> dict[str, Any]:
    """Run a full crawl for all university leadership sources and sync DB table."""
    await _ensure_tables()

    all_configs = load_all_source_configs()
    leadership_configs = [
        cfg
        for cfg in all_configs
        if cfg.get("crawl_method") == "university_leadership"
    ]
    if not include_disabled:
        leadership_configs = [cfg for cfg in leadership_configs if cfg.get("is_enabled", True)]

    if not leadership_configs:
        return {
            "started_at": datetime.now(timezone.utc),
            "finished_at": datetime.now(timezone.utc),
            "total_sources": 0,
            "success_sources": 0,
            "failed_sources": 0,
            "changed_sources": 0,
            "results": [],
        }

    institution_name_map = await _load_institution_name_map()

    semaphore = asyncio.Semaphore(max(1, min(int(max_concurrency), 12)))

    async def _run_one(source_config: dict[str, Any]) -> dict[str, Any]:
        source_id = _normalize_str(source_config.get("id"))
        source_name = _normalize_str(source_config.get("name"))
        university_name = _extract_university_name(source_name, source_id)

        async with semaphore:
            started = datetime.now(timezone.utc)

            try:
                crawler = CrawlerRegistry.create_crawler(source_config)
            except Exception as exc:
                return {
                    "source_id": source_id,
                    "source_name": source_name,
                    "university_name": university_name,
                    "status": "failed",
                    "error": f"create crawler failed: {exc}",
                    "leaders_total": 0,
                    "changed": False,
                    "duration_seconds": 0.0,
                    "started_at": started,
                    "finished_at": datetime.now(timezone.utc),
                }

            result = await crawler.run()
            finished = result.finished_at or datetime.now(timezone.utc)

            json_sync_error = None
            try:
                await save_crawl_result_json(result, source_config)
            except Exception as exc:
                json_sync_error = str(exc)
                logger.warning("Leadership JSON save failed for %s: %s", source_id, exc)

            if result.status.value == "failed":
                return {
                    "source_id": source_id,
                    "source_name": source_name,
                    "university_name": university_name,
                    "status": "failed",
                    "error": result.error_message or json_sync_error,
                    "leaders_total": 0,
                    "changed": False,
                    "duration_seconds": result.duration_seconds,
                    "started_at": result.started_at,
                    "finished_at": finished,
                }

            raw_items = result.items_all or result.items or []
            if not raw_items:
                return {
                    "source_id": source_id,
                    "source_name": source_name,
                    "university_name": university_name,
                    "status": "skipped_empty",
                    "error": json_sync_error,
                    "leaders_total": 0,
                    "changed": False,
                    "duration_seconds": result.duration_seconds,
                    "started_at": result.started_at,
                    "finished_at": finished,
                }

            payload = _build_payload_from_crawl(
                source_config,
                raw_items,
                crawled_at=finished,
                institution_name_map=institution_name_map,
            )

            if payload["leader_count"] <= 0:
                return {
                    "source_id": source_id,
                    "source_name": source_name,
                    "university_name": university_name,
                    "status": "skipped_empty",
                    "error": json_sync_error,
                    "leaders_total": 0,
                    "changed": False,
                    "duration_seconds": result.duration_seconds,
                    "started_at": result.started_at,
                    "finished_at": finished,
                }

            sync_result = await _upsert_current(payload)

            return {
                "source_id": source_id,
                "source_name": source_name,
                "university_name": university_name,
                "status": result.status.value,
                "error": json_sync_error,
                "leaders_total": payload["leader_count"],
                "changed": bool(sync_result.get("changed")),
                "new_leader_count": int(sync_result.get("new_leader_count") or 0),
                "change_version": int(sync_result.get("change_version") or 1),
                "duration_seconds": result.duration_seconds,
                "started_at": result.started_at,
                "finished_at": finished,
            }

    run_started = datetime.now(timezone.utc)
    results = await asyncio.gather(*[_run_one(cfg) for cfg in leadership_configs])
    run_finished = datetime.now(timezone.utc)

    success_sources = sum(1 for r in results if r.get("status") not in {"failed"})
    failed_sources = sum(1 for r in results if r.get("status") == "failed")
    changed_sources = sum(1 for r in results if r.get("changed"))

    return {
        "started_at": run_started,
        "finished_at": run_finished,
        "duration_seconds": (run_finished - run_started).total_seconds(),
        "total_sources": len(leadership_configs),
        "success_sources": success_sources,
        "failed_sources": failed_sources,
        "changed_sources": changed_sources,
        "results": sorted(results, key=lambda x: (_normalize_str(x.get("status")), _normalize_str(x.get("source_id")))),
    }


async def sync_university_leadership_from_json_dir(
    *,
    directory: str | None = None,
) -> dict[str, Any]:
    """Bootstrap/update leadership tables from local JSON files in data/leadership."""
    await _ensure_tables()

    target_dir = Path(directory) if directory else BASE_DIR / "data" / "leadership"
    if not target_dir.exists():
        return {
            "directory": str(target_dir),
            "total_files": 0,
            "synced_files": 0,
            "failed_files": 0,
            "results": [],
        }

    institution_name_map = await _load_institution_name_map()

    files = sorted(p for p in target_dir.glob("*.json") if p.is_file())
    results: list[dict[str, Any]] = []

    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)

            payload = _build_payload_from_json_doc(doc, institution_name_map=institution_name_map)
            if payload["leader_count"] <= 0:
                results.append(
                    {
                        "file": str(path),
                        "status": "skipped_empty",
                        "source_id": payload.get("source_id"),
                        "university_name": payload.get("university_name"),
                        "changed": False,
                        "new_leader_count": 0,
                    }
                )
                continue

            sync_result = await _upsert_current(payload)
            results.append(
                {
                    "file": str(path),
                    "status": "synced",
                    "source_id": payload.get("source_id"),
                    "university_name": payload.get("university_name"),
                    "changed": bool(sync_result.get("changed")),
                    "new_leader_count": int(sync_result.get("new_leader_count") or 0),
                }
            )
        except Exception as exc:
            logger.warning("Failed syncing leadership JSON %s: %s", path, exc)
            results.append(
                {
                    "file": str(path),
                    "status": "failed",
                    "error": str(exc),
                }
            )

    return {
        "directory": str(target_dir),
        "total_files": len(files),
        "synced_files": sum(1 for r in results if r.get("status") == "synced"),
        "failed_files": sum(1 for r in results if r.get("status") == "failed"),
        "results": results,
    }


async def search_institution_scholar_candidates(
    institution_id: str,
    *,
    keyword: str | None = None,
    limit: int = 20,
    only_same_university: bool = True,
) -> dict[str, Any] | None:
    institution = await fetch_institution_by_id(institution_id)
    if not institution:
        return None

    pool = get_pool()
    params: list[Any] = []
    conditions: list[str] = []

    institution_name = _normalize_str(institution.get("name"))

    if only_same_university and institution_name:
        params.append(institution_name)
        conditions.append(f"university = ${len(params)}")

    query = _normalize_str(keyword)
    if query:
        params.append(f"%{query}%")
        p_like = len(params)
        conditions.append(
            "(name ILIKE ${p} OR COALESCE(name_en, '') ILIKE ${p} OR "
            "COALESCE(position, '') ILIKE ${p} OR COALESCE(department, '') ILIKE ${p})".format(
                p=p_like,
            )
        )

    where_sql = ""
    if conditions:
        where_sql = " WHERE " + " AND ".join(conditions)

    order_prefix = ""
    if query:
        params.append(query)
        p_exact = len(params)
        params.append(f"{query}%")
        p_prefix = len(params)
        order_prefix = (
            f"CASE WHEN name = ${p_exact} THEN 0 "
            f"WHEN name ILIKE ${p_prefix} THEN 1 ELSE 2 END, "
        )

    safe_limit = max(1, min(limit, 50))
    params.append(safe_limit)
    p_limit = len(params)

    sql = (
        "SELECT id, name, university, department, position, research_areas, photo_url, data_completeness, updated_at "
        "FROM scholars"
        f"{where_sql} "
        f"ORDER BY {order_prefix}data_completeness DESC NULLS LAST, updated_at DESC NULLS LAST, id ASC "
        f"LIMIT ${p_limit}"
    )

    rows = await pool.fetch(sql, *params)

    items = []
    for row in rows:
        research_areas = row.get("research_areas")
        if not isinstance(research_areas, list):
            research_areas = _ensure_str_list(research_areas)

        items.append(
            {
                "scholar_id": row.get("id"),
                "name": row.get("name"),
                "university": row.get("university"),
                "department": row.get("department"),
                "position": row.get("position"),
                "photo_url": row.get("photo_url"),
                "research_areas": research_areas,
            }
        )

    return {
        "institution_id": institution_id,
        "institution_name": institution_name,
        "query": query,
        "total": len(items),
        "items": items,
    }


def _build_scholar_info_item(row: dict[str, Any]) -> dict[str, Any]:
    research_areas = row.get("research_areas")
    if not isinstance(research_areas, list):
        research_areas = _ensure_str_list(research_areas)

    return {
        "scholar_id": _normalize_str(row.get("id")),
        "name": _normalize_str(row.get("name")),
        "title": _normalize_str(row.get("position")) or None,
        "department": _normalize_str(row.get("department")) or None,
        "research_area": research_areas[0] if research_areas else None,
    }


async def update_institution_manual_people_config(
    institution_id: str,
    *,
    governance_scholar_ids: list[str] | None,
    notable_scholar_ids: list[str] | None,
    enforce_same_university: bool = True,
) -> dict[str, Any] | None:
    institution = await fetch_institution_by_id(institution_id)
    if not institution:
        return None

    governance_ids = _dedupe_preserve_order(governance_scholar_ids or [])
    notable_ids = _dedupe_preserve_order(notable_scholar_ids or [])

    if len(notable_ids) > 10:
        raise ValueError("notable_scholar_ids 最多只能配置 10 位学者")

    all_ids = _dedupe_preserve_order([*governance_ids, *notable_ids])
    scholars_by_id: dict[str, dict[str, Any]] = {}

    if all_ids:
        pool = get_pool()
        rows = await pool.fetch(
            """
            SELECT id, name, university, department, position, research_areas
            FROM scholars
            WHERE id = ANY($1::text[])
            """,
            all_ids,
        )
        scholars_by_id = {str(r["id"]): dict(r) for r in rows}

        missing = [sid for sid in all_ids if sid not in scholars_by_id]
        if missing:
            raise ValueError(f"以下 scholar_id 不存在: {', '.join(missing)}")

        if enforce_same_university:
            institution_name = _normalize_str(institution.get("name"))
            cross_university = [
                sid
                for sid in all_ids
                if _normalize_str(scholars_by_id[sid].get("university")) != institution_name
            ]
            if cross_university:
                raise ValueError(
                    "以下学者不属于当前机构，无法配置: " + ", ".join(cross_university)
                )

    governance_items = [_build_scholar_info_item(scholars_by_id[sid]) for sid in governance_ids]
    notable_items = [_build_scholar_info_item(scholars_by_id[sid]) for sid in notable_ids]

    existing_custom_fields = institution.get("custom_fields")
    if not isinstance(existing_custom_fields, dict):
        existing_custom_fields = {}

    now_iso = datetime.now(timezone.utc).isoformat()
    custom_fields = {
        **existing_custom_fields,
        "manual_governance_team_ids": governance_ids,
        "manual_notable_scholar_ids": notable_ids,
        "manual_people_updated_at": now_iso,
    }

    merged = {
        **institution,
        "id": institution_id,
        # Legacy top section fields are cleared, and resident_leaders keeps a name-only mirror
        # for backward-compatible frontend rendering.
        "resident_leaders": [item["name"] for item in governance_items if item.get("name")],
        "degree_committee": [],
        "teaching_committee": [],
        "university_leaders": governance_items,
        "notable_scholars": notable_items,
        "custom_fields": custom_fields,
    }

    await upsert_institution(merged)
    return await get_institution_detail(institution_id)


__all__ = [
    "get_all_university_leadership_current",
    "list_university_leadership_current",
    "get_university_leadership_current",
    "get_university_leadership_history",
    "run_university_leadership_full_crawl",
    "sync_university_leadership_from_json_dir",
    "search_institution_scholar_candidates",
    "update_institution_manual_people_config",
]
