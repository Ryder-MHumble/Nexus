"""Classification mapping and conversion for institution taxonomy.

Handles conversion between old and new classification systems:
- Old: type (university/department/research_institute/academic_society) + category (细粒度分类)
- New: entity_type (organization/department) + region (国内/国际) + org_type (高校/企业/研究机构/行业学会/其他)
      + classification (共建高校/兄弟院校/海外高校/其他高校) + sub_classification (示范性合作伙伴/京内高校/etc.)
"""

from __future__ import annotations

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
    "京内高校": ("共建高校", "京内高校"),
    "京外C9": ("共建高校", "京外C9"),
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
    "其他高校": ("其他高校", "其他高校"),
    # 研究机构
    "同行业机构": (None, "同行业机构"),
    "交叉学科机构": (None, "交叉学科机构"),
    "国家实验室": (None, "国家实验室"),
}

# New → Old reverse mapping (for backward compatibility)
CLASSIFICATION_TO_CATEGORY = {
    ("共建高校", "示范性合作伙伴"): "示范性合作伙伴",
    ("共建高校", "京内高校"): "京内高校",
    ("共建高校", "京外C9"): "京外C9",
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
    ("其他高校", "其他高校"): "其他高校",
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
    return CATEGORY_TO_CLASSIFICATION.get(old_category, (None, old_category))


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
