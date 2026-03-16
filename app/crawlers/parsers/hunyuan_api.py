"""Tencent Hunyuan news API crawler — fetches news via public JSON API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash

logger = logging.getLogger(__name__)

_HUNYUAN_API_URL = (
    "https://api.hunyuan.tencent.com"
    "/api/vision_platform/public/auditOpenAPI/dynamic/list"
)
_DEFAULT_CONTENT_TYPES = [
    "model_publish",
    "opensource_activity",
    "event_activity",
    "award_evaluation",
]


class HunyuanAPICrawler(BaseCrawler):
    """
    Fetch news from Tencent Hunyuan public API.

    The Hunyuan website (hunyuan.tencent.com/news/home) is a React SPA
    that stores article URLs in JS closures (not in DOM). This parser
    calls the same public API the frontend uses.

    Config fields:
      - max_results: number of results per request (default 20)
      - content_types: list of content types to fetch (default: all blog types)
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        max_results = self.config.get("max_results", 20)
        content_types = self.config.get("content_types", _DEFAULT_CONTENT_TYPES)

        payload = {
            "content_type": content_types,
            "key": "",
            "order_by": "published_at",
            "order_dir": "desc",
            "page_id": 1,
            "page_size": max_results,
        }

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.post(
                _HUNYUAN_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        if data.get("code") != 0:
            logger.warning(
                "Hunyuan API returned error: %s", data.get("msg", "unknown")
            )
            return []

        raw_items = data.get("data", {}).get("items", [])
        items: list[CrawledItem] = []

        for raw in raw_items:
            title = (raw.get("title") or "").strip()
            url = (raw.get("url") or "").strip()
            if not title or not url:
                continue

            published_at = None
            if ts := raw.get("published_at"):
                try:
                    published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
                except (ValueError, OSError):
                    pass

            content = (raw.get("content_brief") or "").strip()
            content_hash = compute_content_hash(content) if content else None

            extra: dict[str, Any] = {}
            if content_type := raw.get("content_type"):
                extra["content_type"] = content_type
            if other_info := raw.get("other_info"):
                extra["source_label"] = other_info

            items.append(
                CrawledItem(
                    title=title,
                    url=url,
                    published_at=published_at,
                    content=content or None,
                    content_hash=content_hash,
                    source_id=self.source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []),
                    extra=extra,
                )
            )

        return items
