from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import feedparser

from app.config import settings
from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.crawlers.utils.html_sanitizer import sanitize_html
from app.crawlers.utils.http_client import fetch_page
from app.crawlers.utils.image_extractor import extract_images
from app.crawlers.utils.text_extract import html_to_text

logger = logging.getLogger(__name__)


class RSSCrawler(BaseCrawler):
    """
    Template crawler for RSS/Atom feeds via feedparser.

    Config fields:
      - url: direct RSS feed URL
      - rsshub_route: RSSHub route (resolved against RSSHUB_BASE_URL)
      - max_entries: max entries to process per crawl (default 20)
      - keyword_filter: optional keywords to filter entries
    """

    def _resolve_feed_url(self) -> str:
        if route := self.config.get("rsshub_route"):
            return f"{settings.RSSHUB_BASE_URL.rstrip('/')}{route}"
        return self.config["url"]

    async def fetch_and_parse(self) -> list[CrawledItem]:
        feed_url = self._resolve_feed_url()
        max_entries = self.config.get("max_entries", 20)
        keyword_filter = self.config.get("keyword_filter", [])

        # Fetch raw XML/RSS
        raw = await fetch_page(
            feed_url,
            headers=self.config.get("headers"),
            request_delay=self.config.get("request_delay"),
        )

        feed = feedparser.parse(raw)
        if feed.bozo and not feed.entries:
            logger.warning("Feed parse error for %s: %s", self.source_id, feed.bozo_exception)

        items: list[CrawledItem] = []
        for entry in feed.entries[:max_entries]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            # Keyword filtering
            if keyword_filter:
                text_to_check = f"{title} {entry.get('summary', '')}"
                if not any(kw in text_to_check for kw in keyword_filter):
                    continue

            # Parse published date
            published_at = None
            if pub := entry.get("published_parsed") or entry.get("updated_parsed"):
                try:
                    published_at = datetime(*pub[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            # Extract content
            content = ""
            if entry.get("content"):
                content = entry.content[0].get("value", "")
            elif entry.get("summary"):
                content = entry.summary

            # Clean HTML from content
            clean_content = html_to_text(content) if content else ""
            content_hash = compute_content_hash(clean_content) if clean_content else None
            content_html = sanitize_html(content, base_url=link) if content else None
            rss_images = extract_images(content, base_url=link) if content else None

            extra: dict[str, Any] = {}
            if rss_images:
                extra["images"] = rss_images

            items.append(
                CrawledItem(
                    title=title,
                    url=link,
                    published_at=published_at,
                    author=entry.get("author"),
                    content=clean_content or None,
                    content_html=content_html,
                    content_hash=content_hash,
                    source_id=self.source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []),
                    extra=extra,
                )
            )

        return items
