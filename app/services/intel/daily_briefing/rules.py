"""Data collection and aggregation for AI Daily Briefing.

Collects articles from all dimensions, filters by date window,
computes per-dimension statistics, and prepares the input summary
for LLM narrative generation.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.services.intel.shared import load_intel_json
from app.services.stores.json_reader import get_all_articles

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dimension → frontend moduleId mapping
# ---------------------------------------------------------------------------

DIMENSION_MODULE_MAP: dict[str, str] = {
    "national_policy": "policy-intel",
    "beijing_policy": "policy-intel",
    "technology": "tech-frontier",
    "talent": "talent-radar",
    "industry": "tech-frontier",
    "universities": "university-eco",
    "events": "smart-schedule",
    "personnel": "talent-radar",
    "twitter": "tech-frontier",
}

# Dimension → Chinese display name
DIMENSION_DISPLAY_NAME: dict[str, str] = {
    "national_policy": "国家政策",
    "beijing_policy": "北京政策",
    "technology": "技术动态",
    "talent": "人才政策",
    "industry": "产业动态",
    "universities": "高校动态",
    "events": "活动会议",
    "personnel": "人事变动",
    "twitter": "Twitter/KOL",
}

# Module → icon mapping for metric cards
MODULE_ICON_MAP: dict[str, str] = {
    "policy-intel": "policy",
    "tech-frontier": "tech",
    "talent-radar": "talent",
    "university-eco": "university",
    "smart-schedule": "calendar",
}

# Module → Chinese title
MODULE_TITLE_MAP: dict[str, str] = {
    "policy-intel": "政策情报",
    "tech-frontier": "科技前沿",
    "talent-radar": "人事动态",
    "university-eco": "高校生态",
    "smart-schedule": "智能日程",
}

# Max articles per dimension to include in LLM input
MAX_ARTICLES_PER_DIM = 20
# Max content chars per article for LLM
MAX_TITLE_LEN = 80
# Max content snippet chars to include in LLM input
MAX_CONTENT_SNIPPET = 300


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


async def collect_daily_articles(
    target_date: date,
    lookback_days: int = 1,
) -> dict[str, Any]:
    """Gather articles in the time window and group by dimension.

    Args:
        target_date: The date for the report.
        lookback_days: How many days back to include (default 1 = yesterday+today).

    Returns:
        Dict with keys: target_date, articles_by_dimension, total_count,
        dimension_counts.
    """
    date_from = target_date - timedelta(days=lookback_days)
    date_to = target_date

    all_articles = await get_all_articles(date_from=date_from, date_to=date_to)

    articles_by_dim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for article in all_articles:
        dim = article.get("dimension", "unknown")
        articles_by_dim[dim].append(article)

    dimension_counts = {dim: len(arts) for dim, arts in articles_by_dim.items()}

    return {
        "target_date": target_date.isoformat(),
        "articles_by_dimension": dict(articles_by_dim),
        "total_count": len(all_articles),
        "dimension_counts": dimension_counts,
    }


# ---------------------------------------------------------------------------
# Metric cards computation
# ---------------------------------------------------------------------------


def compute_metric_cards(
    articles_by_dim: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Compute real MetricCardData from article counts and processed intel.

    Returns list of metric card dicts matching the frontend MetricCardData
    interface.
    """
    # Aggregate article counts by module
    module_article_counts: dict[str, int] = defaultdict(int)
    for dim, articles in articles_by_dim.items():
        module_id = DIMENSION_MODULE_MAP.get(dim, "tech-frontier")
        module_article_counts[module_id] += len(articles)

    # Load policy intel stats
    policy_feed = load_intel_json("policy_intel", "feed.json")
    policy_items = policy_feed.get("items", [])
    high_match_count = sum(
        1 for item in policy_items if item.get("matchScore", 0) >= 70
    )
    opportunities = load_intel_json("policy_intel", "opportunities.json")
    opportunity_count = len(opportunities.get("items", []))

    # Load personnel intel stats
    personnel_changes = load_intel_json("personnel_intel", "changes.json")
    personnel_count = len(personnel_changes.get("items", []))

    cards: list[dict[str, Any]] = []

    # 1. Policy Intel card
    policy_count = module_article_counts.get("policy-intel", 0)
    cards.append({
        "id": "policy-intel",
        "title": "政策情报",
        "icon": "policy",
        "metrics": [
            {
                "label": "新政策",
                "value": f"{policy_count}条",
                "variant": "success" if policy_count > 0 else "default",
            },
            {
                "label": "高匹配",
                "value": f"{high_match_count}条",
                "variant": "warning" if high_match_count > 0 else "default",
            },
            {
                "label": "待申报",
                "value": f"{opportunity_count}项",
            },
        ],
    })

    # 2. Tech Frontier card
    # Count by sub-dimensions for richer display
    tech_dims = ["technology", "industry", "twitter"]
    tech_breakdown = {
        dim: len(articles_by_dim.get(dim, []))
        for dim in tech_dims
    }
    cards.append({
        "id": "tech-frontier",
        "title": "科技前沿",
        "icon": "tech",
        "metrics": [
            {
                "label": "技术动态",
                "value": f"{tech_breakdown.get('technology', 0)}条",
                "variant": "success" if tech_breakdown.get("technology", 0) > 0 else "default",
            },
            {"label": "行业动态", "value": f"{tech_breakdown.get('industry', 0)}条"},
            {"label": "KOL动态", "value": f"{tech_breakdown.get('twitter', 0)}条"},
        ],
    })

    # 3. Talent Radar card
    talent_count = len(articles_by_dim.get("talent", []))
    cards.append({
        "id": "talent-radar",
        "title": "人事动态",
        "icon": "talent",
        "metrics": [
            {
                "label": "人事变动",
                "value": f"{personnel_count}条",
                "variant": "success" if personnel_count > 0 else "default",
            },
            {"label": "人才政策", "value": f"{talent_count}条"},
            {
                "label": "总计",
                "value": f"{module_article_counts.get('talent-radar', 0)}条",
            },
        ],
    })

    # 4. University Eco card
    uni_count = module_article_counts.get("university-eco", 0)
    cards.append({
        "id": "university-eco",
        "title": "高校生态",
        "icon": "university",
        "metrics": [
            {
                "label": "高校动态",
                "value": f"{uni_count}条",
                "variant": "success" if uni_count > 0 else "default",
            },
        ],
    })

    # 5. Smart Schedule card
    events_count = module_article_counts.get("smart-schedule", 0)
    cards.append({
        "id": "smart-schedule",
        "title": "智能日程",
        "icon": "calendar",
        "metrics": [
            {
                "label": "活动会议",
                "value": f"{events_count}条",
                "variant": "success" if events_count > 0 else "default",
            },
        ],
    })

    return cards


