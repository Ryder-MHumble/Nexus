"""Event service — CRUD 操作（Supabase SDK）."""
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client():
    from app.db.client import get_client  # noqa: PLC0415
    return get_client()


def _clean_date(v: Any) -> str | None:
    if not v or v == "":
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(v))
    return m.group(1) if m else None


def _clean(v: Any, t: str | None = None) -> Any:
    if v is None or v == "":
        return None
    if t == "int":
        try:
            return int(v)
        except Exception:
            return None
    return v


def _db_to_detail(row: dict) -> EventDetailResponse:
    """Map DB columns → EventDetailResponse (handles field name differences)."""
    return EventDetailResponse(
        id=row.get("id", ""),
        category=row.get("category") or "",
        event_type=row.get("event_type") or "",
        series=row.get("series") or "",
        series_number=str(row.get("series_number") or ""),
        speaker_name=row.get("speaker_name") or "",
        speaker_organization=row.get("speaker_organization") or "",
        speaker_position=row.get("speaker_title") or "",   # DB: speaker_title → schema: speaker_position
        speaker_bio=row.get("speaker_bio") or "",
        speaker_photo_url=row.get("speaker_photo_url") or "",
        title=row.get("title", ""),
        abstract=row.get("description") or "",             # DB: description → schema: abstract
        event_date=str(_clean_date(row.get("event_date")) or ""),
        duration=float(row.get("duration") or 0),
        location=row.get("location") or "",
        scholar_ids=row.get("scholar_ids") or [],
        publicity=row.get("publicity") or "",
        needs_email_invitation=row.get("needs_email_invitation") or False,
        certificate_number=row.get("certificate_number") or "",
        created_by=row.get("created_by") or "",
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        audit_status=row.get("audit_status") or "",
        custom_fields=row.get("custom_fields") or {},
    )


def _event_to_db_row(evt: dict) -> dict:
    """Convert API event dict to DB row (maps field names)."""
    return {
        "id": evt.get("id"),
        "title": evt.get("title", ""),
        "category": _clean(evt.get("category")),
        "event_type": _clean(evt.get("event_type")),
        "series": _clean(evt.get("series")),
        "series_number": _clean(evt.get("series_number"), "int"),
        "speaker_name": _clean(evt.get("speaker_name")),
        "speaker_organization": _clean(evt.get("speaker_organization")),
        "speaker_title": _clean(evt.get("speaker_position")),
        "speaker_bio": _clean(evt.get("speaker_bio")),
        "speaker_photo_url": _clean(evt.get("speaker_photo_url")),
        "description": _clean(evt.get("abstract")),
        "event_date": _clean_date(evt.get("event_date")),
        "location": _clean(evt.get("location")),
        "scholar_ids": evt.get("scholar_ids") or [],
        "is_past": evt.get("is_past", False),
        "created_at": _clean(evt.get("created_at")),
        "updated_at": _clean(evt.get("updated_at")),
        "custom_fields": evt.get("custom_fields"),
    }


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

async def get_event_list(
    category: str | None = None,
    event_type: str | None = None,
    series: str | None = None,
    speaker_name: str | None = None,
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
    q = client.table("events").select("*").order("event_date", desc=True)
    if category:
        q = q.eq("category", category)
    if event_type:
        q = q.eq("event_type", event_type)
    if series:
        q = q.eq("series", series)
    if speaker_name:
        q = q.ilike("speaker_name", f"%{speaker_name}%")
    if start_date:
        q = q.gte("event_date", start_date)
    if end_date:
        q = q.lte("event_date", end_date)
    if keyword:
        q = q.or_(f"title.ilike.%{keyword}%,description.ilike.%{keyword}%,speaker_name.ilike.%{keyword}%")
    res = await q.execute()
    rows = res.data or []

    if scholar_id:
        rows = [r for r in rows if scholar_id in (r.get("scholar_ids") or [])]

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
            speaker_name=r.get("speaker_name") or "",
            speaker_organization=r.get("speaker_organization") or "",
            event_date=str(_clean_date(r.get("event_date")) or ""),
            location=r.get("location") or "",
            series_number=str(r.get("series_number") or ""),
            scholar_count=len(r.get("scholar_ids") or []),
            created_at=str(r.get("created_at") or ""),
        )
        for r in rows[start: start + page_size]
    ]
    return EventListResponse(total=total, page=page, page_size=page_size,
                             total_pages=total_pages, items=items)


