"""Filtering helpers for scholar queries."""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Institution classification map (from DB, cached in-process)
# ---------------------------------------------------------------------------

_INSTITUTION_CLASSIFICATION_CACHE: dict[str, dict[str, str]] | None = None


_TYPE_TO_ORG_TYPE: dict[str, str] = {
    "university": "高校",
    "company": "企业",
    "research_institute": "研究机构",
    "academic_society": "其他",
}

# Groups that indicate international institutions
_INTL_GROUPS = {"海外高校"}


async def get_institution_classification_map() -> dict[str, dict[str, str]]:
    """Return {institution_name: {region, org_type}} from institutions service.

    Calls the institution service which reads from JSON files with complete data.
    DB table has NULL values for region/org_type/classification fields.

    Fetches once per process and caches the result.
    Falls back to empty dict on error (callers will use heuristics).
    """
    global _INSTITUTION_CLASSIFICATION_CACHE
    if _INSTITUTION_CLASSIFICATION_CACHE is not None:
        return _INSTITUTION_CLASSIFICATION_CACHE

    try:
        from app.services.core.institution import get_institution_list  # noqa: PLC0415

        # Get all institutions from the service (reads from JSON with complete data)
        result = await get_institution_list(
            page=1,
            page_size=500,
            type_filter=None,  # Get all types
        )

        mapping: dict[str, dict[str, str]] = {}
        for inst in result.items:
            name = (inst.name or "").strip()
            if not name:
                continue

            # Use group field to determine region
            group = inst.group or ""
            region = "国际" if group == "海外高校" else "国内"

            # Use type field to determine org_type
            inst_type = inst.type or ""
            org_type = _TYPE_TO_ORG_TYPE.get(inst_type, "")

            mapping[name] = {"region": region, "org_type": org_type}

        _INSTITUTION_CLASSIFICATION_CACHE = mapping
        return mapping
    except Exception as exc:
        # Log error but don't crash - fall back to heuristics
        import logging  # noqa: PLC0415
        logging.getLogger(__name__).warning(
            "Failed to load institution classification map: %s", exc
        )
        return {}


def invalidate_institution_classification_cache() -> None:
    """Call this when institution data changes."""
    global _INSTITUTION_CLASSIFICATION_CACHE
    _INSTITUTION_CLASSIFICATION_CACHE = None


def _get_region(university: str, inst_map: dict[str, dict[str, str]]) -> str:
    """Resolve region for a university name using DB map first, heuristics as fallback."""
    if university in inst_map and inst_map[university].get("region"):
        return inst_map[university]["region"]
    return _derive_region_from_university(university)


def _get_org_type(university: str, inst_map: dict[str, dict[str, str]]) -> str:
    """Resolve org_type for a university name using DB map first, heuristics as fallback."""
    if university in inst_map and inst_map[university].get("org_type"):
        return inst_map[university]["org_type"]
    return _derive_affiliation_type_from_university(university)


def _match_fuzzy(value: str, query: str) -> bool:
    return query.strip().lower() in (value or "").lower()


def _derive_region_from_university(university: str) -> str:
    """Derive region (国内/国际) from university name.

    Rules:
    - 国内: Chinese universities (contains Chinese characters or known domestic names)
    - 国际: International universities (primarily English names without Chinese)
    """
    if not university:
        return ""

    # Check if contains Chinese characters
    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in university)
    if has_chinese:
        return "国内"

    # Known domestic keywords (Chinese institutions with non-Chinese chars)
    domestic_keywords = [
        "中科院", "中国科学院", "中国工程院", "中关村", "昌平",
        "深圳", "上海", "北京", "香港", "澳门",
    ]
    if any(kw in university for kw in domestic_keywords):
        return "国内"

    # Known international universities (English names)
    intl_keywords = [
        "University", "Institute", "College", "School",
        "MIT", "Stanford", "Harvard", "Berkeley", "CMU",
        "Oxford", "Cambridge", "ETH", "EPFL",
        "NUS", "NTU", "KAIST", "Tokyo",
        "A*STAR", "CNRS", "INRIA", "Max Planck",
        "UCLA", "USC", "Caltech", "Georgia Tech",
    ]

    if any(kw in university for kw in intl_keywords):
        return "国际"

    # Pure English name (no Chinese chars) → treat as 国际
    return "国际"


