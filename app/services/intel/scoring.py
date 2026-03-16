"""Keyword scoring and importance computation for intel modules."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


def keyword_score(text: str, keywords: list[tuple[str, int]]) -> int:
    """Scan *text* for keyword matches and accumulate weights.

    Returns raw (unclamped) score.  Caller should ``min(100, max(0, score))``.
    """
    lower = text.lower()
    score = 0
    for kw, weight in keywords:
        if kw.lower() in lower:
            score += weight
    return score


def clamp_score(score: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, score))


def compute_importance(
    match_score: int,
    deadline: str | None,
    title: str,
    *,
    high_keywords: list[str] | None = None,
) -> str:
    """Determine importance level: 紧急 / 重要 / 关注 / 一般.

    *high_keywords*: title keywords that trigger "重要" (default: AI-related).
    """
    if high_keywords is None:
        high_keywords = ["人工智能", "AI", "中关村", "大模型"]

    days_left: int | None = None
    if deadline:
        try:
            dl = datetime.strptime(deadline, "%Y-%m-%d").date()
            days_left = (dl - date.today()).days
        except ValueError:
            pass

    if days_left is not None and 0 < days_left <= 14:
        return "紧急"
    if match_score >= 70:
        return "重要"
    if any(kw in title for kw in high_keywords):
        return "重要"
    if match_score >= 40:
        return "关注"
    return "一般"


def clamp_value(value: Any, lo: int, hi: int, default: int) -> int:
    """Clamp a numeric value to [lo, hi], returning *default* if invalid type."""
    try:
        v = int(value)
        return max(lo, min(hi, v))
    except (TypeError, ValueError):
        return default
