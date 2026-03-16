"""Image metadata extraction from HTML content.

Follows the same pattern as ``pdf_extractor.py``: a single public function
that accepts raw HTML + base URL and returns structured metadata.
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def extract_images(html: str, base_url: str = "") -> list[dict[str, str]]:
    """Extract image metadata from HTML content.

    Returns a list of ``{"src": ..., "alt": ...}`` dicts (``alt`` is omitted
    when empty).  Skips data-URIs, tracking pixels (w/h < 10), and duplicates.
    """
    soup = BeautifulSoup(html, "html.parser")
    images: list[dict[str, str]] = []
    seen: set[str] = set()

    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src.startswith("data:"):
            continue

        # Resolve relative URLs
        if base_url:
            src = urljoin(base_url, src)

        if src in seen:
            continue
        seen.add(src)

        # Skip tiny images (icons / tracking pixels)
        try:
            w = img.get("width", "")
            h = img.get("height", "")
            if (w and int(w) < 10) or (h and int(h) < 10):
                continue
        except (ValueError, TypeError):
            pass

        entry: dict[str, str] = {"src": src}
        alt = (img.get("alt") or "").strip()
        if alt:
            entry["alt"] = alt
        images.append(entry)

    return images
