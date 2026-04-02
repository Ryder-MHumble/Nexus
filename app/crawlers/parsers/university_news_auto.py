from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.http_client import fetch_page
from app.crawlers.utils.selector_parser import extract_date_from_url, parse_detail_html

logger = logging.getLogger(__name__)

_IGNORE_TITLE_KEYWORDS = (
    "首页", "上一页", "下一页", "更多", "点击", "进入", "通知", "公告",
    "专题", "导航", "邮箱", "搜索", "旧版", "english", "vpn", "登录",
)

_LINK_HINTS = (
    "news", "xinwen", "xw", "yaowen", "info", "article", "content", "show", "detail",
)

_AUTO_CONTENT_SELECTORS = (
    ".wp_articlecontent",
    ".v_news_content",
    "#vsb_content",
    "div.Article_content",
    "div.article",
    "article",
    "div.content",
    "div.main-content",
    "div.text",
)


class UniversityNewsAutoCrawler(BaseCrawler):
    """Auto crawler for university news portals with heterogeneous HTML structures.

    This crawler is designed for broad coverage across many Chinese university sites.
    It extracts candidate article links by heuristic scoring and optionally fetches
    detail pages for content extraction.
    """

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "")).strip()

    def _host_matches(self, host: str, allowed_host: str | None) -> bool:
        if not host:
            return False
        if not allowed_host:
            return True
        return host == allowed_host or host.endswith(f".{allowed_host}")

    def _extract_date_from_text(self, text: str) -> datetime | None:
        text = text or ""

        patterns = [
            r"(20\d{2})[年\./-](\d{1,2})[月\./-](\d{1,2})",
            r"(20\d{2})(\d{2})(\d{2})",
            r"(20\d{2})[年\./-](\d{1,2})[月\./-]?",
        ]
        for pattern in patterns:
            m = re.search(pattern, text)
            if not m:
                continue
            try:
                year = int(m.group(1))
                month = int(m.group(2))
                day = int(m.group(3)) if len(m.groups()) >= 3 and m.group(3) else 1
                return datetime(year, month, day)
            except ValueError:
                continue
        return None

    def _is_noise_title(self, title: str) -> bool:
        if not title:
            return True

        if len(title) < 6 or len(title) > 120:
            return True

        lowered = title.lower()
        if any(token in lowered for token in _IGNORE_TITLE_KEYWORDS):
            return True

        if re.fullmatch(r"[\d\W_]+", title):
            return True

        if not re.search(r"[\u4e00-\u9fffA-Za-z]", title):
            return True

        return False

    def _score_candidate(self, title: str, url: str, context_text: str) -> int:
        score = 0
        lowered_url = (url or "").lower()

        if any(hint in lowered_url for hint in _LINK_HINTS):
            score += 2

        if re.search(r"/20\d{2}/|20\d{6}|20\d{2}[\./-]\d{1,2}[\./-]\d{1,2}", lowered_url):
            score += 2

        if re.search(r"\.(htm|html|shtml|jsp)(\?|$)", lowered_url):
            score += 1

        if self._extract_date_from_text(context_text) is not None:
            score += 2

        if any(token in title for token in ("大学", "学院", "实验室", "发布", "举行", "召开", "论坛")):
            score += 1

        return score

    def _extract_candidates(self, html: str, base_url: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        allowed_host = (urlparse(base_url).hostname or "").lower().strip(".")
        if allowed_host.startswith("www."):
            allowed_host = allowed_host[4:]

        allow_external = bool(self.config.get("allow_external_links", False))
        min_score = int(self.config.get("auto_min_score", 3))
        max_items = int(self.config.get("max_items", 12))

        candidates: list[dict] = []
        seen_url: set[str] = set()
        seen_title: set[str] = set()

        for idx, a in enumerate(soup.select("a[href]")):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if parsed.scheme not in {"http", "https"}:
                continue

            host = (parsed.hostname or "").lower().strip(".")
            if host.startswith("www."):
                host = host[4:]

            if not allow_external and not self._host_matches(host, allowed_host):
                continue

            title = self._clean_text(a.get_text(" ", strip=True) or a.get("title") or "")
            if self._is_noise_title(title):
                continue

            if full_url in seen_url or title in seen_title:
                continue

            context = self._clean_text(a.parent.get_text(" ", strip=True) if a.parent else title)
            published_at = (
                self._extract_date_from_text(context)
                or self._extract_date_from_text(title)
                or extract_date_from_url(full_url)
            )

            score = self._score_candidate(title, full_url, context)
            if score < min_score:
                continue

            seen_url.add(full_url)
            seen_title.add(title)
            candidates.append(
                {
                    "idx": idx,
                    "score": score,
                    "title": title,
                    "url": full_url,
                    "published_at": published_at,
                }
            )

        candidates.sort(key=lambda x: (-x["score"], x["idx"]))
        return candidates[:max_items]

    async def _fetch_list_html_with_playwright(self, url: str) -> str | None:
        from app.crawlers.utils.playwright_pool import get_page

        wait_for = self.config.get("wait_for", "networkidle")
        wait_timeout = int(self.config.get("wait_timeout", 12000))

        try:
            async with get_page() as page:
                await page.goto(url, wait_until="domcontentloaded", timeout=wait_timeout)
                if wait_for == "networkidle":
                    await page.wait_for_load_state("networkidle", timeout=wait_timeout)
                else:
                    await page.wait_for_selector(wait_for, timeout=wait_timeout)
                return await page.content()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Playwright fallback failed for %s: %s", self.source_id, exc)
            return None

    async def _extract_detail(self, url: str) -> tuple[str | None, str | None, str | None, list[dict] | None]:
        if not self.config.get("fetch_detail", True):
            return None, None, None, None

        try:
            detail_html = await fetch_page(
                url,
                headers=self.config.get("headers"),
                encoding=self.config.get("encoding"),
                request_delay=self.config.get("request_delay"),
                verify=bool(self.config.get("verify_ssl", True)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Detail fetch failed for %s: %s", url, exc)
            return None, None, None, None

        detail_selectors = self.config.get("detail_selectors")
        min_len = int(self.config.get("detail_min_length", 80))

        if isinstance(detail_selectors, dict) and detail_selectors.get("content"):
            detail = parse_detail_html(detail_html, detail_selectors, url, self.config)
            return detail.content, detail.content_html, detail.content_hash, detail.images

        for selector in _AUTO_CONTENT_SELECTORS:
            detail = parse_detail_html(detail_html, {"content": selector}, url, self.config)
            if detail.content and len(detail.content.strip()) >= min_len:
                return detail.content, detail.content_html, detail.content_hash, detail.images

        return None, None, None, None

    async def fetch_and_parse(self) -> list[CrawledItem]:
        list_url = self.config["url"]
        base_url = self.config.get("base_url", list_url)
        html: str | None = None

        try:
            html = await fetch_page(
                list_url,
                headers=self.config.get("headers"),
                encoding=self.config.get("encoding"),
                request_delay=self.config.get("request_delay"),
                verify=bool(self.config.get("verify_ssl", True)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("HTTP fetch failed for %s: %s", self.source_id, exc)

        candidates = self._extract_candidates(html, base_url) if html else []
        rendered_html: str | None = None

        if not candidates and self.config.get("playwright_fallback", True):
            rendered_html = await self._fetch_list_html_with_playwright(list_url)
            if rendered_html:
                candidates = self._extract_candidates(rendered_html, base_url)

        logger.info("%s auto candidates: %d", self.source_id, len(candidates))

        if not candidates and self.config.get("snapshot_on_empty", True):
            snapshot_html = rendered_html or html
            if snapshot_html:
                snapshot_text = self._clean_text(BeautifulSoup(snapshot_html, "lxml").get_text(" ", strip=True))
                if not snapshot_text:
                    snapshot_text = self._clean_text(snapshot_html)
                if snapshot_text:
                    digest = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
                    return [
                        CrawledItem(
                            title=f"[页面快照] {self.config.get('name', self.source_id)}",
                            url=f"{list_url}#snapshot-{digest[:12]}",
                            content=snapshot_text[:5000],
                            content_hash=digest,
                            source_id=self.source_id,
                            dimension=self.config.get("dimension"),
                            tags=self.config.get("tags", []) + ["snapshot_fallback"],
                            extra={"snapshot_fallback": True},
                        )
                    ]

        detail_max_items = int(self.config.get("detail_max_items", 6))
        request_delay = float(self.config.get("request_delay", 0) or 0)

        items: list[CrawledItem] = []
        for i, cand in enumerate(candidates):
            content = content_html = content_hash = None
            images = None

            if i < detail_max_items and self.config.get("fetch_detail", True):
                if request_delay > 0:
                    await asyncio.sleep(request_delay)
                content, content_html, content_hash, images = await self._extract_detail(cand["url"])

            extra: dict = {}
            if images:
                extra["images"] = images

            items.append(
                CrawledItem(
                    title=cand["title"],
                    url=cand["url"],
                    published_at=cand["published_at"],
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
