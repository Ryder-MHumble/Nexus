"""Build API response objects from database records.

Converts raw database records into Pydantic schema objects for API responses.
"""

from __future__ import annotations

from app.schemas.institution import (
    DepartmentInfo,
    InstitutionDetailResponse,
    InstitutionListItem,
    SecondaryInstitutionInfo,
    ScholarInfo,
)
from app.services.core.institution.classification import (
    normalize_priority,
)


def _parse_scholar_list(raw: list | None) -> list[ScholarInfo]:
    """Convert raw scholar data to ScholarInfo objects.

    Args:
        raw: List of strings or dicts

    Returns:
        List of ScholarInfo objects
    """
    if not raw:
        return []
    result = []
    for item in raw:
        if isinstance(item, str):
            result.append(ScholarInfo(name=item))
        elif isinstance(item, dict):
            result.append(
                ScholarInfo(
                    **{
                        k: v
                        for k, v in item.items()
                        if k in ("name", "scholar_id", "title", "department", "research_area")
                    }
                )
            )
    return result


def _build_secondary_institution_info_list(
    secondary_items: list[InstitutionListItem] | None,
    secondary_records: list[dict] | None = None,
) -> list[SecondaryInstitutionInfo]:
    """Convert InstitutionListItem objects to SecondaryInstitutionInfo objects.

    Args:
        secondary_items: List of InstitutionListItem objects
        secondary_records: Optional list of raw department records for additional data

    Returns:
        List of SecondaryInstitutionInfo objects
    """
    if not secondary_items:
        return []

    # Create a map of records by ID for quick lookup
    record_map = {}
    if secondary_records:
        record_map = {r["id"]: r for r in secondary_records}

    result = []
    for item in secondary_items:
        record = record_map.get(item.id, {})
        result.append(SecondaryInstitutionInfo(
            id=item.id,
            name=item.name,
            scholar_count=item.scholar_count,
            org_name=record.get("org_name"),
            parent_id=record.get("parent_id"),
            sources=record.get("sources") or [],
        ))
    return result


def build_list_item(record: dict) -> InstitutionListItem:
    """Build InstitutionListItem from database record.

    Args:
        record: Raw database record

    Returns:
        InstitutionListItem schema object
    """
    # Normalize priority
    priority = normalize_priority(record.get("priority"))

    return InstitutionListItem(
        id=record["id"],
        name=record["name"],
        # Classification fields
        entity_type=record.get("entity_type"),
        region=record.get("region"),
        org_type=record.get("org_type"),
        classification=record.get("classification"),
        sub_classification=record.get("sub_classification"),
        # Common fields
        priority=priority,
        parent_id=record.get("parent_id"),
        scholar_count=record.get("scholar_count", 0),
        student_count_total=record.get("student_count_total"),
        mentor_count=record.get("mentor_count"),
        avatar=record.get("avatar"),
        org_name=record.get("org_name"),
    )


def build_detail_response(record: dict, departments: list[dict] | None = None) -> InstitutionDetailResponse:
    """Build InstitutionDetailResponse from database record.

    Args:
        record: Raw database record
        departments: Optional list of department records (for organizations)

    Returns:
        InstitutionDetailResponse schema object
    """
    # Build base list item
    base_item = build_list_item(record)

    # Build secondary institution list items if provided
    secondary_items = None
    if departments:
        secondary_items = [build_list_item(dept) for dept in departments]

    secondary_institutions = _build_secondary_institution_info_list(secondary_items, departments)

    # Extract additional detail fields
    detail_data = {
        **base_item.model_dump(),
        # Student and mentor metrics
        "student_count_24": record.get("student_count_24"),
        "student_count_25": record.get("student_count_25"),
        "student_counts_by_year": record.get("student_counts_by_year") or {},
        "student_count_total": record.get("student_count_total"),
        "mentor_count": record.get("mentor_count"),
        # People
        "resident_leaders": record.get("resident_leaders") or [],
        "degree_committee": record.get("degree_committee") or [],
        "teaching_committee": record.get("teaching_committee") or [],
        "university_leaders": _parse_scholar_list(record.get("university_leaders")),
        "notable_scholars": _parse_scholar_list(record.get("notable_scholars")),
        # Cooperation
        "key_departments": record.get("key_departments") or [],
        "joint_labs": record.get("joint_labs") or [],
        "training_cooperation": record.get("training_cooperation") or [],
        "academic_cooperation": record.get("academic_cooperation") or [],
        "talent_dual_appointment": record.get("talent_dual_appointment") or [],
        "recruitment_events": record.get("recruitment_events") or [],
        "visit_exchanges": record.get("visit_exchanges") or [],
        "cooperation_focus": record.get("cooperation_focus") or [],
        "custom_fields": record.get("custom_fields") or {},
        # Secondary institutions
        "secondary_institutions": secondary_institutions,
        "departments": [DepartmentInfo(**item.model_dump()) for item in secondary_institutions],
        # Legacy compatibility
        "type": record.get("type"),
        "group": record.get("group"),
        "category": record.get("category"),
        "sources": record.get("sources") or [],
    }

    return InstitutionDetailResponse(**detail_data)
