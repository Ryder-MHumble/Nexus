from __future__ import annotations

import asyncio
import logging
from typing import Any

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.http_client import fetch_page as http_fetch_page
from app.crawlers.utils.selector_parser import (
    DetailResult,
    parse_detail_html,
    parse_list_items,
)

logger = logging.getLogger(__name__)

_JS_FETCH_SNIPPET = """
async (url) => {
    const resp = await fetch(url);
    return await resp.text();
}
"""


class DynamicPageCrawler(BaseCrawler):
    """
    Template crawler for JS-rendered pages via Playwright.
    Uses same selector pattern as StaticHTMLCrawler but renders with Playwright first.

    Config fields (same as StaticHTMLCrawler plus):
      - wait_for: CSS selector or "networkidle" to wait for
      - wait_timeout: milliseconds (default 10000)
      - detail_use_playwright: bool (default True) — use Playwright or httpx for detail pages
      - detail_fetch_js: bool (default False) — use JS fetch() for detail pages
        (avoids page.goto anti-bot issues; requires same-origin detail URLs)
    """

    async def _fetch_detail_with_js_fetch(
        self, page: Any, detail_url: str, detail_selectors: dict,
    ) -> DetailResult | None:
        """Fetch detail page HTML via JS fetch() in the browser context.

        Shares cookies with the current page, avoids page.goto navigation issues
        caused by anti-bot systems (e.g. Clear-Site-Data headers).
        """
        try:
            detail_html = await page.evaluate(_JS_FETCH_SNIPPET, detail_url)
            return parse_detail_html(detail_html, detail_selectors, detail_url, self.config)
        except Exception as e:
            logger.warning("Failed to JS-fetch detail page %s: %s", detail_url, e)
            return None

    async def _fetch_detail_with_playwright(
        self, page: Any, detail_url: str, detail_selectors: dict, wait_timeout: int,
    ) -> DetailResult | None:
        """Fetch a detail page using Playwright (same context, shares cookies)."""
        try:
            await page.goto(detail_url, wait_until="domcontentloaded", timeout=wait_timeout)
            detail_wait = detail_selectors.get("content", "body")
            try:
                await page.wait_for_selector(detail_wait, timeout=wait_timeout)
            except Exception:
                pass  # Content may already be available or selector optional
            detail_html = await page.content()

            return parse_detail_html(detail_html, detail_selectors, detail_url, self.config)
        except Exception as e:
            logger.warning("Failed to fetch detail page %s: %s", detail_url, e)
            return None

    async def _fetch_detail_with_httpx(
        self, detail_url: str, detail_selectors: dict,
    ) -> DetailResult | None:
        """Fetch a detail page using httpx (faster, for sites without JS protection)."""
        try:
            detail_html = await http_fetch_page(
                detail_url,
                headers=self.config.get("headers"),
                encoding=self.config.get("encoding"),
                request_delay=self.config.get("request_delay"),
            )
            return parse_detail_html(detail_html, detail_selectors, detail_url, self.config)
        except Exception as e:
            logger.warning("Failed to fetch detail page %s: %s", detail_url, e)
            return None

    async def fetch_and_parse(self) -> list[CrawledItem]:
        from app.crawlers.utils.playwright_pool import get_page

        url = self.config["url"]
        selectors = self.config.get("selectors", {})
        base_url = self.config.get("base_url", url)
        keyword_filter = self.config.get("keyword_filter", [])
        keyword_blacklist = self.config.get("keyword_blacklist", [])
        detail_selectors = self.config.get("detail_selectors")
        detail_use_playwright = self.config.get("detail_use_playwright", True)
        detail_fetch_js = self.config.get("detail_fetch_js", False)
        wait_for = self.config.get("wait_for", "networkidle")
        wait_timeout = self.config.get("wait_timeout", 10000)

        warmup_url = self.config.get("warmup_url")

        async with get_page() as page:
            if warmup_url:
                try:
                    await page.goto(warmup_url, wait_until="domcontentloaded", timeout=wait_timeout)
                except Exception:
                    pass  # warmup may return non-200; we just need the cookies/session

            await page.goto(url, wait_until="domcontentloaded", timeout=wait_timeout)

            if wait_for == "networkidle":
                await page.wait_for_load_state("networkidle", timeout=wait_timeout)
            else:
                await page.wait_for_selector(wait_for, timeout=wait_timeout)

            html = await page.content()

            soup = BeautifulSoup(html, "lxml")
            raw_items = parse_list_items(
                soup, selectors, base_url, keyword_filter, keyword_blacklist
            )

            request_delay = self.config.get("request_delay", 0)

            items: list[CrawledItem] = []
            for raw in raw_items:
                content = author = content_hash = content_html = pdf_url = None
                images = None

                if detail_selectors:
                    if request_delay:
                        await asyncio.sleep(request_delay)
                    if detail_fetch_js:
                        detail = await self._fetch_detail_with_js_fetch(
                            page, raw.url, detail_selectors,
                        )
                    elif detail_use_playwright:
                        detail = await self._fetch_detail_with_playwright(
                            page, raw.url, detail_selectors, wait_timeout,
                        )
                    else:
                        detail = await self._fetch_detail_with_httpx(
                            raw.url, detail_selectors,
                        )
                    if detail:
                        content = detail.content
                        content_html = detail.content_html
                        author = detail.author
                        content_hash = detail.content_hash
                        pdf_url = detail.pdf_url
                        images = detail.images

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
