"""Personnel intelligence service — dynamically reads raw data + merges cached LLM enrichments.

Instead of reading a static pre-processed JSON file, this module:
1. Reads ALL raw articles from data/raw/personnel/ on each call
2. Applies the rules engine (fast regex) to extract appointment/dismissal records
3. Merges with cached LLM enrichments from data/processed/personnel_intel/_enriched/
4. Returns the complete, always-up-to-date dataset
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

from app.config import BASE_DIR
from app.services.intel.personnel.rules import (
    change_id,
    compute_match_score,
    extract_changes,
)
from app.services.intel.personnel.source_scope import filter_personnel_scoped_articles
from app.services.intel.shared import article_date, parse_source_filter
from app.services.stores.json_reader import get_articles

logger = logging.getLogger(__name__)

PROCESSED_DIR = BASE_DIR / "data" / "processed" / "personnel_intel"
ENRICHED_DIR = PROCESSED_DIR / "_enriched"


# ---------------------------------------------------------------------------
# Cached LLM enrichments
# ---------------------------------------------------------------------------

def _load_enriched_cache() -> dict[str, dict[str, Any]]:
    """Load all cached LLM enrichments from _enriched/ directory, keyed by change ID."""
    cache: dict[str, dict[str, Any]] = {}
    if not ENRICHED_DIR.exists():
        return cache
    for path in ENRICHED_DIR.glob("*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("enriched_changes", []):
                cid = item.get("id", "")
                if cid:
                    cache[cid] = item
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning("Skipping invalid enriched file %s: %s", path.name, e)
    return cache


# ---------------------------------------------------------------------------
# Live data computation
# ---------------------------------------------------------------------------

def _article_date(a: dict[str, Any]) -> str:
    return article_date(a)


def _article_id(article: dict[str, Any]) -> str:
    """Generate a stable ID for an article-level item."""
    url_hash = article.get("url_hash", "")
    if url_hash:
        return f"art-{url_hash[:16]}"
    key = article.get("url") or article.get("title", "")
    return f"art-{hashlib.sha256(key.encode()).hexdigest()[:16]}"


# Regex to extract person/department from MOE-style titles like:
# "教育部职业教育与成人教育司负责人就《...》答记者问"
_TITLE_DEPT_RE = re.compile(
    r"([\u4e00-\u9fa5]{2,15}(?:部|委|局|厅|司|院|办|会))"
    r"[^就]*(?:负责人|主任|司长|副司长|处长|厅长)?"
)


def _extract_title_info(title: str) -> tuple[str, str | None]:
    """Extract a short description and department from article title.

    Returns (short_name, department).
    """
    # Try to extract department from title
    m = _TITLE_DEPT_RE.search(title)
    dept = m.group(1) if m else None
    # Truncate title for name field
    short = title[:40] + ("…" if len(title) > 40 else "")
    return short, dept


async def _compute_live_changes() -> list[dict[str, Any]]:
    """Read raw personnel articles, apply rules, merge with cached LLM enrichments.

    For articles that don't produce specific appointment/dismissal records,
    an article-level item is created so ALL raw data is represented.

    Returns a list of item dicts, sorted: action group first,
    then by relevance desc, then by date desc.
    """
    articles = await get_articles("personnel")
    articles = filter_personnel_scoped_articles(articles)

    # Deduplicate by url_hash
    seen_hashes: set[str] = set()
    unique: list[dict[str, Any]] = []
    for a in articles:
        h = a.get("url_hash", "")
        if h and h not in seen_hashes:
            seen_hashes.add(h)
            unique.append(a)

    # Extract changes via Tier 1 rules
    raw_changes: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    articles_with_changes: set[str] = set()  # url_hashes that produced changes
    for article in unique:
        changes = extract_changes(article)
        if changes:
            articles_with_changes.add(article.get("url_hash", ""))
        for change in changes:
            cid = change_id(change)
            raw_changes.append((cid, change, article))

    # Load cached LLM enrichments
    enrichment_cache = _load_enriched_cache()

    # Merge: use cached LLM data if available, otherwise default
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for cid, change, article in raw_changes:
        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        if cid in enrichment_cache:
            items.append(enrichment_cache[cid])
        else:
            items.append({
                "id": cid,
                "name": change.get("name", ""),
                "action": change.get("action", ""),
                "position": change.get("position", ""),
                "department": change.get("department"),
                "date": change.get("date", _article_date(article)),
                "source": article.get("source_name", ""),
                "source_id": article.get("source_id", ""),
                "source_name": article.get("source_name", ""),
                "sourceUrl": article.get("url"),
                "relevance": 10,
                "importance": "一般",
                "group": "watch",
                "note": None,
                "actionSuggestion": None,
                "background": None,
                "signals": [],
                "aiInsight": None,
            })

    # Include article-level items for articles without specific changes
    for article in unique:
        url_hash = article.get("url_hash", "")
        if url_hash in articles_with_changes:
            continue  # already represented by extracted changes

        aid = _article_id(article)
        if aid in seen_ids:
            continue
        seen_ids.add(aid)

        title = article.get("title", "")
        short_name, dept = _extract_title_info(title)
        content = (article.get("content") or "")[:300]
        match_score = compute_match_score(article)

        items.append({
            "id": aid,
            "name": short_name,
            "action": "动态",
            "position": "",
            "department": dept or article.get("source_name", ""),
            "date": _article_date(article),
            "source": article.get("source_name", ""),
            "source_id": article.get("source_id", ""),
            "source_name": article.get("source_name", ""),
            "sourceUrl": article.get("url"),
            "relevance": max(match_score // 5, 5),
            "importance": "关注" if match_score >= 30 else "一般",
            "group": "watch",
            "note": title,
            "actionSuggestion": None,
            "background": None,
            "signals": [],
            "aiInsight": content if content else None,
        })

    # Sort: action first, then relevance desc, then date desc
    items.sort(
        key=lambda x: (
            0 if x.get("group") == "action" else 1,
            -(x.get("relevance") or 0),
            x.get("date", "") or "",
        ),
        reverse=False,
    )
    # Re-sort: within same group priority, higher relevance first, then newer date
    items.sort(
        key=lambda x: (
            0 if x.get("group") == "action" else 1,
            -(x.get("relevance") or 0),
        ),
    )

    return items


# ---------------------------------------------------------------------------
# Feed (article-level) — reads from static processed file for backward compat
# ---------------------------------------------------------------------------

def get_personnel_feed(
    importance: str | None = None,
    min_match_score: int | None = None,
    keyword: str | None = None,
    source_id: str | None = None,
    source_ids: str | None = None,
    source_name: str | None = None,
    source_names: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Read feed.json and apply optional filters."""
    from app.services.intel.shared import load_intel_json

    data = load_intel_json("personnel_intel", "feed.json")
    items = data.get("items", [])

    # 应用信源筛选（优先筛选，减少后续处理量）
    source_filter = parse_source_filter(source_id, source_ids, source_name, source_names)
    if source_filter:
        items = [i for i in items if i.get("source_id") in source_filter]

    if importance:
        items = [i for i in items if i.get("importance") == importance]
    if min_match_score is not None:
        items = [i for i in items if (i.get("matchScore") or 0) >= min_match_score]
    if keyword:
        kw = keyword.lower()
        items = [
            i for i in items
            if kw in (i.get("title") or "").lower()
            or kw in (i.get("source") or "").lower()
            or any(kw in c.get("name", "").lower() for c in i.get("changes", []))
            or any(kw in c.get("position", "").lower() for c in i.get("changes", []))
        ]

    total = len(items)
    items = items[offset:offset + limit]
    return {"generated_at": data.get("generated_at"), "item_count": total, "items": items}


