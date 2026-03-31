"""Filtering helpers for scholar queries."""
from __future__ import annotations

import json
import re
import time
from typing import Any

from app.services.core.institution.classification import normalize_org_type

# ---------------------------------------------------------------------------
# Institution classification map (from DB, cached in-process)
# ---------------------------------------------------------------------------

_INSTITUTION_CLASSIFICATION_CACHE: dict[str, dict[str, str]] | None = None
_INSTITUTION_CLASSIFICATION_CACHE_AT: float | None = None
_INSTITUTION_CLASSIFICATION_CACHE_TTL_SECONDS = 60.0
_INSTITUTION_LOOKUP_CACHE_SOURCE_ID: int | None = None
_INSTITUTION_LOOKUP_NORMALIZED: dict[str, dict[str, str]] = {}
_INSTITUTION_LOOKUP_PREFIX_BUCKETS: dict[str, list[str]] = {}


_TYPE_TO_ORG_TYPE: dict[str, str] = {
    "university": "高校",
    "company": "企业",
    "research_institute": "研究机构",
    "academic_society": "其他",
}

# Groups that indicate international institutions
_INTL_GROUPS = {"海外高校"}

_STATUS_SUFFIX_RE = re.compile(
    r"(?:博士在读|硕士在读|博士生|硕士生|博士后|博后|本科生|在读|"
    r"助理教授|副教授|教授|讲师|phd|ap)$",
    re.IGNORECASE,
)
_LEAD_SEP_RE = re.compile(r"^[\s,，;；:：|/\\\-—_()（）\[\]【】]+")
_ROOT_CAPTURE_RE = re.compile(
    r"^(.{2,90}?大学(?:.{0,12}?分校)?(?:\(深圳\)|（深圳）)?)(.+)$"
)
_DEPT_HINT_RE = re.compile(
    r"(学院|学部|系|研究院|研究所|实验室|中心|研究中心|faculty|school|department|lab|institute|college)",
    re.IGNORECASE,
)
_GENERIC_DEPTS = {"学院", "学部", "系", "研究院", "研究所", "实验室", "中心", "研究中心"}
_CAMPUS_PREFIXES = (
    "分校",
    "校区",
    "帕克分校",
    "厄巴纳",
    "洛杉矶分校",
    "圣地亚哥分校",
    "伯克利分校",
    "阿默斯特分校",
    "布法罗分校",
    "芝加哥分校",
    "圣克鲁斯分校",
    "默塞德分校",
    "戴维斯分校",
    "圣塔芭芭拉分校",
    "密西沙加分校",
    "(深圳)",
    "（深圳）",
    "深圳校区",
)
_CAS_SHORT_MAP = {
    "自动化所": "自动化研究所",
    "计算所": "计算技术研究所",
    "信工所": "信息工程研究所",
}
_INTL_STRONG_MARKERS = (
    "美国", "英国", "德国", "法国", "意大利", "西班牙", "日本", "韩国", "印度", "新加坡", "澳大利亚",
    "加拿大", "以色列", "荷兰", "瑞士", "芬兰", "瑞典", "挪威", "丹麦", "比利时", "奥地利",
    "波兰", "罗马尼亚", "克罗地亚", "希腊", "俄罗斯", "乌克兰", "葡萄牙", "捷克", "匈牙利",
    "香港", "澳门", "台湾", "台北", "高雄",
    "纽约", "波士顿", "西雅图", "洛杉矶", "圣地亚哥", "芝加哥", "德克萨斯", "亚利桑那",
    "马萨诸塞", "宾夕法尼亚", "弗吉尼亚", "威斯康星", "伦敦", "巴黎", "柏林", "慕尼黑",
    "苏黎世", "洛桑", "维也纳", "布拉格", "赫尔辛基", "哥本哈根", "奥斯陆", "斯德哥尔摩",
    "都柏林", "罗马", "米兰", "博洛尼亚", "特伦托", "维罗纳", "多伦多", "蒙特利尔",
    "温哥华", "东京", "大阪", "京都", "首尔", "新南威尔士", "墨尔本", "悉尼", "昆士兰",
    "乌迪内", "雅典", "伊利诺伊", "莫纳什",
    "哥伦比亚大学", "哈佛大学", "斯坦福大学", "耶鲁大学", "普林斯顿大学", "康奈尔大学",
    "卡内基梅隆大学", "帝国理工学院", "伦敦大学学院", "伦敦国王学院", "苏黎世联邦理工学院",
    "洛桑联邦理工学院", "麦吉尔大学", "麦考瑞大学", "韩国科学技术院", "高丽大学", "延世大学",
    "东京大学", "大阪大学", "京都大学", "南洋理工大学", "新加坡国立大学", "麻省理工学院",
    "加州大学", "加州理工学院", "德州大学", "德州农工大学", "德克萨斯农工大学",
)
_INTL_STRONG_RE = re.compile(
    "|".join(re.escape(token) for token in sorted(set(_INTL_STRONG_MARKERS), key=len, reverse=True))
)
_DOMESTIC_STRONG_MARKERS = (
    "中国", "中科院", "中国科学院", "中国工程院", "中关村",
    "北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏",
    "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃", "青海", "内蒙古", "广西", "宁夏", "新疆",
)


