"""Project service — 项目标签化 CRUD（兼容旧表结构）。"""
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
from app.services.core.scholar_tag_sync import sync_project_scholar_memberships


def _get_client():
    from app.db.client import get_client  # noqa: PLC0415

    return get_client()


_PROJECT_COLUMNS_CACHE: set[str] | None = None


async def _get_project_columns() -> set[str]:
    global _PROJECT_COLUMNS_CACHE
    if _PROJECT_COLUMNS_CACHE is not None:
        return _PROJECT_COLUMNS_CACHE

    from app.db.pool import get_pool  # noqa: PLC0415

    rows = await get_pool().fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='projects'
        """,
    )
    _PROJECT_COLUMNS_CACHE = {str(r["column_name"]) for r in rows}
    return _PROJECT_COLUMNS_CACHE


def _generate_id() -> str:
    return "proj_" + uuid.uuid4().hex[:8]


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


def _normalize_row(row: dict) -> dict:
    for f in ("related_scholars", "outputs", "cooperation_institutions", "scholar_ids"):
        v = row.get(f)
        if isinstance(v, str):
            try:
                row[f] = json.loads(v)
            except Exception:
                row[f] = []
        elif v is None and f in ("related_scholars", "outputs", "cooperation_institutions", "scholar_ids"):
            row[f] = []
    return row


def _extract_subcategory(row: dict) -> str:
    if row.get("subcategory"):
        return str(row["subcategory"])

    custom_fields = row.get("custom_fields") or {}
    if isinstance(custom_fields, dict):
        sub = custom_fields.get("subcategory")
        if isinstance(sub, str) and sub.strip():
            return sub.strip()

    tags = row.get("tags") or []
    if isinstance(tags, list):
        for t in tags:
            if not isinstance(t, str):
                continue
            if "-" in t:
                _, sub = t.split("-", 1)
                sub = sub.strip()
                if sub:
                    return sub
    return ""


def _extract_scholar_ids(row: dict) -> list[str]:
    direct = row.get("scholar_ids")
    if isinstance(direct, list):
        return _uniq_ids([str(x) for x in direct])

    rel = row.get("related_scholars") or []
    if isinstance(rel, list):
        ids: list[str] = []
        for item in rel:
            if isinstance(item, str):
                ids.append(item)
                continue
            if not isinstance(item, dict):
                continue
            sid = (
                item.get("scholar_id")
                or item.get("id")
                or item.get("url_hash")
            )
            if sid:
                ids.append(str(sid))
        return _uniq_ids(ids)

    return []


def _to_list_item(row: dict) -> ProjectListItem:
    scholar_ids = _extract_scholar_ids(row)
    title = row.get("title") or row.get("name") or ""
    summary = row.get("summary") or row.get("description") or ""
    return ProjectListItem(
        id=row.get("id", ""),
        category=row.get("category") or "",
        subcategory=_extract_subcategory(row),
        title=title,
        summary=summary or "",
        scholar_count=len(scholar_ids),
        created_at=str(row.get("created_at") or ""),
    )


def _to_detail(row: dict) -> ProjectDetailResponse:
    scholar_ids = _extract_scholar_ids(row)
    title = row.get("title") or row.get("name") or ""
    summary = row.get("summary") or row.get("description") or ""
    return ProjectDetailResponse(
        id=row.get("id", ""),
        category=row.get("category") or "",
        subcategory=_extract_subcategory(row),
        title=title,
        summary=summary or "",
        scholar_ids=scholar_ids,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        custom_fields=row.get("custom_fields") or {},
        extra={},
    )


def _build_tags(category: str, subcategory: str) -> list[str]:
    tags: list[str] = []
    if category:
        tags.append(category)
    if subcategory:
        tags.append(subcategory)
    if category and subcategory:
        tags.append(f"{category}-{subcategory}")
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _build_related_scholars(scholar_ids: list[str]) -> list[dict[str, str]]:
    return [{"scholar_id": sid} for sid in _uniq_ids(scholar_ids)]


def _pick_existing_columns(row: dict[str, Any], columns: set[str]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k in columns}


async def list_projects(
    *,
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    subcategory: str | None = None,
    scholar_id: str | None = None,
    keyword: str | None = None,
    custom_field_key: str | None = None,
    custom_field_value: str | None = None,
) -> ProjectListResponse:
    columns = await _get_project_columns()
    client = _get_client()
    q = client.table("projects").select("*")
    if category:
        q = q.eq("category", category)

    if subcategory and "subcategory" in columns:
        q = q.eq("subcategory", subcategory)

    if keyword:
        or_tokens: list[str] = []
        for col in ("title", "summary", "name", "description"):
            if col in columns:
                or_tokens.append(f"{col}.ilike.%{keyword}%")
        if or_tokens:
            q = q.or_(",".join(or_tokens))

    res = await q.execute()
    rows = [_normalize_row(dict(r)) for r in (res.data or [])]

    if subcategory and "subcategory" not in columns:
        rows = [r for r in rows if _extract_subcategory(r) == subcategory]

    if scholar_id:
        rows = [r for r in rows if scholar_id in _extract_scholar_ids(r)]

    if custom_field_key:
        rows = [
            r
            for r in rows
            if (r.get("custom_fields") or {}).get(custom_field_key) == custom_field_value
        ]

    total = len(rows)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    items = [_to_list_item(r) for r in rows[start: start + page_size]]
    return ProjectListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


async def get_project(project_id: str) -> ProjectDetailResponse | None:
    client = _get_client()
    res = await client.table("projects").select("*").eq("id", project_id).execute()
    if res.data:
        return _to_detail(_normalize_row(dict(res.data[0])))
    return None


async def get_stats() -> ProjectStatsResponse:
    client = _get_client()
    res = await client.table("projects").select("*").execute()
    rows = [_normalize_row(dict(r)) for r in (res.data or [])]

    by_category: dict[str, int] = defaultdict(int)
    by_subcategory: dict[str, int] = defaultdict(int)
    total_related_scholars = 0

    for r in rows:
        category = r.get("category") or "未分类"
        subcategory = _extract_subcategory(r) or "未分类"
        by_category[category] += 1
        by_subcategory[subcategory] += 1
        total_related_scholars += len(_extract_scholar_ids(r))

    return ProjectStatsResponse(
        total=len(rows),
        by_category=[{"category": k, "count": v} for k, v in sorted(by_category.items())],
        by_subcategory=[{"subcategory": k, "count": v} for k, v in sorted(by_subcategory.items())],
        total_related_scholars=total_related_scholars,
    )


async def create_project(payload: dict[str, Any]) -> ProjectDetailResponse:
    columns = await _get_project_columns()
    now = datetime.now(timezone.utc).isoformat()
    project_id = _generate_id()
    scholar_ids = _uniq_ids(payload.get("scholar_ids") or [])
    category = str(payload.get("category") or "").strip()
    subcategory = str(payload.get("subcategory") or "").strip()
    title = str(payload.get("title") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    if not title:
        title = f"{category}-{subcategory}".strip("-") or "未命名项目标签"

    custom_fields = payload.get("custom_fields")
    if custom_fields is None:
        custom_fields = {}
    if not isinstance(custom_fields, dict):
        custom_fields = {}

    db_row = {
        "id": project_id,
        "category": category,
        "subcategory": subcategory,
        "title": title,
        "summary": summary,
        "scholar_ids": scholar_ids,
        "name": title,
        "description": summary,
        "status": "在研",
        "pi_name": "系统标签",
        "related_scholars": _build_related_scholars(scholar_ids),
        "tags": _build_tags(category, subcategory),
        "custom_fields": custom_fields,
        "created_at": now,
        "updated_at": now,
    }
    to_insert = _pick_existing_columns(db_row, columns)

    client = _get_client()
    await client.table("projects").insert(to_insert).execute()

    try:
        await sync_project_scholar_memberships(
            project_id=project_id,
            project_title=title,
            category=category,
            subcategory=subcategory,
            new_scholar_ids=scholar_ids,
            old_scholar_ids=[],
        )
    except Exception:
        pass

    detail = await get_project(project_id)
    if detail is not None:
        return detail
    return _to_detail(db_row)


async def update_project(project_id: str, updates: dict[str, Any]) -> ProjectDetailResponse | None:
    from app.services.core.custom_fields import apply_custom_fields_update  # noqa: PLC0415

    current = await get_project(project_id)
    if current is None:
        return None

    columns = await _get_project_columns()
    db_updates: dict[str, Any] = {}

    new_category = current.category
    new_subcategory = current.subcategory
    new_title = current.title
    new_summary = current.summary
    new_scholar_ids = list(current.scholar_ids)

    if "category" in updates and updates["category"] is not None:
        new_category = str(updates["category"]).strip()
        if "category" in columns:
            db_updates["category"] = new_category

    if "subcategory" in updates and updates["subcategory"] is not None:
        new_subcategory = str(updates["subcategory"]).strip()
        if "subcategory" in columns:
            db_updates["subcategory"] = new_subcategory

    if "title" in updates and updates["title"] is not None:
        new_title = str(updates["title"]).strip()
        if "title" in columns:
            db_updates["title"] = new_title
        if "name" in columns:
            db_updates["name"] = new_title

    if "summary" in updates and updates["summary"] is not None:
        new_summary = str(updates["summary"]).strip()
        if "summary" in columns:
            db_updates["summary"] = new_summary
        if "description" in columns:
            db_updates["description"] = new_summary

    if "scholar_ids" in updates and updates["scholar_ids"] is not None:
        new_scholar_ids = _uniq_ids(updates["scholar_ids"])
        if "scholar_ids" in columns:
            db_updates["scholar_ids"] = new_scholar_ids
        if "related_scholars" in columns:
            db_updates["related_scholars"] = _build_related_scholars(new_scholar_ids)

    if "tags" in columns and (
        "category" in updates
        or "subcategory" in updates
    ):
        db_updates["tags"] = _build_tags(new_category, new_subcategory)

    if "custom_fields" in updates:
        custom_updates = updates["custom_fields"]
        if isinstance(custom_updates, dict):
            client = _get_client()
            cur = await client.table("projects").select("custom_fields").eq("id", project_id).execute()
            merged_holder = {"custom_fields": custom_updates}
            if cur.data:
                apply_custom_fields_update(merged_holder, cur.data[0])
            if "custom_fields" in columns:
                db_updates["custom_fields"] = merged_holder["custom_fields"]

    if "updated_at" in columns:
        db_updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    if not db_updates:
        return current

    client = _get_client()
    await client.table("projects").update(db_updates).eq("id", project_id).execute()

    updated = await get_project(project_id)
    if updated is None:
        return None

    if new_scholar_ids != current.scholar_ids or (
        new_category != current.category or new_subcategory != current.subcategory or new_title != current.title
    ):
        try:
            await sync_project_scholar_memberships(
                project_id=project_id,
                project_title=new_title,
                category=new_category,
                subcategory=new_subcategory,
                new_scholar_ids=new_scholar_ids,
                old_scholar_ids=current.scholar_ids,
            )
        except Exception:
            pass

    return updated


async def delete_project(project_id: str) -> bool:
    current = await get_project(project_id)
    if current is None:
        return False

    client = _get_client()
    await client.table("projects").delete().eq("id", project_id).execute()

    try:
        await sync_project_scholar_memberships(
            project_id=project_id,
            project_title=current.title,
            category=current.category,
            subcategory=current.subcategory,
            new_scholar_ids=[],
            old_scholar_ids=current.scholar_ids,
        )
    except Exception:
        pass

    return True


async def batch_create_projects(
    items: list[dict[str, Any]],
    skip_duplicates: bool = True,
) -> dict[str, Any]:
    """Batch-create projects.

    Duplicate detection: same title + same category + same subcategory.
    """
    client = _get_client()
    existing_res = await client.table("projects").select("*").execute()
    existing_keys: set[tuple[str, str, str]] = set()
    for raw in (existing_res.data or []):
        row = _normalize_row(dict(raw))
        title = (row.get("title") or row.get("name") or "").strip().lower()
        category = (row.get("category") or "").strip().lower()
        subcategory = _extract_subcategory(row).strip().lower()
        existing_keys.add((title, category, subcategory))

    result: dict[str, Any] = {
        "total": len(items),
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "items": [],
    }

    for idx, item in enumerate(items, start=1):
        title = (item.get("title") or "").strip()
        category = (item.get("category") or "").strip()
        subcategory = (item.get("subcategory") or "").strip()
        if not title:
            result["failed"] += 1
            result["items"].append(
                {"row": idx, "status": "failed", "title": "", "reason": "title is required"}
            )
            continue

        key = (title.lower(), category.lower(), subcategory.lower())
        if key in existing_keys:
            if skip_duplicates:
                result["skipped"] += 1
                result["items"].append(
                    {
                        "row": idx,
                        "status": "skipped",
                        "title": title,
                        "reason": "duplicate (same title+category+subcategory)",
                    }
                )
            else:
                result["failed"] += 1
                result["items"].append(
                    {"row": idx, "status": "failed", "title": title, "reason": "duplicate"}
                )
            continue

        try:
            created = await create_project(item)
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
