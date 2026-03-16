"""Read and aggregate crawled article data — from Supabase SDK with JSON fallback."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any

from app.crawlers.utils.json_storage import DATA_DIR as RAW_DATA_DIR
from app.crawlers.utils.json_storage import LATEST_FILENAME

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None


def _get_client():
    from app.db.client import get_client  # noqa: PLC0415
    return get_client()


# ---------------------------------------------------------------------------
# JSON fallback implementations
# ---------------------------------------------------------------------------

def _json_get_articles(
    dimension: str,
    group: str | None = None,
    source_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    dim_dir = RAW_DATA_DIR / dimension
    if not dim_dir.exists():
        logger.warning("Dimension directory not found: %s", dim_dir)
        return []

    all_items: list[dict[str, Any]] = []
    json_files = list(dim_dir.rglob(LATEST_FILENAME))

    for json_file in json_files:
        rel = json_file.relative_to(dim_dir)
        parts = rel.parts

        if len(parts) == 3:
            file_group, file_source, _ = parts
        elif len(parts) == 2:
            file_group = None
            file_source, _ = parts
        else:
            continue

        if group and file_group != group:
            continue
        if source_id and file_source != source_id:
            continue

        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s", json_file, e)
            continue

        source_meta = {
            "source_id": data.get("source_id", file_source),
            "source_name": data.get("source_name", file_source),
            "dimension": data.get("dimension", dimension),
            "group": data.get("group", file_group),
            "crawled_at": data.get("crawled_at"),
        }

        for item in data.get("items", []):
            pub_date = _parse_date(item.get("published_at"))
            if date_from and pub_date and pub_date < date_from:
                continue
            if date_to and pub_date and pub_date > date_to:
                continue
            item.update({k: v for k, v in source_meta.items() if k not in item})
            all_items.append(item)

    all_items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return all_items


def _json_get_all_articles(
    dimension: str | None = None,
    source_id: str | None = None,
    keyword: str | None = None,
    tags: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    if not RAW_DATA_DIR.exists():
        return []

    dimensions = (
        [dimension]
        if dimension
        else [d.name for d in RAW_DATA_DIR.iterdir() if d.is_dir()]
    )

    all_items: list[dict[str, Any]] = []
    keyword_lower = keyword.lower() if keyword else None

    for dim in dimensions:
        dim_dir = RAW_DATA_DIR / dim
        if not dim_dir.exists():
            continue

        for json_file in dim_dir.rglob(LATEST_FILENAME):
            rel = json_file.relative_to(dim_dir)
            parts = rel.parts

            if len(parts) == 3:
                file_group, file_source, _ = parts
            elif len(parts) == 2:
                file_group = None
                file_source, _ = parts
            else:
                continue

            if source_id and file_source != source_id:
                continue

            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read %s: %s", json_file, e)
                continue

            source_meta = {
                "source_id": data.get("source_id", file_source),
                "source_name": data.get("source_name", file_source),
                "dimension": data.get("dimension", dim),
                "group": data.get("group", file_group),
                "crawled_at": data.get("crawled_at"),
            }

            for item in data.get("items", []):
                pub_date = _parse_date(item.get("published_at"))
                if date_from and pub_date and pub_date < date_from:
                    continue
                if date_to and pub_date and pub_date > date_to:
                    continue

                if keyword_lower:
                    title = (item.get("title") or "").lower()
                    content = (item.get("content") or "").lower()
                    if keyword_lower not in title and keyword_lower not in content:
                        continue

                if tags:
                    item_tags = item.get("tags") or []
                    if not set(tags) & set(item_tags):
                        continue

                item.update({k: v for k, v in source_meta.items() if k not in item})
                all_items.append(item)

    all_items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return all_items


def _json_get_dimension_stats() -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    if not RAW_DATA_DIR.exists():
        return stats

    for dim_dir in RAW_DATA_DIR.iterdir():
        if not dim_dir.is_dir():
            continue

        dimension = dim_dir.name
        total_items = 0
        sources: set[str] = set()
        latest_date: str | None = None

        for json_file in dim_dir.rglob(LATEST_FILENAME):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                total_items += data.get("item_count", len(data.get("items", [])))
                sid = data.get("source_id")
                if sid:
                    sources.add(sid)
                crawled = data.get("crawled_at", "")
                if crawled and (not latest_date or crawled > latest_date):
                    latest_date = crawled
            except (json.JSONDecodeError, OSError):
                continue

        stats[dimension] = {
            "dimension": dimension,
            "total_items": total_items,
            "source_count": len(sources),
            "sources": sorted(sources),
            "latest_crawl": latest_date,
        }

    return stats


def _json_get_available_dates(dimension: str) -> list[str]:
    dim_dir = RAW_DATA_DIR / dimension
    if not dim_dir.exists():
        return []

    dates: set[str] = set()
    for json_file in dim_dir.rglob(LATEST_FILENAME):
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            crawled_at = data.get("crawled_at")
            if crawled_at:
                d = _parse_date(crawled_at)
                if d:
                    dates.add(d.isoformat())
        except (json.JSONDecodeError, OSError):
            continue

    return sorted(dates, reverse=True)


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def get_articles(
    dimension: str,
    group: str | None = None,
    source_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Fetch articles for a dimension from DB (fallback: JSON files)."""
    try:
        client = _get_client()
        query = client.table("articles").select("*").eq("dimension", dimension).order(
            "published_at", desc=True
        )
        if group is not None:
            query = query.eq("group_name", group)
        if source_id is not None:
            query = query.eq("source_id", source_id)
        if date_from is not None:
            query = query.gte("published_at", datetime(
                date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc
            ).isoformat())
        if date_to is not None:
            query = query.lte("published_at", datetime(
                date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc
            ).isoformat())
        res = await query.execute()
        rows = res.data or []
        # Rename group_name → group for callers
        for r in rows:
            if "group_name" in r:
                r["group"] = r.pop("group_name")
        return rows

    except RuntimeError:
        return _json_get_articles(dimension, group, source_id, date_from, date_to)
    except Exception as exc:
        logger.warning("DB get_articles failed, falling back to JSON: %s", exc)
        return _json_get_articles(dimension, group, source_id, date_from, date_to)