async def get_institution_classification_map() -> dict[str, dict[str, str]]:
    """Return {institution_name: {region, org_type}} from institutions service.

    Fetches from Supabase institutions table with complete classification data.
    Fetches once per process and caches the result.
    Falls back to empty dict on error (callers will use heuristics).
    """
    global _INSTITUTION_CLASSIFICATION_CACHE
    global _INSTITUTION_CLASSIFICATION_CACHE_AT
    now = time.monotonic()
    if (
        _INSTITUTION_CLASSIFICATION_CACHE is not None
        and _INSTITUTION_CLASSIFICATION_CACHE_AT is not None
        and (now - _INSTITUTION_CLASSIFICATION_CACHE_AT) < _INSTITUTION_CLASSIFICATION_CACHE_TTL_SECONDS
    ):
        return _INSTITUTION_CLASSIFICATION_CACHE

    try:
        from app.services.core.institution.storage import fetch_all_institutions  # noqa: PLC0415

        # Get all institutions from database
        institutions = await fetch_all_institutions()

        mapping: dict[str, dict[str, str]] = {}

        # Prefer organization rows so region/org_type inference remains stable.
        for inst in institutions:
            if (inst.get("entity_type") or "") != "organization":
                continue
            name = (inst.get("name") or "").strip()
            if not name:
                continue
            region = inst.get("region") or ""
            org_type = normalize_org_type(inst.get("org_type")) or ""
            mapping[name] = {"region": region, "org_type": org_type}

        # Fill remaining names from non-organization rows only when absent.
        for inst in institutions:
            name = (inst.get("name") or "").strip()
            if not name or name in mapping:
                continue
            region = inst.get("region") or ""
            org_type = normalize_org_type(inst.get("org_type")) or ""
            mapping[name] = {"region": region, "org_type": org_type}

        _INSTITUTION_CLASSIFICATION_CACHE = mapping
        _INSTITUTION_CLASSIFICATION_CACHE_AT = now
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
    global _INSTITUTION_CLASSIFICATION_CACHE_AT
    global _INSTITUTION_LOOKUP_CACHE_SOURCE_ID
    global _INSTITUTION_LOOKUP_NORMALIZED
    global _INSTITUTION_LOOKUP_PREFIX_BUCKETS
    _INSTITUTION_CLASSIFICATION_CACHE = None
    _INSTITUTION_CLASSIFICATION_CACHE_AT = None
    _INSTITUTION_LOOKUP_CACHE_SOURCE_ID = None
    _INSTITUTION_LOOKUP_NORMALIZED = {}
    _INSTITUTION_LOOKUP_PREFIX_BUCKETS = {}


def _normalize_inst_lookup_key(value: str) -> str:
    normalized = "".join(str(value or "").strip().split()).lower()
    for token in (",", "，", ";", "；", ":", "：", "|", "/", "\\", "-", "_", "(", ")", "（", "）", "[", "]", "【", "】", "·", "•", "."):
        normalized = normalized.replace(token, "")
    return normalized


