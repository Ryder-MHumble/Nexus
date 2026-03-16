"""Read pre-processed policy intelligence JSON and serve to API."""
from __future__ import annotations

from typing import Any

from app.services.intel.shared import load_intel_json, parse_source_filter

MODULE = "policy_intel"


def get_policy_feed(
    category: str | None = None,
    importance: str | None = None,
    min_match_score: int | None = None,
    keyword: str | None = None,
    source_id: str | None = None,
    source_ids: str | None = None,
    source_name: str | None = None,
    source_names: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Read feed.json and apply optional filters."""
    data = load_intel_json(MODULE, "feed.json")
    items = data.get("items", [])

    # 应用信源筛选（优先筛选，减少后续处理量）
    source_filter = parse_source_filter(source_id, source_ids, source_name, source_names)
    if source_filter:
        items = [i for i in items if i.get("source_id") in source_filter]

    if category:
        items = [i for i in items if i.get("category") == category]
    if importance:
        items = [i for i in items if i.get("importance") == importance]
    if min_match_score is not None:
        items = [i for i in items if (i.get("matchScore") or 0) >= min_match_score]
    if keyword:
        kw = keyword.lower()
        items = [
            i for i in items
            if kw in (i.get("title") or "").lower()
            or kw in (i.get("summary") or "").lower()
            or kw in (i.get("source") or "").lower()
            or any(kw in t.lower() for t in i.get("tags", []))
        ]

    total = len(items)
    items = items[offset:offset + limit]
    return {"generated_at": data.get("generated_at"), "item_count": total, "items": items}


def get_policy_opportunities(
    status: str | None = None,
    min_match_score: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Read opportunities.json and apply optional filters."""
    data = load_intel_json(MODULE, "opportunities.json")
    items = data.get("items", [])

    if status:
        items = [i for i in items if i.get("status") == status]
    if min_match_score is not None:
        items = [i for i in items if (i.get("matchScore") or 0) >= min_match_score]

    total = len(items)
    items = items[offset:offset + limit]
    return {"generated_at": data.get("generated_at"), "item_count": total, "items": items}


def get_policy_stats() -> dict[str, Any]:
    """Get summary statistics without running filter logic."""
    feed_data = load_intel_json(MODULE, "feed.json")
    opps_data = load_intel_json(MODULE, "opportunities.json")
    return {
        "total_feed_items": feed_data.get("item_count", 0),
        "total_opportunities": opps_data.get("item_count", 0),
        "generated_at": feed_data.get("generated_at"),
    }
