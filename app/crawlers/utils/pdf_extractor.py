"""PDF URL extraction utilities."""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def extract_pdf_url(
    soup: BeautifulSoup,
    page_url: str,
    title: str,
    config: dict,
) -> str | None:
    """
    Extract PDF URL from a page.

    Args:
        soup: BeautifulSoup object of the page
        page_url: Current page URL (for relative path conversion)
        title: Article title (for smart matching)
        config: Source configuration from YAML

    Returns:
        Absolute PDF URL if found, None otherwise

    Extraction strategies (priority order):
        1. CSS selector (config['pdf_selector'])
        2. Smart matching (automatic)
    """
    try:
        # Strategy 1: CSS selector from config
        if pdf_selector := config.get("pdf_selector"):
            return _extract_with_selector(soup, page_url, pdf_selector)

        # Strategy 2: Smart matching
        return _smart_match_pdf(soup, page_url, title)

    except Exception as e:
        logger.warning(f"PDF extraction failed for {page_url}: {e}")
        return None


def _extract_with_selector(
    soup: BeautifulSoup,
    page_url: str,
    selector: str,
) -> str | None:
    """Extract PDF using CSS selector."""
    link = soup.select_one(selector)
    if not link:
        return None

    href = link.get("href")
    if not href:
        return None

    # Convert relative URL to absolute
    return urljoin(page_url, href)


def _smart_match_pdf(
    soup: BeautifulSoup,
    page_url: str,
    title: str,
) -> str | None:
    """
    Smart match PDF links with weighted scoring.

    Weight calculation:
    - Link text contains "PDF"/"下载"/"附件" → +10
    - Link in div.attachments/div.download/etc → +8
    - Link in article/main/content → +3
    - href ends with .pdf → +2

    Returns highest weight link if weight >= 5, else None.
    """
    links = soup.find_all("a", href=True)
    candidates = []

    for link in links:
        href = link.get("href", "")
        if not href.lower().endswith(".pdf"):
            continue

        weight = 2  # Base weight for .pdf link
        link_text = link.get_text(strip=True).lower()

        # Check link text keywords
        pdf_keywords = ["pdf", "下载", "附件", "download", "attachment"]
        if any(kw in link_text for kw in pdf_keywords):
            weight += 10

        # Check parent containers
        parent_containers = ["attachments", "download", "file", "fujian"]
        for parent in link.parents:
            parent_class = " ".join(parent.get("class", [])).lower()
            parent_id = parent.get("id", "").lower()
            if any(cont in parent_class or cont in parent_id for cont in parent_containers):
                weight += 8
                break

        # Check if in main content area
        content_containers = ["article", "main", "content"]
        for parent in link.parents:
            if parent.name in content_containers:
                weight += 3
                break

        abs_url = urljoin(page_url, href)
        candidates.append((weight, abs_url))

    # Sort by weight descending, filter >= 5
    candidates.sort(reverse=True, key=lambda x: x[0])
    valid_candidates = [url for weight, url in candidates if weight >= 5]

    return valid_candidates[0] if valid_candidates else None
