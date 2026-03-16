"""Thread-safe store for user-managed faculty annotations.

Annotations overlay crawled ScholarRecord data without modifying the raw JSON files.
Storage: data/state/scholar_annotations.json

Format:
{
  "{url_hash}": {
    "is_advisor_committee": bool,
    "is_adjunct_supervisor": bool,
    "supervised_students": list[str],
    "joint_research_projects": list[str],
    "joint_management_roles": list[str],
    "academic_exchange_records": list[str],
    "is_potential_recruit": bool,
    "institute_relation_notes": str,
    "relation_updated_by": str,
    "relation_updated_at": str,   // ISO8601
    "user_updates": [
      { update_type, title, content, source_url, published_at, added_by, created_at }
    ]
  }
}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import BASE_DIR
from app.services.stores.base_store import BaseJSONStore

logger = logging.getLogger(__name__)

ANNOTATIONS_FILE = BASE_DIR / "data" / "state" / "scholar_annotations.json"

_RELATION_FIELDS: frozenset[str] = frozenset({
    "is_advisor_committee",
    "adjunct_supervisor",
    "supervised_students",
    "joint_research_projects",
    "joint_management_roles",
    "academic_exchange_records",
    "is_potential_recruit",
    "institute_relation_notes",
    "relation_updated_by",
})

_ACHIEVEMENT_FIELDS: frozenset[str] = frozenset({
    "representative_publications",
    "patents",
    "awards",
    "h_index",
    "citations_count",
    "publications_count",
})


class FacultyAnnotationStore(BaseJSONStore):
    """Store for user-managed faculty relation and achievement annotations."""

    def get_annotation(self, url_hash: str) -> dict[str, Any]:
        """Return the annotation dict for a faculty member, or {} if none exists."""
        with self._lock:
            data = self._load()
        return data.get(url_hash, {})

    def update_relation(self, url_hash: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge *updates* into the institute-relation section of the annotation.

        Auto-sets relation_updated_at to current UTC time.
        Returns the updated annotation dict.
        """
        with self._lock:
            data = self._load()
            ann = data.setdefault(url_hash, {})
            for key, val in updates.items():
                if key in _RELATION_FIELDS and val is not None:
                    ann[key] = val
            ann["relation_updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(data)
        return ann

    def add_user_update(self, url_hash: str, update: dict[str, Any]) -> dict[str, Any]:
        """Append a user-authored dynamic update entry.

        Returns the updated annotation dict.
        """
        with self._lock:
            data = self._load()
            ann = data.setdefault(url_hash, {})
            user_updates = ann.setdefault("user_updates", [])
            entry = {
                "update_type": update.get("update_type", "other"),
                "title": update.get("title", ""),
                "content": update.get("content", ""),
                "source_url": update.get("source_url", ""),
                "published_at": update.get("published_at", ""),
                "added_by": f"user:{update.get('added_by', 'unknown')}",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            user_updates.append(entry)
            self._save(data)
        return ann

    def delete_user_update(self, url_hash: str, update_idx: int) -> dict[str, Any] | None:
        """Delete a user-authored dynamic update by index in the user_updates list.

        Returns:
            Updated annotation dict, or None if url_hash not found.
        Raises:
            ValueError if index is out of range.
            PermissionError if the entry is crawler-generated.
        """
        with self._lock:
            data = self._load()
            if url_hash not in data:
                return None
            ann = data[url_hash]
            user_updates = ann.get("user_updates", [])
            n = len(user_updates)
            if update_idx < 0 or update_idx >= n:
                raise ValueError(
                    f"Index {update_idx} out of range (user_updates has {n} entries)"
                )
            entry = user_updates[update_idx]
            if not entry.get("added_by", "").startswith("user:"):
                raise PermissionError("Cannot delete crawler-generated dynamic updates")
            user_updates.pop(update_idx)
            ann["user_updates"] = user_updates
            self._save(data)
        return ann

    def update_achievements(self, url_hash: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Update user-managed academic achievement fields.

        Each field is replaced entirely when provided (not merged). Fields not in *updates*
        are left unchanged. Auto-sets achievements_updated_at to current UTC time.
        """
        with self._lock:
            data = self._load()
            ann = data.setdefault(url_hash, {})
            for key, val in updates.items():
                if key in _ACHIEVEMENT_FIELDS and val is not None:
                    ann[key] = val
            ann["achievements_updated_by"] = f"user:{updates.get('updated_by', 'unknown')}"
            ann["achievements_updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(data)
        return ann

    def delete_all_for_faculty(self, url_hash: str) -> None:
        """Delete all annotations for a faculty member (called when faculty is deleted).

        Thread-safe with locking.
        """
        with self._lock:
            data = self._load()
            if url_hash in data:
                del data[url_hash]
                self._save(data)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store = FacultyAnnotationStore(ANNOTATIONS_FILE)


# ---------------------------------------------------------------------------
# Backward-compatible module-level functions
# ---------------------------------------------------------------------------


def _load() -> dict[str, dict[str, Any]]:
    """Internal helper — used by scholar_service for a single bulk read."""
    return _store._load()


def get_annotation(url_hash: str) -> dict[str, Any]:
    return _store.get_annotation(url_hash)


def update_relation(url_hash: str, updates: dict[str, Any]) -> dict[str, Any]:
    return _store.update_relation(url_hash, updates)


def add_user_update(url_hash: str, update: dict[str, Any]) -> dict[str, Any]:
    return _store.add_user_update(url_hash, update)


def delete_user_update(url_hash: str, update_idx: int) -> dict[str, Any] | None:
    return _store.delete_user_update(url_hash, update_idx)


def update_achievements(url_hash: str, updates: dict[str, Any]) -> dict[str, Any]:
    return _store.update_achievements(url_hash, updates)


def delete_all_for_faculty(url_hash: str) -> None:
    return _store.delete_all_for_faculty(url_hash)