async def get_dimension_stats() -> dict[str, dict[str, Any]]:
    """Get statistics for all dimensions (DB preferred, JSON fallback)."""
    try:
        client = _get_client()
        # Use Supabase RPC or aggregate via Python (no raw SQL in REST API)
        # Fetch all dimension+source_id+crawled_at for stats calculation
        res = await client.table("articles").select(
            "dimension, source_id, crawled_at"
        ).execute()
        rows = res.data or []

        stats: dict[str, dict[str, Any]] = {}
        for row in rows:
            dim = row["dimension"]
            if dim not in stats:
                stats[dim] = {
                    "dimension": dim,
                    "total_items": 0,
                    "source_count": 0,
                    "_sources": set(),
                    "latest_crawl": None,
                }
            stats[dim]["total_items"] += 1
            stats[dim]["_sources"].add(row["source_id"])
            crawled = row.get("crawled_at") or ""
            if crawled and (not stats[dim]["latest_crawl"] or crawled > stats[dim]["latest_crawl"]):
                stats[dim]["latest_crawl"] = crawled

        for dim, s in stats.items():
            s["source_count"] = len(s.pop("_sources"))
            s["sources"] = []
        return stats

    except RuntimeError:
        return _json_get_dimension_stats()
    except Exception as exc:
        logger.warning("DB get_dimension_stats failed, falling back to JSON: %s", exc)
        return _json_get_dimension_stats()


async def get_all_articles(
    dimension: str | None = None,
    source_id: str | None = None,
    keyword: str | None = None,
    tags: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Fetch articles from all (or a specific) dimension with filtering."""
    try:
        client = _get_client()
        query = client.table("articles").select("*").order("published_at", desc=True)

        if dimension is not None:
            query = query.eq("dimension", dimension)
        if source_id is not None:
            query = query.eq("source_id", source_id)
        if date_from is not None:
            query = query.gte("published_at", datetime(
                date_from.year, date_from.month, date_from.day, tzinfo=timezone.utc
            ).isoformat())
        if date_to is not None:
            query = query.lte("published_at", datetime(
                date_to.year, date_to.month, date_to.day, 23, 59, 59, tzinfo=timezone.utc
            ).isoformat())
        if keyword is not None:
            # Supabase SDK: use ilike on title OR content
            query = query.or_(f"title.ilike.%{keyword}%,content.ilike.%{keyword}%")
        if tags:
            query = query.contains("tags", tags)

        res = await query.execute()
        rows = res.data or []
        for r in rows:
            if "group_name" in r:
                r["group"] = r.pop("group_name")
        return rows

    except RuntimeError:
        return _json_get_all_articles(dimension, source_id, keyword, tags, date_from, date_to)
    except Exception as exc:
        logger.warning("DB get_all_articles failed, falling back to JSON: %s", exc)
        return _json_get_all_articles(dimension, source_id, keyword, tags, date_from, date_to)


async def get_available_dates(dimension: str) -> list[str]:
    """Get all distinct crawl dates for a dimension, sorted desc."""
    try:
        client = _get_client()
        res = await client.table("articles").select("crawled_at").eq(
            "dimension", dimension
        ).execute()
        dates: set[str] = set()
        for row in (res.data or []):
            d = _parse_date(row.get("crawled_at"))
            if d:
                dates.add(d.isoformat())
        return sorted(dates, reverse=True)

    except RuntimeError:
        return _json_get_available_dates(dimension)
    except Exception as exc:
        logger.warning("DB get_available_dates failed, falling back to JSON: %s", exc)
        return _json_get_available_dates(dimension)
