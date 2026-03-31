"""Project taxonomy service for managing the category-tag tree."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.schemas.project import (
    ProjectTaxonomyCategory,
    ProjectTaxonomySubCategory,
    ProjectTaxonomyTree,
)

TAXONOMY_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "project_taxonomy.yaml"
)


def load_taxonomy() -> dict[str, Any]:
    """Load project taxonomy configuration from YAML file."""
    if not TAXONOMY_CONFIG_PATH.exists():
        return {"taxonomy": [], "default_mapping": {}}

    with open(TAXONOMY_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_taxonomy_tree() -> ProjectTaxonomyTree:
    """Return the full 2-level project taxonomy tree."""
    config = load_taxonomy()
    raw_items = config.get("taxonomy", [])

    items: list[ProjectTaxonomyCategory] = []
    total_l2 = 0
    for raw in raw_items:
        children = [
            ProjectTaxonomySubCategory(
                id=str(c.get("id") or ""),
                name=str(c.get("name") or ""),
                sort_order=int(c.get("sort_order") or 0),
            )
            for c in (raw.get("children") or [])
        ]
        total_l2 += len(children)
        items.append(
            ProjectTaxonomyCategory(
                id=str(raw.get("id") or ""),
                name=str(raw.get("name") or ""),
                sort_order=int(raw.get("sort_order") or 0),
                children=children,
            )
        )

    return ProjectTaxonomyTree(
        total_l1=len(items),
        total_l2=total_l2,
        items=items,
    )


def get_default_mapping() -> dict[str, str]:
    """Get default category/subcategory mapping for initial data fill."""
    config = load_taxonomy()
    return config.get("default_mapping", {})