def _ensure_inst_lookup_cache(inst_map: dict[str, dict[str, str]]) -> None:
    global _INSTITUTION_LOOKUP_CACHE_SOURCE_ID
    global _INSTITUTION_LOOKUP_NORMALIZED
    global _INSTITUTION_LOOKUP_PREFIX_BUCKETS

    source_id = id(inst_map)
    if _INSTITUTION_LOOKUP_CACHE_SOURCE_ID == source_id:
        return

    normalized_meta: dict[str, dict[str, str]] = {}
    for name, meta in inst_map.items():
        key = _normalize_inst_lookup_key(name)
        if not key:
            continue
        current = normalized_meta.get(key)
        candidate = {
            "region": str(meta.get("region") or "").strip(),
            "org_type": normalize_org_type(str(meta.get("org_type") or "").strip()) or "",
            "name": name,
        }
        if current is None or len(str(candidate["name"])) > len(str(current["name"])):
            normalized_meta[key] = candidate

    buckets: dict[str, list[str]] = {}
    for key in normalized_meta:
        if len(key) < 3:
            continue
        prefix = key[:1]
        buckets.setdefault(prefix, []).append(key)
    for prefix in buckets:
        buckets[prefix].sort(key=len, reverse=True)

    _INSTITUTION_LOOKUP_CACHE_SOURCE_ID = source_id
    _INSTITUTION_LOOKUP_NORMALIZED = normalized_meta
    _INSTITUTION_LOOKUP_PREFIX_BUCKETS = buckets


def _lookup_institution_meta(
    university: str,
    inst_map: dict[str, dict[str, str]],
) -> dict[str, str]:
    normalized_uni = str(university or "").strip()
    if not normalized_uni:
        return {}

    direct = inst_map.get(normalized_uni)
    if direct and (direct.get("region") or direct.get("org_type")):
        return {
            "region": str(direct.get("region") or "").strip(),
            "org_type": normalize_org_type(str(direct.get("org_type") or "").strip()) or "",
        }

    _ensure_inst_lookup_cache(inst_map)
    uni_key = _normalize_inst_lookup_key(normalized_uni)
    if not uni_key:
        return {}

    exact = _INSTITUTION_LOOKUP_NORMALIZED.get(uni_key)
    if exact and (exact.get("region") or exact.get("org_type")):
        return {
            "region": str(exact.get("region") or "").strip(),
            "org_type": normalize_org_type(str(exact.get("org_type") or "").strip()) or "",
        }

    bucket = _INSTITUTION_LOOKUP_PREFIX_BUCKETS.get(uni_key[:1], [])
    for key in bucket:
        if not uni_key.startswith(key):
            continue
        meta = _INSTITUTION_LOOKUP_NORMALIZED.get(key)
        if not meta:
            continue
        if meta.get("region") or meta.get("org_type"):
            return {
                "region": str(meta.get("region") or "").strip(),
                "org_type": normalize_org_type(str(meta.get("org_type") or "").strip()) or "",
            }
    return {}


def _clean_inst_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _clean_dept_text(value: Any) -> str:
    text = _clean_inst_text(value)
    text = _LEAD_SEP_RE.sub("", text)
    return text.strip("，,;；:：|/\\-—_ ")


def _department_like(value: str) -> bool:
    text = _clean_dept_text(value)
    if not text or text in _GENERIC_DEPTS or len(text) <= 2:
        return False
    return bool(_DEPT_HINT_RE.search(text))


def _starts_with_campus_prefix(suffix: str) -> bool:
    if any(suffix.startswith(prefix) for prefix in _CAMPUS_PREFIXES):
        return True
    return bool(re.match(r"^.{1,8}分校", suffix))


def _strip_location_tail(suffix: str) -> str:
    text = _clean_dept_text(suffix)
    if not text:
        return ""
    for sep_re in (r"[;；|]", r"[，,]"):
        parts = re.split(sep_re, text)
        if len(parts) <= 1:
            continue
        first = _clean_dept_text(parts[0])
        if _department_like(first):
            text = first
    return _clean_dept_text(text)


