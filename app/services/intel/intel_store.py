"""JSON I/O and deduplication utilities for processed intel data."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

PROCESSED_BASE = BASE_DIR / "data" / "processed"

_EMPTY_RESPONSE: dict[str, Any] = {"generated_at": None, "item_count": 0, "items": []}


def load_intel_json(module: str, filename: str) -> dict[str, Any]:
    """Load ``data/processed/{module}/{filename}``, returning empty response on failure."""
    path = PROCESSED_BASE / module / filename
    if not path.exists():
        return dict(_EMPTY_RESPONSE)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load %s: %s", path, e)
        return dict(_EMPTY_RESPONSE)


def get_intel_stats(*modules_and_files: tuple[str, str]) -> dict[str, Any]:
    """Read metadata (item_count, generated_at) from multiple processed files.

    Usage::

        get_intel_stats(("policy_intel", "feed.json"), ("policy_intel", "opportunities.json"))
    """
    stats: dict[str, Any] = {}
    for module, filename in modules_and_files:
        data = load_intel_json(module, filename)
        key = f"{module}_{filename.replace('.json', '')}"
        stats[key] = {
            "item_count": data.get("item_count", 0),
            "generated_at": data.get("generated_at"),
        }
    return stats


def deduplicate_articles(articles: list[dict]) -> list[dict]:
    """Deduplicate articles by url_hash, keeping first occurrence."""
    seen: set[str] = set()
    unique: list[dict] = []
    for a in articles:
        h = a.get("url_hash", "")
        if h and h not in seen:
            seen.add(h)
            unique.append(a)
    return unique
