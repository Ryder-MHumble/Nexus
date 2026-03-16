from __future__ import annotations

import logging

from app.crawlers.base import BaseCrawler, CrawledItem

logger = logging.getLogger(__name__)


class SocialMediaCrawler(BaseCrawler):
    """
    Template crawler for social media platforms.
    Placeholder for Phase 4 implementation.

    Config fields:
      - platform: "weibo" | "xiaohongshu" | "zhihu" | "bilibili" | "douyin"
      - search_keywords: list of search terms
      - cookie_env_var: env var name holding the cookie string
      - method: "cookie_requests" | "mediacrawler"
      - kol_ids: list of user IDs to monitor
      - max_results: max items per crawl
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        platform = self.config.get("platform", "unknown")
        logger.info(
            "SocialMediaCrawler for platform '%s' not yet implemented (Phase 4)", platform
        )
        return []
