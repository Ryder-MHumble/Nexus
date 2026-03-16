"""Daily Briefing pipeline processor — Stage 6.

Generates the AI morning report from crawled and processed data.
Should run AFTER stages 1-5 so that it can use fresh data.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


async def process_daily_briefing() -> dict[str, Any]:
    """Generate the daily briefing report.

    Called by the pipeline orchestrator as Stage 6.

    Returns:
        Summary dict for the pipeline orchestrator.
    """
    from app.services.intel.daily_briefing.service import generate_daily_briefing

    today = date.today()
    result = await generate_daily_briefing(today)

    return {
        "date": result.get("date", today.isoformat()),
        "article_count": result.get("article_count", 0),
        "paragraphs_count": len(result.get("paragraphs", [])),
        "metric_cards_count": len(result.get("metric_cards", [])),
        "has_summary": result.get("summary") is not None,
    }