def get_personnel_changes(
    department: str | None = None,
    action: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Read changes.json and apply optional filters."""
    from app.services.intel.shared import load_intel_json

    data = load_intel_json("personnel_intel", "changes.json")
    items = data.get("items", [])

    if department:
        dept_lower = department.lower()
        items = [i for i in items if dept_lower in (i.get("department") or "").lower()]
    if action:
        items = [i for i in items if i.get("action") == action]
    if keyword:
        kw = keyword.lower()
        items = [
            i for i in items
            if kw in (i.get("name") or "").lower()
            or kw in (i.get("position") or "").lower()
            or kw in (i.get("department") or "").lower()
        ]

    total = len(items)
    items = items[offset:offset + limit]
    return {"generated_at": data.get("generated_at"), "item_count": total, "items": items}


def get_personnel_stats() -> dict[str, Any]:
    """Get summary statistics about personnel data."""
    from app.services.intel.shared import load_intel_json

    feed_data = load_intel_json("personnel_intel", "feed.json")
    changes_data = load_intel_json("personnel_intel", "changes.json")

    dept_counts: dict[str, int] = {}
    for item in changes_data.get("items", []):
        dept = item.get("department") or "其他"
        dept_counts[dept] = dept_counts.get(dept, 0) + 1

    return {
        "total_articles": feed_data.get("item_count", 0),
        "total_changes": changes_data.get("item_count", 0),
        "by_department": dept_counts,
        "generated_at": feed_data.get("generated_at"),
    }


# ---------------------------------------------------------------------------
# Enriched feed — LIVE from raw data + cached LLM enrichments
# ---------------------------------------------------------------------------


async def get_enriched_feed(
    group: str | None = None,
    importance: str | None = None,
    min_relevance: int | None = None,
    keyword: str | None = None,
    source_id: str | None = None,
    source_ids: str | None = None,
    source_name: str | None = None,
    source_names: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Dynamically compute enriched feed from latest raw data + cached LLM enrichments."""
    items = await _compute_live_changes()

    # 应用信源筛选（优先筛选，减少后续处理量）
    source_filter = parse_source_filter(source_id, source_ids, source_name, source_names)
    if source_filter:
        items = [i for i in items if i.get("source_id") in source_filter]

    if group:
        items = [i for i in items if i.get("group") == group]
    if importance:
        items = [i for i in items if i.get("importance") == importance]
    if min_relevance is not None:
        items = [i for i in items if (i.get("relevance") or 0) >= min_relevance]
    if keyword:
        kw = keyword.lower()
        items = [
            i for i in items
            if kw in (i.get("name") or "").lower()
            or kw in (i.get("position") or "").lower()
            or kw in (i.get("department") or "").lower()
            or kw in (i.get("note") or "").lower()
            or kw in (i.get("aiInsight") or "").lower()
        ]

    total = len(items)
    action_count = sum(1 for i in items if i.get("group") == "action")
    watch_count = total - action_count
    items = items[offset:offset + limit]

    return {
        "generated_at": datetime.now().isoformat(),
        "total_count": total,
        "action_count": action_count,
        "watch_count": watch_count,
        "items": items,
    }


async def get_enriched_stats() -> dict[str, Any]:
    """Get summary statistics from live enriched data."""
    items = await _compute_live_changes()

    dept_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    action_group = 0
    high_relevance = 0

    for item in items:
        dept = item.get("department") or "其他"
        dept_counts[dept] = dept_counts.get(dept, 0) + 1

        act = item.get("action", "")
        action_counts[act] = action_counts.get(act, 0) + 1

        if item.get("group") == "action":
            action_group += 1
        if (item.get("relevance") or 0) >= 60:
            high_relevance += 1

    return {
        "total_changes": len(items),
        "action_count": action_group,
        "watch_count": len(items) - action_group,
        "by_department": dept_counts,
        "by_action": action_counts,
        "high_relevance_count": high_relevance,
        "generated_at": datetime.now().isoformat(),
    }
