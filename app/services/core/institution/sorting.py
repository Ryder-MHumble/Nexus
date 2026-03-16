"""Sorting and ordering logic for institutions.

Defines display order for regions, org_types, classifications, and priorities.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Display Order Definitions
# ---------------------------------------------------------------------------

# Region display order
REGION_ORDER = ["国内", "国际"]

# Org type display order
ORG_TYPE_ORDER = ["高校", "企业", "研究机构", "行业学会", "其他"]

# Classification display order (within each org_type)
CLASSIFICATION_ORDER = ["共建高校", "兄弟院校", "海外高校", "其他高校"]

# Priority display order (P0 > P1 > P2 > P3)
PRIORITY_ORDER = ["P0", "P1", "P2", "P3"]

# ---------------------------------------------------------------------------
# Sorting Functions
# ---------------------------------------------------------------------------


def get_sort_key(record: dict) -> tuple:
    """Generate sort key for an institution record.

    Sorting order:
    1. region (国内 before 国际)
    2. org_type (高校 > 企业 > 研究机构 > 行业学会 > 其他)
    3. classification (共建高校 > 兄弟院校 > 海外高校 > 其他高校)
    4. priority (P0 > P1 > P2 > P3)
    5. reputation_rank (ascending, None last)
    6. name (alphabetical)

    Args:
        record: Institution record dict

    Returns:
        Sort key tuple
    """
    region = record.get("region")
    org_type = record.get("org_type")
    classification = record.get("classification")
    priority = record.get("priority")
    reputation_rank = record.get("reputation_rank")
    name = record.get("name", "")

    # Region order
    region_idx = REGION_ORDER.index(region) if region in REGION_ORDER else 999

    # Org type order
    org_type_idx = ORG_TYPE_ORDER.index(org_type) if org_type in ORG_TYPE_ORDER else 999

    # Classification order
    classification_idx = (
        CLASSIFICATION_ORDER.index(classification) if classification in CLASSIFICATION_ORDER else 999
    )

    # Priority order
    priority_idx = PRIORITY_ORDER.index(priority) if priority in PRIORITY_ORDER else 999

    # Reputation rank (None goes last)
    reputation_key = (reputation_rank is None, reputation_rank or 0)

    return (
        region_idx,
        org_type_idx,
        classification_idx,
        priority_idx,
        reputation_key,
        name,
    )


def sort_institutions(records: list[dict]) -> list[dict]:
    """Sort institution records by display order.

    Args:
        records: List of institution records

    Returns:
        Sorted list of records
    """
    return sorted(records, key=get_sort_key)
