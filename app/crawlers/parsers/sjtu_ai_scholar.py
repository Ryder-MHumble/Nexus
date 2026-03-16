"""SJTU AI faculty parser — fetches teacher list via API endpoint.

SJTU AI Institute (上海交通大学人工智能研究院) uses a JavaScript-driven faculty list page
with SPA rendering and Three.js visualization.

This parser calls the API endpoint directly to obtain teacher records.

API endpoint: https://ai.sjtu.edu.cn/api/teacher?time=<timestamp>
Response: HTML fragment with teacher list items (div.teacher-item or div.faculty-item)
Content structure: div[class*='teacher-item'] or div[class*='faculty-item'] with name and link
"""
from __future__ import annotations

import asyncio
import logging
import re as _re
from datetime import datetime, timezone
from time import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_url_hash
from app.crawlers.utils.http_client import fetch_page
from app.schemas.scholar import ScholarRecord, compute_scholar_completeness, parse_research_areas

logger = logging.getLogger(__name__)

_API_BASE = "https://ai.sjtu.edu.cn"
_API_ENDPOINT = f"{_API_BASE}/api/teacher"
_BASE_URL = "https://ai.sjtu.edu.cn"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_text(el: BeautifulSoup | None, selector: str | None) -> str:
    """Extract stripped text from a sub-element found by selector."""
    if el is None or not selector:
        return ""
    found = el.select_one(selector)
    return found.get_text(strip=True) if found else ""


def _extract_email_from_text(text: str) -> str:
    """Find the first email address in text."""
    m = _re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return m.group(0) if m else ""


class SJTUAIFacultyCrawler(BaseCrawler):
    """Crawler for SJTU AI faculty list via API endpoint."""

    async def _fetch_detail(self, profile_url: str, detail_selectors: dict) -> dict:
        """Fetch individual profile page and extract detailed faculty info."""
        result: dict = {}
        try:
            html = await fetch_page(profile_url)
            soup = BeautifulSoup(html, "lxml")

            if bio_sel := detail_selectors.get("bio"):
                if bio_text := _extract_text(soup, bio_sel):
                    result["bio"] = bio_text

            if ra_sel := detail_selectors.get("research_areas"):
                if ra_text := _extract_text(soup, ra_sel):
                    result["research_areas"] = parse_research_areas(ra_text)

            if email_sel := detail_selectors.get("email"):
                if email_text := _extract_text(soup, email_sel):
                    result["email"] = email_text
            if not result.get("email"):
                full_text = soup.get_text()
                if email := _extract_email_from_text(full_text):
                    result["email"] = email

            if pos_sel := detail_selectors.get("position"):
                if pos_text := _extract_text(soup, pos_sel):
                    result["position"] = pos_text

        except Exception as e:
            logger.debug("Failed to fetch faculty detail %s: %s", profile_url, e)
        return result

    async def fetch_and_parse(self) -> list[CrawledItem]:
        university = self.config.get("university", "上海交通大学")
        department = self.config.get("department", "人工智能研究院")
        source_id = self.source_id
        source_url = self.config.get("url", f"{_BASE_URL}/faculty/teachers")
        crawled_at = _now_iso()

        # Fetch faculty list via API endpoint with timestamp
        try:
            timestamp = int(time() * 1000)  # milliseconds
            api_url = f"{_API_ENDPOINT}?time={timestamp}"
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Referer": source_url,
                },
            ) as client:
                response = await client.get(api_url)
                response.raise_for_status()
                content_html = response.text
        except Exception as e:
            logger.error("SJTUAIFacultyCrawler: API request failed: %s", e)
            return []

        if not content_html:
            logger.warning("SJTUAIFacultyCrawler: empty content from API response")
            return []

        soup = BeautifulSoup(content_html, "lxml")
        # Try multiple CSS selectors for teacher items
        faculty_items = soup.select(".teacher-item")
        if not faculty_items:
            faculty_items = soup.select(".faculty-item")
        if not faculty_items:
            faculty_items = soup.select("div[class*='teacher']")

        if not faculty_items:
            logger.warning("SJTUAIFacultyCrawler: no faculty items found in API response")
            return []

        items: list[CrawledItem] = []
        seen_urls: set[str] = set()
        detail_selectors = self.config.get("detail_selectors")
        request_delay = self.config.get("request_delay", 1.0)

        for item_el in faculty_items:
            # Try to extract name from common elements
            name_text = ""
            name_el = item_el.select_one("h3, h4, .name, .teacher-name, .faculty-name")
            if name_el:
                name_text = name_el.get_text(strip=True)
            else:
                # Try the first a tag text if available
                a_tag = item_el.select_one("a")
                if a_tag:
                    name_text = a_tag.get_text(strip=True)

            if not name_text:
                continue

            # Try to extract profile link
            profile_url = ""
            href_el = item_el.select_one("a")
            if href_el and (href := href_el.get("href", "").strip()):
                profile_url = urljoin(_BASE_URL, href)
            else:
                # Synthetic URL for faculty without profile pages
                name_hash = compute_url_hash(f"{source_url}#{name_text}")
                profile_url = f"{source_url}#{name_hash[:16]}"

            if profile_url in seen_urls:
                continue
            seen_urls.add(profile_url)

            # Optional: fetch detail page for enriched data
            bio_text = ""
            position_text = ""
            email_text = ""
            research_areas: list[str] = []
            if detail_selectors and not profile_url.startswith(f"{source_url}#"):
                if request_delay:
                    await asyncio.sleep(request_delay)
                detail = await self._fetch_detail(profile_url, detail_selectors)
                bio_text = detail.get("bio", "")
                position_text = detail.get("position", "")
                email_text = detail.get("email", "")
                research_areas = detail.get("research_areas", [])

            record = ScholarRecord(
                name=name_text,
                university=university,
                department=department,
                profile_url=profile_url,
                source_id=source_id,
                source_url=source_url,
                crawled_at=crawled_at,
                last_seen_at=crawled_at,
                is_active=True,
                bio=bio_text,
                position=position_text,
                email=email_text,
                research_areas=research_areas,
            )
            record.data_completeness = compute_scholar_completeness(record)

            items.append(
                CrawledItem(
                    title=name_text,
                    url=profile_url,
                    published_at=None,
                    author=None,
                    content=None,
                    content_hash=None,
                    source_id=source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []),
                    extra=record.model_dump(),
                )
            )

        logger.info(
            "SJTUAIFacultyCrawler: extracted %d faculty from API endpoint",
            len(items),
        )
        return items
