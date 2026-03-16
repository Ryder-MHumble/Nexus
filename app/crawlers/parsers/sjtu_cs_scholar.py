"""SJTU CS faculty parser — fetches teacher list via AJAX POST endpoint.

SJTU CS (上海交通大学计算机学院) uses a JavaScript-driven faculty list page.
This parser calls the AJAX POST endpoint directly to obtain all teacher records.

AJAX endpoint: https://www.cs.sjtu.edu.cn/active/ajax_teacher_list.html
POST data: page=1&cat_id=20&cat_code=jiaoshiml&type=1
Response: JSON with 'tab_html' (institute filter tabs) and 'content' (teacher list HTML)
Content structure: div.rc-item > .name-list > span > a (name + profile link)
"""
from __future__ import annotations

import asyncio
import logging
import re as _re
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_url_hash
from app.crawlers.utils.http_client import fetch_page
from app.schemas.scholar import ScholarRecord, compute_scholar_completeness, parse_research_areas

logger = logging.getLogger(__name__)

_AJAX_URL = "https://www.cs.sjtu.edu.cn/active/ajax_teacher_list.html"
_AJAX_DATA = {
    "page": "1",
    "cat_id": "20",
    "cat_code": "jiaoshiml",
    "type": "1",
}
_BASE_URL = "https://www.cs.sjtu.edu.cn"


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


class SJTUCSFacultyCrawler(BaseCrawler):
    """Crawler for SJTU CS faculty list via AJAX POST endpoint."""

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
        department = self.config.get("department", "计算机科学与工程系")
        source_id = self.source_id
        source_url = self.config.get("url", _AJAX_URL)
        crawled_at = _now_iso()

        # Fetch faculty list via AJAX POST
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": "https://www.cs.sjtu.edu.cn/jiaoshiml.html",
                },
            ) as client:
                response = await client.post(_AJAX_URL, data=_AJAX_DATA)
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            logger.error("SJTUCSFacultyCrawler: AJAX request failed: %s", e)
            return []

        content_html = data.get("content", "")
        if not content_html:
            logger.warning("SJTUCSFacultyCrawler: empty content from AJAX response")
            return []

        soup = BeautifulSoup(content_html, "lxml")
        faculty_links = soup.select(".name-list span a")

        if not faculty_links:
            logger.warning("SJTUCSFacultyCrawler: no faculty links found in AJAX response")
            return []

        items: list[CrawledItem] = []
        seen_urls: set[str] = set()
        detail_selectors = self.config.get("detail_selectors")
        request_delay = self.config.get("request_delay", 1.0)

        for a_tag in faculty_links:
            name_text = a_tag.get_text(strip=True)
            if not name_text:
                continue

            href = a_tag.get("href", "").strip()
            if href:
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
            "SJTUCSFacultyCrawler: extracted %d faculty from AJAX endpoint",
            len(items),
        )
        return items
