from __future__ import annotations

from app.services.stores.json_reader import get_dimension_stats

DIMENSION_NAMES = {
    "national_policy": "对国家",
    "beijing_policy": "对北京",
    "regional_policy": "对区域",
    "technology": "对技术",
    "talent": "对人才",
    "industry": "对产业",
    "sentiment": "对学院舆情",
    "universities": "对高校",
    "events": "对日程",
    "personnel": "对人事",
    "scholars": "高校师资",
}


async def list_dimensions() -> list[dict]:
    """List all dimensions with article counts and last updated timestamps."""
    stats = await get_dimension_stats()

    dimensions = []
    found = set()
    for dim_id, dim_stats in stats.items():
        found.add(dim_id)
        dimensions.append({
            "id": dim_id,
            "name": DIMENSION_NAMES.get(dim_id, dim_id),
            "article_count": dim_stats.get("total_items", 0),
            "last_updated": dim_stats.get("latest_crawl"),
        })

    # Include dimensions with zero articles
    for dim_id, dim_name in DIMENSION_NAMES.items():
        if dim_id not in found:
            dimensions.append({
                "id": dim_id,
                "name": dim_name,
                "article_count": 0,
                "last_updated": None,
            })

    dim_order = list(DIMENSION_NAMES.keys())
    return sorted(
        dimensions,
        key=lambda d: dim_order.index(d["id"]) if d["id"] in dim_order else len(dim_order),
    )
