"""Date and datetime utilities shared across intel modules."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

# Gov-site URL date patterns (for policy articles where published_at is missing)
_GOV_URL_DATE_RE1 = re.compile(r"/t(\d{4})(\d{2})(\d{2})_")
_GOV_URL_DATE_RE2 = re.compile(r"/(\d{4})(\d{2})/t\d+")


def article_date(article: dict, *, url_fallback: bool = False) -> str:
    """Extract YYYY-MM-DD date string from article.

    *url_fallback*: if True, attempt to parse date from gov-site URL patterns
    when published_at is unavailable (used by policy processor).
    """
    pub = article.get("published_at")
    if pub:
        try:
            return datetime.fromisoformat(pub).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    if url_fallback:
        url = article.get("url", "")
        m = _GOV_URL_DATE_RE1.search(url)
        if m:
            return f"{m[1]}-{m[2]}-{m[3]}"
        m = _GOV_URL_DATE_RE2.search(url)
        if m:
            return f"{m[1]}-{m[2]}-01"
    return date.today().isoformat()


def article_datetime(article: dict) -> datetime:
    """Extract datetime from article, fallback to now(UTC)."""
    pub = article.get("published_at")
    if pub:
        try:
            return datetime.fromisoformat(pub)
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)


def parse_date_str(s: str | None) -> str | None:
    """Try to parse a date string in various formats to YYYY-MM-DD."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def str_or_none(value: Any) -> str | None:
    """Normalize value to a non-empty string or None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", ""):
        return None
    return s