async def get_event_detail(event_id: str) -> EventDetailResponse | None:
    client = _get_client()
    res = await client.table("events").select("*").eq("id", event_id).execute()
    if res.data:
        return _db_to_detail(res.data[0])
    return None


async def get_event_stats() -> EventStatsResponse:
    client = _get_client()
    res = await client.table("events").select(
        "category,event_type,event_date,speaker_name,scholar_ids"
    ).execute()
    rows = res.data or []
    by_category: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_month: dict[str, int] = {}
    speakers: set[str] = set()
    for r in rows:
        cat = r.get("category") or "未分类"
        by_category[cat] = by_category.get(cat, 0) + 1
        t = r.get("event_type") or "未分类"
        by_type[t] = by_type.get(t, 0) + 1
        d = _clean_date(r.get("event_date"))
        if d:
            m = d[:7]
            by_month[m] = by_month.get(m, 0) + 1
        if r.get("speaker_name"):
            speakers.add(r["speaker_name"])
    return EventStatsResponse(
        total=len(rows),
        by_category=[{"category": k, "count": v} for k, v in by_category.items()],
        by_type=[{"event_type": k, "count": v} for k, v in by_type.items()],
        by_month=[{"month": k, "count": v} for k, v in sorted(by_month.items(), reverse=True)],
        total_speakers=len(speakers),
        avg_duration=0.0,
    )


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

async def create_event(evt_data: dict[str, Any]) -> EventDetailResponse:
    now = datetime.now(timezone.utc).isoformat()
    evt_data["id"] = str(uuid.uuid4())
    evt_data.setdefault("created_at", now)
    evt_data.setdefault("updated_at", now)

    client = _get_client()
    await client.table("events").insert(_event_to_db_row(evt_data)).execute()
    return _db_to_detail(_event_to_db_row(evt_data) | {"id": evt_data["id"]})


async def update_event(event_id: str, updates: dict[str, Any]) -> EventDetailResponse | None:
    from app.services.core.custom_fields import apply_custom_fields_update  # noqa: PLC0415

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    # custom_fields 浅合并
    if "custom_fields" in updates:
        client = _get_client()
        cur = await client.table("events").select("custom_fields").eq("id", event_id).execute()
        if cur.data:
            apply_custom_fields_update(updates, cur.data[0])
        else:
            return None

    db_updates = _event_to_db_row({**updates, "id": event_id})
    db_updates = {k: v for k, v in db_updates.items() if k != "id" and v is not None}
    # custom_fields goes directly, not through _event_to_db_row
    if "custom_fields" in updates:
        db_updates["custom_fields"] = updates["custom_fields"]

    client = _get_client()
    await client.table("events").update(db_updates).eq("id", event_id).execute()

    # Fetch the updated record
    res = await client.table("events").select("*").eq("id", event_id).execute()
    if res.data:
        return _db_to_detail(res.data[0])
    return None


async def delete_event(event_id: str) -> bool:
    client = _get_client()
    exist = await client.table("events").select("id").eq("id", event_id).execute()
    if not exist.data:
        return False
    await client.table("events").delete().eq("id", event_id).execute()
    return True


