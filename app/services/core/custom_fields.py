"""Shared utility for custom_fields merge logic."""
from __future__ import annotations

from typing import Any


def merge_custom_fields(
    existing: dict[str, str], incoming: dict[str, str | None],
) -> dict[str, str]:
    """Shallow-merge custom fields: incoming keys override, null values delete.

    Args:
        existing: Current custom_fields from DB (or {}).
        incoming: User-provided updates. Keys with None value are deleted.

    Returns:
        Merged dict with null-valued keys removed.
    """
    merged = {**existing}
    for k, v in incoming.items():
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = v
    return merged


def apply_custom_fields_update(updates: dict[str, Any], current_row: dict[str, Any]) -> None:
    """If updates contains 'custom_fields', merge it with the existing value in-place.

    Modifies `updates['custom_fields']` to the final merged dict ready for DB write.
    """
    if "custom_fields" not in updates:
        return
    existing = current_row.get("custom_fields") or {}
    updates["custom_fields"] = merge_custom_fields(existing, updates["custom_fields"])