def _extract_primary_affiliation(university: str) -> tuple[str, str]:
    """Extract level-1 institution name and moved level-2 suffix from university field."""
    text = _clean_inst_text(university)
    if not text:
        return "", ""

    for sep in ("；", ";", "|"):
        if sep not in text:
            continue
        first = _clean_inst_text(text.split(sep, 1)[0])
        if first:
            text = first
            break

    trimmed = _STATUS_SUFFIX_RE.sub("", text).strip(" ,，;；:：")
    if trimmed and trimmed != text:
        if any(
            token in trimmed
            for token in ("大学", "学院", "研究所", "研究院", "公司", "集团", "university", "institute", "college")
        ):
            text = trimmed

    if text in _CAS_SHORT_MAP:
        return "中国科学院大学", _CAS_SHORT_MAP[text]

    cas_match = re.match(r"^(?:中国科学院|中科院)(.+?)(?:研究所|所)$", text)
    if cas_match:
        body = _clean_dept_text(cas_match.group(1))
        moved = body if body.endswith("研究所") else f"{body}研究所"
        return "中国科学院大学", moved

    matched = _ROOT_CAPTURE_RE.match(text)
    if not matched:
        return text, ""

    root = _clean_inst_text(matched.group(1))
    suffix = _clean_dept_text(matched.group(2))
    suffix = re.sub(rf"[，,;；]\s*{re.escape(root)}\s*$", "", suffix)
    suffix = _strip_location_tail(suffix)
    if not suffix:
        return text, ""
    if _starts_with_campus_prefix(suffix):
        return text, ""
    if not _department_like(suffix):
        return text, ""
    return root, suffix


def _is_strong_intl_name(value: str) -> bool:
    text = _clean_inst_text(value)
    if not text:
        return False
    if _INTL_STRONG_RE.search(text):
        return True
    lower = text.lower()
    has_chinese = any("\u4e00" <= c <= "\u9fff" for c in text)
    if not has_chinese and any(k in lower for k in ("university", "institute", "college", "school")):
        return True
    return any(k in lower for k in ("ucla", "usc", "mit", "caltech", "georgia tech", "stanford", "harvard", "oxford", "cambridge"))


def _get_region(university: str, inst_map: dict[str, dict[str, str]]) -> str:
    """Resolve region for a university name using DB map first, heuristics as fallback."""
    normalized_uni = _clean_inst_text(university)
    if not normalized_uni:
        return "国内"
    primary_uni, _ = _extract_primary_affiliation(normalized_uni)
    resolved_uni = primary_uni or normalized_uni
    if _is_strong_intl_name(resolved_uni):
        return "国际"

    meta = _lookup_institution_meta(resolved_uni, inst_map)
    if not meta and resolved_uni != normalized_uni:
        meta = _lookup_institution_meta(normalized_uni, inst_map)
    if meta.get("region"):
        return meta["region"]
    return _derive_region_from_university(resolved_uni)


def _get_org_type(university: str, inst_map: dict[str, dict[str, str]]) -> str:
    """Resolve org_type for a university name using DB map first, heuristics as fallback."""
    normalized_uni = _clean_inst_text(university)
    if not normalized_uni:
        return "其他"
    primary_uni, _ = _extract_primary_affiliation(normalized_uni)
    resolved_uni = primary_uni or normalized_uni
    meta = _lookup_institution_meta(resolved_uni, inst_map)
    if not meta and resolved_uni != normalized_uni:
        meta = _lookup_institution_meta(normalized_uni, inst_map)
    if meta.get("org_type"):
        return normalize_org_type(meta["org_type"]) or "其他"
    return normalize_org_type(_derive_affiliation_type_from_university(resolved_uni)) or "其他"


def _normalize_exact_text(value: Any) -> str:
    """Normalize text for exact-match comparison.

    Rules:
    - trim leading/trailing spaces
    - collapse consecutive whitespace to a single space
    - lowercase (for case-insensitive exact match)
    """
    if value is None:
        return ""
    return " ".join(str(value).strip().split()).lower()


def _match_exact(value: str, query: str) -> bool:
    return _normalize_exact_text(value) == _normalize_exact_text(query)


def _normalize_department_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).strip("，,;；:：|/\\-—_ ")


def _merge_department_text(existing: str, moved: str) -> str:
    old_value = _normalize_department_text(existing)
    moved_value = _normalize_department_text(moved)
    if not moved_value:
        return old_value
    if not old_value:
        return moved_value
    if moved_value in old_value:
        return old_value
    if old_value in moved_value:
        return moved_value
    return f"{old_value} / {moved_value}"


def _matches_university_filter(item: dict[str, Any], query: str) -> bool:
    raw_uni = str(item.get("university", "") or "")
    primary_uni, _ = _extract_primary_affiliation(raw_uni)
    if _match_exact(raw_uni, query):
        return True
    if primary_uni and _match_exact(primary_uni, query):
        return True
    return False


