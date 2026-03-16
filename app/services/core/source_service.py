from __future__ import annotations

from typing import Any

from app.scheduler.manager import load_all_source_configs
from app.services.stores.source_state import (
    get_all_source_states,
    set_enabled_override,
)


def _merge_config_and_state(
    config: dict[str, Any], states: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Merge YAML config with runtime state from source_state.json."""
    source_id = config["id"]
    state = states.get(source_id, {})

    # is_enabled: override takes precedence over YAML
    override = state.get("is_enabled_override")
    is_enabled = override if override is not None else config.get("is_enabled", True)

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
    }


async def list_sources(dimension: str | None = None) -> list[dict[str, Any]]:
    configs = load_all_source_configs()
    states = await get_all_source_states()

    results = []
    for config in configs:
        if dimension and config.get("dimension") != dimension:
            continue
        results.append(_merge_config_and_state(config, states))

    results.sort(key=lambda s: (s["dimension"], s["priority"]))
    return results


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
