"""Legacy compatibility layer for institution service.

Provides backward-compatible functions for existing code that hasn't migrated yet.
"""

from __future__ import annotations

from app.schemas.institution import InstitutionListResponse
from app.services.core.institution.list_query import get_institutions_unified
from app.services.core.institution.storage import fetch_all_institutions


async def get_institution_list(
    type_filter: str | None = None,
    group: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    parent_id: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    custom_field_key: str | None = None,
    custom_field_value: str | None = None,
    entity_type: str | None = None,
    region: str | None = None,
    org_type: str | None = None,
    classification: str | None = None,
    sub_classification: str | None = None,
) -> InstitutionListResponse:
    """Legacy wrapper for get_institutions_unified.

    Maps old parameter names to new ones for backward compatibility.
    """
    # Map legacy type_filter to entity_type + org_type
    if type_filter and not entity_type:
        type_map = {
            "university": ("organization", "高校"),
            "department": ("department", None),
            "research_institute": ("organization", "研究机构"),
            "academic_society": ("organization", "行业学会"),
        }
        if type_filter in type_map:
            entity_type, mapped_org_type = type_map[type_filter]
            if not org_type:
                org_type = mapped_org_type

    # Map legacy group to classification
    if group and not classification:
        group_map = {
            "共建高校": "共建高校",
            "兄弟院校": "兄弟院校",
            "海外高校": "海外高校",
            "其他高校": "其他高校",
        }
        classification = group_map.get(group)

    # Map legacy category to sub_classification
    if category and not sub_classification:
        sub_classification = category

    # Call unified function with flat view
    return await get_institutions_unified(
        view="flat",
        entity_type=entity_type,
        region=region,
        org_type=org_type,
        classification=classification,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


def search_institutions_for_aminer(name: str) -> list[dict]:
    """Search institutions by name for AMiner integration (synchronous, fuzzy match).

    This is a synchronous wrapper for backward compatibility.
    For new code, use async functions from storage module.

    Args:
        name: Search query (case-insensitive, substring match)

    Returns:
        List of matching institution dicts
    """
    if not name or not name.strip():
        return []

    import asyncio

    query = name.strip().lower()

    async def _search():
        institutions = await fetch_all_institutions()
        matches = []
        for inst in institutions:
            inst_name = inst.get("name", "").lower()
            if query in inst_name and inst.get("entity_type") == "organization":
                matches.append(inst)
        return matches

    # Run async function in sync context
    try:
        # Try to get existing event loop
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # No event loop exists, create a new one
        return asyncio.run(_search())

    # If loop exists but is not running, use it
    if not loop.is_running():
        return loop.run_until_complete(_search())

    # If loop is running (we're in async context), this shouldn't happen
    # but if it does, we need to create a task
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, _search())
        return future.result()
