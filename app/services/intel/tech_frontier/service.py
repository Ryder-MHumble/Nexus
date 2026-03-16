"""Tech Frontier data service — reads processed JSON and serves API queries."""
from __future__ import annotations

from typing import Any

from app.services.intel.shared import load_intel_json, parse_source_filter

MODULE = "tech_frontier"


def get_topics(
    *,
    heat_trend: str | None = None,
    our_status: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Get tech frontier topics with optional filters."""
    data = load_intel_json(MODULE, "topics.json")
    items = data.get("items", [])

    if heat_trend:
        items = [i for i in items if i.get("heatTrend") == heat_trend]

    if our_status:
        items = [i for i in items if i.get("ourStatus") == our_status]

    if keyword:
        kw = keyword.lower()
        items = [
            i for i in items
            if kw in (i.get("topic", "") + i.get("description", "")).lower()
            or any(kw in t.lower() for t in i.get("tags", []))
        ]

    total = len(items)
    items = items[offset:offset + limit]

    return {
        "generated_at": data.get("generated_at"),
        "item_count": total,
        "items": items,
    }


def get_topic_detail(topic_id: str) -> dict[str, Any] | None:
    """Get a single topic by ID."""
    data = load_intel_json(MODULE, "topics.json")
    for item in data.get("items", []):
        if item.get("id") == topic_id:
            return item
    return None


def get_opportunities(
    *,
    priority: str | None = None,
    opp_type: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Get tech frontier opportunities with optional filters."""
    data = load_intel_json(MODULE, "opportunities.json")
    items = data.get("items", [])

    if priority:
        items = [i for i in items if i.get("priority") == priority]

    if opp_type:
        items = [i for i in items if i.get("type") == opp_type]

    if keyword:
        kw = keyword.lower()
        items = [
            i for i in items
            if kw in (i.get("name", "") + i.get("summary", "")).lower()
        ]

    total = len(items)
    items = items[offset:offset + limit]

    return {
        "generated_at": data.get("generated_at"),
        "item_count": total,
        "items": items,
    }


def get_stats() -> dict[str, Any]:
    """Get tech frontier KPI statistics."""
    data = load_intel_json(MODULE, "stats.json")
    if not data or not data.get("totalTopics"):
        return {
            "generated_at": None,
            "totalTopics": 0,
            "surgingCount": 0,
            "highGapCount": 0,
            "weeklyNewSignals": 0,
            "urgentOpportunities": 0,
            "totalOpportunities": 0,
            "totalArticlesProcessed": 0,
            "dimensionBreakdown": {},
            "topicBreakdown": {},
        }
    return data


def get_signals(
    *,
    topic_id: str | None = None,
    signal_type: str | None = None,
    keyword: str | None = None,
    source_id: str | None = None,
    source_ids: str | None = None,
    source_name: str | None = None,
    source_names: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Get flattened signal feed from all topics.

    Merges relatedNews and kolVoices from topics into a single time-sorted list.
    """
    data = load_intel_json(MODULE, "topics.json")
    topics = data.get("items", [])

    signals: list[dict] = []

    for topic in topics:
        tid = topic.get("id", "")
        tname = topic.get("topic", "")

        if topic_id and tid != topic_id:
            continue

        if signal_type != "kol":
            for news in topic.get("relatedNews", []):
                signals.append({
                    "kind": "news",
                    "data": news,
                    "parentTopicId": tid,
                    "parentTopicName": tname,
                    "date": news.get("date", ""),
                })

        if signal_type != "news":
            for kol in topic.get("kolVoices", []):
                signals.append({
                    "kind": "kol",
                    "data": kol,
                    "parentTopicId": tid,
                    "parentTopicName": tname,
                    "date": kol.get("date", ""),
                })

    # Deduplicate by data.id
    seen: set[str] = set()
    unique: list[dict] = []
    for s in signals:
        sid = s["data"].get("id", "")
        if sid and sid not in seen:
            seen.add(sid)
            unique.append(s)

    # 应用信源筛选
    source_filter = parse_source_filter(source_id, source_ids, source_name, source_names)
    if source_filter:
        unique = [s for s in unique if s["data"].get("source_id") in source_filter]

    # Keyword filter
    if keyword:
        kw = keyword.lower()
        unique = [
            s for s in unique
            if kw in s["data"].get("title", "").lower()
            or kw in s["data"].get("summary", s["data"].get("statement", "")).lower()
        ]

    # Sort by date descending
    unique.sort(key=lambda s: s.get("date", ""), reverse=True)

    total = len(unique)
    unique = unique[offset:offset + limit]

    return {
        "generated_at": data.get("generated_at"),
        "item_count": total,
        "items": unique,
    }
