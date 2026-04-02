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

    def _append_image(src_raw: str, alt_raw: str = "") -> None:
        src = src_raw.strip()
        if not src or src.startswith("data:"):
            return

        # Resolve relative URLs
        if base_url:
            src = urljoin(base_url, src)

        if src in seen:
            return
        seen.add(src)

        entry: dict[str, str] = {"src": src}
        alt = alt_raw.strip()
        if alt:
            entry["alt"] = alt
        images.append(entry)

    for img in soup.find_all("img"):
        # Skip tiny images (icons / tracking pixels)
        try:
            w = img.get("width", "")
            h = img.get("height", "")
            if (w and int(w) < 10) or (h and int(h) < 10):
                continue
        except (ValueError, TypeError):
            pass

        _append_image(img.get("src") or "", img.get("alt") or "")

    # Fallback for pages that use OpenGraph/Twitter card images but no inline <img>.
    for meta in soup.find_all("meta"):
        key = str(meta.get("property") or meta.get("name") or "").strip().lower()
        if key not in {"og:image", "twitter:image", "twitter:image:src"}:
            continue
        _append_image(meta.get("content") or "", meta.get("content") or "")

    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).strip().lower()
        if rel not in {"image_src", "apple-touch-icon", "icon"}:
            continue
        _append_image(link.get("href") or "", "")

    return images
