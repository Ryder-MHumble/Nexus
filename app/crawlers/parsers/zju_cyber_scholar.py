"""ZJU Cybersecurity faculty parser — extracts faculty from rich-text table at icsr.zju.edu.cn.

The faculty page is a manually-edited rich text article within a wp_editor table.
All hyperlinks on the page point to the same URL (website bug), so we parse the
text content directly in "姓名，职称研究方向：xxx" format.

URL: https://icsr.zju.edu.cn/szdw/list.htm
"""
from __future__ import annotations

import logging
import re as _re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_url_hash
from app.crawlers.utils.http_client import fetch_page
from app.schemas.scholar import ScholarRecord, compute_scholar_completeness, parse_research_areas

logger = logging.getLogger(__name__)

# Regex: Chinese name (2-4 chars) at start, followed by comma/comma-space, then title+info
_ENTRY_RE = _re.compile(
    r"^([\u4e00-\u9fff]{2,4}|[A-Za-z][\w\s·]+?)"  # Name (Chinese 2-4 chars or English)
    r"[，,]\s*"                                       # Separator
    r"(.+)$"                                          # Rest: position + research direction
)
_RESEARCH_RE = _re.compile(r"研究方向[：:](.+)$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ZJUCyberFacultyCrawler(BaseCrawler):
    """Crawler for ZJU Cybersecurity School faculty (rich-text table format)."""

    async def fetch_and_parse(self) -> list[CrawledItem]:
        university = self.config.get("university", "浙江大学")
        department = self.config.get("department", "网络空间安全学院")
        source_id = self.source_id
        source_url = self.config.get("url")
        crawled_at = _now_iso()

        try:
            html = await fetch_page(source_url)
            soup = BeautifulSoup(html, "lxml")
        except Exception as e:
            logger.error("ZJUCyberFacultyCrawler: failed to fetch %s: %s", source_url, e)
            return []

        # Find the content area — typically in wp_editor table or article content div
        content_area = (
            soup.find("table", class_="wp_editor_art_paste_table")
            or soup.find("div", class_="wp_articlecontent")
            or soup.find("div", class_="article-txt")
        )
        if not content_area:
            logger.warning("ZJUCyberFacultyCrawler: no content area found")
            return []

        # Pre-scan: detect broken link pattern (all <a> tags sharing the same href)
        all_hrefs = [a.get("href", "") for a in content_area.find_all("a") if a.get("href")]
        unique_hrefs = set(all_hrefs)
        # If >80% of links point to the same URL, links are broken — always use synthetic URLs
        broken_links = len(unique_hrefs) <= 2 and len(all_hrefs) > 5

        # Extract text blocks from <td> elements (each td typically has one faculty entry)
        items: list[CrawledItem] = []
        seen_names: set[str] = set()

        # Collect text blocks from table cells
        cells = content_area.find_all("td")
        for cell in cells:
            text = cell.get_text(strip=True)
            if not text or len(text) < 4:
                continue

            # Skip section headers
            skip_headers = ("高层次人才", "青年人才", "三、教师队伍")
            if text in skip_headers or text.startswith(("一、", "二、")):
                continue

            # Try to parse "姓名，职称研究方向：xxx" format
            m = _ENTRY_RE.match(text)
            if not m:
                continue

            name = m.group(1).strip()
            rest = m.group(2).strip()

            # Skip if name is a common non-name word
            if name in ("研究方向", "研究领域", "教师队伍", "青年人才", "高层次人才"):
                continue

            if name in seen_names:
                continue
            seen_names.add(name)

            # Parse position and research areas from remaining text
            position = ""
            research_areas: list[str] = []

            ra_match = _RESEARCH_RE.search(rest)
            if ra_match:
                ra_text = ra_match.group(1).strip()
                research_areas = parse_research_areas(ra_text)
                position = rest[:ra_match.start()].strip().rstrip("，,、")
            else:
                position = rest

            # Try to extract photo from cell
            photo_url = ""
            img = cell.find("img")
            if img and img.get("src"):
                src = img["src"]
                if src.startswith("http"):
                    photo_url = src
                else:
                    base_url = self.config.get("base_url", source_url)
                    from urllib.parse import urljoin
                    photo_url = urljoin(base_url, src)

            # Only use real links if the page doesn't have the broken all-same-URL pattern
            profile_url = ""
            if not broken_links:
                link = cell.find("a")
                if link and link.get("href"):
                    href = link["href"]
                    from urllib.parse import urljoin
                    profile_url = urljoin(self.config.get("base_url", source_url), href)

            # Generate synthetic URL for deduplication if profile link is broken/missing
            if not profile_url:
                name_hash = compute_url_hash(f"{source_url}#{name}")
                profile_url = f"{source_url}#{name_hash[:16]}"

            record = ScholarRecord(
                name=name,
                university=university,
                department=department,
                position=position,
                research_areas=research_areas,
                photo_url=photo_url,
                profile_url=profile_url,
                source_id=source_id,
                source_url=source_url,
                crawled_at=crawled_at,
                last_seen_at=crawled_at,
                is_active=True,
            )
            record.data_completeness = compute_scholar_completeness(record)

            items.append(
                CrawledItem(
                    title=name,
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

        logger.info("ZJUCyberFacultyCrawler: extracted %d faculty", len(items))
        return items
