from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.crawlers.utils.http_client import fetch_json
from app.utils.date_parsing import parse_datetime_text

logger = logging.getLogger(__name__)

_DEFAULT_API_BASE = "https://www.zhejianglab.org/ZJGW/api/v1/website"
_DEFAULT_DETAIL_URL = "https://www.zhejianglab.org/lab/post/{id}"


class ZhejiangLabWebsiteAPICrawler(BaseCrawler):
    """Fetch Zhejiang Lab news from the website JSON API used by the frontend."""

    async def fetch_and_parse(self) -> list[CrawledItem]:
        api_base = str(self.config.get("api_base_url") or _DEFAULT_API_BASE).rstrip("/")
        detail_url_template = str(
            self.config.get("detail_url_template") or _DEFAULT_DETAIL_URL
        )
        headers = {
            "websiteId": str(self.config.get("website_id", 1)),
            **(self.config.get("headers") or {}),
        }
        module_ids = self.config.get("module_ids") or [515, 527]
        max_items = int(self.config.get("max_items", 12))

        seen_urls: set[str] = set()
        items: list[CrawledItem] = []

        for module_id in module_ids:
            payload = await fetch_json(
                f"{api_base}/column/queryDataByMoudleId",
                headers=headers,
                params={"moudleId": str(module_id)},
                timeout=30.0,
                request_delay=self.config.get("request_delay"),
            )

            for column in payload.get("data", []) or []:
                column_name = str(column.get("columnName") or "").strip()
                for record in column.get("data", []) or []:
                    title = str(record.get("title") or "").strip()
                    if not title:
                        continue

                    record_id = record.get("id")
                    outer_url = str(record.get("outerUrl") or "").strip()
                    url = outer_url or detail_url_template.format(id=record_id)
                    if not url or url in seen_urls:
                        continue

                    seen_urls.add(url)

                    content_html = str(record.get("introduce") or "").strip() or None
                    content_text = str(record.get("originalContent") or "").strip()
                    if not content_text and content_html:
                        content_text = BeautifulSoup(content_html, "lxml").get_text("\n", strip=True)
                    content = content_text or None

                    published_at = (
                        parse_datetime_text(str(record.get("publishTime") or "").strip())
                        or parse_datetime_text(str(record.get("gmtCreated") or "").strip())
                    )

                    hash_source = content or content_html or title
                    content_hash = compute_content_hash(hash_source) if hash_source else None

                    items.append(
                        CrawledItem(
                            title=title,
                            url=url,
                            published_at=published_at,
                            author=str(record.get("createdBy") or "").strip() or None,
                            content=content,
                            content_html=content_html,
                            content_hash=content_hash,
                            source_id=self.source_id,
                            dimension=self.config.get("dimension"),
                            tags=self.config.get("tags", []),
                            extra={
                                "module_id": module_id,
                                "column_name": column_name,
                                "record_id": record_id,
                            },
                        )
                    )

        items.sort(
            key=lambda item: (
                item.published_at is None,
                -(item.published_at.timestamp() if item.published_at else 0),
                item.title,
            )
        )
        return items[:max_items]
