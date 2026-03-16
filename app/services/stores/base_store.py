"""Base class for thread-safe JSON file stores."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class BaseJSONStore:
    """Thread-safe JSON file store with atomic writes and error-resilient reads.

    Subclasses implement business logic as methods, using ``_load`` / ``_save``
    for all file I/O and ``_lock`` for serialisation.
    """

    def __init__(self, file_path: Path) -> None:
        self._file = file_path
        self._lock = Lock()

    def _load(self) -> dict[str, Any] | list[Any]:
        """Load JSON data from file. Returns empty dict on missing or corrupt file."""
        if not self._file.exists():
            return {}
        try:
            with open(self._file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupted %s, starting fresh: %s", self._file.name, exc)
            return {}

    def _save(self, data: dict[str, Any] | list[Any]) -> None:
        """Atomically write *data* to the file via a temporary file."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        tmp.replace(self._file)
