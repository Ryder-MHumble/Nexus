"""List query and filtering logic for institutions.

Provides unified query interface supporting both flat and hierarchy views.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from time import monotonic
from typing import Any

from app.schemas.institution import InstitutionListResponse
from app.services.core.institution.classification import normalize_org_type
from app.services.core.institution.detail_builder import build_list_item
from app.services.core.institution.sorting import sort_institutions
from app.services.core.institution.storage import fetch_all_institutions

_HIERARCHY_CACHE_TTL_SECONDS = 30.0
_hierarchy_cache: dict[
    tuple[str | None, str | None, str | None, bool | None],
    tuple[float, dict],
] = {}


def _normalize_name(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _normalize_display_name(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_department_name(value: Any) -> str:
    text = _normalize_display_name(value)
    return text.strip("，,;；:：|/\\-—_ ")


def _merge_department_name(existing: str, moved: str) -> str:
    old_value = _normalize_department_name(existing)
    moved_value = _normalize_department_name(moved)
    if not moved_value:
        return old_value
    if not old_value:
        return moved_value
    if moved_value in old_value:
        return old_value
    if old_value in moved_value:
        return moved_value
    return f"{old_value} / {moved_value}"


def _build_virtual_org_id(name_key: str) -> str:
    digest = hashlib.sha1(name_key.encode("utf-8")).hexdigest()[:12]
    return f"virtual_org_{digest}"


def _build_virtual_dept_id(org_id: str, dept_key: str) -> str:
    digest = hashlib.sha1(f"{org_id}:{dept_key}".encode("utf-8")).hexdigest()[:12]
    return f"{org_id}_dept_{digest}"


def _derive_virtual_classification(*, region: str, org_type: str) -> str | None:
    normalized_org_type = normalize_org_type(org_type) or org_type
    if normalized_org_type == "高校":
        return "海外高校" if region == "国际" else "其他高校"
    if normalized_org_type == "研究机构":
        return "新研机构"
    if normalized_org_type == "行业学会":
        return "行业学会"
    return None


def _build_virtual_org_record(university_name: str) -> dict[str, Any]:
    from app.services.scholar._filters import (
        _derive_affiliation_type_from_university,
        _derive_region_from_university,
    )

    normalized_name = _normalize_display_name(university_name)
    name_key = _normalize_name(normalized_name)
    region = _derive_region_from_university(normalized_name)
    resolved_org_type = normalize_org_type(_derive_affiliation_type_from_university(normalized_name))
    return {
        "id": _build_virtual_org_id(name_key),
        "name": normalized_name,
        "entity_type": "organization",
        "region": region,
        "org_type": resolved_org_type,
        "classification": _derive_virtual_classification(region=region, org_type=resolved_org_type),
        "sub_classification": None,
    }


def _resolve_hierarchy_org_meta(
    org_name: str,
    source_record: dict[str, Any] | None,
    inst_map: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Resolve region/org_type/classification with scholar filter-compatible rules."""
    from app.services.scholar._filters import _get_org_type, _get_region

    display_name = _normalize_display_name(org_name)
    resolved_region = _get_region(display_name, inst_map)
    resolved_org_type = normalize_org_type(_get_org_type(display_name, inst_map))
    fallback_classification = _derive_virtual_classification(
        region=resolved_region,
        org_type=resolved_org_type or "",
    )

    src = source_record or {}
    return {
        "region": resolved_region,
        "org_type": resolved_org_type,
        "classification": src.get("classification") or fallback_classification,
        "sub_classification": src.get("sub_classification"),
    }


def _match_hierarchy_filters(
    record: dict[str, Any],
    *,
    region: str | None,
    org_type: str | None,
    classification: str | None,
) -> bool:
    if region and record.get("region") != region:
        return False
    if org_type and normalize_org_type(record.get("org_type")) != normalize_org_type(org_type):
        return False
    if classification and record.get("classification") != classification:
        return False
    return True


