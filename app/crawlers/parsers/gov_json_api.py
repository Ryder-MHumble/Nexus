"""Gov.cn policy search API crawler — fetches policy documents via JSON API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.crawlers.utils.http_client import fetch_json

logger = logging.getLogger(__name__)

_GOV_SEARCH_URL = "https://sousuo.www.gov.cn/search-gov/data"


class GovJSONAPICrawler(BaseCrawler):
    """
    Fetch policy documents from gov.cn search API.

    Config fields:
      - search_keywords: list of keywords to search (default ["人工智能"])
      - max_results: number of results per keyword (default 10)
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        keywords = self.config.get("search_keywords", ["人工智能"])
        max_results = self.config.get("max_results", 10)

        all_items: list[CrawledItem] = []
        seen_urls: set[str] = set()

        for keyword in keywords:
            try:
                items = await self._search_keyword(keyword, max_results)
                for item in items:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        all_items.append(item)
            except Exception as e:
                logger.warning("Gov search failed for keyword '%s': %s", keyword, e)

        return all_items

    async def _search_keyword(
        self, keyword: str, max_results: int
    ) -> list[CrawledItem]:
        data: dict[str, Any] = await fetch_json(
            _GOV_SEARCH_URL,
            params={
                "t": "govall",
                "q": keyword,
                "timetype": "timeqb",
                "sort": "pubtime",
                "p": "0",
                "n": str(max_results),
            },
            timeout=30.0,
        )

        items: list[CrawledItem] = []
        results = data.get("searchVO", {}).get("listVO", [])
        for result in results:
            title = result.get("title", "").strip()
            url = result.get("url", "").strip()
            if not title or not url:
                continue

            # Clean HTML tags from title
            title = title.replace("<em>", "").replace("</em>", "")

            # Parse date
            published_at = None
            if date_str := result.get("pubtimeStr"):
                try:
                    published_at = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    try:
                        published_at = datetime.strptime(date_str, "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
                    except ValueError:
                        pass

            content = result.get("content", "") or ""
            content = content.replace("<em>", "").replace("</em>", "")
            content_hash = compute_content_hash(content) if content else None

            items.append(
                CrawledItem(
                    title=title,
                    url=url,
                    published_at=published_at,
                    author=result.get("source"),
                    content=content or None,
                    content_hash=content_hash,
                    source_id=self.source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []),
                    extra={"search_keyword": keyword},
                )
            )

        return items
