"""Institution data builder — generates institutions.json from scholars.json."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.scheduler.manager import load_all_source_configs
from app.services.stores.source_state import get_all_source_states


def _normalize_university_id(name: str) -> str:
    """Normalize university name to ID (e.g., '清华大学' → 'tsinghua')."""
    mapping = {
        "清华大学": "tsinghua",
        "北京大学": "pku",
        "南京大学": "nju",
        "浙江大学": "zju",
        "中国科学院": "cas",
        "中国科学院大学": "cas",
        "复旦大学": "fudan",
        "中国人民大学": "ruc",
        "上海交通大学": "sjtu",
        "中国科学技术大学": "ustc",
    }
    return mapping.get(name, name.lower().replace(" ", "_"))


def _normalize_department_id(university_id: str, dept_name: str) -> str:
    """Normalize department name to ID."""
    dept_normalized = dept_name.lower().replace(" ", "_").replace("、", "_")
    return f"{university_id}_{dept_normalized}"


def _load_scholars_from_unified_json() -> list[dict[str, Any]]:
    """Load all scholars from data/scholars/scholars.json.

    Returns:
        List of scholar dictionaries with university and department fields.
    """
    scholars_file = Path("data/scholars/scholars.json")
    if not scholars_file.exists():
        return []

    try:
        with open(scholars_file, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("scholars", [])
    except (json.JSONDecodeError, OSError):
        return []


def build_institutions_data() -> dict[str, Any]:
    """Build institutions data from scholars.json.

    IMPORTANT: This function reads from data/scholars/scholars.json (unified scholar database)
    and groups scholars by university and department. It merges with existing institutions.json
    to preserve manually added fields (category, priority, student_count, etc.)

    Returns:
        Dictionary with structure:
        {
            "last_updated": "ISO timestamp",
            "universities": [
                {
                    "id": "tsinghua",
                    "name": "清华大学",
                    "scholar_count": 156,
                    "departments": [...],
                    # ... other fields preserved from existing data
                }
            ]
        }
    """
    # Load existing institutions.json if it exists
    existing_data = {}
    existing_events: list = []
    institutions_file = Path("data/scholars/institutions.json")
    if institutions_file.exists():
        try:
            with open(institutions_file, encoding="utf-8") as f:
                existing_json = json.load(f)
                # Build lookup by university name
                for uni in existing_json.get("universities", []):
                    existing_data[uni["name"]] = uni
                # Preserve events data
                existing_events = existing_json.get("events", [])
        except (json.JSONDecodeError, OSError):
            pass

    # Load all scholars from unified JSON
    scholars = _load_scholars_from_unified_json()

    # Group scholars by (university, department)
    uni_dept_scholars: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for scholar in scholars:
        university = (scholar.get("university") or "").strip()
        department = (scholar.get("department") or "").strip()

        if not university:
            continue

        # Use "未分类" for scholars without department
        if not department:
            department = "未分类"

        key = (university, department)
        uni_dept_scholars[key].append(scholar)

    # Build universities structure
    universities_by_name: dict[str, dict[str, Any]] = {}

    for (university_name, dept_name), dept_scholars in sorted(uni_dept_scholars.items()):
        if university_name not in universities_by_name:
            # Start with existing data if available
            if university_name in existing_data:
                universities_by_name[university_name] = existing_data[university_name].copy()
                universities_by_name[university_name]["scholar_count"] = 0
                universities_by_name[university_name]["departments"] = {}
            else:
                universities_by_name[university_name] = {
                    "id": _normalize_university_id(university_name),
                    "name": university_name,
                    "org_name": None,
                    "scholar_count": 0,
                    "departments": {},
                }

        uni_data = universities_by_name[university_name]
        dept_id = _normalize_department_id(uni_data["id"], dept_name)

        # Count scholars in this department
        dept_scholar_count = len(dept_scholars)

        # Find source info from YAML configs (if available)
        configs = load_all_source_configs()
        states = get_all_source_states()
        scholar_configs = [c for c in configs if c.get("dimension") == "scholars"]

        source_items = []
        for cfg in scholar_configs:
            if cfg.get("university") == university_name and cfg.get("department") == dept_name:
                source_id = cfg.get("id", "")
                state = states.get(source_id, {})

                # Determine if enabled
                override = state.get("is_enabled_override")
                is_enabled = override if override is not None else cfg.get("is_enabled", True)

                source_items.append(
                    {
                        "source_id": source_id,
                        "source_name": cfg.get("name", source_id),
                        "scholar_count": dept_scholar_count,  # Use actual count from scholars.json
                        "is_enabled": is_enabled,
                        "last_crawl_at": state.get("last_crawl_at"),
                    }
                )

        # If no YAML source found, create a placeholder
        if not source_items:
            source_items.append(
                {
                    "source_id": f"manual_{uni_data['id']}_{dept_id}",
                    "source_name": f"{university_name}-{dept_name}",
                    "scholar_count": dept_scholar_count,
                    "is_enabled": True,
                    "last_crawl_at": None,
                }
            )

        uni_data["departments"][dept_id] = {
            "id": dept_id,
            "name": dept_name,
            "scholar_count": dept_scholar_count,
            "sources": source_items,
            "org_name": None,  # Will be filled by AMiner enrichment
        }

        uni_data["scholar_count"] += dept_scholar_count

    # Convert to list format
    universities = []
    for uni_data in universities_by_name.values():
        uni_data["departments"] = list(uni_data["departments"].values())
        universities.append(uni_data)

    # Add universities from existing data that don't have scholars
    for uni_name, uni_data in existing_data.items():
        if uni_name not in universities_by_name:
            universities.append(uni_data)

    result: dict[str, Any] = {
        "last_updated": datetime.now(UTC).isoformat(),
        "universities": sorted(universities, key=lambda u: u["name"]),
    }
    # Preserve events so that rebuild_institutions.py doesn't wipe event data
    if existing_events:
        result["events"] = existing_events
    return result


def save_institutions_data(data: dict[str, Any] | None = None) -> Path:
    """Build and save institutions.json.

    Args:
        data: Pre-built institutions data. If None, builds from scratch.

    Returns:
        Path to saved institutions.json
    """
    if data is None:
        data = build_institutions_data()

    output_path = Path("data/scholars/institutions.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return output_path
