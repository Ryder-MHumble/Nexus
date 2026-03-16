"""Project service — 项目库 CRUD 操作（Supabase SDK）."""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.schemas.project import (
    ProjectDetailResponse,
    ProjectListItem,
    ProjectListResponse,
    ProjectStatsResponse,
)

VALID_STATUSES = {"申请中", "在研", "已结题", "暂停", "终止"}
VALID_CATEGORIES = {"国家级", "省部级", "横向课题", "院内课题", "国际合作", "其他"}


class ProjectNotFoundError(ValueError):
    pass


class ProjectAlreadyExistsError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client():
    from app.db.client import get_client  # noqa: PLC0415
    return get_client()


def _generate_id() -> str:
    return "proj_" + uuid.uuid4().hex[:8]


def _row_to_dict(row: dict) -> dict:
    """Normalize DB row (JSONB fields may be dicts or strings)."""
    for f in ("related_scholars", "outputs", "cooperation_institutions"):
        v = row.get(f)
        if isinstance(v, str):
            try:
                row[f] = json.loads(v)
            except Exception:
                row[f] = []
        elif v is None:
            row[f] = []
    return row


def _to_list_item(p: dict) -> ProjectListItem:
    return ProjectListItem(
        id=p["id"],
        name=p["name"],
        pi_name=p["pi_name"],
        pi_institution=p.get("pi_institution"),
        funder=p.get("funder"),
        funding_amount=p.get("funding_amount"),
        start_year=p.get("start_year"),
        end_year=p.get("end_year"),
        status=p.get("status", "在研"),
        category=p.get("category"),
        tags=p.get("tags") or [],
    )


def _to_detail(p: dict) -> ProjectDetailResponse:
    from app.schemas.project import ProjectScholar, ProjectOutput  # noqa: PLC0415

    scholars = [
        ProjectScholar(**s) if isinstance(s, dict) else s
        for s in (p.get("related_scholars") or [])
    ]
    outputs = [
        ProjectOutput(**o) if isinstance(o, dict) else o
        for o in (p.get("outputs") or [])
    ]
    return ProjectDetailResponse(
        id=p["id"],
        name=p["name"],
        status=p.get("status", "在研"),
        category=p.get("category"),
        pi_name=p["pi_name"],
        pi_institution=p.get("pi_institution"),
        funder=p.get("funder"),
        funding_amount=p.get("funding_amount"),
        start_year=p.get("start_year"),
        end_year=p.get("end_year"),
        description=p.get("description"),
        keywords=p.get("keywords") or [],
        tags=p.get("tags") or [],
        related_scholars=scholars,
        cooperation_institutions=p.get("cooperation_institutions") or [],
        outputs=outputs,
        created_at=p.get("created_at"),
        updated_at=p.get("updated_at"),
        extra=p.get("extra") or {},
        custom_fields=p.get("custom_fields") or {},
    )


def _serialize_for_db(p: dict) -> dict:
    row = {k: v for k, v in p.items()
           if k not in ("keywords", "extra")}  # not in schema
    for f in ("related_scholars", "outputs", "cooperation_institutions"):
        v = row.get(f)
        if isinstance(v, list):
            row[f] = [item.model_dump() if hasattr(item, "model_dump") else item for item in v]
    return row


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

async def list_projects(
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    category: str | None = None,
    funder: str | None = None,
    keyword: str | None = None,
    pi_name: str | None = None,
    tag: str | None = None,
    custom_field_key: str | None = None,
    custom_field_value: str | None = None,
) -> ProjectListResponse:
    client = _get_client()
    q = client.table("projects").select("*")
    if status:
        q = q.eq("status", status)
    if category:
        q = q.eq("category", category)
    if funder:
        q = q.ilike("funder", f"%{funder}%")
    if pi_name:
        q = q.ilike("pi_name", f"%{pi_name}%")
    if keyword:
        q = q.or_(f"name.ilike.%{keyword}%,description.ilike.%{keyword}%")
    res = await q.execute()
    rows = [_row_to_dict(r) for r in (res.data or [])]

    if tag:
        rows = [r for r in rows if tag in (r.get("tags") or [])]

    if custom_field_key:
        rows = [
            r for r in rows
            if (r.get("custom_fields") or {}).get(custom_field_key) == custom_field_value
        ]

    total = len(rows)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    items = [_to_list_item(r) for r in rows[start: start + page_size]]
    return ProjectListResponse(total=total, page=page, page_size=page_size,
                               total_pages=total_pages, items=items)


async def get_project(project_id: str) -> ProjectDetailResponse | None:
    client = _get_client()
    res = await client.table("projects").select("*").eq("id", project_id).execute()
    if res.data:
        return _to_detail(_row_to_dict(res.data[0]))
    return None