# ---------------------------------------------------------------------------
# LLM input preparation
# ---------------------------------------------------------------------------


def prepare_llm_input(
    articles_by_dim: dict[str, list[dict[str, Any]]],
) -> tuple[str, dict[str, dict[str, Any]]]:
    """Build structured text summary for LLM consumption.

    Each article entry includes dimension tag, title, source, date, and content
    snippet. An article_index is built for post-processing (injecting url/content
    into narrative link objects).

    Returns:
        Tuple of (llm_input_text, article_index).
        article_index maps short ID (url_hash[:8]) to article metadata.
    """
    lines: list[str] = []
    article_index: dict[str, dict[str, Any]] = {}

    # Group dimensions by module for clearer LLM input structure
    module_groups: list[tuple[str, str, list[str]]] = [
        ("政策情报", "policy-intel", ["national_policy", "beijing_policy"]),
        ("科技前沿", "tech-frontier", ["technology", "industry", "twitter"]),
        ("高校动态", "university-eco", ["universities"]),
        ("人事动态", "talent-radar", ["talent", "personnel"]),
        ("活动会议", "smart-schedule", ["events"]),
    ]

    for group_name, _module_id, dim_list in module_groups:
        group_articles: list[tuple[str, dict[str, Any]]] = []
        for dim in dim_list:
            for article in articles_by_dim.get(dim, []):
                group_articles.append((dim, article))

        if not group_articles:
            continue

        # Add section header for this module group
        lines.append(f"\n### {group_name}（共{len(group_articles)}条）")
        lines.append("")

        for dim in dim_list:
            articles = articles_by_dim.get(dim, [])
            if not articles:
                continue

            # Prioritize new articles, then by published_at desc (stable sort)
            sorted_articles = sorted(
                articles, key=lambda a: a.get("published_at") or "", reverse=True,
            )
            sorted_articles.sort(
                key=lambda a: not a.get("is_new", False),
            )

            display_name = DIMENSION_DISPLAY_NAME.get(dim, dim)
            module_id = DIMENSION_MODULE_MAP.get(dim, "tech-frontier")
            for article in sorted_articles[:MAX_ARTICLES_PER_DIM]:
                title = (article.get("title") or "").strip()
                full_title = title
                if len(title) > MAX_TITLE_LEN:
                    title = title[:MAX_TITLE_LEN] + "..."
                source_name = article.get("source_name", "")
                pub_date = (article.get("published_at") or "")[:10]
                url_hash = article.get("url_hash", "")
                short_id = url_hash[:8] if url_hash else ""

                # Build article index entry for post-processing
                if short_id:
                    content_raw = (article.get("content") or "").strip()
                    article_index[short_id] = {
                        "url": article.get("url", ""),
                        "title": full_title,
                        "contentSnippet": (
                            content_raw[:MAX_CONTENT_SNIPPET] if content_raw else ""
                        ),
                        "sourceName": source_name,
                        "moduleId": module_id,
                    }

                extra_info = ""
                # Include policy enrichment info if available
                if dim in ("national_policy", "beijing_policy"):
                    extra = article.get("extra", {})
                    match_score = extra.get("matchScore")
                    funding = extra.get("funding")
                    deadline = extra.get("deadline")
                    parts = []
                    if match_score:
                        parts.append(f"匹配度{match_score}")
                    if funding:
                        parts.append(f"资金{funding}")
                    if deadline:
                        parts.append(f"截止{deadline}")
                    if parts:
                        extra_info = ", " + ", ".join(parts)

                # Main line with short ID for LLM cross-referencing
                id_tag = f"[#{short_id}] " if short_id else ""
                line = (
                    f"{id_tag}[{display_name}] {title}"
                    f"（来源: {source_name}, {pub_date}{extra_info}）"
                )
                lines.append(line)

                # Add content snippet if available
                content_raw = (article.get("content") or "").strip()
                if content_raw:
                    snippet = content_raw[:MAX_CONTENT_SNIPPET]
                    if len(content_raw) > MAX_CONTENT_SNIPPET:
                        snippet += "..."
                    lines.append(f"  正文摘要: {snippet}")

    return "\n".join(lines), article_index


