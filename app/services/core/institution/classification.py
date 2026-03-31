"""Classification mapping and conversion for institution taxonomy.

Handles conversion between old and new classification systems:
- Old: type (university/department/research_institute/academic_society) + category (细粒度分类)
- New: entity_type (organization/department) + region (国内/国际) + org_type (高校/企业/研究机构/行业学会/其他)
      + classification (共建高校/兄弟院校/海外高校/其他高校) + sub_classification (示范性合作伙伴/京内高校/etc.)
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Old → New Mapping Tables
# ---------------------------------------------------------------------------

# type → (entity_type, org_type)
TYPE_TO_ENTITY_ORG = {
    "university": ("organization", "高校"),
    "department": ("department", None),
    "research_institute": ("organization", "研究机构"),
    "academic_society": ("organization", "行业学会"),
    "company": ("organization", "企业"),
}

# category → (classification, sub_classification)
CATEGORY_TO_CLASSIFICATION = {
    # 共建高校
    "示范性合作伙伴": ("共建高校", "示范性合作伙伴"),
    "境内高校": ("共建高校", "境内高校"),
    "京内高校": ("共建高校", "境内高校"),  # 历史别名兼容
    "京外C9高校": ("共建高校", "京外C9高校"),
    "京外C9": ("共建高校", "京外C9高校"),  # 历史别名兼容
    "综合强校": ("共建高校", "综合强校"),
    "工科强校": ("共建高校", "工科强校"),
    "特色高校": ("共建高校", "特色高校"),
    # 兄弟院校
    "兄弟院校": ("兄弟院校", "兄弟院校"),
    # 海外高校
    "香港高校": ("海外高校", "香港高校"),
    "亚太高校": ("海外高校", "亚太高校"),
    "欧美高校": ("海外高校", "欧美高校"),
    "其他地区高校": ("海外高校", "其他地区高校"),
    # 其他高校
    "特色专科学校": ("其他高校", "特色专科学校"),
    "北京市属高校": ("其他高校", "北京市属高校"),
    "地方重点高校": ("其他高校", "地方重点高校"),
    "其他高校": ("其他高校", "其他"),
    "其他": ("其他高校", "其他"),
    # 新研机构（研究机构）
    "同行机构": ("新研机构", "同行机构"),
    "同行业机构": ("新研机构", "同行机构"),  # 历史别名兼容
    "交叉学科机构": ("新研机构", "交叉学科机构"),
    "国家实验室": ("新研机构", "国家实验室"),
    # 行业学会
    "行业学会": ("行业学会", "行业学会"),
}

# New → Old reverse mapping (for backward compatibility)
CLASSIFICATION_TO_CATEGORY = {
    ("共建高校", "示范性合作伙伴"): "示范性合作伙伴",
    ("共建高校", "境内高校"): "境内高校",
    ("共建高校", "京外C9高校"): "京外C9高校",
    ("共建高校", "综合强校"): "综合强校",
    ("共建高校", "工科强校"): "工科强校",
    ("共建高校", "特色高校"): "特色高校",
    ("兄弟院校", "兄弟院校"): "兄弟院校",
    ("海外高校", "香港高校"): "香港高校",
    ("海外高校", "亚太高校"): "亚太高校",
    ("海外高校", "欧美高校"): "欧美高校",
    ("海外高校", "其他地区高校"): "其他地区高校",
    ("其他高校", "特色专科学校"): "特色专科学校",
    ("其他高校", "北京市属高校"): "北京市属高校",
    ("其他高校", "地方重点高校"): "地方重点高校",
    ("其他高校", "其他"): "其他",
    ("新研机构", "同行机构"): "同行机构",
    ("新研机构", "交叉学科机构"): "交叉学科机构",
    ("新研机构", "国家实验室"): "国家实验室",
    ("行业学会", "行业学会"): "行业学会",
}

# ---------------------------------------------------------------------------
# New classification taxonomy (for editing and validation)
# ---------------------------------------------------------------------------

CLASSIFICATION_SUBCLASSIFICATION_OPTIONS: Final[dict[str, list[str]]] = {
    "共建高校": ["示范性合作伙伴", "境内高校", "京外C9高校", "综合强校", "工科强校", "特色高校"],
    "兄弟院校": ["兄弟院校"],
    "海外高校": ["香港高校", "亚太高校", "欧美高校", "其他地区高校"],
    "其他高校": ["特色专科学校", "北京市属高校", "地方重点高校", "其他"],
    "新研机构": ["同行机构", "交叉学科机构", "国家实验室"],
    "行业学会": ["行业学会"],
}

_CLASSIFICATION_ALIASES: Final[dict[str, str]] = {
    "科研院所": "新研机构",
    "研究机构": "新研机构",
}

_ORG_TYPE_ALIASES: Final[dict[str, str]] = {
    "高校": "高校",
    "企业": "企业",
    "公司": "企业",
    "研究机构": "研究机构",
    "科研院所": "研究机构",
    "行业学会": "行业学会",
    "行业协会": "行业学会",
    "其他": "其他",
}

_SUB_CLASSIFICATION_ALIASES: Final[dict[str, str]] = {
    "京内高校": "境内高校",
    "京外C9": "京外C9高校",
    "其他高校": "其他",
    "同行业机构": "同行机构",
}

_ORG_TYPE_ALLOWED_CLASSIFICATIONS: Final[dict[str, set[str]]] = {
    "高校": {"共建高校", "兄弟院校", "海外高校", "其他高校"},
    "研究机构": {"新研机构"},
    "行业学会": {"行业学会"},
}

SUB_CLASSIFICATION_TO_CLASSIFICATION: Final[dict[str, str]] = {
    sub: classification
    for classification, sub_list in CLASSIFICATION_SUBCLASSIFICATION_OPTIONS.items()
    for sub in sub_list
}

# ---------------------------------------------------------------------------
# Conversion Functions
# ---------------------------------------------------------------------------


def convert_type_to_entity_org(old_type: str | None) -> tuple[str | None, str | None]:
    """Convert old type field to (entity_type, org_type).

    Args:
        old_type: Old type value (university/department/research_institute/academic_society/company)

    Returns:
        Tuple of (entity_type, org_type)
    """
    if not old_type:
        return None, None
    return TYPE_TO_ENTITY_ORG.get(old_type, (None, None))


def convert_category_to_classification(
    old_category: str | None,
) -> tuple[str | None, str | None]:
    """Convert old category field to (classification, sub_classification).

    Args:
        old_category: Old category value (细粒度分类)

    Returns:
        Tuple of (classification, sub_classification)
    """
    if not old_category:
        return None, None
    return CATEGORY_TO_CLASSIFICATION.get(old_category, (None, normalize_sub_classification(old_category)))


def convert_classification_to_category(
    classification: str | None, sub_classification: str | None
) -> str | None:
    """Convert new classification fields back to old category (for backward compatibility).

    Args:
        classification: New classification value
        sub_classification: New sub_classification value

    Returns:
        Old category value or None
    """
    if not classification or not sub_classification:
        return None
    return CLASSIFICATION_TO_CATEGORY.get((classification, sub_classification))


def normalize_priority(priority: int | str | None) -> str | None:
    """Normalize priority value to string format (P0/P1/P2/P3).

    Args:
        priority: Priority value (int 0-3 or string "P0"-"P3")

    Returns:
        Normalized priority string or None
    """
    if priority is None:
        return None
    if isinstance(priority, int):
        return f"P{priority}"
    if isinstance(priority, str) and priority.startswith("P"):
        return priority
    return None


def parse_priority(priority: int | str | None) -> int | None:
    """Parse priority into DB integer format (0-3).

    Accepts int or 'P0'/'P1'/'P2'/'P3'. Returns None when empty.
    """
    if priority is None:
        return None
    if isinstance(priority, int):
        return priority
    if isinstance(priority, str):
        value = priority.strip().upper()
        if value == "":
            return None
        if value.startswith("P"):
            value = value[1:]
        if value.isdigit():
            return int(value)
    raise ValueError("priority 必须为整数或 P0/P1/P2/P3")


def normalize_classification(classification: str | None) -> str | None:
    """Normalize top-level classification with aliases."""
    if classification is None:
        return None
    value = classification.strip()
    if value == "":
        return None
    return _CLASSIFICATION_ALIASES.get(value, value)


def normalize_org_type(org_type: str | None) -> str | None:
    """Normalize org_type with aliases."""
    if org_type is None:
        return None
    value = org_type.strip()
    if value == "":
        return None
    return _ORG_TYPE_ALIASES.get(value, value)


def normalize_sub_classification(sub_classification: str | None) -> str | None:
    """Normalize sub-classification with aliases."""
    if sub_classification is None:
        return None
    value = sub_classification.strip()
    if value == "":
        return None
    return _SUB_CLASSIFICATION_ALIASES.get(value, value)


def resolve_classification_pair(
    classification: str | None,
    sub_classification: str | None,
    *,
    org_type: str | None = None,
) -> tuple[str | None, str | None]:
    """Validate and resolve classification/sub_classification pair.

    Rules:
    - Allows either value to be omitted.
    - If only sub_classification is provided, infer classification.
    - If both are provided, they must match the predefined taxonomy.
    """
    normalized_classification = normalize_classification(classification)
    normalized_sub = normalize_sub_classification(sub_classification)
    normalized_org_type = normalize_org_type(org_type)

    if normalized_sub and not normalized_classification:
        normalized_classification = SUB_CLASSIFICATION_TO_CLASSIFICATION.get(normalized_sub)
        if not normalized_classification:
            raise ValueError(f"未知的 sub_classification: {normalized_sub}")

    if normalized_classification and normalized_sub:
        allowed = CLASSIFICATION_SUBCLASSIFICATION_OPTIONS.get(normalized_classification)
        if not allowed:
            raise ValueError(f"未知的 classification: {normalized_classification}")
        if normalized_sub not in allowed:
            raise ValueError(
                f"classification '{normalized_classification}' 不允许 sub_classification '{normalized_sub}'"
            )

    if normalized_classification and not normalized_sub:
        # 保留仅设置顶层分类的能力（前端可后续补全子分类）
        if normalized_classification not in CLASSIFICATION_SUBCLASSIFICATION_OPTIONS:
            raise ValueError(f"未知的 classification: {normalized_classification}")

    if normalized_org_type:
        allowed = _ORG_TYPE_ALLOWED_CLASSIFICATIONS.get(normalized_org_type)
        if allowed:
            if normalized_classification and normalized_classification not in allowed:
                allowed_text = " / ".join(sorted(allowed))
                raise ValueError(
                    f"org_type '{normalized_org_type}' 仅允许 classification 为: {allowed_text}"
                )
        else:
            # 企业/其他等类型默认不挂高校分类
            if normalized_classification:
                raise ValueError(
                    f"org_type '{normalized_org_type}' 不支持设置 classification/sub_classification"
                )

    return normalized_classification, normalized_sub