async def get_institutions_unified(
    view: str = "flat",
    entity_type: str | None = None,
    region: str | None = None,
    org_type: str | None = None,
    classification: str | None = None,
    sub_classification: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    is_adjunct_supervisor: bool | None = None,
) -> InstitutionListResponse | dict:
    """Unified institution query interface.

    Args:
        view: View type ("flat" for list, "hierarchy" for tree structure)
        entity_type: Filter by entity type (organization/department)
        region: Filter by region (国内/国际)
        org_type: Filter by org type (高校/企业/研究机构/行业学会/其他)
        classification: Filter by classification (共建高校/兄弟院校/海外高校/其他高校)
        keyword: Search keyword (matches id or name)
        page: Page number (1-indexed)
        page_size: Items per page
        is_adjunct_supervisor: Filter scholars by adjunct supervisor status

    Returns:
        InstitutionListResponse for flat view, dict for hierarchy view
    """
    normalized_org_type = normalize_org_type(org_type)

    if view == "hierarchy":
        cache_key = (region, normalized_org_type, classification, is_adjunct_supervisor)
        now = monotonic()
        cached = _hierarchy_cache.get(cache_key)
        if cached and (now - cached[0]) < _HIERARCHY_CACHE_TTL_SECONDS:
            return cached[1]

        result = await _get_hierarchy_view(
            region=region,
            org_type=normalized_org_type,
            classification=classification,
            is_adjunct_supervisor=is_adjunct_supervisor,
        )
        _hierarchy_cache[cache_key] = (now, result)
        return result
    else:
        return await _get_flat_view(
            entity_type=entity_type,
            region=region,
            org_type=normalized_org_type,
            classification=classification,
            sub_classification=sub_classification,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )


async def _get_flat_view(
    entity_type: str | None = None,
    region: str | None = None,
    org_type: str | None = None,
    classification: str | None = None,
    sub_classification: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> InstitutionListResponse:
    """Get flat list view of institutions.

    Args:
        entity_type: Filter by entity type
        region: Filter by region
        org_type: Filter by org type
        classification: Filter by classification
        keyword: Search keyword
        page: Page number
        page_size: Items per page

    Returns:
        InstitutionListResponse with paginated results
    """
    normalized_org_type = normalize_org_type(org_type)

    # Fetch all records
    all_records = await fetch_all_institutions()

    # Apply filters
    filtered = _apply_filters(
        all_records,
        entity_type=entity_type,
        region=region,
        org_type=normalized_org_type,
        classification=classification,
        sub_classification=sub_classification,
        keyword=keyword,
    )

    # Sort
    sorted_records = sort_institutions(filtered)

    # Paginate
    total = len(sorted_records)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_records = sorted_records[start_idx:end_idx]

    # Build response items
    items = [build_list_item(rec) for rec in page_records]

    return InstitutionListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
        items=items,
    )


