"""Shared HTML parsing logic for template crawlers (static & dynamic).

Extracts date, list items, and detail page content from BeautifulSoup elements.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from app.crawlers.utils.dedup import compute_content_hash
from app.crawlers.utils.html_sanitizer import sanitize_html
from app.crawlers.utils.image_extractor import extract_images
from app.crawlers.utils.pdf_extractor import extract_pdf_url
from app.crawlers.utils.text_extract import html_to_text

logger = logging.getLogger(__name__)


@dataclass
class RawListItem:
    """Intermediate result from parsing a list page element."""

    title: str
    url: str
    published_at: datetime | None = None


@dataclass
class DetailResult:
    """Result from parsing a detail page."""

    content: str | None = None
    content_html: str | None = None
    author: str | None = None
    content_hash: str | None = None
    pdf_url: str | None = None
    images: list[dict[str, str]] | None = None


def extract_date(el: Tag, selectors: dict) -> datetime | None:
    """Extract date from an element using selector + format + optional regex.

    Tries plain get_text first (handles inline dates like "2026/02/13"),
    falls back to separator=" " (handles split dates like <p>12</p><span>2026.02</span>).
    """
    date_selector = selectors.get("date")
    if not date_selector:
        return None
    date_el = el.select_one(date_selector)
    if date_el is None:
        return None
    date_format = selectors.get("date_format")
    if not date_format:
        return None

    date_regex = selectors.get("date_regex")

    for date_text in (
        date_el.get_text(strip=True),
        date_el.get_text(separator=" ", strip=True),
    ):
        text = date_text
        if date_regex:
            m = re.search(date_regex, text)
            if m:
                text = m.group(0)
            else:
                continue
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return None


def extract_date_from_url(url: str) -> datetime | None:
    """Extract date from URL path, common in Chinese government websites.

    Supports:
    - /t20250701_xxx.html  → 2025-07-01
    - /202507/txxx.html    → 2025-07-01 (day from tYYYYMMDD if present, else 1st)
    """
    # Pattern 1: tYYYYMMDD_ (most specific)
    m = re.search(r'/t(\d{4})(\d{2})(\d{2})_', url)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            pass
    # Pattern 2: /YYYYMM/ directory with t-prefixed filename
    m = re.search(r'/(\d{4})(\d{2})/t\d+', url)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), 1)
        except ValueError:
            pass
    return None


def _normalize_base_url(base_url: str) -> str:
    """Ensure base_url ends with '/' so urljoin treats the last segment as a directory.

    Without a trailing slash, urljoin treats the last path segment as a file
    and drops it when resolving relative links (e.g., ./202602/xxx.html).
    """
    parsed = urlparse(base_url)
    path = parsed.path
    if not path or path.endswith("/"):
        return base_url
    # If the last segment contains a dot, treat it as a file (e.g., index.html)
    last_segment = path.rsplit("/", 1)[-1]
    if "." in last_segment:
        return base_url
    return urlunparse(parsed._replace(path=path + "/"))


def parse_list_items(
    soup: BeautifulSoup,
    selectors: dict,
    base_url: str,
    keyword_filter: list[str] | None = None,
    keyword_blacklist: list[str] | None = None,
) -> list[RawListItem]:
    """Parse a list page and extract title, link, and date for each item.

    Supports the "_self" convention: if title/link selector is "_self",
    the list_item element itself is used.
    """
    base_url = _normalize_base_url(base_url)
    list_elements = soup.select(selectors.get("list_item", "li"))
    items: list[RawListItem] = []

    for el in list_elements:
        # Extract title ("_self" means use el itself)
        title_selector = selectors.get("title", "a")
        if title_selector == "_self":
            title_el = el
        else:
            title_el = el.select_one(title_selector) if title_selector else el
        if title_el is None:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        # Extract link ("_self" means use el itself)
        link_selector = selectors.get("link", "a")
        if link_selector == "_self":
            link_el = el
        else:
            link_el = el.select_one(link_selector) if link_selector else el
        if link_el is None:
            continue
        link_attr = selectors.get("link_attr", "href")
        raw_link = link_el.get(link_attr, "").strip()
        if not raw_link:
            continue
        url = urljoin(base_url, raw_link)

        # Keyword filtering
        if keyword_filter and not any(kw in title for kw in keyword_filter):
            continue

        # Blacklist filtering (drop if title contains any blacklist keyword)
        if keyword_blacklist and any(bw in title for bw in keyword_blacklist):
            continue

        published_at = extract_date(el, selectors)
        if published_at is None:
            published_at = extract_date_from_url(url)

        items.append(RawListItem(title=title, url=url, published_at=published_at))

    # Deduplicate by title (some sites expose the same article via multiple URL paths,
    # e.g. most.gov.cn with/without /fdzdgknr/, ndrc.gov.cn with/without /tz/)
    seen_titles: set[str] = set()
    deduped: list[RawListItem] = []
    for item in items:
        if item.title not in seen_titles:
            seen_titles.add(item.title)
            deduped.append(item)
        else:
            logger.debug("Dropped duplicate title: %s (url=%s)", item.title, item.url)
    if len(deduped) < len(items):
        logger.info("Title dedup: %d → %d items", len(items), len(deduped))
    return deduped


def parse_detail_html(
    html: str,
    detail_selectors: dict,
    page_url: str = "",
    config: dict | None = None,
) -> DetailResult:
    """Parse a detail page HTML and extract content, author, content_hash, and PDF URL.

    Uses html.parser instead of lxml because some government sites (notably gov.cn)
    produce deeply nested <table> structures that lxml fails to parse correctly.
    html.parser handles all tested sites reliably.

    Args:
        html: HTML string to parse
        detail_selectors: Selector config for content/author
        page_url: Current page URL for PDF extraction
        config: Full source config for PDF extraction
    """
    detail_soup = BeautifulSoup(html, "html.parser")
    result = DetailResult()

    if content_sel := detail_selectors.get("content"):
        content_el = detail_soup.select_one(content_sel)
        if content_el:
            raw_html = str(content_el)
            result.content = html_to_text(raw_html)
            result.content_hash = compute_content_hash(result.content)
            result.content_html = sanitize_html(raw_html, base_url=page_url)
            result.images = extract_images(raw_html, base_url=page_url)

    if author_sel := detail_selectors.get("author"):
        author_el = detail_soup.select_one(author_sel)
        if author_el:
            result.author = author_el.get_text(strip=True)

    # Extract PDF URL
    if config and page_url:
        title = config.get("name", "")
        result.pdf_url = extract_pdf_url(detail_soup, page_url, title, config)

    return result
