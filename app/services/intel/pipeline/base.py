"""Shared pipeline utilities — hash tracking, JSON output."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class HashTracker:
    """Incremental processing tracker using a JSON file of url_hashes.

    Usage::

        tracker = HashTracker(PROCESSED_DIR / "_processed_hashes.json", PROCESSED_DIR)
        processed = tracker.load()
        ...
        tracker.save(processed)
    """

    def __init__(self, hashes_file: Path, processed_dir: Path) -> None:
        self._hashes_file = hashes_file
        self._processed_dir = processed_dir

    def load(self) -> set[str]:
        if not self._hashes_file.exists():
            return set()
        try:
            with open(self._hashes_file, encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("hashes", []))
        except (json.JSONDecodeError, OSError):
            return set()

    def save(self, hashes: set[str]) -> None:
        self._processed_dir.mkdir(parents=True, exist_ok=True)
        with open(self._hashes_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "hashes": sorted(hashes),
                    "last_run": datetime.now(timezone.utc).isoformat(),
                },
                f, ensure_ascii=False, indent=2,
            )


def save_output_json(
    processed_dir: Path,
    filename: str,
    items: list[Any],
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write standard intel output JSON file.

    Output format::

        {"generated_at": "...", "item_count": N, "items": [...], ...extra}
    """
    processed_dir.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "generated_at": now_iso,
        "item_count": len(items),
        "items": items,
    }
    if extra:
        payload.update(extra)

    with open(processed_dir / filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
