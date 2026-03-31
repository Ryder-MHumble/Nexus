from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.scheduler.manager import load_all_source_configs
from app.services.stores.source_state import (
    get_all_source_states,
    set_enabled_override,
)


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _parse_csv(value: str | None) -> set[str]:
    if value is None:
        return set()
    return {_normalize_text(item) for item in value.split(",") if _normalize_text(item)}


def _combine_filters(single: str | None, multiple: str | None) -> set[str]:
    values = set()
    if _normalize_text(single):
        values.add(_normalize_text(single))
    values |= _parse_csv(multiple)
    return values


def _derive_health_status(last_crawl_at: Any, consecutive_failures: Any) -> str:
    failures = int(consecutive_failures or 0)
    if failures >= 3:
        return "failing"
    if failures > 0:
        return "warning"
    if last_crawl_at:
        return "healthy"
    return "unknown"


def _merge_config_and_state(
    config: dict[str, Any], states: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Merge YAML config with runtime state from source_state.json."""
    source_id = config["id"]
    state = states.get(source_id, {})

    # is_enabled: override takes precedence over YAML
    override = state.get("is_enabled_override")
    is_enabled = override if override is not None else config.get("is_enabled", True)
    tags_raw = config.get("tags", [])
    tags = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []
    health_status = _derive_health_status(
        state.get("last_crawl_at"),
        state.get("consecutive_failures", 0),
    )

    return {
        "id": source_id,
        "name": config.get("name", source_id),
        "url": config.get("url", ""),
        "dimension": config.get("dimension", ""),
        "crawl_method": config.get("crawl_method", "static"),
        "schedule": config.get("schedule", "daily"),
        "is_enabled": is_enabled,
        "priority": config.get("priority", 2),
        "last_crawl_at": state.get("last_crawl_at"),
        "last_success_at": state.get("last_success_at"),
        "consecutive_failures": state.get("consecutive_failures", 0),
        "source_file": config.get("source_file"),
        "group": config.get("group"),
        "tags": tags,
        "crawler_class": config.get("crawler_class"),
        "dimension_name": config.get("dimension_name"),
        "dimension_description": config.get("dimension_description"),
        "health_status": health_status,
        "is_enabled_overridden": override is not None,
    }


def _filter_sources(
    items: list[dict[str, Any]],
    *,
    dimension: str | None = None,
    dimensions: str | None = None,
    group: str | None = None,
    groups: str | None = None,
    tag: str | None = None,
    tags: str | None = None,
    crawl_method: str | None = None,
    schedule: str | None = None,
    is_enabled: bool | None = None,
    health_status: str | None = None,
    health_statuses: str | None = None,
    keyword: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dimension_filters = _combine_filters(dimension, dimensions)
    group_filters = _combine_filters(group, groups)
    tag_filters = _combine_filters(tag, tags)
    health_filters = _combine_filters(health_status, health_statuses)
    method_filter = _normalize_text(crawl_method)
    schedule_filter = _normalize_text(schedule)
    keyword_filter = _normalize_text(keyword)

    filtered: list[dict[str, Any]] = []
    for item in items:
        item_dimension = _normalize_text(item.get("dimension"))
        item_group = _normalize_text(item.get("group"))
        item_method = _normalize_text(item.get("crawl_method"))
        item_schedule = _normalize_text(item.get("schedule"))
        item_health = _normalize_text(item.get("health_status"))
        item_tags = {_normalize_text(t) for t in item.get("tags", []) if _normalize_text(t)}

        if dimension_filters and item_dimension not in dimension_filters:
            continue
        if group_filters and item_group not in group_filters:
            continue
        if tag_filters and not (item_tags & tag_filters):
            continue
        if method_filter and item_method != method_filter:
            continue
        if schedule_filter and item_schedule != schedule_filter:
            continue
        if is_enabled is not None and item.get("is_enabled") is not is_enabled:
            continue
        if health_filters and item_health not in health_filters:
            continue
        if keyword_filter:
            haystack = " ".join(
                [
                    _normalize_text(item.get("id")),
                    _normalize_text(item.get("name")),
                    _normalize_text(item.get("url")),
                    _normalize_text(item.get("group")),
                    _normalize_text(item.get("dimension")),
                    _normalize_text(item.get("dimension_name")),
                    " ".join(item_tags),
                ]
            )
            if keyword_filter not in haystack:
                continue

        filtered.append(item)

    applied_filters: dict[str, Any] = {}
    if dimension_filters:
        applied_filters["dimensions"] = sorted(dimension_filters)
    if group_filters:
        applied_filters["groups"] = sorted(group_filters)
    if tag_filters:
        applied_filters["tags"] = sorted(tag_filters)
    if method_filter:
        applied_filters["crawl_method"] = method_filter
    if schedule_filter:
        applied_filters["schedule"] = schedule_filter
    if is_enabled is not None:
        applied_filters["is_enabled"] = is_enabled
    if health_filters:
        applied_filters["health_statuses"] = sorted(health_filters)
    if keyword_filter:
        applied_filters["keyword"] = keyword_filter

    return filtered, applied_filters


def _sort_sources(
    items: list[dict[str, Any]],
    sort_by: str = "dimension_priority",
    order: str = "asc",
) -> list[dict[str, Any]]:
    reverse = _normalize_text(order) == "desc"
    sort_key = _normalize_text(sort_by) or "dimension_priority"

    def default_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            _normalize_text(item.get("dimension")),
            int(item.get("priority", 2)),
            _normalize_text(item.get("name")),
            _normalize_text(item.get("id")),
        )

    if sort_key == "dimension_priority":
        return sorted(items, key=default_key, reverse=reverse)

    def extract_value(item: dict[str, Any]) -> tuple[int, Any]:
        value = item.get(sort_key)
        if value is None:
            return (1, "")
        if isinstance(value, bool):
            return (0, 1 if value else 0)
        if isinstance(value, (int, float)):
            return (0, value)
        return (0, _normalize_text(str(value)))

    return sorted(
        items,
        key=lambda s: (extract_value(s), _normalize_text(s.get("id"))),
        reverse=reverse,
    )


def _build_facets(items: list[dict[str, Any]]) -> dict[str, Any]:
    dim_counts: Counter[str] = Counter()
    dim_enabled: Counter[str] = Counter()
    dim_labels: dict[str, str | None] = {}
    group_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    method_counts: Counter[str] = Counter()
    schedule_counts: Counter[str] = Counter()
    health_counts: Counter[str] = Counter()

    for item in items:
        dim = str(item.get("dimension", ""))
        dim_counts[dim] += 1
        if item.get("is_enabled"):
            dim_enabled[dim] += 1
        if dim and item.get("dimension_name") and dim not in dim_labels:
            dim_labels[dim] = item.get("dimension_name")

        group = str(item.get("group", ""))
        if group:
            group_counts[group] += 1
        method = str(item.get("crawl_method", ""))
        if method:
            method_counts[method] += 1
        schedule = str(item.get("schedule", ""))
        if schedule:
            schedule_counts[schedule] += 1
        health = str(item.get("health_status", ""))
        if health:
            health_counts[health] += 1
        for tag in item.get("tags", []):
            if tag:
                tag_counts[str(tag)] += 1

    def to_facet(counter: Counter[str]) -> list[dict[str, Any]]:
        return [
            {"key": key, "count": count}
            for key, count in sorted(counter.items(), key=lambda x: (-x[1], x[0]))
        ]

    dimensions = []
    for key, count in sorted(dim_counts.items(), key=lambda x: (-x[1], x[0])):
        dimensions.append(
            {
                "key": key,
                "label": dim_labels.get(key),
                "count": count,
                "enabled_count": dim_enabled.get(key, 0),
            }
        )

    return {
        "dimensions": dimensions,
        "groups": to_facet(group_counts),
        "tags": to_facet(tag_counts),
        "crawl_methods": to_facet(method_counts),
        "schedules": to_facet(schedule_counts),
        "health_statuses": to_facet(health_counts),
    }


async def _load_merged_sources() -> list[dict[str, Any]]:
    configs = load_all_source_configs()
    states = await get_all_source_states()
    return [_merge_config_and_state(config, states) for config in configs]


async def list_sources(
    dimension: str | None = None,
    *,
    dimensions: str | None = None,
    group: str | None = None,
    groups: str | None = None,
    tag: str | None = None,
    tags: str | None = None,
    crawl_method: str | None = None,
    schedule: str | None = None,
    is_enabled: bool | None = None,
    health_status: str | None = None,
    health_statuses: str | None = None,
    keyword: str | None = None,
    sort_by: str = "dimension_priority",
    order: str = "asc",
) -> list[dict[str, Any]]:
    merged_sources = await _load_merged_sources()
    filtered, _ = _filter_sources(
        merged_sources,
        dimension=dimension,
        dimensions=dimensions,
        group=group,
        groups=groups,
        tag=tag,
        tags=tags,
        crawl_method=crawl_method,
        schedule=schedule,
        is_enabled=is_enabled,
        health_status=health_status,
        health_statuses=health_statuses,
        keyword=keyword,
    )
    return _sort_sources(filtered, sort_by=sort_by, order=order)


async def list_source_facets(
    dimension: str | None = None,
    *,
    dimensions: str | None = None,
    group: str | None = None,
    groups: str | None = None,
    tag: str | None = None,
    tags: str | None = None,
    crawl_method: str | None = None,
    schedule: str | None = None,
    is_enabled: bool | None = None,
    health_status: str | None = None,
    health_statuses: str | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    merged_sources = await _load_merged_sources()
    filtered, _ = _filter_sources(
        merged_sources,
        dimension=dimension,
        dimensions=dimensions,
        group=group,
        groups=groups,
        tag=tag,
        tags=tags,
        crawl_method=crawl_method,
        schedule=schedule,
        is_enabled=is_enabled,
        health_status=health_status,
        health_statuses=health_statuses,
        keyword=keyword,
    )
    return _build_facets(filtered)


async def list_sources_catalog(
    dimension: str | None = None,
    *,
    dimensions: str | None = None,
    group: str | None = None,
    groups: str | None = None,
    tag: str | None = None,
    tags: str | None = None,
    crawl_method: str | None = None,
    schedule: str | None = None,
    is_enabled: bool | None = None,
    health_status: str | None = None,
    health_statuses: str | None = None,
    keyword: str | None = None,
    sort_by: str = "dimension_priority",
    order: str = "asc",
    page: int = 1,
    page_size: int = 100,
    include_facets: bool = True,
) -> dict[str, Any]:
    merged_sources = await _load_merged_sources()
    total_sources = len(merged_sources)
    filtered, applied_filters = _filter_sources(
        merged_sources,
        dimension=dimension,
        dimensions=dimensions,
        group=group,
        groups=groups,
        tag=tag,
        tags=tags,
        crawl_method=crawl_method,
        schedule=schedule,
        is_enabled=is_enabled,
        health_status=health_status,
        health_statuses=health_statuses,
        keyword=keyword,
    )
    sorted_items = _sort_sources(filtered, sort_by=sort_by, order=order)

    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 500))
    total_filtered = len(sorted_items)
    total_pages = max(1, math.ceil(total_filtered / safe_page_size))
    if safe_page > total_pages:
        safe_page = total_pages
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    page_items = sorted_items[start:end]

    return {
        "generated_at": datetime.now(timezone.utc),
        "total_sources": total_sources,
        "filtered_sources": total_filtered,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": total_pages,
        "items": page_items,
        "facets": _build_facets(sorted_items) if include_facets else None,
        "applied_filters": applied_filters,
    }


async def get_source(source_id: str) -> dict[str, Any] | None:
    configs = load_all_source_configs()
    config = next((c for c in configs if c["id"] == source_id), None)
    if config is None:
        return None
    states = await get_all_source_states()
    return _merge_config_and_state(config, states)


async def update_source(source_id: str, is_enabled: bool) -> dict[str, Any] | None:
    configs = load_all_source_configs()
    config = next((c for c in configs if c["id"] == source_id), None)
    if config is None:
        return None
    await set_enabled_override(source_id, is_enabled)
    states = await get_all_source_states()
    return _merge_config_and_state(config, states)
