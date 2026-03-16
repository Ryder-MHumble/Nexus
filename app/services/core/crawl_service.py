from __future__ import annotations

from typing import Any

from app.scheduler.manager import load_all_source_configs
from app.schemas.crawl_log import CrawlHealthResponse
from app.services.stores.crawl_log_store import get_crawl_logs as _get_logs
from app.services.stores.crawl_log_store import get_recent_log_stats
from app.services.stores.source_state import get_all_source_states


async def get_crawl_logs(
    source_id: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    return await _get_logs(source_id=source_id, limit=limit)


async def get_crawl_health() -> CrawlHealthResponse:
    """Aggregate crawl health statistics from YAML configs + source state + logs."""
    configs = load_all_source_configs()
    states = await get_all_source_states()

    total_sources = len(configs)

    # Count enabled (with override support)
    enabled_sources = 0
    healthy = warning = failing = 0
    for c in configs:
        state = states.get(c["id"], {})
        override = state.get("is_enabled_override")
        is_enabled = override if override is not None else c.get("is_enabled", True)
        if is_enabled:
            enabled_sources += 1
            failures = state.get("consecutive_failures", 0)
            if failures == 0:
                healthy += 1
            elif failures <= 2:
                warning += 1
            else:
                failing += 1

    recent = await get_recent_log_stats(hours=24)

    return CrawlHealthResponse(
        total_sources=total_sources,
        enabled_sources=enabled_sources,
        healthy=healthy,
        warning=warning,
        failing=failing,
        last_24h_crawls=recent["crawls"],
        last_24h_new_articles=recent["new_articles"],
    )
