"""ISCAS faculty parser — fetches researcher list from Chinese Academy of Sciences Institute of Software.

ISCAS (中国科学院软件研究所) faculty listing page contains semi-structured lists
of researchers. This parser extracts researcher names from HTML and optionally
fetches their detail pages for richer information using heading-based section extraction.

URL: http://www.iscas.ac.cn/rcdw2016/yjyzgjgcs2016/
"""
from __future__ import annotations

import asyncio
import logging
import re as _re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_url_hash, compute_content_hash
from app.crawlers.utils.http_client import fetch_page
from app.schemas.scholar import ScholarRecord, compute_scholar_completeness, parse_research_areas

logger = logging.getLogger(__name__)

_EMAIL_RE = _re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_CHINESE_NAME_RE = _re.compile(r"[\u4e00-\u9fff]{2,4}")
_ACADEMICIAN_RE = _re.compile(r"^([\u4e00-\u9fff]{2,4})院士")  # Match "XX院士" at start


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
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else ""


class ISCASFacultyCrawler(BaseCrawler):
    """Crawler for ISCAS (Institute of Software, Chinese Academy of Sciences) faculty list."""

    async def _fetch_detail(self, profile_url: str, detail_selectors: dict) -> dict:
        """Fetch individual profile page and extract detailed faculty info.

        Supports three extraction strategies:
        1. CSS selectors (bio, research_areas, position, email)
        2. heading_sections: {field: "heading_text"} — find h2/h3/h4/p/div containing heading_text,
           extract next sibling
        3. label_prefix_sections: {field: "Label:"} — find <p>/<li> starting with prefix, extract remainder
        """
        result: dict = {}
        try:
            html = await fetch_page(profile_url)
            soup = BeautifulSoup(html, "lxml")

            # Strategy 1: Direct CSS selectors
            if bio_sel := detail_selectors.get("bio"):
                if bio_text := _extract_text(soup, bio_sel):
                    result["bio"] = bio_text

            if ra_sel := detail_selectors.get("research_areas"):
                if ra_text := _extract_text(soup, ra_sel):
                    result["research_areas"] = parse_research_areas(ra_text)

            if email_sel := detail_selectors.get("email"):
                if email_text := _extract_text(soup, email_sel):
                    result["email"] = email_text

            if pos_sel := detail_selectors.get("position"):
                if pos_text := _extract_text(soup, pos_sel):
                    result["position"] = pos_text

            # Strategy 2: heading_sections — find h2/h3/h4/p/div by text match, extract next sibling
            if heading_sections := detail_selectors.get("heading_sections"):
                for field, heading_text in heading_sections.items():
                    if result.get(field):  # already extracted by direct selector, skip
                        continue
                    for tag in soup.find_all(["h2", "h3", "h4", "p", "div"]):
                        if _re.search(heading_text, tag.get_text(strip=True)):
                            sibling = tag.find_next_sibling()
                            if sibling:
                                text = sibling.get_text(strip=True)
                                if text:
                                    if field == "research_areas":
                                        result[field] = parse_research_areas(text)
                                    else:
                                        result[field] = text
                            break

            # Strategy 3: label_prefix_sections — find <p>/<li> starting with prefix
            if label_prefix_sections := detail_selectors.get("label_prefix_sections"):
                for field, label_prefix in label_prefix_sections.items():
                    if result.get(field):  # already extracted, skip
                        continue
                    for el in soup.find_all(["p", "li"]):
                        text = el.get_text(strip=True)
                        if text.startswith(label_prefix):
                            value = text[len(label_prefix):].strip()
                            if value:
                                if field == "research_areas":
                                    result[field] = parse_research_areas(value)
                                else:
                                    result[field] = value
                            break

            # Fallback: search for email in full text if not found by selector/prefix
            if not result.get("email"):
                full_text = soup.get_text()
                if email := _extract_email_from_text(full_text):
                    result["email"] = email

        except Exception as e:
            logger.debug("Failed to fetch faculty detail %s: %s", profile_url, e)
        return result

    async def fetch_and_parse(self) -> list[CrawledItem]:
        university = self.config.get("university", "中国科学院")
        department = self.config.get("department", "软件研究所")
        source_id = self.source_id
        source_url = self.config.get("url")
        crawled_at = _now_iso()
        base_url = self.config.get("base_url", source_url)

        # Fetch page
        try:
            html = await fetch_page(source_url)
            soup = BeautifulSoup(html, "lxml")
        except Exception as e:
            logger.error("ISCASFacultyCrawler: failed to fetch %s: %s", source_url, e)
            return []

        # Phase 1: Extract faculty links and names
        items: list[CrawledItem] = []
        seen_urls: set[str] = set()

        # Get list_item selector from config (default: div.text)
        list_item_selector = self.config.get("faculty_selectors", {}).get(
            "list_item", "div.text p, div.text li, ul li a, div.faculty a, p a, div.content a, table a"
        )

        # Try multiple selectors to find faculty elements
        faculty_elements = soup.select(list_item_selector)

        # Fallback: extract Chinese names (2-4 characters) if no clear links found
        if not faculty_elements:
            text = soup.get_text()
            names = _CHINESE_NAME_RE.findall(text)
            # Filter to likely actual names (avoid single-char matches, remove duplicates)
            seen_names = set()
            faculty_elements = []
            for name in names:
                if name not in seen_names and len(name) >= 2:
                    seen_names.add(name)
                    # Create pseudo-element with name attribute
                    faculty_elements.append({"name": name})

        detail_selectors = self.config.get("detail_selectors", {})
        request_delay = self.config.get("request_delay", 1.0)

        for elem in faculty_elements:
            # Handle HTML element
            if hasattr(elem, "get_text"):
                raw_text = elem.get_text(strip=True)
                href = elem.get("href", "").strip() if hasattr(elem, "get") else ""
            else:
                # Handle dict (extracted name from text)
                raw_text = elem.get("name", "")
                href = ""

            if not raw_text or len(raw_text) < 2:
                continue

            # If text contains multiple space-separated names, split them
            # This is for pages like ISCAS where list is just space-separated names in <p> tags
            # Skip splitting if it's clearly a single entity (has non-Chinese chars mixed with spaces, or href)
            name_parts = []

            # Special handling for academician page: extract "XX院士" format names
            if source_id == "iscas_academician":
                match = _ACADEMICIAN_RE.search(raw_text)
                if match:
                    name_parts = [match.group(1)]  # Extract just the name part

            if not name_parts:
                if href or "english" in raw_text.lower() or "@" in raw_text:
                    # Single entity with href or contains non-Chinese, treat as single name
                    name_parts = [raw_text]
                else:
                    # Try to split by space and filter for actual Chinese names
                    tokens = raw_text.split()
                    for token in tokens:
                        # Keep tokens that look like Chinese names (2-4 chars, mostly CJK)
                        if _CHINESE_NAME_RE.match(token):
                            name_parts.append(token)
                    # If no names found after splitting, treat whole text as name
                    if not name_parts:
                        name_parts = [raw_text]

            for name_text in name_parts:
                name_text = name_text.strip()
                if not name_text or len(name_text) < 2:
                    continue

                # Construct profile URL
                if href and href.startswith("http"):
                    profile_url = href
                elif href:
                    profile_url = urljoin(base_url, href)
                else:
                    # Synthetic URL for faculty without profile pages
                    name_hash = compute_url_hash(f"{source_url}#{name_text}")
                    profile_url = f"{source_url}#{name_hash[:16]}"

                if profile_url in seen_urls:
                    continue
                seen_urls.add(profile_url)

                # Optional: fetch detail page
                bio_text = ""
                position_text = ""
                email_text = ""
                research_areas: list[str] = []

                if (
                    detail_selectors
                    and not profile_url.startswith(f"{source_url}#")
                ):
                    if request_delay:
                        await asyncio.sleep(request_delay)
                    detail = await self._fetch_detail(profile_url, detail_selectors)
                    bio_text = detail.get("bio", "")
                    position_text = detail.get("position", "")
                    email_text = detail.get("email", "")
                    research_areas = detail.get("research_areas", [])

                # Construct ScholarRecord
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

        logger.info("ISCASFacultyCrawler: extracted %d faculty", len(items))
        return items
