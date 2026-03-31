"""Event taxonomy service for managing the 3-level category structure."""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

# Load taxonomy configuration
TAXONOMY_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "event_taxonomy.yaml"


def load_taxonomy() -> dict[str, Any]:
    """Load taxonomy configuration from YAML file."""
    if not TAXONOMY_CONFIG_PATH.exists():
        return {"taxonomy": [], "default_mapping": {}}

    with open(TAXONOMY_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_taxonomy_tree() -> list[dict[str, Any]]:
    """
    Get the full taxonomy tree structure.

    Returns:
        List of L1 categories with nested L2 series.
    """
    config = load_taxonomy()
    return config.get("taxonomy", [])


def get_all_categories() -> list[str]:
    """Get all L1 category names."""
    tree = get_taxonomy_tree()
    return [node["name"] for node in tree]


def get_series_by_category(category: str) -> list[str]:
    """Get all L2 series names under a given L1 category."""
    tree = get_taxonomy_tree()
    for node in tree:
        if node["name"] == category:
            return [child["name"] for child in node.get("children", [])]
    return []


def validate_category_series(category: str, series: str) -> bool:
    """
    Validate if a category-series combination is valid.

    Args:
        category: L1 category name
        series: L2 series name

    Returns:
        True if valid, False otherwise
    """
    valid_series = get_series_by_category(category)
    return series in valid_series


def get_default_mapping() -> dict[str, str]:
    """Get default category-series mapping for data migration."""
    config = load_taxonomy()
    return config.get("default_mapping", {})


def get_taxonomy_stats() -> dict[str, Any]:
    """
    Get statistics about the taxonomy structure.

    Returns:
        Dict with counts of L1, L2 categories and the full tree.
    """
    tree = get_taxonomy_tree()
    l1_count = len(tree)
    l2_count = sum(len(node.get("children", [])) for node in tree)

    return {
        "total_l1": l1_count,
        "total_l2": l2_count,
        "tree": tree,
    }
