"""Tech Frontier processing pipeline — callable from orchestrator.

Reads raw articles from technology/industry/twitter/universities dimensions,
classifies by 8 tech topics, computes heat trends, extracts signals and
opportunities, and generates processed JSON files for the frontend API.

Output:
  data/processed/tech_frontier/
    topics.json          — 8 topics with embedded signals, news, KOL voices
    opportunities.json   — detected opportunities
    stats.json           — KPI metrics
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.config import BASE_DIR
from app.services.intel.pipeline.base import HashTracker, save_output_json
from app.services.intel.tech_frontier.rules import (
    TOPICS_CONFIG,
    UNI_AI_INSTITUTE_SOURCES,
    build_kol_voice,
    build_topic_news,
    classify_article,
    compute_heat,
    detect_opportunity,
    is_kol_source,
    split_by_period,
)
from app.services.stores.json_reader import get_articles

logger = logging.getLogger(__name__)

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

PROCESSED_DIR = BASE_DIR / "data" / "processed" / "tech_frontier"

_hash_tracker = HashTracker(PROCESSED_DIR / "_processed_hashes.json", PROCESSED_DIR)

# Dimensions and source filters
PRIMARY_DIMENSIONS = ["technology"]
TWITTER_DIMENSION = "twitter"
TWITTER_TECH_SOURCES = {
    "twitter_ai_kol_international",
    "twitter_ai_kol_chinese",
    "twitter_ai_breakthrough",
    "twitter_ai_papers",
}
INDUSTRY_DIMENSION = "industry"
UNIVERSITY_DIMENSION = "universities"

# Limits per topic to keep output manageable
MAX_NEWS_PER_TOPIC = 30
MAX_KOL_PER_TOPIC = 10

FEED_MIN_SCORE = 20  # Minimum match_score for articles to appear in relatedNews


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


async def _load_all_articles() -> list[dict]:
    """Load articles from all relevant dimensions and filter."""
    articles: list[dict] = []

    # 1. Technology dimension (all sources)
    for dim in PRIMARY_DIMENSIONS:
        articles.extend(await get_articles(dim))

    # 2. Twitter (only tech-related sources)
    twitter_articles = await get_articles(TWITTER_DIMENSION)
    articles.extend(
        a for a in twitter_articles
        if a.get("source_id") in TWITTER_TECH_SOURCES
    )

    # 3. Industry dimension (all enabled sources)
    articles.extend(await get_articles(INDUSTRY_DIMENSION))

    # 4. Universities (only AI research institute sources)
    uni_articles = await get_articles(UNIVERSITY_DIMENSION)
    articles.extend(
        a for a in uni_articles
        if a.get("source_id") in UNI_AI_INSTITUTE_SOURCES
    )

    return articles


def _deduplicate(articles: list[dict]) -> list[dict]:
    """Deduplicate by url_hash, keeping first occurrence."""
    seen: set[str] = set()
    unique: list[dict] = []
    for a in articles:
        h = a.get("url_hash", "")
        if h and h not in seen:
            seen.add(h)
            unique.append(a)
    return unique


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------


def _process_articles(
    articles: list[dict],
) -> tuple[list[dict], list[dict], dict]:
    """Process articles into topics and opportunities.

    Returns (topics_list, opportunities_list, stats_dict).
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # Classify all articles → topic assignments
    topic_articles: dict[str, list[tuple[dict, int]]] = defaultdict(list)
    all_opportunities: list[dict] = []
    dimension_counts: dict[str, int] = defaultdict(int)

    for article in articles:
        dim = article.get("dimension", "")
        dimension_counts[dim] += 1

        # Classify into topics
        matches = classify_article(article)
        for m in matches:
            topic_articles[m["topic_id"]].append((article, m["match_score"]))

        # Detect opportunities
        opp = detect_opportunity(article)
        if opp:
            all_opportunities.append(opp)

    # Deduplicate opportunities by ID
    seen_opp: set[str] = set()
    unique_opps: list[dict] = []
    for opp in all_opportunities:
        if opp["id"] not in seen_opp:
            seen_opp.add(opp["id"])
            unique_opps.append(opp)

    # Build topic objects
    topics: list[dict] = []
    topic_counts: dict[str, int] = {}

    for config in TOPICS_CONFIG:
        topic_id = config["id"]
        matched = topic_articles.get(topic_id, [])
        topic_counts[topic_id] = len(matched)

        # Split into time periods for heat calculation
        matched_articles = [a for a, _ in matched]
        current, previous = split_by_period(matched_articles, days=7)

        heat_trend, heat_label = compute_heat(len(current), len(previous))

        # Build relatedNews and kolVoices
        related_news: list[dict] = []
        kol_voices: list[dict] = []

        # Sort by match score descending
        matched_sorted = sorted(matched, key=lambda x: x[1], reverse=True)

        for article, score in matched_sorted:
            source_id = article.get("source_id", "")

            if is_kol_source(source_id):
                if len(kol_voices) < MAX_KOL_PER_TOPIC:
                    kol_voices.append(build_kol_voice(article))
            else:
                if score >= FEED_MIN_SCORE and len(related_news) < MAX_NEWS_PER_TOPIC:
                    related_news.append(build_topic_news(article, score))

        # Sort news by date descending
        related_news.sort(
            key=lambda x: x.get("date", ""),
            reverse=True,
        )

        topic_obj = {
            "id": topic_id,
            "topic": config["topic"],
            "description": config["description"],
            "tags": config["tags"],
            "heatTrend": heat_trend,
            "heatLabel": heat_label,
            "ourStatus": config["ourStatus"],
            "ourStatusLabel": config["ourStatusLabel"],
            "gapLevel": config["gapLevel"],
            "trendingKeywords": [],  # Filled by Tier 2 LLM
            "relatedNews": related_news,
            "kolVoices": kol_voices,
            "aiSummary": "",         # Filled by Tier 2 LLM
            "aiInsight": "",         # Filled by Tier 2 LLM
            "aiRiskAssessment": None,  # Filled by Tier 2 LLM
            "memoSuggestion": None,    # Filled by Tier 2 LLM
            "totalSignals": len(matched),
            "signalsSinceLastWeek": len(current),
            "lastUpdated": now_iso,
        }
        topics.append(topic_obj)

    # Sort topics: surging first, then by signal count
    _trend_order = {"surging": 0, "rising": 1, "stable": 2, "declining": 3}
    topics.sort(key=lambda t: (_trend_order.get(t["heatTrend"], 9), -t["totalSignals"]))

    # Build stats
    stats = {
        "generated_at": now_iso,
        "totalTopics": len(topics),
        "surgingCount": sum(1 for t in topics if t["heatTrend"] == "surging"),
        "highGapCount": sum(1 for t in topics if t["gapLevel"] == "high"),
        "weeklyNewSignals": sum(t["signalsSinceLastWeek"] for t in topics),
        "urgentOpportunities": sum(
            1 for o in unique_opps if o["priority"] == "紧急"
        ),
        "totalOpportunities": len(unique_opps),
        "totalArticlesProcessed": len(articles),
        "dimensionBreakdown": dict(dimension_counts),
        "topicBreakdown": topic_counts,
    }

    return topics, unique_opps, stats


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def process_tech_frontier_pipeline(
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Run tech frontier processing pipeline (Tier 1 rules).

    Generates topics.json, opportunities.json, and stats.json
    under data/processed/tech_frontier/.

    Returns summary dict for the pipeline orchestrator.
    """
    # Load articles from all dimensions
    all_articles = await _load_all_articles()
    logger.info("Tech frontier pipeline: loaded %d articles", len(all_articles))

    # Deduplicate
    unique = _deduplicate(all_articles)
    logger.info("Tech frontier pipeline: %d unique articles", len(unique))

    # Incremental hash tracking
    processed_hashes = set() if force else _hash_tracker.load()
    new_articles = [
        a for a in unique if a.get("url_hash", "") not in processed_hashes
    ]

    logger.info(
        "Tech frontier pipeline: %d new (previously: %d)",
        len(new_articles), len(processed_hashes),
    )

    # Update hash tracking
    new_count = 0
    if new_articles:
        for article in new_articles:
            h = article.get("url_hash", "")
            if h:
                processed_hashes.add(h)
                new_count += 1
        _hash_tracker.save(processed_hashes)

    # Process ALL unique articles (not just new) to rebuild complete output
    topics, opportunities, stats = _process_articles(unique)

    # Write output files
    save_output_json(PROCESSED_DIR, "topics.json", topics)
    save_output_json(PROCESSED_DIR, "opportunities.json", opportunities)

    # stats.json has a custom schema — write manually
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_DIR / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    logger.info(
        "Tech frontier output: %d topics, %d opportunities, %d total signals",
        len(topics),
        len(opportunities),
        stats["weeklyNewSignals"],
    )

    return {
        "total_articles": len(all_articles),
        "unique": len(unique),
        "new_processed": new_count,
        "topics": len(topics),
        "opportunities": len(opportunities),
        "weekly_signals": stats["weeklyNewSignals"],
        "topic_breakdown": stats["topicBreakdown"],
    }


async def process_tech_frontier_llm_enrichment() -> dict[str, Any]:
    """Tier 2: LLM enrichment for tech frontier topics.

    Reads topics.json, enriches with AI summaries/insights via LLM,
    writes updated topics.json + opportunities.json.

    Returns summary dict for the pipeline orchestrator.
    """
    from app.services.intel.tech_frontier.llm import (
        enrich_opportunity,
        enrich_topic,
    )

    topics_data = _load_json("topics.json")
    opps_data = _load_json("opportunities.json")
    topics = topics_data.get("items", [])
    opps = opps_data.get("items", [])

    if not topics:
        return {"skipped": True, "reason": "no topics to enrich"}

    enriched_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    # Enrich topics with enough signals
    for topic in topics:
        if topic.get("totalSignals", 0) < 5:
            continue
        if topic.get("aiSummary"):
            continue  # already enriched

        enrichment = await enrich_topic(topic)
        if enrichment:
            topic["aiSummary"] = enrichment.get("aiSummary", "")
            topic["aiInsight"] = enrichment.get("aiInsight", "")
            topic["aiRiskAssessment"] = enrichment.get("aiRiskAssessment")
            topic["memoSuggestion"] = enrichment.get("memoSuggestion")
            topic["lastUpdated"] = now_iso
            enriched_count += 1

    # Enrich opportunities
    opp_enriched = 0
    for opp in opps:
        if opp.get("aiAssessment"):
            continue
        enrichment = await enrich_opportunity(opp)
        if enrichment:
            opp["aiAssessment"] = enrichment.get("aiAssessment", "")
            opp["actionSuggestion"] = enrichment.get("actionSuggestion", "")
            opp_enriched += 1

    # Write updated files
    save_output_json(PROCESSED_DIR, "topics.json", topics)
    save_output_json(PROCESSED_DIR, "opportunities.json", opps)

    logger.info(
        "Tech frontier LLM enrichment: %d topics, %d opportunities enriched",
        enriched_count, opp_enriched,
    )

    return {
        "topics_enriched": enriched_count,
        "opportunities_enriched": opp_enriched,
    }


def _load_json(filename: str) -> dict:
    path = PROCESSED_DIR / filename
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