async def get_stats() -> ProjectStatsResponse:
    client = _get_client()
    res = await client.table("projects").select(
        "status,category,funder,funding_amount"
    ).execute()
    rows = res.data or []

    by_status: dict[str, int] = defaultdict(int)
    by_category: dict[str, int] = defaultdict(int)
    by_funder_count: dict[str, int] = defaultdict(int)
    by_funder_amount: dict[str, float] = defaultdict(float)
    total_funding = 0.0
    active_count = 0
    for r in rows:
        s = r.get("status", "未知")
        by_status[s] += 1
        if s == "在研":
            active_count += 1
        cat = r.get("category") or "未分类"
        by_category[cat] += 1
        funder = r.get("funder") or "未知"
        by_funder_count[funder] += 1
        amount = float(r.get("funding_amount") or 0)
        by_funder_amount[funder] += amount
        total_funding += amount
    return ProjectStatsResponse(
        total=len(rows),
        by_status=[{"status": k, "count": v} for k, v in sorted(by_status.items())],
        by_category=[{"category": k, "count": v} for k, v in sorted(by_category.items())],
        by_funder=[{"funder": k, "count": by_funder_count[k],
                    "total_amount": by_funder_amount[k]} for k in sorted(by_funder_count)],
        total_funding=total_funding,
        active_count=active_count,
    )


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

async def create_project(payload: dict[str, Any]) -> ProjectDetailResponse:
    now = datetime.now(timezone.utc).isoformat()
    project_id = _generate_id()
    new_project: dict[str, Any] = {
        "id": project_id,
        "created_at": now,
        "updated_at": now,
        **{k: v for k, v in payload.items() if v is not None},
    }
    for list_field in ("related_scholars", "outputs"):
        if isinstance(new_project.get(list_field), list):
            new_project[list_field] = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in new_project[list_field]
            ]

    client = _get_client()
    await client.table("projects").insert(_serialize_for_db(new_project)).execute()
    return _to_detail(new_project)


async def update_project(project_id: str, updates: dict[str, Any]) -> ProjectDetailResponse | None:
    from app.services.core.custom_fields import apply_custom_fields_update  # noqa: PLC0415

    now = datetime.now(timezone.utc).isoformat()
    clean_updates = {k: v for k, v in updates.items() if v is not None}
    clean_updates["updated_at"] = now

    # custom_fields 浅合并：需要先读取现有值
    if "custom_fields" in updates:
        clean_updates["custom_fields"] = updates["custom_fields"]  # 保留 null 值用于合并
        client = _get_client()
        cur = await client.table("projects").select("custom_fields").eq("id", project_id).execute()
        if cur.data:
            apply_custom_fields_update(clean_updates, cur.data[0])
        else:
            return None
    for list_field in ("related_scholars", "outputs"):
        if isinstance(clean_updates.get(list_field), list):
            clean_updates[list_field] = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in clean_updates[list_field]
            ]

    client = _get_client()
    db_updates = {k: v for k, v in clean_updates.items() if k not in ("keywords", "extra")}
    await client.table("projects").update(db_updates).eq("id", project_id).execute()

    # Fetch the updated record
    res = await client.table("projects").select("*").eq("id", project_id).execute()
    if res.data:
        return _to_detail(_row_to_dict(res.data[0]))
    return None


async def delete_project(project_id: str) -> bool:
    client = _get_client()
    exist = await client.table("projects").select("id").eq("id", project_id).execute()
    if not exist.data:
        return False
    await client.table("projects").delete().eq("id", project_id).execute()
    return True


async def batch_create_projects(
    items: list[dict[str, Any]],
    skip_duplicates: bool = True,
) -> dict[str, Any]:
    """Batch-create projects.

    Duplicate detection: same name + same pi_name (case-insensitive).
    Returns summary: {total, success, skipped, failed, items}.
    """
    client = _get_client()

    # Pre-fetch existing (name, pi_name) pairs for dedup
    existing_res = await client.table("projects").select("id,name,pi_name").execute()
    existing_keys: set[tuple[str, str]] = {
        (
            (r.get("name") or "").strip().lower(),
            (r.get("pi_name") or "").strip().lower(),
        )
        for r in (existing_res.data or [])
    }

    result: dict[str, Any] = {"total": len(items), "success": 0, "skipped": 0, "failed": 0,
                               "items": []}

    for idx, item in enumerate(items, start=1):
        name = (item.get("name") or "").strip()
        pi_name = (item.get("pi_name") or "").strip()
        if not name:
            result["failed"] += 1
            result["items"].append({"row": idx, "status": "failed", "name": "",
                                     "reason": "name is required"})
            continue
        if not pi_name:
            result["failed"] += 1
            result["items"].append({"row": idx, "status": "failed", "name": name,
                                     "reason": "pi_name is required"})
            continue

        key = (name.lower(), pi_name.lower())
        if key in existing_keys:
            if skip_duplicates:
                result["skipped"] += 1
                result["items"].append({"row": idx, "status": "skipped", "name": name,
                                         "reason": "duplicate (same name+pi_name)"})
            else:
                result["failed"] += 1
                result["items"].append({"row": idx, "status": "failed", "name": name,
                                         "reason": "duplicate"})
            continue

        try:
            created = await create_project(item)
            existing_keys.add(key)  # prevent within-batch duplicates
            result["success"] += 1
            result["items"].append({"row": idx, "status": "success", "name": name,
                                     "id": created.id})
        except Exception as exc:
            result["failed"] += 1
            result["items"].append({"row": idx, "status": "failed", "name": name,
                                     "reason": str(exc)})

    return result
