"""Response shape transformers — convert raw scholar dicts to API output shapes."""
from __future__ import annotations

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


def _to_list_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "url_hash": item.get("url_hash") or "",
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
    }


def _to_detail(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "url_hash": item.get("url_hash") or "",
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
        "is_potential_recruit": bool(item.get("is_potential_recruit", False)),
        "institute_relation_notes": item.get("institute_relation_notes") or "",
        "relation_updated_by": item.get("relation_updated_by") or "",
        "relation_updated_at": item.get("relation_updated_at") or "",
        "recent_updates": item.get("recent_updates") or [],
        "tags": item.get("tags") or [],
        "custom_fields": item.get("custom_fields") or {},
    }