async def _get_hierarchy_view(
    region: str | None = None,
    org_type: str | None = None,
    classification: str | None = None,
    is_adjunct_supervisor: bool | None = None,
) -> dict:
    """Get hierarchy view of institutions (organizations with nested departments).

    Args:
        region: Filter by region
        org_type: Filter by org type
        classification: Filter by classification
        is_adjunct_supervisor: Filter scholars by adjunct supervisor status

    Returns:
        Dict with organizations list, each containing nested departments
    """
    normalized_org_type = normalize_org_type(org_type)

    # Fetch all records
    all_records = await fetch_all_institutions()

    # Always dedupe from full institution set first. Region/type filters are
    # applied after metadata normalization to avoid double-counting the same
    # organization under inconsistent institution-table labels.
    organizations = _apply_filters(
        all_records,
        entity_type="organization",
    )

    # Always use scholar table aggregation as source of truth for counts and
    # to bring in institutions missing from the institutions table.
    (
        scholar_counts,
        university_names_by_key,
        department_names_by_org,
    ) = await _aggregate_scholars_by_institution(
        is_adjunct_supervisor=is_adjunct_supervisor,
    )
    from app.services.scholar._filters import get_institution_classification_map

    inst_map = await get_institution_classification_map()

    # Build parent_id -> departments map.
    departments_by_parent: dict[str, list[dict]] = defaultdict(list)
    for rec in all_records:
        if rec.get("entity_type") != "department":
            continue
        parent_id = rec.get("parent_id")
        if parent_id and rec.get("name"):
            departments_by_parent[parent_id].append(rec)

    # Deduplicate organizations by normalized name.
    sorted_orgs = sort_institutions(organizations)
    orgs_by_name_key: dict[str, dict[str, Any]] = {}
    for org in sorted_orgs:
        org_name = org.get("name")
        name_key = _normalize_name(org_name)
        if not name_key:
            continue
        entry = orgs_by_name_key.get(name_key)
        if entry is None:
            orgs_by_name_key[name_key] = {
                "canonical": org,
                "all_records": [org],
            }
        else:
            entry["all_records"].append(org)

    # Build hierarchy from institutions table first.
    result_orgs = []
    for org_entry in orgs_by_name_key.values():
        org = org_entry["canonical"]
        org_name = org["name"]
        org_name_key = _normalize_name(org_name)
        org_records: list[dict[str, Any]] = org_entry["all_records"]

        # Merge departments from duplicate organization rows.
        all_depts: list[dict[str, Any]] = []
        for org_record in org_records:
            all_depts.extend(departments_by_parent.get(org_record["id"], []))

        # Deduplicate departments by normalized name.
        sorted_depts = sort_institutions(all_depts)
        dept_by_name_key: dict[str, dict[str, Any]] = {}
        for dept in sorted_depts:
            dept_name = dept.get("name")
            dept_key = _normalize_name(dept_name)
            if not dept_key:
                continue
            if dept_key not in dept_by_name_key:
                dept_by_name_key[dept_key] = dept

        # Fill missing department nodes from scholar-derived aggregation to avoid
        # dropping counts when department rows are not configured in institutions.
        for dept_key, dept_name in department_names_by_org.get(org_name_key, {}).items():
            if dept_key in dept_by_name_key:
                continue
            dept_by_name_key[dept_key] = {
                "id": _build_virtual_dept_id(org["id"], dept_key),
                "name": dept_name,
                "entity_type": "department",
                "parent_id": org["id"],
            }

        # Keep hierarchy payload lean for scholar page sidebar.
        resolved_meta = _resolve_hierarchy_org_meta(org_name, org, inst_map)
        org_item = {
            "id": org["id"],
            "name": org["name"],
            "entity_type": org.get("entity_type"),
            "region": resolved_meta.get("region"),
            "org_type": resolved_meta.get("org_type"),
            "classification": resolved_meta.get("classification"),
            "sub_classification": resolved_meta.get("sub_classification"),
        }
        if not _match_hierarchy_filters(
            org_item,
            region=region,
            org_type=normalized_org_type,
            classification=classification,
        ):
            continue

        org_item["scholar_count"] = scholar_counts.get(("org", org_name_key), 0)
        secondary_institutions = sorted(
            [
                {
                    "id": dept["id"],
                    "name": dept["name"],
                    "scholar_count": scholar_counts.get(
                        ("dept", org_name_key, _normalize_name(dept["name"])),
                        0,
                    ),
                }
                for dept in dept_by_name_key.values()
            ],
            key=lambda d: (-int(d.get("scholar_count") or 0), str(d.get("name") or "")),
        )
        org_item["secondary_institutions"] = secondary_institutions
        org_item["departments"] = secondary_institutions

        result_orgs.append(org_item)

    # Append scholar-derived virtual organizations (not yet covered by
    # institutions table) so total count stays consistent with scholar stats.
    covered_org_keys = set(orgs_by_name_key.keys())
    for org_key, scholar_name in university_names_by_key.items():
        if org_key in covered_org_keys:
            continue
        if scholar_counts.get(("org", org_key), 0) <= 0:
            continue

        virtual_org = _build_virtual_org_record(scholar_name)
        resolved_meta = _resolve_hierarchy_org_meta(scholar_name, None, inst_map)
        virtual_org["region"] = resolved_meta.get("region")
        virtual_org["org_type"] = resolved_meta.get("org_type")
        virtual_org["classification"] = resolved_meta.get("classification")
        virtual_org["sub_classification"] = resolved_meta.get("sub_classification")
        if not _match_hierarchy_filters(
            virtual_org,
            region=region,
            org_type=normalized_org_type,
            classification=classification,
        ):
            continue

        org_id = virtual_org["id"]
        departments = []
        for dept_key, dept_name in department_names_by_org.get(org_key, {}).items():
            dept_count = scholar_counts.get(("dept", org_key, dept_key), 0)
            if dept_count <= 0:
                continue
            departments.append(
                {
                    "id": _build_virtual_dept_id(org_id, dept_key),
                    "name": dept_name,
                    "scholar_count": dept_count,
                }
            )
        departments.sort(
            key=lambda d: (-int(d.get("scholar_count") or 0), str(d.get("name") or ""))
        )

        result_orgs.append(
            {
                "id": org_id,
                "name": virtual_org["name"],
                "entity_type": "organization",
                "region": virtual_org.get("region"),
                "org_type": virtual_org.get("org_type"),
                "classification": virtual_org.get("classification"),
                "sub_classification": None,
                "scholar_count": scholar_counts.get(("org", org_key), 0),
                "secondary_institutions": departments,
                "departments": departments,
            }
        )

    # Keep organization order deterministic by scholar_count then name.
    result_orgs.sort(
        key=lambda i: (-int(i.get("scholar_count") or 0), str(i.get("name") or ""))
    )

    return {
        "primary_institutions": result_orgs,
        "organizations": result_orgs,
    }


