"""Venue service — CRUD 操作（Supabase SDK）.

venues 表结构：
  id             text  PK (venue_<hex8>)
  name           text  NOT NULL   缩写/简称
  full_name      text  NULLABLE   全称
  type           text  NOT NULL   conference | journal
  rank           text  NULLABLE   A* | A | B | C
  fields         text[]           研究领域标签
  description    text  NULLABLE   简介
  h5_index       int   NULLABLE   H5 指数
  acceptance_rate float NULLABLE  录用率（0-1）
  impact_factor  float NULLABLE   影响因子（期刊）
  publisher      text  NULLABLE   出版商/主办方
  website        text  NULLABLE   官网 URL
  issn           text  NULLABLE   ISSN（期刊）
  frequency      text  NULLABLE   出版频率
  is_active      bool  DEFAULT true
  custom_fields  jsonb DEFAULT '{}'
  created_at     timestamptz DEFAULT now()
  updated_at     timestamptz DEFAULT now()
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.schemas.venue import (
    VenueBatchResult,
    VenueCreate,
    VenueDetailResponse,
    VenueListItem,
    VenueListResponse,
    VenueStatsResponse,
    VenueUpdate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client():
    from app.db.client import get_client  # noqa: PLC0415
    return get_client()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id() -> str:
    return "venue_" + uuid.uuid4().hex[:8]


def _clean(v: Any) -> Any:
    if v is None or v == "":
        return None
    return v


def _db_to_list_item(row: dict) -> VenueListItem:
    return VenueListItem(
        id=row.get("id", ""),
        name=row.get("name", ""),
        full_name=row.get("full_name"),
        type=row.get("type", "conference"),
        rank=row.get("rank"),
        fields=row.get("fields") or [],
        description=row.get("description"),
        h5_index=row.get("h5_index"),
        acceptance_rate=row.get("acceptance_rate"),
        impact_factor=row.get("impact_factor"),
        is_active=row.get("is_active", True),
    )


def _db_to_detail(row: dict) -> VenueDetailResponse:
    return VenueDetailResponse(
        id=row.get("id", ""),
        name=row.get("name", ""),
        full_name=row.get("full_name"),
        type=row.get("type", "conference"),
        rank=row.get("rank"),
        fields=row.get("fields") or [],
        description=row.get("description"),
        h5_index=row.get("h5_index"),
        acceptance_rate=row.get("acceptance_rate"),
        impact_factor=row.get("impact_factor"),
        publisher=row.get("publisher"),
        website=row.get("website"),
        issn=row.get("issn"),
        frequency=row.get("frequency"),
        is_active=row.get("is_active", True),
        custom_fields=row.get("custom_fields") or {},
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

async def get_venue_list(
    type: str | None = None,
    rank: str | None = None,
    field: str | None = None,
    keyword: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> VenueListResponse:
    client = _get_client()
    q = client.table("venues").select("*", count="exact")

    if type:
        q = q.eq("type", type)
    if rank:
        q = q.eq("rank", rank)
    if is_active is not None:
        q = q.eq("is_active", is_active)
    if field:
        # PostgreSQL array contains operator via filter
        q = q.contains("fields", [field])
    if keyword:
        q = q.or_(f"name.ilike.%{keyword}%,full_name.ilike.%{keyword}%,description.ilike.%{keyword}%")

    q = q.order("name")
    offset = (page - 1) * page_size
    q = q.range(offset, offset + page_size - 1)

    res = await q.execute()
    rows = res.data or []
    total = res.count or 0
    total_pages = max(1, (total + page_size - 1) // page_size)

    return VenueListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=[_db_to_list_item(r) for r in rows],
    )


async def get_venue_detail(venue_id: str) -> VenueDetailResponse | None:
    client = _get_client()
    res = await client.table("venues").select("*").eq("id", venue_id).limit(1).execute()
    if not res.data:
        return None
    return _db_to_detail(res.data[0])


async def get_venue_stats() -> VenueStatsResponse:
    client = _get_client()
    res = await client.table("venues").select("type, rank, fields").execute()
    rows = res.data or []

    # by_type
    type_counts: dict[str, int] = {}
    rank_counts: dict[str, int] = {}
    field_counts: dict[str, int] = {}
    for row in rows:
        t = row.get("type") or "unknown"
        type_counts[t] = type_counts.get(t, 0) + 1

        r = row.get("rank") or "unknown"
        rank_counts[r] = rank_counts.get(r, 0) + 1

        for f in (row.get("fields") or []):
            field_counts[f] = field_counts.get(f, 0) + 1

    rank_order = ["A*", "A", "B", "C", "unknown"]

    return VenueStatsResponse(
        total=len(rows),
        by_type=[{"type": k, "count": v} for k, v in sorted(type_counts.items())],
        by_rank=[
            {"rank": k, "count": rank_counts[k]}
            for k in rank_order
            if k in rank_counts
        ],
        by_field=sorted(
            [{"field": k, "count": v} for k, v in field_counts.items()],
            key=lambda x: -x["count"],
        ),
    )


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

async def create_venue(data: VenueCreate) -> VenueDetailResponse:
    client = _get_client()
    now = _now_iso()
    row = {
        "id": _gen_id(),
        "name": data.name,
        "full_name": _clean(data.full_name),
        "type": data.type,
        "rank": _clean(data.rank),
        "fields": data.fields or [],
        "description": _clean(data.description),
        "h5_index": data.h5_index,
        "acceptance_rate": data.acceptance_rate,
        "impact_factor": data.impact_factor,
        "publisher": _clean(data.publisher),
        "website": _clean(data.website),
        "issn": _clean(data.issn),
        "frequency": _clean(data.frequency),
        "is_active": data.is_active,
        "custom_fields": data.custom_fields or {},
        "created_at": now,
        "updated_at": now,
    }
    res = await client.table("venues").insert(row).execute()
    return _db_to_detail(res.data[0])


async def update_venue(venue_id: str, data: VenueUpdate) -> VenueDetailResponse | None:
    client = _get_client()
    # Check exists
    existing = await client.table("venues").select("custom_fields").eq("id", venue_id).limit(1).execute()
    if not existing.data:
        return None

    patch: dict[str, Any] = {"updated_at": _now_iso()}

    if data.name is not None:
        patch["name"] = data.name
    if data.full_name is not None:
        patch["full_name"] = data.full_name
    if data.type is not None:
        patch["type"] = data.type
    if data.rank is not None:
        patch["rank"] = data.rank
    if data.fields is not None:
        patch["fields"] = data.fields
    if data.description is not None:
        patch["description"] = data.description
    if data.h5_index is not None:
        patch["h5_index"] = data.h5_index
    if data.acceptance_rate is not None:
        patch["acceptance_rate"] = data.acceptance_rate
    if data.impact_factor is not None:
        patch["impact_factor"] = data.impact_factor
    if data.publisher is not None:
        patch["publisher"] = data.publisher
    if data.website is not None:
        patch["website"] = data.website
    if data.issn is not None:
        patch["issn"] = data.issn
    if data.frequency is not None:
        patch["frequency"] = data.frequency
    if data.is_active is not None:
        patch["is_active"] = data.is_active
    if data.custom_fields is not None:
        # Shallow merge: null values delete the key
        base = existing.data[0].get("custom_fields") or {}
        merged = {**base, **data.custom_fields}
        patch["custom_fields"] = {k: v for k, v in merged.items() if v is not None}

    res = await client.table("venues").update(patch).eq("id", venue_id).execute()
    if not res.data:
        return None
    return _db_to_detail(res.data[0])


async def delete_venue(venue_id: str) -> bool:
    client = _get_client()
    existing = await client.table("venues").select("id").eq("id", venue_id).limit(1).execute()
    if not existing.data:
        return False
    await client.table("venues").delete().eq("id", venue_id).execute()
    return True


# ---------------------------------------------------------------------------
# Batch create
# ---------------------------------------------------------------------------

async def batch_create_venues(items: list[dict]) -> VenueBatchResult:
    client = _get_client()
    # Fetch existing names to detect duplicates
    existing_res = await client.table("venues").select("name").execute()
    existing_names = {r["name"].lower() for r in (existing_res.data or [])}

    results: list[dict] = []
    success = skipped = failed = 0
    now = _now_iso()

    for item in items:
        name = item.get("name", "")
        if name.lower() in existing_names:
            skipped += 1
            results.append({"name": name, "status": "skipped", "reason": "already_exists"})
            continue
        try:
            row = {
                "id": _gen_id(),
                "name": name,
                "full_name": _clean(item.get("full_name")),
                "type": item.get("type", "conference"),
                "rank": _clean(item.get("rank")),
                "fields": item.get("fields") or [],
                "description": _clean(item.get("description")),
                "h5_index": item.get("h5_index"),
                "acceptance_rate": item.get("acceptance_rate"),
                "impact_factor": item.get("impact_factor"),
                "publisher": _clean(item.get("publisher")),
                "website": _clean(item.get("website")),
                "issn": _clean(item.get("issn")),
                "frequency": _clean(item.get("frequency")),
                "is_active": item.get("is_active", True),
                "custom_fields": item.get("custom_fields") or {},
                "created_at": now,
                "updated_at": now,
            }
            await client.table("venues").insert(row).execute()
            existing_names.add(name.lower())
            success += 1
            results.append({"name": name, "status": "success"})
        except Exception as e:
            failed += 1
            results.append({"name": name, "status": "failed", "reason": str(e)})

    return VenueBatchResult(success=success, skipped=skipped, failed=failed, items=results)
