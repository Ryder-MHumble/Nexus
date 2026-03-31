"""Response shape transformers — convert raw scholar dicts to API output shapes."""
from __future__ import annotations

import json
from typing import Any

_EMPTY_ADJUNCT: dict[str, str] = {
    "status": "", "type": "", "agreement_type": "", "agreement_period": "", "recommender": "",
}


def _coerce_adjunct_supervisor(raw: Any) -> dict[str, str]:
    """Normalize adjunct_supervisor field."""
    if isinstance(raw, dict):
        return {
            "status": raw.get("status", ""),
            "type": raw.get("type", ""),
            "agreement_type": raw.get("agreement_type", ""),
            "agreement_period": raw.get("agreement_period", ""),
            "recommender": raw.get("recommender", ""),
        }
    return dict(_EMPTY_ADJUNCT)


def _coerce_project_tags(raw: Any, *, legacy_category: str = "", legacy_subcategory: str = "") -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "").strip()
            subcategory = str(item.get("subcategory") or "").strip()
            if not category and not subcategory:
                continue
            tags.append(
                {
                    "category": category,
                    "subcategory": subcategory,
                    "project_id": str(item.get("project_id") or ""),
                    "project_title": str(item.get("project_title") or ""),
                }
            )
    if tags:
        return tags

    category = legacy_category.strip()
    subcategory = legacy_subcategory.strip()
    if not category and not subcategory:
        return []
    return [{
        "category": category,
        "subcategory": subcategory,
        "project_id": "",
        "project_title": "",
    }]


def _coerce_event_tags(raw: Any) -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return tags
    for item in raw:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        series = str(item.get("series") or "").strip()
        event_type = str(item.get("event_type") or "").strip()
        if not category and not series and not event_type:
            continue
        tags.append(
            {
                "category": category,
                "series": series,
                "event_type": event_type,
                "event_id": str(item.get("event_id") or ""),
                "event_title": str(item.get("event_title") or ""),
            }
        )
    return tags


def _is_cobuild_scholar(
    item: dict[str, Any],
    project_tags: list[dict[str, str]],
    event_tags: list[dict[str, str]],
) -> bool:
    # Category tags are the source of truth for co-build relationship.
    if project_tags or event_tags:
        return True
    explicit = item.get("is_cobuild_scholar")
    if isinstance(explicit, bool):
        return explicit
    return False


def _coerce_custom_fields(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _to_list_item(item: dict[str, Any]) -> dict[str, Any]:
    project_tags = _coerce_project_tags(
        item.get("project_tags"),
        legacy_category=str(item.get("project_category") or ""),
        legacy_subcategory=str(item.get("project_subcategory") or ""),
    )
    participated_event_ids = item.get("participated_event_ids") or []
    event_tags = _coerce_event_tags(item.get("event_tags"))
    return {
        # DB rows commonly use `id` as the canonical scholar key.
        # Fallback to id when legacy payload misses `url_hash`.
        "url_hash": item.get("url_hash") or item.get("id") or "",
        "name": item.get("name") or "",
        "name_en": item.get("name_en") or "",
        "photo_url": item.get("photo_url") or "",
        "university": item.get("university") or "",
        "department": item.get("department") or "",
        "position": item.get("position") or "",
        "academic_titles": item.get("academic_titles") or [],
        "is_academician": bool(item.get("is_academician", False)),
        "research_areas": item.get("research_areas") or [],
        "email": item.get("email") or "",
        "profile_url": item.get("profile_url") or "",
        "is_potential_recruit": bool(item.get("is_potential_recruit", False)),
        "is_advisor_committee": bool(item.get("is_advisor_committee", False)),
        "adjunct_supervisor": _coerce_adjunct_supervisor(item.get("adjunct_supervisor")),
        "is_cobuild_scholar": _is_cobuild_scholar(item, project_tags, event_tags),
        "project_tags": project_tags,
        "participated_event_ids": participated_event_ids,
        "event_tags": event_tags,
    }


def _to_detail(item: dict[str, Any]) -> dict[str, Any]:
    project_tags = _coerce_project_tags(
        item.get("project_tags"),
        legacy_category=str(item.get("project_category") or ""),
        legacy_subcategory=str(item.get("project_subcategory") or ""),
    )
    event_tags = _coerce_event_tags(item.get("event_tags"))
    return {
        # DB rows commonly use `id` as the canonical scholar key.
        # Fallback to id when legacy payload misses `url_hash`.
        "url_hash": item.get("url_hash") or item.get("id") or "",
        "url": item.get("url") or "",
        "content": item.get("content") or "",
        "name": item.get("name") or "",
        "name_en": item.get("name_en") or "",
        "gender": item.get("gender") or "",
        "photo_url": item.get("photo_url") or "",
        "university": item.get("university") or "",
        "department": item.get("department") or "",
        "secondary_departments": item.get("secondary_departments") or [],
        "position": item.get("position") or "",
        "academic_titles": item.get("academic_titles") or [],
        "is_academician": bool(item.get("is_academician", False)),
        "research_areas": item.get("research_areas") or [],
        "keywords": item.get("keywords") or [],
        "bio": item.get("bio") or "",
        "bio_en": item.get("bio_en") or "",
        "email": item.get("email") or "",
        "phone": item.get("phone") or "",
        "office": item.get("office") or "",
        "profile_url": item.get("profile_url") or "",
        "lab_url": item.get("lab_url") or "",
        "google_scholar_url": item.get("google_scholar_url") or "",
        "dblp_url": item.get("dblp_url") or "",
        "orcid": item.get("orcid") or "",
        "phd_institution": item.get("phd_institution") or "",
        "phd_year": item.get("phd_year") or "",
        "education": item.get("education") or [],
        "publications_count": item.get("publications_count") or -1,
        "h_index": item.get("h_index") or -1,
        "citations_count": item.get("citations_count") or -1,
        "metrics_updated_at": item.get("metrics_updated_at") or "",
        "representative_publications": item.get("representative_publications") or [],
        "patents": item.get("patents") or [],
        "awards": item.get("awards") or [],
        "is_advisor_committee": bool(item.get("is_advisor_committee", False)),
        "adjunct_supervisor": _coerce_adjunct_supervisor(item.get("adjunct_supervisor")),
        "supervised_students": item.get("supervised_students") or [],
        "joint_research_projects": item.get("joint_research_projects") or [],
        "joint_management_roles": item.get("joint_management_roles") or [],
        "academic_exchange_records": item.get("academic_exchange_records") or [],
        "participated_event_ids": item.get("participated_event_ids") or [],
        "event_tags": event_tags,
        "project_tags": project_tags,
        "is_cobuild_scholar": _is_cobuild_scholar(item, project_tags, event_tags),
        "is_potential_recruit": bool(item.get("is_potential_recruit", False)),
        "institute_relation_notes": item.get("institute_relation_notes") or "",
        "relation_updated_by": item.get("relation_updated_by") or "",
        "relation_updated_at": item.get("relation_updated_at") or "",
        "recent_updates": item.get("recent_updates") or [],
        "tags": item.get("tags") or [],
        "custom_fields": _coerce_custom_fields(item.get("custom_fields")),
    }
