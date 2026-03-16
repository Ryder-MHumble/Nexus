from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.crawlers.base import CrawlStatus
from app.crawlers.registry import CrawlerRegistry
from app.crawlers.utils.json_storage import save_crawl_result_json
from app.services.stores.crawl_log_store import append_crawl_log
from app.services.stores.source_state import update_source_state

logger = logging.getLogger(__name__)


async def execute_crawl_job(source_config: dict[str, Any]) -> None:
    """Execute a crawl for a single source. Called by APScheduler."""
    source_id = source_config["id"]
    logger.info("Starting crawl: %s", source_id)

    now = datetime.now(timezone.utc)

    try:
        crawler = CrawlerRegistry.create_crawler(source_config)
    except Exception as e:
        logger.error("Failed to create crawler for %s: %s", source_id, e)
        await append_crawl_log(
            source_id=source_id,
            status=CrawlStatus.FAILED.value,
            error_message=f"Crawler creation failed: {e}",
            started_at=now,
            finished_at=now,
        )
        await update_source_state(source_id, last_crawl_at=now)
        return

    result = await crawler.run()

    # Save to local JSON and upsert to DB
    try:
        await save_crawl_result_json(result, source_config)
    except Exception as e:
        logger.warning("Failed to save JSON for %s: %s", source_id, e)

    # Log the crawl result
    await append_crawl_log(
        source_id=source_id,
        status=result.status.value,
        items_total=result.items_total,
        items_new=result.items_new,
        error_message=result.error_message,
        started_at=result.started_at,
        finished_at=result.finished_at,
        duration_seconds=result.duration_seconds,
    )

    # Update source runtime state
    finished = result.finished_at or datetime.now(timezone.utc)
    if result.status in (CrawlStatus.SUCCESS, CrawlStatus.NO_NEW_CONTENT):
        await update_source_state(
            source_id,
            last_crawl_at=finished,
            last_success_at=finished,
            reset_failures=True,
        )
    else:
        await update_source_state(source_id, last_crawl_at=finished)

    logger.info(
        "Crawl complete: %s | status=%s | new=%d/%d | duration=%.1fs",
        source_id,
        result.status.value,
        result.items_new,
        result.items_total,
        result.duration_seconds,
    )