async def add_scholar_to_event(event_id: str, scholar_id: str) -> EventDetailResponse | None:
    detail = await get_event_detail(event_id)
    if not detail:
        return None
    ids = list(detail.scholar_ids)
    if scholar_id not in ids:
        ids.append(scholar_id)
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

    Duplicate detection: same title + same event_date + same speaker_name.
    Returns summary: {total, success, skipped, failed, items}.
    """
    client = _get_client()

    # Pre-fetch existing events for dedup (title+date+speaker)
    existing_res = await client.table("events").select(
        "id,title,event_date,speaker_name"
    ).execute()
    existing_keys: set[tuple[str, str, str]] = set()
    for r in (existing_res.data or []):
        key = (
            (r.get("title") or "").strip().lower(),
            (str(_clean_date(r.get("event_date")) or "")).strip(),
            (r.get("speaker_name") or "").strip().lower(),
        )
        existing_keys.add(key)

    result: dict[str, Any] = {"total": len(items), "success": 0, "skipped": 0, "failed": 0,
                               "items": []}

    for idx, item in enumerate(items, start=1):
        title = (item.get("title") or "").strip()
        if not title:
            result["failed"] += 1
            result["items"].append({"row": idx, "status": "failed", "title": "",
                                     "reason": "title is required"})
            continue

        key = (
            title.lower(),
            (str(_clean_date(item.get("event_date")) or "")).strip(),
            (item.get("speaker_name") or "").strip().lower(),
        )
        if key in existing_keys:
            if skip_duplicates:
                result["skipped"] += 1
                result["items"].append({"row": idx, "status": "skipped", "title": title,
                                         "reason": "duplicate (same title+date+speaker)"})
            else:
                result["failed"] += 1
                result["items"].append({"row": idx, "status": "failed", "title": title,
                                         "reason": "duplicate"})
            continue

        try:
            created = await create_event(item)
            existing_keys.add(key)  # prevent duplicates within the same batch
            result["success"] += 1
            result["items"].append({"row": idx, "status": "success", "title": title,
                                     "id": created.id})
        except Exception as exc:
            result["failed"] += 1
            result["items"].append({"row": idx, "status": "failed", "title": title,
                                     "reason": str(exc)})

    return result


# ---------------------------------------------------------------------------
# Taxonomy operations
# ---------------------------------------------------------------------------

def _row_to_node(row: dict) -> TaxonomyNode:
    return TaxonomyNode(
        id=row.get("id", ""),
        level=row.get("level", 1),
        name=row.get("name", ""),
        parent_id=row.get("parent_id"),
        sort_order=row.get("sort_order") or 0,
        created_at=str(row.get("created_at") or ""),
    )


async def get_taxonomy_tree() -> TaxonomyTree:
    """Return the full 3-level taxonomy tree."""
    client = _get_client()
    res = await client.table("event_taxonomy").select("*").order("sort_order").execute()
    rows = res.data or []

    # Index by id and group by level
    by_id: dict[str, dict] = {r["id"]: r for r in rows}
    l1_rows = [r for r in rows if r["level"] == 1]
    l2_rows = [r for r in rows if r["level"] == 2]
    l3_rows = [r for r in rows if r["level"] == 3]

    # Build L3 grouped by parent_id
    l3_by_parent: dict[str, list[TaxonomyL3]] = {}
    for r in l3_rows:
        pid = r.get("parent_id") or ""
        l3_by_parent.setdefault(pid, []).append(
            TaxonomyL3(**_row_to_node(r).model_dump())
        )

    # Build L2 grouped by parent_id
    l2_by_parent: dict[str, list[TaxonomyL2]] = {}
    for r in l2_rows:
        pid = r.get("parent_id") or ""
        node = TaxonomyL2(
            **_row_to_node(r).model_dump(),
            children=l3_by_parent.get(r["id"], []),
        )
        l2_by_parent.setdefault(pid, []).append(node)

    # Build L1 list
    l1_items: list[TaxonomyL1] = []
    for r in l1_rows:
        node = TaxonomyL1(
            **_row_to_node(r).model_dump(),
            children=l2_by_parent.get(r["id"], []),
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