def _matches_department_filter(item: dict[str, Any], query: str) -> bool:
    raw_dep = str(item.get("department", "") or "")
    _, moved_dep = _extract_primary_affiliation(str(item.get("university", "") or ""))
    merged_dep = _merge_department_text(raw_dep, moved_dep)
    if _match_exact(raw_dep, query):
        return True
    if moved_dep and _match_exact(moved_dep, query):
        return True
    if merged_dep and _match_exact(merged_dep, query):
        return True
    return False


def _norm_token(value: Any) -> str:
    if value is None:
        return ""
    return "".join(str(value).strip().split()).lower()


def _to_text_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        return [text]
    return []


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


def _community_matches(item: dict[str, Any], community_name: str | None, community_type: str | None) -> bool:
    if not community_name and not community_type:
        return True

    custom_fields = _coerce_custom_fields(item.get("custom_fields"))

    tags_raw = _to_text_list(item.get("tags"))
    community_tags_raw = _to_text_list(custom_fields.get("community_tags"))
    pool = tags_raw + community_tags_raw

    name_target = _norm_token(community_name) if community_name else ""
    type_target = _norm_token(community_type) if community_type else ""

    def _pool_has(target: str) -> bool:
        if not target:
            return True
        for tag in pool:
            token = _norm_token(tag)
            if not token:
                continue
            if token == target:
                return True
            if ":" in token and token.split(":")[-1] == target:
                return True
        return False

    if name_target:
        cf_name = _norm_token(custom_fields.get("community_name"))
        if cf_name != name_target and not _pool_has(name_target):
            return False

    if type_target:
        cf_type = _norm_token(custom_fields.get("community_type"))
        if cf_type != type_target and not _pool_has(type_target):
            return False

    return True


def _extract_project_tags(item: dict[str, Any]) -> list[dict[str, str]]:
    raw_tags = item.get("project_tags")
    tags: list[dict[str, str]] = []
    if isinstance(raw_tags, list):
        for raw in raw_tags:
            if not isinstance(raw, dict):
                continue
            category = str(raw.get("category") or "").strip()
            subcategory = str(raw.get("subcategory") or "").strip()
            if not category and not subcategory:
                continue
            tags.append(
                {
                    "category": category,
                    "subcategory": subcategory,
                }
            )
    if tags:
        return tags

    legacy_category = str(item.get("project_category") or "").strip()
    legacy_subcategory = str(item.get("project_subcategory") or "").strip()
    if not legacy_category and not legacy_subcategory:
        return []
    return [{"category": legacy_category, "subcategory": legacy_subcategory}]


def _extract_event_tags(item: dict[str, Any]) -> list[dict[str, str]]:
    raw_tags = item.get("event_tags")
    tags: list[dict[str, str]] = []
    if not isinstance(raw_tags, list):
        return tags
    for raw in raw_tags:
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "").strip()
        series = str(raw.get("series") or "").strip()
        event_type = str(raw.get("event_type") or "").strip()
        if not category and not series and not event_type:
            continue
        tags.append(
            {
                "category": category,
                "series": series,
                "event_type": event_type,
            }
        )
    return tags


_PROJECT_SUBCATEGORY_ALIASES: dict[str, set[str]] = {
    "学院学生高校导师": {"学院学生事务导师"},
    "学院学生事务导师": {"学院学生高校导师"},
    "科技教育委员会": {"科技育青委员会"},
    "科技育青委员会": {"科技教育委员会"},
}


def _project_subcategory_targets(value: str) -> set[str]:
    target = value.strip()
    if not target:
        return set()
    targets = {target}
    targets.update(_PROJECT_SUBCATEGORY_ALIASES.get(target, set()))
    return targets


def _split_multi_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = str(raw).strip()
    if not normalized:
        return []
    for sep in ("，", ";", "；", "|", "\n", "\r", "\t"):
        normalized = normalized.replace(sep, ",")
    values = [v.strip() for v in normalized.split(",")]
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _is_cobuild_scholar(
    item: dict[str, Any],
    project_tags: list[dict[str, str]],
    event_tags: list[dict[str, str]],
) -> bool:
    if project_tags or event_tags:
        return True
    explicit = item.get("is_cobuild_scholar")
    if isinstance(explicit, bool):
        return explicit
    return False