def _derive_affiliation_type_from_university(university: str) -> str:
    """Derive affiliation_type (高校/企业/研究机构/其他) from university name.

    Rules:
    - 高校: Contains 大学/学院/University/College
    - 研究机构: Contains 研究院/研究所/研究中心/Institute/Laboratory/Lab
    - 企业: Contains 公司/集团/科技/Company/Corp/Inc
    - 其他: Everything else
    """
    if not university:
        return ""

    uni_lower = university.lower()

    # 高校 keywords
    if any(kw in uni_lower for kw in [
        "大学", "学院", "university", "college",
        "ucla", "usc", "mit", "caltech", "georgia tech",
    ]):
        return "高校"

    # 研究机构 keywords
    if any(kw in uni_lower for kw in [
        "研究院", "研究所", "研究中心", "科学院", "工程院",
        "实验室", "中科院", "自动化所", "计算所", "软件所",
        "数学所", "物理所", "化学所", "生物所",
        "institute", "laboratory", "lab", "research center",
        "a*star", "cnrs", "inria", "max planck",
    ]):
        return "研究机构"

    # 企业 keywords
    if any(kw in uni_lower for kw in [
        "公司", "集团", "企业",
        "company", "corp", "inc", "ltd",
        "亚马逊", "谷歌", "微软", "华为", "腾讯", "阿里", "百度", "字节",
        "amazon", "google", "microsoft", "meta", "apple",
        "科技", "technology", "tech",
    ]):
        # Exclude false positives: "大学" or "学院" in name takes precedence
        if not any(kw in uni_lower for kw in ["大学", "学院", "university", "college"]):
            return "企业"

    return "其他"


def _apply_filters(
    items: list[dict[str, Any]],
    *,
    university: str | None,
    department: str | None,
    position: str | None,
    is_academician: bool | None,
    is_potential_recruit: bool | None,
    is_advisor_committee: bool | None,
    is_adjunct_supervisor: bool | None,
    has_email: bool | None,
    keyword: str | None,
    region: str | None,
    affiliation_type: str | None,
    institution_names: list[str] | None = None,
    custom_field_key: str | None = None,
    custom_field_value: str | None = None,
    inst_map: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    result = items

    # institution_names: exact-match on university field (used by institution_group/category filter)
    if institution_names is not None:
        name_set = set(institution_names)
        result = [i for i in result if (i.get("university") or "") in name_set]

    if university:
        result = [i for i in result if _match_fuzzy(i.get("university", ""), university)]

    if department:
        result = [i for i in result if _match_fuzzy(i.get("department", ""), department)]

    if position:
        result = [i for i in result if i.get("position", "") == position]

    if is_academician is not None:
        result = [i for i in result if bool(i.get("is_academician", False)) == is_academician]

    if is_potential_recruit is not None:
        result = [i for i in result if bool(i.get("is_potential_recruit", False)) == is_potential_recruit]

    if is_advisor_committee is not None:
        result = [i for i in result if bool(i.get("is_advisor_committee", False)) == is_advisor_committee]

    if is_adjunct_supervisor is not None:
        def _has_adjunct(item: dict[str, Any]) -> bool:
            adj = item.get("adjunct_supervisor")
            if isinstance(adj, dict):
                return bool(adj.get("status", ""))
            return False
        result = [i for i in result if _has_adjunct(i) == is_adjunct_supervisor]

    if has_email is not None:
        result = [i for i in result if bool(i.get("email", "")) == has_email]

    _map = inst_map or {}
    if region:
        result = [
            i for i in result
            if _get_region(i.get("university", ""), _map) == region
        ]

    if affiliation_type:
        result = [
            i for i in result
            if _get_org_type(i.get("university", ""), _map) == affiliation_type
        ]

    if keyword:
        kw = keyword.strip().lower()

        def _matches(i: dict[str, Any]) -> bool:
            if kw in (i.get("name") or "").lower():
                return True
            if kw in (i.get("name_en") or "").lower():
                return True
            if kw in (i.get("bio") or "").lower():
                return True
            if any(kw in area.lower() for area in (i.get("research_areas") or [])):
                return True
            if any(kw in kw_tag.lower() for kw_tag in (i.get("keywords") or [])):
                return True
            return False

        result = [i for i in result if _matches(i)]

    if custom_field_key:
        result = [
            i for i in result
            if (i.get("custom_fields") or {}).get(custom_field_key) == custom_field_value
        ]

    return result
