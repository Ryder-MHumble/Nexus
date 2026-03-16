from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.http_client import fetch_page
from app.crawlers.utils.selector_parser import parse_detail_html, parse_list_items

logger = logging.getLogger(__name__)


class StaticHTMLCrawler(BaseCrawler):
    """
    Template crawler for static HTML list pages via requests + BeautifulSoup4.

    Config fields:
      - url: list page URL
      - selectors:
          list_item: CSS selector for each article entry
          title: CSS selector for title (relative to list_item), or "_self"
          link: CSS selector for link (relative to list_item), or "_self"
          link_attr: attribute for link (default "href")
          date: CSS selector for date (relative to list_item)
          date_format: strptime format (e.g., "%Y-%m-%d")
          date_regex: optional regex to extract date string before parsing
      - base_url: for resolving relative links
      - encoding: page encoding override
      - keyword_filter: optional keywords
      - detail_selectors: (optional) for fetching detail pages
          content: CSS selector for article body
          author: CSS selector for author
      - headers: custom HTTP headers
      - request_delay: seconds between requests

    Special selector values:
      "_self" — use the list_item element itself (for pages where <a> is the list item)
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        url = self.config["url"]
        selectors = self.config.get("selectors", {})
        base_url = self.config.get("base_url", url)
        keyword_filter = self.config.get("keyword_filter", [])
        keyword_blacklist = self.config.get("keyword_blacklist", [])
        detail_selectors = self.config.get("detail_selectors")

        html = await fetch_page(
            url,
            headers=self.config.get("headers"),
            encoding=self.config.get("encoding"),
            request_delay=self.config.get("request_delay"),
        )

        soup = BeautifulSoup(html, "lxml")
        raw_items = parse_list_items(soup, selectors, base_url, keyword_filter, keyword_blacklist)

        items: list[CrawledItem] = []
        for raw in raw_items:
            content = author = content_hash = content_html = pdf_url = None
            images = None

            if detail_selectors:
                try:
                    detail_html = await fetch_page(
                        raw.url,
                        headers=self.config.get("headers"),
                        encoding=self.config.get("encoding"),
                        request_delay=self.config.get("request_delay"),
                    )
                    detail = parse_detail_html(detail_html, detail_selectors, raw.url, self.config)
                    content = detail.content
                    content_html = detail.content_html
                    author = detail.author
                    content_hash = detail.content_hash
                    pdf_url = detail.pdf_url
                    images = detail.images
                except Exception as e:
                    logger.warning("Failed to fetch detail page %s: %s", raw.url, e)

            extra = {}
            if pdf_url:
                extra["pdf_url"] = pdf_url
            if images:
                extra["images"] = images

            items.append(
                CrawledItem(
                    title=raw.title,
                    url=raw.url,
                    published_at=raw.published_at,
                    author=author,
                    content=content,
                    content_html=content_html,
                    content_hash=content_hash,
                    source_id=self.source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []),
                    extra=extra,
                )
            )

        return items
