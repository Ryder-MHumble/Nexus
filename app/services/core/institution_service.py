"""Institution service — 统一的机构（高校+院系）CRUD 操作."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.institution import (
    DepartmentInfo,
    InstitutionDetailResponse,
    InstitutionListItem,
    InstitutionListResponse,
    InstitutionStatsResponse,
    ScholarInfo,
)

INSTITUTIONS_FILE = Path("data/scholars/institutions.json")

# ---------------------------------------------------------------------------
# 分类体系：新 Schema（entity_type + region + org_type + classification + sub_classification）
# ---------------------------------------------------------------------------

# 兼容层：旧 API 参数映射到新字段
# type → entity_type + org_type
_LEGACY_TYPE_MAP: dict[str, tuple[str, str | None]] = {
    "university": ("organization", "高校"),
    "department": ("department", None),
    "research_institute": ("organization", "研究机构"),
    "academic_society": ("organization", "行业学会"),
}

# group → classification（旧的 group 参数映射到新的 classification）
_LEGACY_GROUP_MAP: dict[str, str] = {
    "共建高校": "共建高校",
    "兄弟院校": "兄弟院校",
    "海外高校": "海外高校",
    "其他高校": "其他高校",
    "科研院所": None,  # 研究机构没有 classification
    "行业学会": None,  # 行业学会没有 classification
    "高校": None,      # 聚合分组，需要特殊处理
}

# category → sub_classification（旧的 category 直接映射到 sub_classification）

# sub_classification → classification 映射（用于从细粒度分类推导顶层分类）
_SUB_TO_CLASSIFICATION: dict[str, str] = {
    # 共建高校
    "示范性合作伙伴": "共建高校",
    "京内高校": "共建高校",
    "京外C9": "共建高校",
    "综合强校": "共建高校",
    "工科强校": "共建高校",
    "特色高校": "共建高校",
    # 兄弟院校
    "兄弟院校": "兄弟院校",
    # 海外高校
    "香港高校": "海外高校",
    "亚太高校": "海外高校",
    "欧美高校": "海外高校",
    "其他地区高校": "海外高校",
    # 其他高校
    "特色专科学校": "其他高校",
    "北京市属高校": "其他高校",
    "地方重点高校": "其他高校",
    "其他高校": "其他高校",
    # 研究机构
    "同行业机构": None,
    "交叉学科机构": None,
    "国家实验室": None,
}

# classification 显示顺序（数字越小越靠前）
_CLASSIFICATION_ORDER: dict[str, int] = {
    "共建高校": 0,
    "兄弟院校": 1,
    "海外高校": 2,
    "其他高校": 3,
}

# sub_classification 内部排序：同一 classification 内的 sub_classification 显示顺序
_SUB_CLASSIFICATION_ORDER: dict[str, int] = {
    # 共建高校
    "示范性合作伙伴": 0,
    "京内高校": 1,
    "京外C9": 2,
    "综合强校": 3,
    "工科强校": 4,
    "特色高校": 5,
    # 海外高校
    "香港高校": 0,
    "亚太高校": 1,
    "欧美高校": 2,
    "其他地区高校": 3,
    # 其他高校
    "特色专科学校": 0,
    "北京市属高校": 1,
    "地方重点高校": 2,
    "其他高校": 3,
    # 研究机构
    "同行业机构": 0,
    "交叉学科机构": 1,
    "国家实验室": 2,
}

# org_type 显示顺序
_ORG_TYPE_ORDER: dict[str, int] = {
    "高校": 0,
    "企业": 1,
    "研究机构": 2,
    "行业学会": 3,
    "其他": 4,
}

# P0 机构内部固定排序（ID → order）：清华 > 北大 > 其他
_INSTITUTION_PRESTIGE_ORDER: dict[str, int] = {
    # 示范性合作伙伴
    "tsinghua": 0,
    "pku": 1,
    # 京外C9（复交浙南科在前）
    "fudan": 10,
    "sjtu": 11,
    "zju": 12,
    "nju": 13,
    "ustc": 14,
    "hit": 15,
    "xjtu": 16,
    # 京内高校
    "cas": 20,
    "buaa": 21,
    "bit": 22,
    "bupt": 23,
    "bnu": 24,
    "ruc": 25,
    # 海外顶尖
    "nus": 30,
    "ntu_sg": 31,
    "hku": 32,
    "cuhk": 33,
    "hkust": 34,
}


def _derive_classification(sub_classification: str | None) -> str | None:
    """从 sub_classification 派生 classification（顶层分类）."""
    if not sub_classification:
        return None
    return _SUB_TO_CLASSIFICATION.get(sub_classification)


def _match_classification(
    row_classification: str | None,
    row_org_type: str | None,
    filter_classification: str,
) -> bool:
    """判断机构的 classification 是否匹配筛选条件.

    支持：
    - 精确匹配（如 filter='共建高校'）
    - 聚合匹配（如 filter='高校' 匹配所有 org_type='高校' 的机构）
    """
    # 聚合匹配：高校 → 所有 org_type='高校'
    if filter_classification == "高校":
        return row_org_type == "高校"

    # 聚合匹配：科研院所 → 所有 org_type='研究机构'
    if filter_classification == "科研院所":
        return row_org_type == "研究机构"

    # 聚合匹配：行业学会 → 所有 org_type='行业学会'
    if filter_classification == "行业学会":
        return row_org_type == "行业学会"

    # 精确匹配
    return row_classification == filter_classification


def _legacy_type_to_new(legacy_type: str | None) -> tuple[str | None, str | None]:
    """兼容层：旧 type 参数转换为新的 entity_type + org_type."""
    if not legacy_type:
        return None, None
    return _LEGACY_TYPE_MAP.get(legacy_type, (None, None))


def _legacy_group_to_classification(legacy_group: str | None) -> str | None:
    """兼容层：旧 group 参数转换为新的 classification."""
    if not legacy_group:
        return None
    return _LEGACY_GROUP_MAP.get(legacy_group)


def _normalize_priority(raw) -> int:
    """将 priority 归一化为整数（DB 存整数 0-3，或字符串 P0-P3）."""
    if raw is None:
        return 99
    if isinstance(raw, int):
        return raw
    s = str(raw).strip().upper()
    _map = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return _map.get(s, 99)


def _institution_sort_key(inst: dict) -> tuple:
    """生成机构排序 key：entity_type → region → org_type → classification → priority → sub_classification → 声望 → 名称."""
    entity_type = inst.get("entity_type") or "organization"
    region = inst.get("region") or "国内"
    org_type = inst.get("org_type") or "其他"
    classification = inst.get("classification") or ""
    sub_classification = inst.get("sub_classification") or ""

    return (
        0 if entity_type == "organization" else 1,  # 机构主体先于院系
        0 if region == "国内" else 1,               # 国内先于国际
        _ORG_TYPE_ORDER.get(org_type, 99),
        _CLASSIFICATION_ORDER.get(classification, 99),
        _normalize_priority(inst.get("priority")),
        _SUB_CLASSIFICATION_ORDER.get(sub_classification, 99),
        _INSTITUTION_PRESTIGE_ORDER.get(inst.get("id", ""), 999),
        inst.get("name", ""),
    )


class InstitutionAlreadyExistsError(ValueError):
    """Raised when trying to create an institution that already exists."""


def _get_client():
    from app.db.client import get_client  # noqa: PLC0415
    return get_client()


def _load_institutions() -> dict[str, Any]:
    """Load institutions data from JSON file."""
    if not INSTITUTIONS_FILE.exists():
        return {"last_updated": "", "universities": []}

    with open(INSTITUTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_institutions(data: dict[str, Any]) -> None:
    """Save institutions data to JSON file."""
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(INSTITUTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _flatten_institutions(universities: list[dict]) -> list[dict]:
    """将高校和院系扁平化为统一的机构列表.

    Returns:
        [
            {id, name, type='university', category, priority, scholar_count, ...},
            {id, name, type='department', parent_id, scholar_count, ...},
            ...
        ]
    """
    result = []

    for univ in universities:
        # 高校本身（数据直接存储在 univ 对象中，不在 details 字段）
        result.append({
            "id": univ["id"],
            "name": univ["name"],
            "type": "university",
            "category": univ.get("category"),
            "priority": univ.get("priority"),
            "scholar_count": univ.get("scholar_count", 0),
            "student_count_total": univ.get("student_count_total"),
            "mentor_count": univ.get("mentor_count"),
            "parent_id": None,
        })

        # 院系
        for dept in univ.get("departments", []):
            result.append({
                "id": dept["id"],
                "name": dept["name"],
                "type": "department",
                "category": None,
                "priority": None,
                "scholar_count": dept.get("scholar_count", 0),
                "student_count_total": None,
                "mentor_count": None,
                "parent_id": univ["id"],
            })

    return result


async def get_institution_list(
    type_filter: str | None = None,  # 兼容旧参数：'university' | 'department' | 'research_institute' | 'academic_society'
    group: str | None = None,        # 兼容旧参数：顶层分组（共建高校/兄弟院校/海外高校/其他高校/科研院所/行业学会/高校）
    category: str | None = None,     # 兼容旧参数：细粒度分类
    priority: str | None = None,
    parent_id: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    custom_field_key: str | None = None,
    custom_field_value: str | None = None,
    # 新参数（可选，优先级高于旧参数）
    entity_type: str | None = None,      # 'organization' | 'department'
    region: str | None = None,           # '国内' | '国际'
    org_type: str | None = None,         # '高校' | '企业' | '研究机构' | '行业学会' | '其他'
    classification: str | None = None,   # '共建高校' | '兄弟院校' | '海外高校' | '其他高校'
    sub_classification: str | None = None,  # '示范性合作伙伴' | '京内高校' | '京外C9' | ...
) -> InstitutionListResponse:
    """获取机构列表（高校+院系统一查询）.

    支持新旧两套参数：
    - 旧参数：type, group, category（兼容层自动转换）
    - 新参数：entity_type, region, org_type, classification, sub_classification（优先使用）
    """
    # 兼容层：旧参数转换为新参数
    if type_filter and not entity_type:
        entity_type_from_legacy, org_type_from_legacy = _legacy_type_to_new(type_filter)
        if not entity_type:
            entity_type = entity_type_from_legacy
        if not org_type:
            org_type = org_type_from_legacy

    if group and not classification:
        classification = _legacy_group_to_classification(group)
        # 特殊处理：group='高校' 需要匹配所有 org_type='高校'
        if group == "高校":
            org_type = "高校"
            classification = None  # 不限制 classification

    if category and not sub_classification:
        sub_classification = category

    # Try DB first
    try:
        client = _get_client()
        q = client.table("institutions").select(
            "id,name,entity_type,region,org_type,classification,"
            "priority,scholar_count,student_count_total,mentor_count,parent_id,avatar"
        )

        # 新字段过滤
        if entity_type:
            q = q.eq("entity_type", entity_type)
        if region:
            q = q.eq("region", region)
        if org_type:
            q = q.eq("org_type", org_type)
        if classification:
            q = q.eq("classification", classification)
        if sub_classification:
            q = q.eq("sub_classification", sub_classification)

        # 通用过滤
        if priority:
            q = q.eq("priority", priority)
        if parent_id:
            q = q.eq("parent_id", parent_id)
        if keyword:
            q = q.or_(f"name.ilike.%{keyword}%,id.ilike.%{keyword}%")

        res = await q.execute()
        institutions = res.data or []

        # 客户端过滤：聚合分组（group='高校' 已在上面处理）
        # 客户端过滤：聚合分组（group='科研院所' / '行业学会'）
        if group in ("科研院所", "行业学会") and not org_type:
            target_org_type = "研究机构" if group == "科研院所" else "行业学会"
            institutions = [i for i in institutions if i.get("org_type") == target_org_type]

        institutions.sort(key=_institution_sort_key)
        total = len(institutions)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        items = [
            InstitutionListItem(
                id=i["id"],
                name=i["name"],
                entity_type=i.get("entity_type"),
                region=i.get("region"),
                org_type=i.get("org_type"),
                classification=i.get("classification"),
                priority=f"P{i['priority']}" if i.get("priority") is not None else None,
                scholar_count=i.get("scholar_count", 0),
                student_count_total=i.get("student_count_total"),
                mentor_count=i.get("mentor_count"),
                parent_id=i.get("parent_id"),
                avatar=i.get("avatar"),
            )
            for i in institutions[start: start + page_size]
        ]
        return InstitutionListResponse(total=total, page=page, page_size=page_size,
                                       total_pages=total_pages, items=items)
    except Exception as exc:
        import logging; logging.getLogger(__name__).warning("DB get_institution_list failed: %s", exc)

    # JSON fallback（保留原逻辑，但已废弃）
    data = _load_institutions()
    universities = data.get("universities", [])

    # 扁平化
    institutions = _flatten_institutions(universities)

    # 过滤（使用旧逻辑）
    filtered = institutions

    if type_filter:
        filtered = [i for i in filtered if i["type"] == type_filter]

    if group:
        filtered = [i for i in filtered if _match_classification(
            _derive_classification(i.get("category")),
            "高校" if i.get("type") == "university" else None,
            group
        )]

    if category:
        filtered = [i for i in filtered if i.get("category") == category]

    if priority:
        filtered = [i for i in filtered if i.get("priority") == priority]

    if parent_id:
        filtered = [i for i in filtered if i.get("parent_id") == parent_id]

    if keyword:
        kw = keyword.lower()
        filtered = [
            i for i in filtered
            if kw in i["name"].lower() or kw in i["id"].lower()
        ]

    filtered.sort(key=_institution_sort_key)

    # 分页
    total = len(filtered)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    end = start + page_size
    items = filtered[start:end]

    # 转换为 schema
    list_items = [
        InstitutionListItem(
            id=inst["id"],
            name=inst["name"],
            type=inst["type"],
            group=_derive_classification(inst.get("category")),
            category=inst.get("category"),
            priority=inst.get("priority"),
            scholar_count=inst["scholar_count"],
            student_count_total=inst.get("student_count_total"),
            mentor_count=inst.get("mentor_count"),
            parent_id=inst.get("parent_id"),
            avatar=inst.get("avatar"),
        )
        for inst in items
    ]

    return InstitutionListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=list_items,
    )


async def get_institution_detail(institution_id: str) -> InstitutionDetailResponse | None:
    """获取机构详情（高校或院系）."""
    # Try DB first
    try:
        client = _get_client()
        res = await client.table("institutions").select("*").eq("id", institution_id).execute()
        rows = res.data or []

        if rows:
            row = rows[0]
            if row.get("entity_type") == "organization":
                return _build_university_detail_from_db(row)
            else:
                return _build_department_detail_from_db(row)
    except Exception as exc:
        import logging; logging.getLogger(__name__).warning("DB get_institution_detail failed: %s", exc)

    data = _load_institutions()
    universities = data.get("universities", [])

    # 查找高校
    for univ in universities:
        if univ["id"] == institution_id:
            return _build_university_detail(univ, data.get("last_updated"))

        # 查找院系
        for dept in univ.get("departments", []):
            if dept["id"] == institution_id:
                return _build_department_detail(dept, univ["id"])

    return None


def _build_university_detail(univ: dict, last_updated: str | None = None) -> InstitutionDetailResponse:
    """构建高校详情响应."""
    # 数据直接存储在 univ 对象中，不在 details 字段

    # 解析学者信息（university_leaders 现在是字符串列表）
    university_leaders_raw = univ.get("university_leaders", [])
    university_leaders = []
    if isinstance(university_leaders_raw, list):
        for item in university_leaders_raw:
            if isinstance(item, str):
                university_leaders.append(ScholarInfo(name=item))
            elif isinstance(item, dict):
                university_leaders.append(ScholarInfo(**item))

    # 解析重要学者（notable_scholars 现在是字符串列表）
    notable_scholars_raw = univ.get("notable_scholars", [])
    notable_scholars = []
    if isinstance(notable_scholars_raw, list):
        for item in notable_scholars_raw:
            if isinstance(item, str):
                notable_scholars.append(ScholarInfo(name=item))
            elif isinstance(item, dict):
                notable_scholars.append(ScholarInfo(**item))

    # 解析院系信息
    departments = [
        DepartmentInfo(
            id=d["id"],
            name=d["name"],
            scholar_count=d.get("scholar_count", 0),
            org_name=d.get("org_name")
        )
        for d in univ.get("departments", [])
    ]

    return InstitutionDetailResponse(
        id=univ["id"],
        name=univ["name"],
        type="university",
        org_name=univ.get("org_name"),
        avatar=univ.get("avatar"),
        group=_derive_group(univ.get("category")),
        category=univ.get("category"),
        priority=univ.get("priority"),
        student_count_24=univ.get("student_count_24"),
        student_count_25=univ.get("student_count_25"),
        student_count_total=univ.get("student_count_total"),
        mentor_count=univ.get("mentor_count"),
        resident_leaders=univ.get("resident_leaders", []),
        degree_committee=univ.get("degree_committee", []),
        teaching_committee=univ.get("teaching_committee", []),
        university_leaders=university_leaders,
        notable_scholars=notable_scholars,
        parent_id=None,
        departments=departments,
        scholar_count=univ.get("scholar_count", 0),
        last_updated=last_updated,
    )


def _build_department_detail(dept: dict, parent_id: str) -> InstitutionDetailResponse:
    """构建院系详情响应."""
    return InstitutionDetailResponse(
        id=dept["id"],
        name=dept["name"],
        type="department",
        avatar=dept.get("avatar"),
        category=None,
        priority=None,
        student_count_24=None,
        student_count_25=None,
        student_count_total=None,
        mentor_count=None,
        resident_leaders=[],
        degree_committee=[],
        teaching_committee=[],
        university_leaders=[],
        notable_scholars=[],
        parent_id=parent_id,
        departments=[],
        scholar_count=dept.get("scholar_count", 0),
        last_updated=None,
    )


def _build_university_detail_from_db(row: dict) -> InstitutionDetailResponse:
    """Build InstitutionDetailResponse from a DB institutions row (entity_type=organization)."""
    # Parse ScholarInfo lists
    def _parse_scholar_list(raw) -> list:
        if not raw:
            return []
        result = []
        for item in raw:
            if isinstance(item, str):
                result.append(ScholarInfo(name=item))
            elif isinstance(item, dict):
                result.append(ScholarInfo(**{k: v for k, v in item.items() if k in ("name", "url", "department")}))
        return result

    # Build departments list (fetch separately or use empty list)
    departments: list[DepartmentInfo] = []

    entity_type = row.get("entity_type") or "organization"

    return InstitutionDetailResponse(
        id=row["id"],
        name=row["name"],
        entity_type=entity_type,
        region=row.get("region"),
        org_type=row.get("org_type"),
        classification=row.get("classification"),
        org_name=row.get("org_name"),
        avatar=row.get("avatar"),
        priority=f"P{row['priority']}" if row.get("priority") is not None else None,
        student_count_24=row.get("student_count_24"),
        student_count_25=row.get("student_count_25"),
        student_count_total=row.get("student_count_total"),
        mentor_count=row.get("mentor_count"),
        resident_leaders=row.get("resident_leaders") or [],
        degree_committee=row.get("degree_committee") or [],
        teaching_committee=row.get("teaching_committee") or [],
        university_leaders=_parse_scholar_list(row.get("university_leaders")),
        notable_scholars=_parse_scholar_list(row.get("notable_scholars")),
        parent_id=None,
        departments=departments,
        scholar_count=row.get("scholar_count", 0),
        last_updated=None,
    )


def _build_department_detail_from_db(row: dict) -> InstitutionDetailResponse:
    """Build InstitutionDetailResponse from a DB institutions row (type=department)."""
    return InstitutionDetailResponse(
        id=row["id"],
        name=row["name"],
        entity_type="department",
        avatar=row.get("avatar"),
        parent_id=row.get("parent_id"),
        departments=[],
        scholar_count=row.get("scholar_count", 0),
        last_updated=None,
    )


async def get_institution_stats() -> InstitutionStatsResponse:
    """获取机构统计信息."""
    try:
        client = _get_client()
        res = await client.table("institutions").select(
            "entity_type,classification,priority,scholar_count,student_count_total,mentor_count"
        ).execute()
        rows = res.data or []

        unis = [r for r in rows if r.get("entity_type") == "organization"]
        depts = [r for r in rows if r.get("entity_type") == "department"]
        by_category: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        for r in unis:
            cat = r.get("classification") or "未分类"
            by_category[cat] = by_category.get(cat, 0) + 1
            raw_pri = r.get("priority")
            pri = f"P{raw_pri}" if raw_pri is not None else "未设置"
            by_priority[pri] = by_priority.get(pri, 0) + 1
        return InstitutionStatsResponse(
            total_universities=len(unis),
            total_departments=len(depts),
            total_scholars=sum(r.get("scholar_count", 0) or 0 for r in unis),
            by_category=[{"classification": k, "count": v} for k, v in by_category.items()],
            by_priority=[{"priority": k, "count": v} for k, v in by_priority.items()],
            total_students=sum(r.get("student_count_total", 0) or 0 for r in unis),
            total_mentors=sum(r.get("mentor_count", 0) or 0 for r in unis),
        )
    except Exception as exc:
        import logging; logging.getLogger(__name__).warning("DB get_institution_stats failed: %s", exc)

    data = _load_institutions()
    universities = data.get("universities", [])

    total_universities = len(universities)
    total_departments = sum(len(u.get("departments", [])) for u in universities)
    total_scholars = sum(u.get("scholar_count", 0) for u in universities)

    # 按分类统计（数据直接在 univ 对象中）
    by_category: dict[str, int] = {}
    for univ in universities:
        cat = univ.get("category", "未分类")
        if cat:
            by_category[cat] = by_category.get(cat, 0) + 1

    # 按优先级统计（数据直接在 univ 对象中）
    by_priority: dict[str, int] = {}
    for univ in universities:
        pri = univ.get("priority", "未设置")
        if pri:
            by_priority[pri] = by_priority.get(pri, 0) + 1

    # 学生和导师总数（数据直接在 univ 对象中）
    total_students = sum(
        univ.get("student_count_total", 0) or 0
        for univ in universities
    )
    total_mentors = sum(
        univ.get("mentor_count", 0) or 0
        for univ in universities
    )

    return InstitutionStatsResponse(
        total_universities=total_universities,
        total_departments=total_departments,
        total_scholars=total_scholars,
        by_category=[{"category": k, "count": v} for k, v in by_category.items()],
        by_priority=[{"priority": k, "count": v} for k, v in by_priority.items()],
        total_students=total_students,
        total_mentors=total_mentors,
    )


async def create_institution(inst_data: dict[str, Any]) -> InstitutionDetailResponse:
    """创建新机构（高校或院系），支持三种场景."""
    from app.services.core.id_generator import (  # noqa: PLC0415
        generate_institution_id,
        is_valid_institution_id,
    )

    client = _get_client()
    inst_name = inst_data.get("name")
    if not inst_name:
        raise ValueError("Institution name is required")

    inst_id = inst_data.get("id")
    if not inst_id:
        inst_id = generate_institution_id(inst_name)
    elif not is_valid_institution_id(inst_id):
        raise ValueError(f"Invalid institution ID format: '{inst_id}'.")

    # 重复检测
    check = await client.table("institutions").select("id").eq("id", inst_id).execute()
    if check.data:
        raise InstitutionAlreadyExistsError(f"机构 '{inst_id}'（{inst_name}）已存在")

    student_count_24 = inst_data.get("student_count_24") or 0
    student_count_25 = inst_data.get("student_count_25") or 0

    entity_type = inst_data.get("entity_type", "organization")
    org_type = inst_data.get("org_type")
    region = inst_data.get("region", "国内")
    classification = inst_data.get("classification")

    if entity_type == "organization":
        row: dict[str, Any] = {
            "id": inst_id, "name": inst_name,
            "entity_type": entity_type,
            "region": region,
            "org_type": org_type,
            "classification": classification,
            "org_name": inst_data.get("org_name"),
            "scholar_count": 0,
            "priority": inst_data.get("priority"),
            "student_count_24": student_count_24,
            "student_count_25": student_count_25,
            "student_count_total": student_count_24 + student_count_25,
            "mentor_count": inst_data.get("mentor_count") or 0,
            "resident_leaders": inst_data.get("resident_leaders") or [],
            "degree_committee": inst_data.get("degree_committee") or [],
            "teaching_committee": inst_data.get("teaching_committee") or [],
            "university_leaders": inst_data.get("university_leaders") or [],
            "notable_scholars": inst_data.get("notable_scholars") or [],
            "key_departments": inst_data.get("key_departments") or [],
            "joint_labs": inst_data.get("joint_labs") or [],
            "training_cooperation": inst_data.get("training_cooperation") or [],
            "academic_cooperation": inst_data.get("academic_cooperation") or [],
            "talent_dual_appointment": inst_data.get("talent_dual_appointment") or [],
            "recruitment_events": inst_data.get("recruitment_events") or [],
            "visit_exchanges": inst_data.get("visit_exchanges") or [],
            "cooperation_focus": inst_data.get("cooperation_focus") or [],
            "custom_fields": inst_data.get("custom_fields") or {},
        }
        res = await client.table("institutions").insert(row).execute()
        created = res.data[0] if res.data else row

        # 场景 3: 同时创建院系
        departments_input = inst_data.get("departments") or []
        for dept_input in departments_input:
            dept_name = dept_input.get("name")
            if not dept_name:
                continue
            dept_id = dept_input.get("id") or generate_institution_id(dept_name)
            await client.table("institutions").insert({
                "id": dept_id, "name": dept_name,
                "entity_type": "department",
                "parent_id": inst_id, "org_name": dept_input.get("org_name"), "scholar_count": 0,
            }).execute()

        return _build_university_detail_from_db(created)

    else:  # department
        parent_id = inst_data.get("parent_id")
        if not parent_id:
            raise ValueError("创建院系时 parent_id 为必填项")
        parent_check = await client.table("institutions").select("id").eq("id", parent_id).execute()
        if not parent_check.data:
            raise ValueError(f"父高校 '{parent_id}' 不存在")

        row = {
            "id": inst_id, "name": inst_name,
            "entity_type": "department",
            "parent_id": parent_id, "org_name": inst_data.get("org_name"), "scholar_count": 0,
        }
        res = await client.table("institutions").insert(row).execute()
        created = res.data[0] if res.data else row
        return _build_department_detail_from_db(created)


async def update_institution(
    institution_id: str, updates: dict[str, Any]
) -> InstitutionDetailResponse | None:
    """更新机构信息（DB）."""
    from app.services.core.custom_fields import apply_custom_fields_update  # noqa: PLC0415

    client = _get_client()

    # custom_fields 浅合并
    if "custom_fields" in updates:
        tbl = client.table("institutions")
        cur = await tbl.select("custom_fields").eq("id", institution_id).execute()
        if cur.data:
            apply_custom_fields_update(updates, cur.data[0])
        else:
            return None

    # 重新计算学生总数
    if "student_count_24" in updates or "student_count_25" in updates:
        # Get current values first
        cur = await client.table("institutions").select(
            "student_count_24,student_count_25"
        ).eq("id", institution_id).execute()
        if cur.data:
            cur_row = cur.data[0]
            sc24 = updates.get("student_count_24", cur_row.get("student_count_24") or 0) or 0
            sc25 = updates.get("student_count_25", cur_row.get("student_count_25") or 0) or 0
            updates["student_count_total"] = sc24 + sc25

    # Update the institution
    await client.table("institutions").update(updates).eq("id", institution_id).execute()

    # Fetch the updated record
    res = await client.table("institutions").select("*").eq("id", institution_id).execute()
    if not res.data:
        return None
    row = res.data[0]
    if row.get("entity_type") == "organization":
        return _build_university_detail_from_db(row)
    return _build_department_detail_from_db(row)


async def delete_institution(institution_id: str) -> bool:
    """删除机构（DB）."""
    client = _get_client()
    exist = await client.table("institutions").select("id").eq("id", institution_id).execute()
    if not exist.data:
        return False
    await client.table("institutions").delete().eq("id", institution_id).execute()
    return True


# ---------------------------------------------------------------------------
# AMiner integration helpers
# ---------------------------------------------------------------------------


def search_institutions_for_aminer(name: str) -> list[dict]:
    """Search institutions by name for AMiner integration (fuzzy match).

    Args:
        name: Search query (case-insensitive, substring match)

    Returns:
        List of matching university dicts
    """
    if not name or not name.strip():
        return []

    query = name.strip().lower()
    data = _load_institutions()
    universities = data.get("universities", [])

    matches = []
    for univ in universities:
        name_zh = univ.get("name", "").lower()
        if query in name_zh:
            matches.append(univ)

    return matches


# ---------------------------------------------------------------------------
# Scholar Institutions API helpers
# ---------------------------------------------------------------------------


async def _fetch_all_institutions_from_db() -> list[dict]:
    """Fetch all rows from institutions table."""
    client = _get_client()
    res = await client.table("institutions").select("*").execute()
    return res.data or []


async def get_institution_taxonomy() -> dict[str, Any]:
    """返回机构分类树（classification → sub_classification → institution → departments）。

    供前端侧边栏使用，按照新 Schema 的 classification/sub_classification 体系分类。
    """
    from app.schemas.institution import (  # noqa: PLC0415
        InstitutionTreeCategory,
        InstitutionTreeDepartment,
        InstitutionTreeGroup,
        InstitutionTreeInstitution,
        InstitutionTreeResponse,
    )

    try:
        client = _get_client()
        res = await client.table("institutions").select(
            "id,name,entity_type,region,org_type,classification,sub_classification,"
            "priority,scholar_count,parent_id,type,category,avatar"  # 保留旧字段兼容
        ).execute()
        rows = res.data or []
    except Exception as exc:
        import logging as _log  # noqa: PLC0415
        _log.getLogger(__name__).warning("DB get_institution_tree failed: %s", exc)
        data = _load_institutions()
        rows = _flatten_institutions(data.get("universities", []))

    # 过滤：只保留 organization（机构主体）
    orgs = [r for r in rows if r.get("entity_type") == "organization" or r.get("type") == "university"]
    depts = [r for r in rows if r.get("entity_type") == "department" or r.get("type") == "department"]

    # Build organization → departments map
    dept_map: dict[str, list[dict]] = {}
    for d in depts:
        pid = d.get("parent_id")
        if pid:
            dept_map.setdefault(pid, []).append({
                "name": d["name"],
                "scholar_count": d.get("scholar_count", 0),
            })

    # Group orgs: classification → sub_classification → [institution, ...]
    tree: dict[str, dict[str, list]] = {}
    for org in orgs:
        # 兼容新旧字段
        classification = org.get("classification")
        sub_classification = org.get("sub_classification")
        org_type = org.get("org_type")

        # 兼容层：如果新字段为空，从旧字段推导
        if not classification and org.get("category"):
            classification = _derive_classification(org.get("category"))
        if not sub_classification:
            sub_classification = org.get("category")

        # 特殊处理：研究机构和行业学会没有 classification，直接用 org_type 作为顶层分组
        if not classification:
            if org_type == "研究机构":
                classification = "科研院所"
            elif org_type == "行业学会":
                classification = "行业学会"
            else:
                classification = "其他"

        # 如果没有 sub_classification，使用 classification 作为默认值
        if not sub_classification:
            sub_classification = classification

        tree.setdefault(classification, {}).setdefault(sub_classification, []).append({
            "id": org["id"],
            "name": org["name"],
            "scholar_count": org.get("scholar_count", 0),
            "departments": sorted(
                dept_map.get(org["id"], []),
                key=lambda d: -d["scholar_count"],
            ),
        })

    # Sort institutions within each sub_classification by prestige → scholar count → name
    for subs_map in tree.values():
        for insts in subs_map.values():
            insts.sort(key=lambda i: (
                _INSTITUTION_PRESTIGE_ORDER.get(i["id"], 999),
                -i["scholar_count"],
                i["name"],
            ))

    # Build response
    groups_list = []
    for classification, subs_map in sorted(tree.items(), key=lambda kv: _CLASSIFICATION_ORDER.get(kv[0], 99)):
        categories_list = []
        for sub_classification, insts in sorted(subs_map.items(), key=lambda kv: _SUB_CLASSIFICATION_ORDER.get(kv[0], 99)):
            cat_count = sum(i["scholar_count"] for i in insts)
            categories_list.append(InstitutionTreeCategory(
                category=sub_classification,  # 前端显示的是 sub_classification
                scholar_count=cat_count,
                institutions=[
                    InstitutionTreeInstitution(
                        id=i["id"],
                        name=i["name"],
                        scholar_count=i["scholar_count"],
                        departments=[InstitutionTreeDepartment(**d) for d in i["departments"]],
                        avatar=i.get("avatar"),
                    )
                    for i in insts
                ],
            ))
        group_count = sum(c.scholar_count for c in categories_list)
        groups_list.append(InstitutionTreeGroup(
            group=classification,  # 顶层分组
            scholar_count=group_count,
            categories=categories_list,
        ))

    total = sum(g.scholar_count for g in groups_list)
    return InstitutionTreeResponse(total_scholar_count=total, groups=groups_list)


async def get_scholar_institution_detail(university_id: str) -> dict[str, Any] | None:
    """Get single university with all departments (from DB)."""
    rows = await _fetch_all_institutions_from_db()
    uni = next((r for r in rows if r["id"] == university_id and r.get("type") == "university"), None)
    if not uni:
        return None
    depts = [
        {"id": r["id"], "name": r["name"], "scholar_count": r.get("scholar_count", 0), "org_name": r.get("org_name")}
        for r in rows if r.get("type") == "department" and r.get("parent_id") == university_id
    ]
    return {**uni, "departments": depts}


async def get_scholar_department_detail(
    university_id: str,
    department_id: str,
) -> dict[str, Any] | None:
    """Get single department (from DB)."""
    client = _get_client()
    res = await client.table("institutions").select("*").eq("id", department_id).execute()
    rows = res.data or []
    for r in rows:
        if r.get("parent_id") == university_id:
            return r
    return None


async def get_institution_taxonomy() -> dict[str, Any]:
    """获取机构分类体系的层级结构和统计数据，用于前端动态渲染导航栏.

    返回格式：
    {
        "total": 277,
        "regions": {
            "国内": {
                "count": 250,
                "org_types": {
                    "高校": {
                        "count": 200,
                        "classifications": {
                            "共建高校": {"count": 50},
                            "兄弟院校": {"count": 80}
                        }
                    },
                    "企业": {"count": 10},
                    "研究机构": {"count": 15}
                }
            },
            "国际": {"count": 27, "org_types": {...}}
        }
    }
    """
    from app.db.client import get_client

    client = get_client()

    # 只查询 organization 类型（不包括 department）
    res = await client.table("institutions").select("entity_type,region,org_type,classification,sub_classification").eq("entity_type", "organization").execute()

    rows = res.data or []

    # 构建层级统计结构
    taxonomy: dict[str, Any] = {
        "total": len(rows),
        "regions": {}
    }

    for row in rows:
        region = row.get("region") or "未分类"
        org_type = row.get("org_type") or "其他"
        classification = row.get("classification")

        # 初始化 region
        if region not in taxonomy["regions"]:
            taxonomy["regions"][region] = {
                "count": 0,
                "org_types": {}
            }

        taxonomy["regions"][region]["count"] += 1

        # 初始化 org_type
        if org_type not in taxonomy["regions"][region]["org_types"]:
            taxonomy["regions"][region]["org_types"][org_type] = {
                "count": 0
            }

        taxonomy["regions"][region]["org_types"][org_type]["count"] += 1

        # 如果是高校，添加 classification 统计
        if org_type == "高校" and classification:
            if "classifications" not in taxonomy["regions"][region]["org_types"][org_type]:
                taxonomy["regions"][region]["org_types"][org_type]["classifications"] = {}

            if classification not in taxonomy["regions"][region]["org_types"][org_type]["classifications"]:
                taxonomy["regions"][region]["org_types"][org_type]["classifications"][classification] = {
                    "count": 0
                }

            taxonomy["regions"][region]["org_types"][org_type]["classifications"][classification]["count"] += 1

    return taxonomy


# ---------------------------------------------------------------------------
# 新增方法：支持「机构页」和「学者页」的不同需求
# ---------------------------------------------------------------------------


async def get_organizations_only(
    region: str | None = None,
    org_type: str | None = None,
    classification: str | None = None,
    sub_classification: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> InstitutionListResponse:
    """获取组织级别机构列表（不包含院系）— 用于「机构页」.

    Args:
        region: 地域筛选（国内 | 国际）
        org_type: 机构类型（高校 | 企业 | 研究机构 | 行业学会 | 其他）
        classification: 顶层分类（共建高校 | 兄弟院校 | 海外高校 | 其他高校）
        sub_classification: 细粒度分类（示范性合作伙伴 | 京内高校 | 京外C9 | ...）
        keyword: 关键词搜索（机构名称或 ID）
        page: 页码
        page_size: 每页条数

    Returns:
        InstitutionListResponse: 只包含 entity_type='organization' 的机构列表
    """
    from app.db.client import get_client

    client = get_client()

    # 构建查询
    query = client.table("institutions").select("*").eq("entity_type", "organization")

    # 应用筛选条件
    if region:
        query = query.eq("region", region)
    if org_type:
        query = query.eq("org_type", org_type)
    if classification:
        query = query.eq("classification", classification)
    if sub_classification:
        query = query.eq("sub_classification", sub_classification)
    if keyword:
        # 模糊搜索：name 或 id
        query = query.or_(f"name.ilike.%{keyword}%,id.ilike.%{keyword}%")

    # 执行查询
    res = await query.execute()
    rows = res.data or []

    # 排序
    rows.sort(key=_institution_sort_key)

    # 分页
    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]

    # 转换为 InstitutionListItem
    items = []
    for row in page_rows:
        # 转换 priority: int → str (P0/P1/P2/P3)
        priority_val = row.get("priority")
        if priority_val is not None and isinstance(priority_val, int):
            priority_str = f"P{priority_val}"
        else:
            priority_str = priority_val

        items.append(InstitutionListItem(
            id=row["id"],
            name=row["name"],
            type=row.get("type") or "university",  # 兼容旧字段
            entity_type=row.get("entity_type"),
            region=row.get("region"),
            org_type=row.get("org_type"),
            classification=row.get("classification"),
            sub_classification=row.get("sub_classification"),
            category=row.get("category"),  # 兼容旧字段
            priority=priority_str,
            scholar_count=row.get("scholar_count", 0),
            mentor_count=row.get("mentor_count", 0),
            student_count_total=row.get("student_count_total"),
            parent_id=row.get("parent_id"),
        ))

    return InstitutionListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,  # 向上取整
        items=items,
    )


async def get_institutions_hierarchy(
    region: str | None = None,
    org_type: str | None = None,
    classification: str | None = None,
) -> dict:
    """获取「组织→部门」层级结构 — 用于「学者页」.

    Args:
        region: 地域筛选（国内 | 国际）
        org_type: 机构类型（高校 | 企业 | 研究机构 | 其他）
        classification: 顶层分类（共建高校 | 兄弟院校 | 海外高校 | 其他高校）

    Returns:
        {
            "organizations": [
                {
                    "id": "tsinghua",
                    "name": "清华大学",
                    "entity_type": "organization",
                    "region": "国内",
                    "org_type": "高校",
                    "classification": "共建高校",
                    "sub_classification": "示范性合作伙伴",
                    "scholar_count": 770,
                    "departments": [
                        {"id": "tsinghua_cs", "name": "计算机系", "scholar_count": 136},
                        ...
                    ]
                },
                ...
            ]
        }
    """
    from app.db.client import get_client

    client = get_client()

    # 1. 查询所有组织
    org_query = client.table("institutions").select("*").eq("entity_type", "organization")

    if region:
        org_query = org_query.eq("region", region)
    if org_type:
        org_query = org_query.eq("org_type", org_type)
    if classification:
        org_query = org_query.eq("classification", classification)

    org_res = await org_query.execute()
    orgs = org_res.data or []

    # 2. 查询所有部门
    dept_res = await client.table("institutions").select("*").eq("entity_type", "department").execute()
    depts = dept_res.data or []

    # 3. 构建 parent_id → departments 映射
    dept_map: dict[str, list[dict]] = {}
    for dept in depts:
        parent_id = dept.get("parent_id")
        if parent_id:
            if parent_id not in dept_map:
                dept_map[parent_id] = []
            dept_map[parent_id].append({
                "id": dept["id"],
                "name": dept["name"],
                "scholar_count": dept.get("scholar_count", 0),
            })

    # 4. 组装层级结构
    organizations = []
    for org in orgs:
        org_id = org["id"]
        organizations.append({
            "id": org_id,
            "name": org["name"],
            "entity_type": org.get("entity_type"),
            "region": org.get("region"),
            "org_type": org.get("org_type"),
            "classification": org.get("classification"),
            "sub_classification": org.get("sub_classification"),
            "scholar_count": org.get("scholar_count", 0),
            "departments": dept_map.get(org_id, []),
        })

    # 5. 排序
    organizations.sort(key=_institution_sort_key)

    return {"organizations": organizations}

