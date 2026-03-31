"""Taxonomy and statistics for institutions.

Provides classification hierarchy statistics and aggregated counts.
"""

from __future__ import annotations

from collections import defaultdict

from app.db.client import get_client
from app.schemas.institution import InstitutionStatsResponse
from app.services.core.institution.classification import normalize_org_type
from app.services.core.institution.sorting import (
    CLASSIFICATION_ORDER,
    ORG_TYPE_ORDER,
    REGION_ORDER,
)
from app.services.core.institution.storage import fetch_all_institutions


async def get_institution_stats() -> InstitutionStatsResponse:
    """Get institution statistics.

    Returns:
        InstitutionStatsResponse with counts by category, priority, etc.
    """
    all_records = await fetch_all_institutions()

    # Count by category (old field)
    by_category = defaultdict(int)
    for rec in all_records:
        category = rec.get("category")
        if category:
            by_category[category] += 1

    # Count by priority
    by_priority = defaultdict(int)
    for rec in all_records:
        priority = rec.get("priority")
        if priority is not None:
            priority_str = f"P{priority}" if isinstance(priority, int) else priority
            by_priority[priority_str] += 1

    # Sum student and mentor counts
    total_students_24 = sum(rec.get("student_count_24", 0) or 0 for rec in all_records)
    total_students_25 = sum(rec.get("student_count_25", 0) or 0 for rec in all_records)
    total_mentors = sum(rec.get("mentor_count", 0) or 0 for rec in all_records)

    organizations = [r for r in all_records if r.get("entity_type") == "organization"]
    departments = [r for r in all_records if r.get("entity_type") == "department"]
    total_students = total_students_24 + total_students_25

    # Query actual scholar count directly from scholars table
    client = get_client()
    scholars_resp = await client.table("scholars").select("id", count="exact").limit(1).execute()
    total_scholars = scholars_resp.count or 0

    return InstitutionStatsResponse(
        total_primary_institutions=len(organizations),
        total_secondary_institutions=len(departments),
        total_universities=len(organizations),
        total_departments=len(departments),
        total_scholars=total_scholars,
        by_category=[{"classification": k, "count": v} for k, v in sorted(by_category.items())],
        by_priority=[{"priority": k, "count": v} for k, v in sorted(by_priority.items())],
        total_students=total_students,
        total_mentors=total_mentors,
    )


async def get_institution_taxonomy() -> dict:
    """Get institution taxonomy (old version, classification level only).

    Returns:
        Dict with region → org_type → classification hierarchy
    """
    all_records = await fetch_all_institutions()

    # Build taxonomy structure
    taxonomy = {
        "total": len(all_records),
        "org_type_aliases": {"公司": "企业", "科研院所": "研究机构"},
        "regions": {},
    }

    for region in REGION_ORDER:
        region_records = [r for r in all_records if r.get("region") == region]
        if not region_records:
            continue

        region_data = {"count": len(region_records), "org_types": {}}

        for org_type in ORG_TYPE_ORDER:
            org_type_records = [
                r
                for r in region_records
                if normalize_org_type(r.get("org_type")) == org_type
            ]
            if not org_type_records:
                continue

            org_type_data = {
                "count": len(org_type_records),
                "display_name": "公司" if org_type == "企业" else org_type,
                "classifications": {},
            }

            for classification in CLASSIFICATION_ORDER:
                classification_records = [
                    r for r in org_type_records if r.get("classification") == classification
                ]
                if classification_records:
                    org_type_data["classifications"][classification] = {
                        "count": len(classification_records)
                    }

            region_data["org_types"][org_type] = org_type_data

        taxonomy["regions"][region] = region_data

    return taxonomy
