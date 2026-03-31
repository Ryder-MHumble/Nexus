"""Event service — CRUD 操作（标签化活动模型）。"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.schemas.event import (
    EventDetailResponse,
    EventListItem,
    EventListResponse,
    EventStatsResponse,
    TaxonomyL1,
    TaxonomyL2,
    TaxonomyL3,
    TaxonomyNode,
    TaxonomyTree,
)
from app.services.core.scholar_tag_sync import sync_event_scholar_memberships


def _get_client():
    from app.db.client import get_client  # noqa: PLC0415

    return get_client()


def _clean_date(v: Any) -> str | None:
    if not v or v == "":
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(v))
    return m.group(1) if m else None


def _clean(v: Any) -> Any:
    if v is None or v == "":
        return None
    return v


def _uniq_ids(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        sid = str(item or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def _db_to_detail(row: dict) -> EventDetailResponse:
    return EventDetailResponse(
        id=row.get("id", ""),
        category=row.get("category") or "",
        event_type=row.get("event_type") or "",
        series=row.get("series") or "",
        title=row.get("title", ""),
        abstract=row.get("description") or "",
        event_date=str(_clean_date(row.get("event_date")) or ""),
        event_time=row.get("event_time") or "",
        location=row.get("location") or "",
        cover_image_url=row.get("poster_url") or "",
        scholar_ids=_uniq_ids(row.get("scholar_ids") or []),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        custom_fields=row.get("custom_fields") or {},
    )


def _event_to_db_row(evt: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": evt.get("id"),
        "title": evt.get("title", ""),
        "category": _clean(evt.get("category")),
        "event_type": _clean(evt.get("event_type")),
        "series": _clean(evt.get("series")),
        "description": _clean(evt.get("abstract")),
        "event_date": _clean_date(evt.get("event_date")),
        "event_time": _clean(evt.get("event_time")),
        "location": _clean(evt.get("location")),
        "poster_url": _clean(evt.get("cover_image_url")),
        "scholar_ids": _uniq_ids(evt.get("scholar_ids") or []),
        "is_past": evt.get("is_past", False),
        "created_at": _clean(evt.get("created_at")),
        "updated_at": _clean(evt.get("updated_at")),
        "custom_fields": evt.get("custom_fields"),
    }


async def get_event_list(
    category: str | None = None,
    event_type: str | None = None,
    series: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    scholar_id: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    custom_field_key: str | None = None,
    custom_field_value: str | None = None,
) -> EventListResponse:
    client = _get_client()
    q = (
        client.table("events")
        .select("*")
        .order("event_date", desc=True)
        .order("created_at", desc=True)
    )
    if category:
        q = q.eq("category", category)
    if event_type:
        q = q.eq("event_type", event_type)
    if series:
        q = q.eq("series", series)
    if start_date:
        q = q.gte("event_date", start_date)
    if end_date:
        q = q.lte("event_date", end_date)
    if keyword:
        q = q.or_(
            f"title.ilike.%{keyword}%,description.ilike.%{keyword}%,series.ilike.%{keyword}%,event_type.ilike.%{keyword}%"
        )

    res = await q.execute()
    rows = res.data or []

    if scholar_id:
        rows = [r for r in rows if scholar_id in _uniq_ids(r.get("scholar_ids") or [])]

    if custom_field_key:
        rows = [
            r for r in rows
            if (r.get("custom_fields") or {}).get(custom_field_key) == custom_field_value
        ]

    total = len(rows)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    items = [
        EventListItem(
            id=r.get("id", ""),
            category=r.get("category") or "",
            event_type=r.get("event_type") or "",
            series=r.get("series") or "",
            title=r.get("title", ""),
            abstract=r.get("description") or "",
            event_date=str(_clean_date(r.get("event_date")) or ""),
            event_time=r.get("event_time") or "",
            location=r.get("location") or "",
            cover_image_url=r.get("poster_url") or "",
            scholar_count=len(_uniq_ids(r.get("scholar_ids") or [])),
            created_at=str(r.get("created_at") or ""),
        )
        for r in rows[start: start + page_size]
    ]
    return EventListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


async def get_event_detail(event_id: str) -> EventDetailResponse | None:
    client = _get_client()
    res = await client.table("events").select("*").eq("id", event_id).execute()
    if res.data:
        return _db_to_detail(res.data[0])
    return None


async def get_event_stats() -> EventStatsResponse:
    client = _get_client()
    res = await client.table("events").select(
        "category,series,event_type,event_date,scholar_ids"
    ).execute()
    rows = res.data or []
    by_category: dict[str, int] = {}
    by_series: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_month: dict[str, int] = {}
    total_related_scholars = 0

    for r in rows:
        cat = r.get("category") or "未分类"
        by_category[cat] = by_category.get(cat, 0) + 1

        series = r.get("series") or "未分类"
        by_series[series] = by_series.get(series, 0) + 1

        event_type = r.get("event_type") or "未分类"
        by_type[event_type] = by_type.get(event_type, 0) + 1

        d = _clean_date(r.get("event_date"))
        if d:
            m = d[:7]
            by_month[m] = by_month.get(m, 0) + 1

        total_related_scholars += len(_uniq_ids(r.get("scholar_ids") or []))

    return EventStatsResponse(
        total=len(rows),
        by_category=[{"category": k, "count": v} for k, v in by_category.items()],
        by_series=[{"series": k, "count": v} for k, v in by_series.items()],
        by_type=[{"event_type": k, "count": v} for k, v in by_type.items()],
        by_month=[
            {"month": k, "count": v}
            for k, v in sorted(by_month.items(), reverse=True)
        ],
        total_related_scholars=total_related_scholars,
    )


async def create_event(evt_data: dict[str, Any]) -> EventDetailResponse:
    now = datetime.now(timezone.utc).isoformat()
    evt_data["id"] = str(uuid.uuid4())
    evt_data["scholar_ids"] = _uniq_ids(evt_data.get("scholar_ids") or [])
    evt_data.setdefault("created_at", now)
    evt_data.setdefault("updated_at", now)

    client = _get_client()
    await client.table("events").insert(_event_to_db_row(evt_data)).execute()

    try:
        await sync_event_scholar_memberships(
            event_id=evt_data["id"],
            new_scholar_ids=evt_data["scholar_ids"],
            old_scholar_ids=[],
        )
    except Exception:
        # Sync failure should not block event creation.
        pass

    detail = await get_event_detail(evt_data["id"])
    if detail is not None:
        return detail
    return _db_to_detail(_event_to_db_row(evt_data) | {"id": evt_data["id"]})


async def update_event(event_id: str, updates: dict[str, Any]) -> EventDetailResponse | None:
    from app.services.core.custom_fields import apply_custom_fields_update  # noqa: PLC0415

    existing = await get_event_detail(event_id)
    if not existing:
        return None

    updates = dict(updates)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    if "scholar_ids" in updates:
        updates["scholar_ids"] = _uniq_ids(updates.get("scholar_ids") or [])

    if "custom_fields" in updates:
        client = _get_client()
        cur = await client.table("events").select("custom_fields").eq("id", event_id).execute()
        if cur.data:
            apply_custom_fields_update(updates, cur.data[0])

    db_updates = _event_to_db_row({**updates, "id": event_id})
    db_updates = {k: v for k, v in db_updates.items() if k != "id" and v is not None}
    if "custom_fields" in updates:
        db_updates["custom_fields"] = updates["custom_fields"]

    client = _get_client()
    await client.table("events").update(db_updates).eq("id", event_id).execute()

    res = await client.table("events").select("*").eq("id", event_id).execute()
    if not res.data:
        return None
    updated = _db_to_detail(res.data[0])

    if "scholar_ids" in updates and updates["scholar_ids"] != existing.scholar_ids:
        try:
            await sync_event_scholar_memberships(
                event_id=event_id,
                new_scholar_ids=updates["scholar_ids"],
                old_scholar_ids=existing.scholar_ids,
            )
        except Exception:
            pass

    return updated


async def delete_event(event_id: str) -> bool:
    existing = await get_event_detail(event_id)
    if not existing:
        return False

    client = _get_client()
    await client.table("events").delete().eq("id", event_id).execute()

    try:
        await sync_event_scholar_memberships(
            event_id=event_id,
            new_scholar_ids=[],
            old_scholar_ids=existing.scholar_ids,
        )
    except Exception:
        pass

    return True


async def add_scholar_to_event(event_id: str, scholar_id: str) -> EventDetailResponse | None:
    detail = await get_event_detail(event_id)
    if not detail:
        return None
    ids = list(detail.scholar_ids)
    sid = scholar_id.strip()
    if sid and sid not in ids:
        ids.append(sid)
    return await update_event(event_id, {"scholar_ids": ids})


async def remove_scholar_from_event(event_id: str, scholar_id: str) -> EventDetailResponse | None:
    detail = await get_event_detail(event_id)
    if not detail:
        return None
    ids = [i for i in detail.scholar_ids if i != scholar_id]
    return await update_event(event_id, {"scholar_ids": ids})


async def get_event_scholars(event_id: str) -> list[str] | None:
    detail = await get_event_detail(event_id)
    return detail.scholar_ids if detail else None


async def batch_create_events(
    items: list[dict[str, Any]],
    skip_duplicates: bool = True,
) -> dict[str, Any]:
    """Batch-create events.

    Duplicate detection: same title + same event_date + same series + same event_type.
    """
    client = _get_client()
    existing_res = await client.table("events").select(
        "id,title,event_date,series,event_type"
    ).execute()
    existing_keys: set[tuple[str, str, str, str]] = set()
    for r in (existing_res.data or []):
        key = (
            (r.get("title") or "").strip().lower(),
            str(_clean_date(r.get("event_date")) or "").strip(),
            (r.get("series") or "").strip().lower(),
            (r.get("event_type") or "").strip().lower(),
        )
        existing_keys.add(key)

    result: dict[str, Any] = {
        "total": len(items),
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "items": [],
    }

    for idx, item in enumerate(items, start=1):
        title = (item.get("title") or "").strip()
        if not title:
            result["failed"] += 1
            result["items"].append(
                {"row": idx, "status": "failed", "title": "", "reason": "title is required"}
            )
            continue

        key = (
            title.lower(),
            str(_clean_date(item.get("event_date")) or "").strip(),
            (item.get("series") or "").strip().lower(),
            (item.get("event_type") or "").strip().lower(),
        )
        if key in existing_keys:
            if skip_duplicates:
                result["skipped"] += 1
                result["items"].append(
                    {
                        "row": idx,
                        "status": "skipped",
                        "title": title,
                        "reason": "duplicate (same title+date+series+event_type)",
                    }
                )
            else:
                result["failed"] += 1
                result["items"].append(
                    {"row": idx, "status": "failed", "title": title, "reason": "duplicate"}
                )
            continue

        try:
            created = await create_event(item)
            existing_keys.add(key)
            result["success"] += 1
            result["items"].append(
                {"row": idx, "status": "success", "title": title, "id": created.id}
            )
        except Exception as exc:
            result["failed"] += 1
            result["items"].append(
                {"row": idx, "status": "failed", "title": title, "reason": str(exc)}
            )

    return result


def _row_to_node(row: dict) -> TaxonomyNode:
    node_id = row.get("id")
    parent = row.get("parent_id")
    return TaxonomyNode(
        id=str(node_id) if node_id is not None else "",
        level=row.get("level", 1),
        name=row.get("name", ""),
        parent_id=str(parent) if parent is not None else None,
        sort_order=row.get("sort_order") or 0,
        created_at=str(row.get("created_at") or ""),
    )


async def get_taxonomy_tree() -> TaxonomyTree:
    """Return the full 3-level taxonomy tree."""
    client = _get_client()
    res = await client.table("event_taxonomy").select("*").order("sort_order").execute()
    rows = res.data or []

    l1_rows = [r for r in rows if r["level"] == 1]
    l2_rows = [r for r in rows if r["level"] == 2]
    l3_rows = [r for r in rows if r["level"] == 3]

    l3_by_parent: dict[str, list[TaxonomyL3]] = {}
    for r in l3_rows:
        pid = str(r.get("parent_id") or "")
        l3_by_parent.setdefault(pid, []).append(TaxonomyL3(**_row_to_node(r).model_dump()))

    l2_by_parent: dict[str, list[TaxonomyL2]] = {}
    for r in l2_rows:
        pid = str(r.get("parent_id") or "")
        node_id = str(r["id"])
        node = TaxonomyL2(
            **_row_to_node(r).model_dump(),
            children=l3_by_parent.get(node_id, []),
        )
        l2_by_parent.setdefault(pid, []).append(node)

    l1_items: list[TaxonomyL1] = []
    for r in l1_rows:
        node_id = str(r["id"])
        node = TaxonomyL1(
            **_row_to_node(r).model_dump(),
            children=l2_by_parent.get(node_id, []),
        )
        l1_items.append(node)

    return TaxonomyTree(
        total_l1=len(l1_rows),
        total_l2=len(l2_rows),
        total_l3=len(l3_rows),
        items=l1_items,
    )


async def create_taxonomy_node(data: dict[str, Any]) -> TaxonomyNode:
    """Create a new taxonomy node (L1/L2/L3)."""
    client = _get_client()
    row = {
        "id": str(uuid.uuid4()),
        "level": data["level"],
        "name": data["name"],
        "parent_id": data.get("parent_id"),
        "sort_order": data.get("sort_order", 0),
    }
    res = await client.table("event_taxonomy").insert(row).select("*").execute()
    if not res.data:
        raise ValueError("Failed to create taxonomy node")
    return _row_to_node(res.data[0])


async def update_taxonomy_node(node_id: str, data: dict[str, Any]) -> TaxonomyNode | None:
    """Update name or sort_order of a taxonomy node."""
    client = _get_client()
    updates = {k: v for k, v in data.items() if v is not None}
    if not updates:
        res = await client.table("event_taxonomy").select("*").eq("id", node_id).execute()
        return _row_to_node(res.data[0]) if res.data else None
    res = await client.table("event_taxonomy").update(updates).eq("id", node_id).execute()
    if res.data:
        return _row_to_node(res.data[0])
    return None


async def delete_taxonomy_node(node_id: str) -> bool:
    """Delete a taxonomy node (cascades to children via FK)."""
    client = _get_client()
    exist = await client.table("event_taxonomy").select("id").eq("id", node_id).execute()
    if not exist.data:
        return False
    await client.table("event_taxonomy").delete().eq("id", node_id).execute()
    return True