def _apply_filters(
    records: list[dict],
    entity_type: str | None = None,
    region: str | None = None,
    org_type: str | None = None,
    classification: str | None = None,
    sub_classification: str | None = None,
    keyword: str | None = None,
) -> list[dict]:
    """Apply filters to institution records.

    Args:
        records: List of institution records
        entity_type: Filter by entity type
        region: Filter by region
        org_type: Filter by org type
        classification: Filter by classification
        keyword: Search keyword

    Returns:
        Filtered list of records
    """
    filtered = records
    normalized_org_type = normalize_org_type(org_type)

    if entity_type:
        filtered = [r for r in filtered if r.get("entity_type") == entity_type]

    if region:
        filtered = [r for r in filtered if r.get("region") == region]

    if normalized_org_type:
        filtered = [
            r
            for r in filtered
            if normalize_org_type(r.get("org_type")) == normalized_org_type
        ]

    if classification:
        filtered = [r for r in filtered if r.get("classification") == classification]

    if sub_classification:
        filtered = [r for r in filtered if r.get("sub_classification") == sub_classification]

    if keyword:
        keyword_lower = keyword.lower()
        filtered = [
            r
            for r in filtered
            if keyword_lower in r["id"].lower() or keyword_lower in r["name"].lower()
        ]

    return filtered


async def _aggregate_scholars_by_institution(
    is_adjunct_supervisor: bool | None = None,
) -> tuple[dict[tuple, int], dict[str, str], dict[str, dict[str, str]]]:
    """Count scholars by normalized university and department.

    Args:
        is_adjunct_supervisor: When True, only count adjunct supervisors;
            when False/None, count all scholars.

    Returns:
        Tuple:
        1) Dict mapping (type, university_key[, department_key]) -> scholar count
        2) Dict mapping university_key -> representative university display name
        3) Dict mapping university_key -> {department_key -> representative dept name}
    """
    from app.db.pool import get_pool

    from app.services.scholar._filters import _extract_primary_affiliation

    # SQL aggregation remains fast while preserving raw affiliation text for
    # L1/L2 split normalization in Python.
    where_clauses: list[str] = []
    if is_adjunct_supervisor is True:
        where_clauses.append("COALESCE(adjunct_supervisor->>'status', '') <> ''")
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    sql = f"""
        SELECT
            COALESCE(
                NULLIF(REGEXP_REPLACE(BTRIM(COALESCE(university, '')), '\\s+', ' ', 'g'), ''),
                '未知机构'
            ) AS university_name,
            NULLIF(
                REGEXP_REPLACE(BTRIM(COALESCE(department, '')), '\\s+', ' ', 'g'),
                ''
            ) AS department_name,
            COUNT(*)::int AS scholar_count
        FROM scholars
        {where_sql}
        GROUP BY university_name, department_name
    """
    rows = await get_pool().fetch(sql)

    counts: dict[tuple, int] = defaultdict(int)
    university_names_by_key: dict[str, str] = {}
    department_names_by_org: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        raw_university_name = _normalize_display_name(row.get("university_name") or "")
        raw_department_name = _normalize_department_name(row.get("department_name") or "")
        primary_uni, moved_department = _extract_primary_affiliation(raw_university_name)
        university_name = _normalize_display_name(primary_uni or raw_university_name or "未知机构")
        university_key = _normalize_name(university_name)
        if not university_key:
            continue
        department_name = _merge_department_name(raw_department_name, moved_department)
        department_key = _normalize_name(department_name)
        c = int(row.get("scholar_count") or 0)
        counts[("org", university_key)] += c
        if university_name and university_key not in university_names_by_key:
            university_names_by_key[university_key] = university_name
        if department_key:
            counts[("dept", university_key, department_key)] += c
            if department_name and department_key not in department_names_by_org[university_key]:
                department_names_by_org[university_key][department_key] = department_name

    return dict(counts), university_names_by_key, {
        org_key: dict(dept_map)
        for org_key, dept_map in department_names_by_org.items()
    }
