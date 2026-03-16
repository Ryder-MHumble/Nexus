"""HTML sanitization for content_html field.

Cleans raw HTML to a safe subset, keeping content-meaningful tags
(paragraphs, headings, images, links, tables, code blocks) while
stripping dangerous/noise elements (scripts, navigation, iframes).
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Tags to preserve (whitelist approach — safer than blacklist)
_SAFE_TAGS = frozenset({
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "img", "a",
    "ul", "ol", "li",
    "table", "thead", "tbody", "tr", "td", "th",
    "blockquote", "pre", "code",
    "strong", "em", "b", "i", "u", "s",
    "br", "hr",
    "figure", "figcaption",
    "sup", "sub", "span",
    "dl", "dt", "dd",
})

# Attributes allowed per tag (everything else is stripped)
_SAFE_ATTRS: dict[str, frozenset[str]] = {
    "img": frozenset({"src", "alt", "width", "height", "title"}),
    "a": frozenset({"href", "title"}),
    "td": frozenset({"colspan", "rowspan"}),
    "th": frozenset({"colspan", "rowspan"}),
    "code": frozenset({"class"}),
    "pre": frozenset({"class"}),
}

# Tags removed entirely including all children
_STRIP_TAGS = frozenset({
    "script", "style", "nav", "footer", "header", "iframe", "noscript", "svg",
})


def sanitize_html(html: str, base_url: str = "") -> str:
    """Clean HTML to a safe tag/attribute subset.

    - Removes dangerous tags (script, style, nav, …) with their children.
    - Unwraps unknown tags (keeps their text content, drops the tag itself).
    - Normalises ``img.src`` and ``a.href`` to absolute URLs via *base_url*.

    Returns a sanitised HTML string suitable for the ``content_html`` field.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. Remove dangerous/noise tags entirely
    for tag in soup.find_all(list(_STRIP_TAGS)):
        tag.decompose()

    # 2. Process remaining tags
    for tag in list(soup.find_all(True)):
        if tag.name not in _SAFE_TAGS:
            tag.unwrap()
            continue

        # Filter attributes to whitelist
        allowed = _SAFE_ATTRS.get(tag.name, frozenset())
        for attr in list(tag.attrs):
            if attr not in allowed:
                del tag[attr]

        # Normalise relative URLs to absolute
        if base_url:
            if tag.name == "img" and tag.get("src"):
                tag["src"] = urljoin(base_url, tag["src"])
            elif tag.name == "a" and tag.get("href"):
                tag["href"] = urljoin(base_url, tag["href"])

    return str(soup).strip()
