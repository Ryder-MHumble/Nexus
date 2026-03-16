"""Content filtering utilities for crawlers.

Provides flexible keyword-based filtering with support for:
- Whitelist filtering (keyword_filter)
- Blacklist filtering (keyword_blacklist)
- No filtering (when both are empty/None)
"""
from __future__ import annotations


def should_keep_item(
    text: str,
    keyword_filter: list[str] | None = None,
    keyword_blacklist: list[str] | None = None,
) -> bool:
    """Check if an item should be kept based on keyword filters.

    Args:
        text: Text to check (usually title or title+content)
        keyword_filter: Whitelist - if provided, text must contain at least one keyword
        keyword_blacklist: Blacklist - if provided, text must NOT contain any keyword

    Returns:
        True if item should be kept, False if it should be filtered out

    Examples:
        >>> should_keep_item("AI技术发展", ["AI", "人工智能"])
        True
        >>> should_keep_item("普通新闻", ["AI", "人工智能"])
        False
        >>> should_keep_item("普通新闻", None)  # No filter = keep all
        True
        >>> should_keep_item("广告内容", None, ["广告", "推广"])
        False
        >>> should_keep_item("AI广告", ["AI"], ["广告"])  # Blacklist takes precedence
        False
    """
    # Blacklist check first (takes precedence)
    if keyword_blacklist:
        if any(kw in text for kw in keyword_blacklist):
            return False

    # Whitelist check (only if provided)
    if keyword_filter:
        if not any(kw in text for kw in keyword_filter):
            return False

    # No filters or passed all checks
    return True
