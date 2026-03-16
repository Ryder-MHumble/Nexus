"""Daily Briefing service — orchestrate data collection, LLM generation, caching."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

PROCESSED_DIR = BASE_DIR / "data" / "processed" / "daily_briefing"


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _cache_path(target_date: date) -> Path:
    return PROCESSED_DIR / f"{target_date.isoformat()}.json"


def _load_cache(target_date: date) -> dict[str, Any] | None:
    path = _cache_path(target_date)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load briefing cache %s: %s", path, e)
        return None


def _save_cache(target_date: date, data: dict[str, Any]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(target_date)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
        logger.info("Briefing cached to %s", path)
    except OSError as e:
        logger.error("Failed to save briefing cache: %s", e)
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_daily_briefing(
    target_date: date | None = None,
    force_regenerate: bool = False,
) -> dict[str, Any]:
    """Get the daily briefing, using cache when available.

    Args:
        target_date: Report date (defaults to today).
        force_regenerate: If True, ignore cache and regenerate.

    Returns:
        Complete DailyBriefingResponse-shaped dict.
    """
    if target_date is None:
        target_date = date.today()

    if not force_regenerate:
        cached = _load_cache(target_date)
        if cached:
            logger.info("Returning cached briefing for %s", target_date)
            return cached

    return await generate_daily_briefing(target_date)


async def generate_daily_briefing(target_date: date) -> dict[str, Any]:
    """Full generation pipeline: collect → metrics → LLM → cache.

    Returns:
        Complete DailyBriefingResponse-shaped dict.
    """
    from app.services.intel.daily_briefing import llm, rules

    # Step 1: Collect articles
    collected = await rules.collect_daily_articles(target_date)
    articles_by_dim = collected["articles_by_dimension"]
    total_count = collected["total_count"]
    dimension_counts = collected["dimension_counts"]

    logger.info(
        "Collected %d articles across %d dimensions for briefing on %s",
        total_count, len(articles_by_dim), target_date,
    )

    # Step 2: Compute metric cards (always works, no LLM)
    metric_cards = rules.compute_metric_cards(articles_by_dim)

    # Step 3: Generate narrative
    # Build article index for injecting url/contentSnippet into link segments
    llm_input_text, article_index = rules.prepare_llm_input(articles_by_dim)

    if total_count == 0:
        # No articles — return placeholder
        narrative = {
            "paragraphs": [["院长，今日暂无新的信息更新。各维度数据将在下次爬取后自动更新。"]],
            "summary": "今日暂无新的信息更新。",
        }
    elif settings.ENABLE_LLM_ENRICHMENT and settings.OPENROUTER_API_KEY:
        # Try LLM generation
        try:
            metric_summary = rules.build_metric_summary(articles_by_dim, target_date)
            narrative = await llm.generate_briefing_narrative(
                llm_input_text, metric_summary, article_index=article_index,
            )
            logger.info("LLM briefing narrative generated successfully")
        except Exception as e:
            logger.warning("LLM briefing failed, using fallback: %s", e)
            narrative = llm.build_fallback_briefing(articles_by_dim)
    else:
        # No LLM configured — use fallback
        logger.info("LLM not configured, using fallback briefing")
        narrative = llm.build_fallback_briefing(articles_by_dim)

    # Step 4: Assemble response
    now = datetime.now(timezone.utc)
    response = {
        "generated_at": now.isoformat(),
        "date": target_date.isoformat(),
        "paragraphs": narrative["paragraphs"],
        "metric_cards": metric_cards,
        "summary": narrative.get("summary"),
        "article_count": total_count,
        "dimension_counts": dimension_counts,
    }

    # Step 5: Save cache
    _save_cache(target_date, response)

    return response


async def get_metric_cards_only(
    target_date: date | None = None,
) -> dict[str, Any]:
    """Return only metric cards (no LLM narrative), computed in real-time."""
    from app.services.intel.daily_briefing import rules

    if target_date is None:
        target_date = date.today()

    collected = await rules.collect_daily_articles(target_date)
    articles_by_dim = collected["articles_by_dimension"]
    metric_cards = rules.compute_metric_cards(articles_by_dim)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": target_date.isoformat(),
        "metric_cards": metric_cards,
        "article_count": collected["total_count"],
        "dimension_counts": collected["dimension_counts"],
    }
