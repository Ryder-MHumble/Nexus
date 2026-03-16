"""Scholar service — public API for loading, filtering, and updating scholar data.

Internal implementation is split across private sub-modules:
  _data.py         — unified scholars.json loading and annotation merging
  _filters.py      — multi-field filtering helpers
  _transformers.py — response shape converters (_to_list_item, _to_detail)
"""
from __future__ import annotations

import json
import logging
import math
from collections import Counter
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

from app.services.stores import scholar_annotation_store as annotation_store
from app.services.stores import supervised_student_store as student_store
from app.services.scholar._data import (
    SCHOLARS_FILE,
    _find_raw_file_by_hash,
    _load_all_with_annotations,
    _load_all_with_annotations_async,
)
from app.services.scholar._filters import (
    _apply_filters,
    get_institution_classification_map,
)
from app.services.scholar._transformers import _to_detail, _to_list_item
from app.services.scholar._create import import_scholars_excel, _parse_excel_row  # noqa: F401


# ---------------------------------------------------------------------------
# Create operation (async, Supabase-first)
# ---------------------------------------------------------------------------


async def create_scholar(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Create a new scholar record, saving to Supabase (with JSON fallback).

    Returns:
        (scholar_detail_dict, "")  on success
        (None, "duplicate:{url_hash}")  on duplicate
        (None, error_message)  on error
    """
    from app.crawlers.utils.dedup import compute_url_hash  # noqa: PLC0415

    name = (data.get("name") or "").strip()
    if not name:
        return None, "name is required"

    university = (data.get("university") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    profile_url = (data.get("profile_url") or "").strip()
    department = (data.get("department") or "").strip()

    dept_part = f"/{department}" if department else ""
    url = profile_url or f"manual://{name}@{university}{dept_part}"
    url_hash = compute_url_hash(url)

    # --- Try Supabase ---
    try:
        from app.db.client import get_client  # noqa: PLC0415
        client = get_client()

        # Duplicate check by url_hash (same URL = same scholar)
        dup_check = await client.table("scholars").select("id").eq("id", url_hash).execute()
        if dup_check.data:
            return None, f"duplicate:{url_hash}"

        # Also check same name + university combination
        name_check = await (
            client.table("scholars")
            .select("id,name,university,email,phone")
            .eq("name", name)
            .execute()
        )
        for existing in (name_check.data or []):
            if (existing.get("university") or "").lower() != university.lower():
                continue
            existing_email = (existing.get("email") or "").strip()
            existing_phone = (existing.get("phone") or "").strip()
            has_contact = bool(email or phone)
            existing_has_contact = bool(existing_email or existing_phone)
            if not has_contact and not existing_has_contact:
                return None, f"duplicate:{existing['id']}"
            if has_contact and existing_has_contact:
                if email and email.lower() == existing_email.lower():
                    return None, f"duplicate:{existing['id']}"
                if phone and phone == existing_phone:
                    return None, f"duplicate:{existing['id']}"

        record: dict[str, Any] = {
            "id": url_hash,
            "source_url": url,
            "name": name,
            "name_en": data.get("name_en") or "",
            "gender": data.get("gender") or "",
            "photo_url": data.get("photo_url") or "",
            "university": university,
            "department": department,
            "secondary_departments": data.get("secondary_departments") or [],
            "position": data.get("position") or "",
            "academic_titles": data.get("academic_titles") or [],
            "is_academician": bool(data.get("is_academician", False)),
            "research_areas": data.get("research_areas") or [],
            "keywords": data.get("keywords") or [],
            "bio": data.get("bio") or "",
            "bio_en": data.get("bio_en") or "",
            "email": email,
            "phone": phone,
            "office": data.get("office") or "",
            "profile_url": profile_url,
            "lab_url": data.get("lab_url") or "",
            "google_scholar_url": data.get("google_scholar_url") or "",
            "dblp_url": data.get("dblp_url") or "",
            "orcid": data.get("orcid") or "",
            "phd_institution": data.get("phd_institution") or "",
            "phd_year": int(data["phd_year"]) if data.get("phd_year") else None,
            "education": data.get("education") or [],
            "publications_count": -1,
            "h_index": -1,
            "citations_count": -1,
            "representative_publications": [],
            "patents": [],
            "awards": [],
            "is_advisor_committee": False,
            "adjunct_supervisor": {"status": "", "type": "", "agreement_type": "", "agreement_period": "", "recommender": ""},
            "is_potential_recruit": False,
            "institute_relation_notes": "",
            "supervised_students": [],
            "joint_research_projects": [],
            "joint_management_roles": [],
            "academic_exchange_records": [],
            "relation_updated_by": "",
            "relation_updated_at": None,
            "recent_updates": [],
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "metrics_updated_at": None,
        }
        await client.table("scholars").insert(record).execute()
        return await get_scholar_detail(url_hash), ""

    except Exception as exc:
        logger.error("DB create_scholar failed: %s", exc, exc_info=True)
        return None, f"save failed: {exc}"


async def import_scholars_async(
    file_content: bytes,
    filename: str,
    skip_duplicates: bool = True,
    added_by: str = "user",
) -> dict[str, Any]:
    """Async version of Excel/CSV import — saves each record to Supabase via create_scholar.

    Returns a summary dict compatible with ScholarImportResult schema.
    """
    import csv  # noqa: PLC0415
    from io import StringIO, BytesIO  # noqa: PLC0415

    result: dict[str, Any] = {"total": 0, "success": 0, "skipped": 0, "failed": 0, "items": []}

    # --- Parse file ---
    try:
        is_csv = filename.lower().endswith(".csv")
        if is_csv:
            text = file_content.decode("utf-8-sig")
            reader = csv.DictReader(StringIO(text))
            rows = list(reader)
        else:
            try:
                import openpyxl  # noqa: PLC0415
            except ImportError:
                result["failed"] = 1
                result["items"].append({"row": 0, "status": "failed", "name": "",
                                        "reason": "openpyxl not installed"})
                return result
            wb = openpyxl.load_workbook(BytesIO(file_content), read_only=True)
            ws = wb.active
            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
            headers = [str(c).strip() if c else "" for c in header_row]
            rows = []
            for rv in ws.iter_rows(min_row=2, values_only=True):
                row_dict = {}
                for ci, val in enumerate(rv):
                    if ci < len(headers):
                        row_dict[headers[ci]] = str(val).strip() if val else ""
                rows.append(row_dict)
    except Exception as exc:
        logger.error("Failed to parse file %s: %s", filename, exc, exc_info=True)
        result["failed"] = 1
        result["items"].append({"row": 0, "status": "failed", "name": "",
                                 "reason": f"parse error: {exc}"})
        return result

    result["total"] = len(rows)

    for row_idx, row in enumerate(rows, start=1):
        parsed = _parse_excel_row(row)
        name = parsed.get("name", "").strip()
        if not name:
            result["failed"] += 1
            result["items"].append({"row": row_idx, "status": "failed", "name": "",
                                     "reason": "name is required"})
            continue

        parsed["added_by"] = added_by
        detail, error = await create_scholar(parsed)

        if error.startswith("duplicate:"):
            existing_hash = error.split(":", 1)[1]
            if skip_duplicates:
                result["skipped"] += 1
                result["items"].append({"row": row_idx, "status": "skipped", "name": name,
                                         "url_hash": existing_hash, "reason": "duplicate"})
            else:
                result["failed"] += 1
                result["items"].append({"row": row_idx, "status": "failed", "name": name,
                                         "reason": "duplicate"})
        elif error:
            result["failed"] += 1
            result["items"].append({"row": row_idx, "status": "failed", "name": name,
                                     "reason": error})
        else:
            result["success"] += 1
            result["items"].append({"row": row_idx, "status": "success", "name": name,
                                     "url_hash": detail["url_hash"] if detail else ""})

    return result


async def batch_create_scholars(
    items: list[dict[str, Any]],
    skip_duplicates: bool = True,
    added_by: str = "user",
) -> dict[str, Any]:
    """Batch-create scholars from a list of dicts.  Each dict uses the same field
    names as ScholarCreateRequest.  Returns a summary dict.
    """
    result: dict[str, Any] = {"total": len(items), "success": 0, "skipped": 0, "failed": 0,
                               "items": []}
    for row_idx, data in enumerate(items, start=1):
        name = (data.get("name") or "").strip()
        if not name:
            result["failed"] += 1
            result["items"].append({"row": row_idx, "status": "failed", "name": "",
                                     "reason": "name is required"})
            continue

        data_with_by = {**data, "added_by": added_by}
        detail, error = await create_scholar(data_with_by)

        if error.startswith("duplicate:"):
            existing_hash = error.split(":", 1)[1]
            if skip_duplicates:
                result["skipped"] += 1
                result["items"].append({"row": row_idx, "status": "skipped", "name": name,
                                         "url_hash": existing_hash, "reason": "duplicate"})
            else:
                result["failed"] += 1
                result["items"].append({"row": row_idx, "status": "failed", "name": name,
                                         "reason": "duplicate"})
        elif error:
            result["failed"] += 1
            result["items"].append({"row": row_idx, "status": "failed", "name": name,
                                     "reason": error})
        else:
            result["success"] += 1
            result["items"].append({"row": row_idx, "status": "success", "name": name,
                                     "url_hash": detail["url_hash"] if detail else ""})

    return result


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


async def _resolve_institution_names_by_group_or_category(
    group: str | None,
    category: str | None,
) -> list[str] | None:
    """通过 institution_group 或 institution_category 查找机构名称列表，用于学者过滤."""
    if not group and not category:
        return None
    try:
        from app.services.core.institution import get_institution_list  # noqa: PLC0415
        result = await get_institution_list(
            group=group,
            category=category,
            type_filter="university",
            page_size=500,
        )
        return [item.name for item in result.items]
    except Exception as exc:
        logger.warning("Failed to resolve institution names for group=%s category=%s: %s", group, category, exc)
        return None


async def get_scholar_list(
    *,
    university: str | None = None,
    department: str | None = None,
    position: str | None = None,
    is_academician: bool | None = None,
    is_potential_recruit: bool | None = None,
    is_advisor_committee: bool | None = None,
    is_adjunct_supervisor: bool | None = None,
    has_email: bool | None = None,
    keyword: str | None = None,
    region: str | None = None,
    affiliation_type: str | None = None,
    institution_group: str | None = None,
    institution_category: str | None = None,
    page: int = 1,
    page_size: int = 20,
    custom_field_key: str | None = None,
    custom_field_value: str | None = None,
) -> dict[str, Any]:
    # Resolve institution_group/category → list of institution names for filtering
    institution_names: list[str] | None = None
    if institution_group or institution_category:
        institution_names = await _resolve_institution_names_by_group_or_category(
            institution_group, institution_category
        )

    items = await _load_all_with_annotations_async()

    # Fetch DB-based classification map when region/affiliation_type filter is active
    inst_map: dict = {}
    if region or affiliation_type:
        inst_map = await get_institution_classification_map()

    filtered = _apply_filters(
        items,
        university=university,
        department=department,
        position=position,
        is_academician=is_academician,
        is_potential_recruit=is_potential_recruit,
        is_advisor_committee=is_advisor_committee,
        is_adjunct_supervisor=is_adjunct_supervisor,
        has_email=has_email,
        keyword=keyword,
        region=region,
        affiliation_type=affiliation_type,
        institution_names=institution_names,
        custom_field_key=custom_field_key,
        custom_field_value=custom_field_value,
        inst_map=inst_map,
    )

    filtered.sort(key=lambda i: i.get("name", ""))

    total = len(filtered)
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    start = (page - 1) * page_size
    page_items = filtered[start : start + page_size]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": [_to_list_item(i) for i in page_items],
    }


async def get_scholar_detail(url_hash: str) -> dict[str, Any] | None:
    """Return full scholar detail merged with annotations, or None if not found."""
    items = await _load_all_with_annotations_async()
    for item in items:
        if item.get("url_hash", "") == url_hash:
            detail = _to_detail(item)
            detail["supervised_students_count"] = student_store.count_students(url_hash)
            return detail
    return None


async def get_scholar_stats() -> dict[str, Any]:
    items = await _load_all_with_annotations_async()

    total = len(items)
    academicians = sum(1 for i in items if i.get("is_academician", False))
    potential_recruits = sum(1 for i in items if i.get("is_potential_recruit", False))
    advisor_committee = sum(1 for i in items if i.get("is_advisor_committee", False))
    adjunct_supervisors = sum(
        1 for i in items
        if (i.get("adjunct_supervisor") or {}).get("status")
    )

    uni_counter: Counter = Counter()
    dept_counter: Counter = Counter()
    pos_counter: Counter = Counter()

    for item in items:
        uni = item.get("university", "") or "未知"
        uni_counter[uni] += 1
        dept = item.get("department", "") or "未知"
        dept_counter[(uni, dept)] += 1
        pos = item.get("position", "") or "未知"
        pos_counter[pos] += 1

    return {
        "total": total,
        "academicians": academicians,
        "potential_recruits": potential_recruits,
        "advisor_committee": advisor_committee,
        "adjunct_supervisors": adjunct_supervisors,
        "by_university": [
            {"university": u, "count": c}
            for u, c in uni_counter.most_common(15)
        ],
        "by_department": [
            {"university": u, "department": d, "count": c}
            for (u, d), c in dept_counter.most_common(30)
        ],
        "by_position": [
            {"position": p, "count": c}
            for p, c in pos_counter.most_common(10)
        ],
    }


# ---------------------------------------------------------------------------
# Write helpers (delegate to annotation_store)
# ---------------------------------------------------------------------------


async def update_scholar_relation(url_hash: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    if await get_scholar_detail(url_hash) is None:
        return None
    annotation_store.update_relation(url_hash, updates)
    return await get_scholar_detail(url_hash)


async def add_scholar_update(url_hash: str, update: dict[str, Any]) -> dict[str, Any] | None:
    if await get_scholar_detail(url_hash) is None:
        return None
    annotation_store.add_user_update(url_hash, update)
    return await get_scholar_detail(url_hash)


async def delete_scholar_update(url_hash: str, update_idx: int) -> dict[str, Any] | None:
    if await get_scholar_detail(url_hash) is None:
        return None
    annotation_store.delete_user_update(url_hash, update_idx)
    return await get_scholar_detail(url_hash)


async def update_scholar_achievements(url_hash: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    if await get_scholar_detail(url_hash) is None:
        return None
    annotation_store.update_achievements(url_hash, updates)
    return await get_scholar_detail(url_hash)


# ---------------------------------------------------------------------------
# Raw JSON modification helpers
# ---------------------------------------------------------------------------


async def update_scholar_basic(url_hash: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update basic scholar information.

    Tries Supabase DB first (mirrors the read path), falls back to local JSON file.
    Returns the updated full detail (merged with annotations) or None if not found.
    """
    # Build the payload to write (exclude meta-param, add audit fields)
    db_updates: dict[str, Any] = {}
    for key, value in updates.items():
        if key == "updated_by":
            continue
        if isinstance(value, list):
            db_updates[key] = [
                v.model_dump() if hasattr(v, "model_dump") else v
                for v in value
            ]
        else:
            db_updates[key] = value
    db_updates["updated_at"] = datetime.now(UTC).isoformat()

    # custom_fields 浅合并
    if "custom_fields" in db_updates:
        from app.services.core.custom_fields import apply_custom_fields_update  # noqa: PLC0415
        try:
            from app.db.client import get_client as _gc  # noqa: PLC0415
            cur = await _gc().table("scholars").select("custom_fields").eq("id", url_hash).execute()
            if cur.data:
                apply_custom_fields_update(db_updates, cur.data[0])
        except Exception:
            pass  # fallback: write as-is

    # --- Try Supabase first (matches the read path) ---
    try:
        from app.db.client import get_client  # noqa: PLC0415
        client = get_client()
        # Check existence first (supabase-py v2 update() returns [] by default without .select())
        exist = await client.table("scholars").select("id").eq("id", url_hash).execute()
        if exist.data:
            await client.table("scholars").update(db_updates).eq("id", url_hash).execute()
            return await get_scholar_detail(url_hash)
        # Not in DB → fall through to JSON fallback
    except Exception as exc:
        logger.warning("Supabase update_scholar_basic failed, trying local JSON: %s", exc)

    # --- Fallback: local JSON file ---
    result = _find_raw_file_by_hash(url_hash)
    if result is None:
        return None

    file_path, item_idx = result

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    scholar = data["scholars"][item_idx]
    scholar.update(db_updates)
    data["scholars"][item_idx] = scholar

    tmp_path = file_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp_path.replace(file_path)

    return await get_scholar_detail(url_hash)


async def delete_scholar(url_hash: str) -> bool:
    """Delete a scholar record (Supabase-first, JSON fallback)."""
    # --- Try Supabase first ---
    try:
        from app.db.client import get_client  # noqa: PLC0415
        client = get_client()
        # supabase-py v2 delete() also returns [] by default without .select()
        exist = await client.table("scholars").select("id").eq("id", url_hash).execute()
        if exist.data:
            await client.table("scholars").delete().eq("id", url_hash).execute()
            annotation_store.delete_all_for_faculty(url_hash)
            student_store.delete_all_students(url_hash)
            return True
        # Not in DB → fall through to JSON
    except Exception as exc:
        logger.warning("DB delete_scholar failed, trying JSON: %s", exc)

    # --- Fallback: local JSON file ---
    try:
        result = _find_raw_file_by_hash(url_hash)
        if result is None:
            return False

        file_path, item_idx = result

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        scholars = data.get("scholars", [])
        if item_idx >= len(scholars) or scholars[item_idx].get("url_hash") != url_hash:
            return False

        scholars.pop(item_idx)
        data["scholars"] = scholars
        data["last_updated"] = datetime.now(UTC).isoformat()

        tmp_path = file_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(file_path)

        annotation_store.delete_all_for_faculty(url_hash)
        student_store.delete_all_students(url_hash)
        return True

    except Exception as exc:
        logger.error("Error deleting scholar %s: %s", url_hash, exc, exc_info=True)
        return False