def _derive_region_from_university(university: str) -> str:
    """Derive region (国内/国际) from university name.

    Rules:
    - 国内: Chinese universities (contains Chinese characters or known domestic names)
    - 国际: International universities (primarily English names without Chinese)
    """
    if not university:
        return ""

    normalized = _clean_inst_text(university)
    primary_uni, _ = _extract_primary_affiliation(normalized)
    resolved_uni = primary_uni or normalized
    resolved_uni_lower = resolved_uni.lower()
    has_chinese = any("\u4e00" <= c <= "\u9fff" for c in resolved_uni)

    if _is_strong_intl_name(resolved_uni):
        return "国际"

    if any(token in resolved_uni for token in _DOMESTIC_STRONG_MARKERS):
        return "国内"

    # Known international universities (English names)
    intl_keywords = [
        "university", "institute", "college", "school",
        "mit", "stanford", "harvard", "berkeley", "cmu",
        "oxford", "cambridge", "eth", "epfl",
        "nus", "ntu", "kaist", "tokyo",
        "a*star", "cnrs", "inria", "max planck",
        "ucla", "usc", "caltech", "georgia tech",
    ]
    if any(kw in resolved_uni_lower for kw in intl_keywords):
        return "国际"

    if has_chinese:
        return "国内"
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

    normalized = _clean_inst_text(university)
    primary_uni, _ = _extract_primary_affiliation(normalized)
    resolved_uni = primary_uni or normalized
    uni_lower = resolved_uni.lower()

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
    project_category: str | None,
    project_subcategory: str | None,
    project_categories: str | None,
    project_subcategories: str | None,
    event_types: str | None,
    participated_event_id: str | None,
    is_cobuild_scholar: bool | None,
    region: str | None,
    affiliation_type: str | None,
    institution_names: list[str] | None = None,
    custom_field_key: str | None = None,
    custom_field_value: str | None = None,
    inst_map: dict[str, dict[str, str]] | None = None,
    community_name: str | None = None,
    community_type: str | None = None,
) -> list[dict[str, Any]]:
    result = items

    # institution_names: exact-match on university field (used by institution_group/category filter)
    if institution_names is not None:
        name_set = set(institution_names)
        result = [i for i in result if (i.get("university") or "") in name_set]

    if university:
        result = [i for i in result if _matches_university_filter(i, university)]

    if department:
        result = [i for i in result if _matches_department_filter(i, department)]

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

    normalized_affiliation_type = normalize_org_type(affiliation_type)
    if normalized_affiliation_type:
        result = [
            i for i in result
            if normalize_org_type(_get_org_type(i.get("university", ""), _map))
            == normalized_affiliation_type
        ]

    if community_name or community_type:
        result = [i for i in result if _community_matches(i, community_name, community_type)]

    if project_category:
        target = project_category.strip()
        result = [
            i for i in result
            if any((tag.get("category") or "") == target for tag in _extract_project_tags(i))
        ]

    if project_subcategory:
        targets = _project_subcategory_targets(project_subcategory)
        result = [
            i for i in result
            if any((tag.get("subcategory") or "") in targets for tag in _extract_project_tags(i))
        ]

    if project_categories:
        category_targets = set(_split_multi_values(project_categories))
        result = [
            i for i in result
            if any((tag.get("category") or "") in category_targets for tag in _extract_project_tags(i))
        ]

    if project_subcategories:
        subcategory_targets: set[str] = set()
        for token in _split_multi_values(project_subcategories):
            subcategory_targets.update(_project_subcategory_targets(token))
        result = [
            i for i in result
            if any((tag.get("subcategory") or "") in subcategory_targets for tag in _extract_project_tags(i))
        ]

    if event_types:
        event_type_targets = set(_split_multi_values(event_types))
        result = [
            i for i in result
            if any((tag.get("event_type") or "") in event_type_targets for tag in _extract_event_tags(i))
        ]

    if participated_event_id:
        target = participated_event_id.strip()

        def _has_event(item: dict[str, Any]) -> bool:
            event_ids = item.get("participated_event_ids") or []
            if isinstance(event_ids, list):
                return target in event_ids
            return False

        result = [i for i in result if _has_event(i)]

    if is_cobuild_scholar is not None:
        result = [
            i for i in result
            if _is_cobuild_scholar(
                i,
                _extract_project_tags(i),
                _extract_event_tags(i),
            )
            == is_cobuild_scholar
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
            if _coerce_custom_fields(i.get("custom_fields")).get(custom_field_key) == custom_field_value
        ]

    return result
