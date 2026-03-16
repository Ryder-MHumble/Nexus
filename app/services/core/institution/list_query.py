"""List query and filtering logic for institutions.

Provides unified query interface supporting both flat and hierarchy views.
"""

from __future__ import annotations

from app.schemas.institution import InstitutionListResponse
from app.services.core.institution.detail_builder import build_list_item
from app.services.core.institution.sorting import sort_institutions
from app.services.core.institution.storage import fetch_all_institutions


async def get_institutions_unified(
    view: str = "flat",
    entity_type: str | None = None,
    region: str | None = None,
    org_type: str | None = None,
    classification: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
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

    Returns:
        InstitutionListResponse for flat view, dict for hierarchy view
    """
    if view == "hierarchy":
        return await _get_hierarchy_view(
            region=region,
            org_type=org_type,
            classification=classification,
        )
    else:
        return await _get_flat_view(
            entity_type=entity_type,
            region=region,
            org_type=org_type,
            classification=classification,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )


async def _get_flat_view(
    entity_type: str | None = None,
    region: str | None = None,
    org_type: str | None = None,
    classification: str | None = None,
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
    # Fetch all records
    all_records = await fetch_all_institutions()

    # Apply filters
    filtered = _apply_filters(
        all_records,
        entity_type=entity_type,
        region=region,
        org_type=org_type,
        classification=classification,
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
) -> dict:
    """Get hierarchy view of institutions (organizations with nested departments).

    Args:
        region: Filter by region
        org_type: Filter by org type
        classification: Filter by classification

    Returns:
        Dict with organizations list, each containing nested departments
    """
    # Fetch all records
    all_records = await fetch_all_institutions()

    # Filter organizations
    organizations = _apply_filters(
        all_records,
        entity_type="organization",
        region=region,
        org_type=org_type,
        classification=classification,
    )

    # Sort organizations
    sorted_orgs = sort_institutions(organizations)

    # Build hierarchy
    result_orgs = []
    for org in sorted_orgs:
        org_id = org["id"]

        # Find departments for this organization
        departments = [
            rec for rec in all_records if rec.get("parent_id") == org_id
        ]
        sorted_depts = sort_institutions(departments)

        # Build organization item with departments
        org_item = build_list_item(org).model_dump()
        org_item["departments"] = [
            {
                "id": dept["id"],
                "name": dept["name"],
                "scholar_count": dept.get("scholar_count", 0),
            }
            for dept in sorted_depts
        ]

        result_orgs.append(org_item)

    return {"organizations": result_orgs}


def _apply_filters(
    records: list[dict],
    entity_type: str | None = None,
    region: str | None = None,
    org_type: str | None = None,
    classification: str | None = None,
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

    if entity_type:
        filtered = [r for r in filtered if r.get("entity_type") == entity_type]

    if region:
        filtered = [r for r in filtered if r.get("region") == region]

    if org_type:
        filtered = [r for r in filtered if r.get("org_type") == org_type]

    if classification:
        filtered = [r for r in filtered if r.get("classification") == classification]

    if keyword:
        keyword_lower = keyword.lower()
        filtered = [
            r
            for r in filtered
            if keyword_lower in r["id"].lower() or keyword_lower in r["name"].lower()
        ]

    return filtered
