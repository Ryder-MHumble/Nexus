"""University Ecosystem service — reads raw crawled data for the 高校生态 page."""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timezone
from typing import Any

from app.config import BASE_DIR
from app.crawlers.utils.json_storage import DATA_DIR as RAW_DATA_DIR
from app.crawlers.utils.json_storage import LATEST_FILENAME
from app.services.intel.shared import parse_source_filter
from app.services.stores.json_reader import get_articles
from app.services.stores.source_state import get_all_source_states

logger = logging.getLogger(__name__)

PROCESSED_DIR = BASE_DIR / "data" / "processed" / "university_eco"

DIMENSION = "universities"

GROUP_NAMES: dict[str, str] = {
    "university_news": "高校新闻",
    "ai_institutes": "AI研究机构",
    "provincial": "省级教育厅",
    "awards": "科技荣誉",
    "aggregators": "教育聚合",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None


def _extract_thumbnail(item: dict[str, Any]) -> str | None:
    images = (item.get("extra") or {}).get("images") or []
    if images and isinstance(images, list):
        first = images[0]
        if isinstance(first, dict):
            return first.get("src")
    return None


def _to_feed_item(item: dict[str, Any]) -> dict[str, Any]:
    raw_images = (item.get("extra") or {}).get("images") or []
    images = [
        {"src": img.get("src", ""), "alt": img.get("alt")}
        for img in raw_images
        if isinstance(img, dict) and img.get("src")
    ]
    return {
        "id": item.get("url_hash", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "published_at": item.get("published_at"),
        "source_id": item.get("source_id", ""),
        "source_name": item.get("source_name", ""),
        "group": item.get("group"),
        "tags": item.get("tags") or [],
        "has_content": bool(item.get("content")),
        "thumbnail": _extract_thumbnail(item),
        "is_new": item.get("is_new", False),
        "content": item.get("content"),
        "images": images,
    }


def _to_article_detail(item: dict[str, Any]) -> dict[str, Any]:
    raw_images = (item.get("extra") or {}).get("images") or []
    images = [
        {"src": img.get("src", ""), "alt": img.get("alt")}
        for img in raw_images
        if isinstance(img, dict) and img.get("src")
    ]
    return {
        "id": item.get("url_hash", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "published_at": item.get("published_at"),
        "source_id": item.get("source_id", ""),
        "source_name": item.get("source_name", ""),
        "group": item.get("group"),
        "tags": item.get("tags") or [],
        "content": item.get("content"),
        "images": images,
        "is_new": item.get("is_new", False),
    }


# ---------------------------------------------------------------------------
# 1. Overview
# ---------------------------------------------------------------------------

async def get_overview() -> dict[str, Any]:
    """Build dashboard overview for the universities dimension."""
    from app.scheduler.manager import load_all_source_configs

    articles = await get_articles(DIMENSION)
    today = date.today()

    # Per-group aggregation
    group_data: dict[str, dict[str, Any]] = {}
    latest_crawl: str | None = None

    for item in articles:
        grp = item.get("group") or "unknown"
        entry = group_data.setdefault(grp, {
            "total": 0, "new_today": 0, "sources": set(),
        })
        entry["total"] += 1
        entry["sources"].add(item.get("source_id", ""))

        pub = _parse_date(item.get("published_at"))
        if pub == today:
            entry["new_today"] += 1

        crawled = item.get("crawled_at") or ""
        if crawled and (not latest_crawl or crawled > latest_crawl):
            latest_crawl = crawled

    # Source counts from YAML
    all_configs = load_all_source_configs()
    uni_configs = [c for c in all_configs if c.get("dimension") == DIMENSION]
    total_source_count = len(uni_configs)

    # Active sources (those that produced data)
    active_sources: set[str] = set()
    for entry in group_data.values():
        active_sources |= entry["sources"]

    # Build groups list
    new_today_total = 0
    groups: list[dict[str, Any]] = []
    for grp_id, grp_name in GROUP_NAMES.items():
        entry = group_data.get(grp_id, {"total": 0, "new_today": 0, "sources": set()})
        new_today_total += entry["new_today"]
        groups.append({
            "group": grp_id,
            "group_name": grp_name,
            "total_articles": entry["total"],
            "new_today": entry["new_today"],
            "source_count": len(entry["sources"]),
        })

    return {
        "generated_at": _now_iso(),
        "total_articles": len(articles),
        "new_today": new_today_total,
        "active_source_count": len(active_sources),
        "total_source_count": total_source_count,
        "groups": groups,
        "latest_crawl_at": latest_crawl,
    }


# ---------------------------------------------------------------------------
# 2. Feed
# ---------------------------------------------------------------------------

async def get_feed(
    group: str | None = None,
    source_id: str | None = None,
    source_ids: str | None = None,
    source_name: str | None = None,
    source_names: str | None = None,
    keyword: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Paginated article feed with filtering."""
    # 应用信源筛选（优先筛选，减少后续处理量）
    source_filter = parse_source_filter(source_id, source_ids, source_name, source_names)

    # 如果有 source_filter，不传 source_id 给 get_articles，之后手动过滤
    articles = await get_articles(
        DIMENSION,
        group=group,
        source_id=None if source_filter else source_id,
        date_from=date_from,
        date_to=date_to,
    )

    # 手动应用信源过滤
    if source_filter:
        articles = [a for a in articles if a.get("source_id") in source_filter]

    # Keyword filter on title
    if keyword:
        kw = keyword.lower()
        articles = [
            a for a in articles
            if kw in (a.get("title") or "").lower()
        ]

    total = len(articles)
    total_pages = max(1, math.ceil(total / page_size))
    offset = (page - 1) * page_size
    page_items = articles[offset:offset + page_size]

    return {
        "generated_at": _now_iso(),
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": [_to_feed_item(a) for a in page_items],
    }


# ---------------------------------------------------------------------------
# 3. Article Detail
# ---------------------------------------------------------------------------

async def get_article_detail(url_hash: str) -> dict[str, Any] | None:
    """Get full article by url_hash. Returns None if not found."""
    articles = await get_articles(DIMENSION)
    for item in articles:
        if item.get("url_hash") == url_hash:
            return _to_article_detail(item)
    return None


# ---------------------------------------------------------------------------
# 4. Sources
# ---------------------------------------------------------------------------

async def get_sources(group: str | None = None) -> dict[str, Any]:
    """List university sources with their latest crawl metadata."""
    from app.scheduler.manager import load_all_source_configs

    all_configs = load_all_source_configs()
    uni_configs = [c for c in all_configs if c.get("dimension") == DIMENSION]

    if group:
        uni_configs = [c for c in uni_configs if c.get("group") == group]

    states = await get_all_source_states()

    # Read per-source metadata from latest.json files
    source_meta: dict[str, dict[str, Any]] = {}
    dim_dir = RAW_DATA_DIR / DIMENSION
    if dim_dir.exists():
        for json_file in dim_dir.rglob(LATEST_FILENAME):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                sid = data.get("source_id")
                if sid:
                    source_meta[sid] = {
                        "item_count": data.get("item_count", 0),
                        "new_item_count": data.get("new_item_count", 0),
                        "crawled_at": data.get("crawled_at"),
                    }
            except (json.JSONDecodeError, OSError):
                continue

    items: list[dict[str, Any]] = []
    enabled_count = 0

    for cfg in uni_configs:
        sid = cfg.get("id", "")
        state = states.get(sid, {})
        override = state.get("is_enabled_override")
        is_enabled = override if override is not None else cfg.get("is_enabled", True)
        if is_enabled:
            enabled_count += 1

        meta = source_meta.get(sid, {})
        items.append({
            "source_id": sid,
            "source_name": cfg.get("name", sid),
            "group": cfg.get("group", ""),
            "url": cfg.get("url", ""),
            "item_count": meta.get("item_count", 0),
            "new_item_count": meta.get("new_item_count", 0),
            "last_crawled_at": meta.get("crawled_at") or state.get("last_crawl_at"),
            "is_enabled": is_enabled,
        })

    return {
        "generated_at": _now_iso(),
        "total_sources": len(items),
        "enabled_sources": enabled_count,
        "items": items,
    }


# ---------------------------------------------------------------------------
# 5. Research Outputs (from processed data)
# ---------------------------------------------------------------------------

def get_research_outputs(
    rtype: str | None = None,
    influence: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Paginated list of classified research outputs from processed data."""
    research_path = PROCESSED_DIR / "research_outputs.json"
    if not research_path.exists():
        return {
            "generated_at": _now_iso(),
            "item_count": 0,
            "type_stats": {"论文": 0, "专利": 0, "获奖": 0},
            "items": [],
        }

    with open(research_path, encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])

    # Apply filters
    if rtype:
        items = [i for i in items if i.get("type") == rtype]
    if influence:
        items = [i for i in items if i.get("influence") == influence]

    # Type stats (from full set before pagination)
    type_stats: dict[str, int] = {"论文": 0, "专利": 0, "获奖": 0}
    for i in items:
        t = i.get("type", "")
        if t in type_stats:
            type_stats[t] += 1

    # Pagination
    total = len(items)
    offset = (page - 1) * page_size
    page_items = items[offset:offset + page_size]

    return {
        "generated_at": data.get("generated_at", _now_iso()),
        "item_count": total,
        "type_stats": type_stats,
        "items": page_items,
    }