def build_metric_summary(
    articles_by_dim: dict[str, list[dict[str, Any]]],
    target_date: date,
) -> str:
    """Build a short statistical summary for the LLM user prompt."""
    total = sum(len(v) for v in articles_by_dim.values())
    dim_count = len([d for d, v in articles_by_dim.items() if v])
    parts: list[str] = [
        f"日期: {target_date.isoformat()}",
        f"总计: {total}条信息，覆盖{dim_count}个维度",
    ]

    # Policy
    national_count = len(articles_by_dim.get("national_policy", []))
    beijing_count = len(articles_by_dim.get("beijing_policy", []))
    policy_count = national_count + beijing_count
    if policy_count > 0:
        detail = []
        if national_count:
            detail.append(f"国家级 {national_count}条")
        if beijing_count:
            detail.append(f"北京市 {beijing_count}条")
        parts.append(f"政策情报: {policy_count}条新政策（{', '.join(detail)}）")

    # Tech
    tech_count = len(articles_by_dim.get("technology", []))
    industry_count = len(articles_by_dim.get("industry", []))
    twitter_count = len(articles_by_dim.get("twitter", []))
    tech_total = tech_count + industry_count + twitter_count
    if tech_total > 0:
        detail = []
        if tech_count:
            detail.append(f"技术 {tech_count}篇")
        if industry_count:
            detail.append(f"行业 {industry_count}篇")
        if twitter_count:
            detail.append(f"KOL {twitter_count}篇")
        parts.append(f"科技前沿: {tech_total}篇（{', '.join(detail)}）")

    # Talent + Personnel
    talent_count = len(articles_by_dim.get("talent", []))
    personnel_count = len(articles_by_dim.get("personnel", []))
    if talent_count + personnel_count > 0:
        detail = []
        if personnel_count:
            detail.append(f"人事变动 {personnel_count}条")
        if talent_count:
            detail.append(f"人才政策 {talent_count}条")
        parts.append(f"人事动态: {talent_count + personnel_count}条（{', '.join(detail)}）")

    # Universities
    uni_count = len(articles_by_dim.get("universities", []))
    if uni_count > 0:
        parts.append(f"高校动态: {uni_count}篇")

    # Events
    events_count = len(articles_by_dim.get("events", []))
    if events_count > 0:
        parts.append(f"活动会议: {events_count}个")

    # Instruction for LLM
    parts.append("")
    parts.append("请为每个有数据的维度都生成至少一个段落，每段尽量覆盖该维度3-5条重要信息。")

    return "\n".join(parts)
