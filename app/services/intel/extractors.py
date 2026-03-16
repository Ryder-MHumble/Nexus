"""Regex extraction helpers for intel modules — funding, deadlines, leader names."""
from __future__ import annotations

import re
from datetime import date, datetime

_TITLES = (
    "总理|副总理|部长|副部长|主任|副主任|书记|副书记"
    "|院长|副院长|局长|副局长|委员|主席|副主席"
    "|市长|副市长|区长|副区长|司长|副司长"
)

FUNDING_PATTERNS = [
    re.compile(
        r"(?:不超过|最高|最多|上限)?\s*(\d+(?:\.\d+)?(?:\s*[-~至到]\s*\d+(?:\.\d+)?)?)\s*万(?:元)?",
    ),
    re.compile(r"(\d+(?:\.\d+)?)\s*亿(?:元)?"),
]

DEADLINE_PATTERNS = [
    re.compile(
        r"截止[日时]?[期间]?[为：:\s]*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
    ),
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[前止]"),
    re.compile(r"截止[日时]?[期间]?[为：:\s]*(\d{4})[/-](\d{1,2})[/-](\d{1,2})"),
]

LEADER_NAME_RE = re.compile(
    rf"(?:{_TITLES})\s*([\u4e00-\u9fa5]{{2,4}})"
    rf"|([\u4e00-\u9fa5]{{2,4}})\s*(?:{_TITLES})",
)


def extract_funding(text: str) -> str | None:
    """Extract funding amount from text using regex."""
    for pattern in FUNDING_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def extract_deadline(text: str) -> str | None:
    """Extract deadline date from text.  Returns YYYY-MM-DD or None."""
    for pattern in DEADLINE_PATTERNS:
        m = pattern.search(text)
        if m:
            groups = m.groups()
            try:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                return date(year, month, day).isoformat()
            except (ValueError, IndexError):
                continue
    return None


def extract_leader(text: str) -> str | None:
    """Extract leader name from text near title/position keywords."""
    m = LEADER_NAME_RE.search(text)
    if m:
        return m.group(1) or m.group(2)
    return None


def compute_days_left(deadline: str | None) -> int | None:
    """Compute days from today to *deadline* (YYYY-MM-DD).  None if no deadline."""
    if not deadline:
        return None
    try:
        dl = datetime.strptime(deadline, "%Y-%m-%d").date()
        return max(0, (dl - date.today()).days)
    except (ValueError, TypeError):
        return None
