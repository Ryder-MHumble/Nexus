"""Cross-entity synchronization helpers for scholar event/project tag fields."""
from __future__ import annotations

from typing import Any


def _get_client():
    from app.db.client import get_client  # noqa: PLC0415

    return get_client()


_SCHOLAR_COLUMNS_CACHE: set[str] | None = None


async def _get_scholar_columns() -> set[str]:
    global _SCHOLAR_COLUMNS_CACHE
    if _SCHOLAR_COLUMNS_CACHE is not None:
        return _SCHOLAR_COLUMNS_CACHE

    from app.db.pool import get_pool  # noqa: PLC0415

    rows = await get_pool().fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='scholars'
        """,
    )
    _SCHOLAR_COLUMNS_CACHE = {str(r["column_name"]) for r in rows}
    return _SCHOLAR_COLUMNS_CACHE


def _uniq_ids(ids: list[str] | None) -> list[str]:
    if not ids:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in ids:
        sid = str(raw or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def _normalize_project_tags(raw: Any) -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return tags
    for item in raw:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        subcategory = str(item.get("subcategory") or "").strip()
        if not category and not subcategory:
            continue
        tags.append(
            {
                "category": category,
                "subcategory": subcategory,
                "project_id": str(item.get("project_id") or ""),
                "project_title": str(item.get("project_title") or ""),
            }
        )
    return tags


def _dedupe_project_tags(tags: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, str]] = []
    for tag in tags:
        key = (
            tag.get("category", ""),
            tag.get("subcategory", ""),
            tag.get("project_id", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


def _project_match(
    tag: dict[str, str],
    *,
    project_id: str,
    category: str,
    subcategory: str,
) -> bool:
    tag_pid = str(tag.get("project_id") or "")
    if tag_pid:
        return tag_pid == project_id
    return (
        str(tag.get("category") or "") == category
        and str(tag.get("subcategory") or "") == subcategory
    )


async def sync_event_scholar_memberships(
    *,
    event_id: str,
    new_scholar_ids: list[str] | None,
    old_scholar_ids: list[str] | None = None,
) -> None:
    """Synchronize scholars.participated_event_ids after event scholar_ids changes."""
    new_ids = set(_uniq_ids(new_scholar_ids))
    old_ids = set(_uniq_ids(old_scholar_ids))
    add_ids = new_ids - old_ids
    remove_ids = old_ids - new_ids
    target_ids = sorted(add_ids | remove_ids)
    if not target_ids:
        return

    scholar_cols = await _get_scholar_columns()
    if "participated_event_ids" not in scholar_cols:
        return

    from app.db.pool import get_pool  # noqa: PLC0415

    client = _get_client()
    rows = [
        dict(r)
        for r in await get_pool().fetch(
            """
            SELECT id, participated_event_ids
            FROM scholars
            WHERE id = ANY($1::text[])
            """,
            target_ids,
        )
    ]
    by_id = {str(r.get("id")): r for r in rows}

    for scholar_id in target_ids:
        row = by_id.get(scholar_id) or {}
        current = _uniq_ids(row.get("participated_event_ids") or [])
        if scholar_id in add_ids and event_id not in current:
            current.append(event_id)
        if scholar_id in remove_ids:
            current = [eid for eid in current if eid != event_id]
        await (
            client.table("scholars")
            .update({"participated_event_ids": current})
            .eq("id", scholar_id)
            .execute()
        )


async def sync_project_scholar_memberships(
    *,
    project_id: str,
    project_title: str,
    category: str,
    subcategory: str,
    new_scholar_ids: list[str] | None,
    old_scholar_ids: list[str] | None = None,
) -> None:
    """Synchronize scholars.project_tags/is_cobuild_scholar when project-scholar links change."""
    new_ids = set(_uniq_ids(new_scholar_ids))
    old_ids = set(_uniq_ids(old_scholar_ids))
    add_ids = new_ids - old_ids
    remove_ids = old_ids - new_ids
    target_ids = sorted(add_ids | remove_ids)
    if not target_ids:
        return

    scholar_cols = await _get_scholar_columns()
    updatable_cols = {
        c
        for c in (
            "project_tags",
            "is_cobuild_scholar",
            "project_category",
            "project_subcategory",
        )
        if c in scholar_cols
    }
    if not updatable_cols:
        return

    select_cols = ["id"]
    if "project_tags" in scholar_cols:
        select_cols.append("project_tags")
    if "project_category" in scholar_cols:
        select_cols.append("project_category")
    if "project_subcategory" in scholar_cols:
        select_cols.append("project_subcategory")

    from app.db.pool import get_pool  # noqa: PLC0415

    client = _get_client()
    rows = [
        dict(r)
        for r in await get_pool().fetch(
            f"""
            SELECT {", ".join(select_cols)}
            FROM scholars
            WHERE id = ANY($1::text[])
            """,
            target_ids,
        )
    ]
    by_id = {str(r.get("id")): r for r in rows}

    for scholar_id in target_ids:
        row = by_id.get(scholar_id) or {"id": scholar_id}
        tags = _normalize_project_tags(row.get("project_tags") or [])

        # Backfill from legacy single-value fields when project_tags column is newly added.
        if not tags:
            legacy_category = str(row.get("project_category") or "").strip()
            legacy_subcategory = str(row.get("project_subcategory") or "").strip()
            if legacy_category or legacy_subcategory:
                tags = [
                    {
                        "category": legacy_category,
                        "subcategory": legacy_subcategory,
                        "project_id": "",
                        "project_title": "",
                    }
                ]

        if scholar_id in add_ids:
            tags = [
                t
                for t in tags
                if not _project_match(
                    t,
                    project_id=project_id,
                    category=category,
                    subcategory=subcategory,
                )
            ]
            tags.append(
                {
                    "category": category,
                    "subcategory": subcategory,
                    "project_id": project_id,
                    "project_title": project_title,
                }
            )
        if scholar_id in remove_ids:
            tags = [
                t
                for t in tags
                if not _project_match(
                    t,
                    project_id=project_id,
                    category=category,
                    subcategory=subcategory,
                )
            ]

        tags = _dedupe_project_tags(tags)
        first = tags[0] if tags else {}

        update_payload: dict[str, Any] = {}
        if "project_tags" in updatable_cols:
            update_payload["project_tags"] = tags
        if "is_cobuild_scholar" in updatable_cols:
            update_payload["is_cobuild_scholar"] = bool(tags)
        if "project_category" in updatable_cols:
            update_payload["project_category"] = str(first.get("category") or "")
        if "project_subcategory" in updatable_cols:
            update_payload["project_subcategory"] = str(first.get("subcategory") or "")

        if update_payload:
            await (
                client.table("scholars")
                .update(update_payload)
                .eq("id", scholar_id)
                .execute()
            )
