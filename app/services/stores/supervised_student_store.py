"""Thread-safe store for supervised student records.

Each faculty member (identified by url_hash) can have a list of students.
Storage: data/state/supervised_students.json

Format:
{
  "{faculty_url_hash}": [
    {
      "id": "uuid4-string",
      "student_no": "240101003",
      "name": "何雨桐",
      "home_university": "北京大学",
      "degree_type": "博士",
      "enrollment_year": "2024",
      "expected_graduation_year": "2027",
      "status": "在读",
      "email": "",
      "phone": "",
      "notes": "",
      "added_by": "user:admin",
      "created_at": "2026-03-02T10:00:00+00:00",
      "updated_at": "2026-03-02T10:00:00+00:00"
    }
  ]
}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import BASE_DIR
from app.services.stores.base_store import BaseJSONStore

logger = logging.getLogger(__name__)

STUDENTS_FILE = BASE_DIR / "data" / "state" / "supervised_students.json"

_MUTABLE_FIELDS: frozenset[str] = frozenset({
    "student_no",
    "name",
    "home_university",
    "degree_type",
    "enrollment_year",
    "expected_graduation_year",
    "status",
    "email",
    "phone",
    "notes",
})


class SupervisedStudentStore(BaseJSONStore):
    """Store for supervised student records per faculty member."""

    def list_students(self, faculty_url_hash: str) -> list[dict[str, Any]]:
        """Return all student records for a faculty member, or [] if none."""
        with self._lock:
            data = self._load()
        return data.get(faculty_url_hash, [])

    def get_student(self, faculty_url_hash: str, student_id: str) -> dict[str, Any] | None:
        """Return a single student record by id, or None if not found."""
        with self._lock:
            data = self._load()
        for student in data.get(faculty_url_hash, []):
            if student.get("id") == student_id:
                return student
        return None

    def add_student(self, faculty_url_hash: str, data_in: dict[str, Any]) -> dict[str, Any]:
        """Append a new student record and return it.

        Generates server-side id, created_at, updated_at.
        Normalises added_by to 'user:{username}'.
        """
        now = datetime.now(timezone.utc).isoformat()
        raw_added_by = data_in.get("added_by", "")
        record: dict[str, Any] = {
            "id": str(uuid4()),
            "student_no": data_in.get("student_no", ""),
            "name": data_in.get("name", ""),
            "home_university": data_in.get("home_university", ""),
            "degree_type": data_in.get("degree_type", ""),
            "enrollment_year": data_in.get("enrollment_year", ""),
            "expected_graduation_year": data_in.get("expected_graduation_year", ""),
            "status": data_in.get("status", "在读"),
            "email": data_in.get("email", ""),
            "phone": data_in.get("phone", ""),
            "notes": data_in.get("notes", ""),
            "added_by": f"user:{raw_added_by}" if raw_added_by else "user:unknown",
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            data = self._load()
            data.setdefault(faculty_url_hash, []).append(record)
            self._save(data)
        return record

    def update_student(
        self,
        faculty_url_hash: str,
        student_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Apply partial updates to a student record.

        Returns the updated record, or None if not found.
        Only whitelisted mutable fields are applied; 'updated_at' is auto-set.
        """
        with self._lock:
            data = self._load()
            for student in data.get(faculty_url_hash, []):
                if student.get("id") == student_id:
                    for key, val in updates.items():
                        if key in _MUTABLE_FIELDS and val is not None:
                            student[key] = val
                    student["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self._save(data)
                    return student
        return None

    def delete_student(self, faculty_url_hash: str, student_id: str) -> bool:
        """Delete a student record by id. Returns True if deleted, False if not found."""
        with self._lock:
            data = self._load()
            students = data.get(faculty_url_hash, [])
            new_list = [s for s in students if s.get("id") != student_id]
            if len(new_list) == len(students):
                return False
            data[faculty_url_hash] = new_list
            self._save(data)
        return True

    def count_students(self, faculty_url_hash: str) -> int:
        """Return the number of students for a faculty member."""
        with self._lock:
            data = self._load()
        return len(data.get(faculty_url_hash, []))

    def delete_all_students(self, faculty_url_hash: str) -> None:
        """Delete all student records for a faculty member (called when faculty is deleted).

        Thread-safe with locking.
        """
        with self._lock:
            data = self._load()
            if faculty_url_hash in data:
                del data[faculty_url_hash]
                self._save(data)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store = SupervisedStudentStore(STUDENTS_FILE)


# ---------------------------------------------------------------------------
# Backward-compatible module-level functions
# ---------------------------------------------------------------------------


def list_students(faculty_url_hash: str) -> list[dict[str, Any]]:
    return _store.list_students(faculty_url_hash)


def get_student(faculty_url_hash: str, student_id: str) -> dict[str, Any] | None:
    return _store.get_student(faculty_url_hash, student_id)


def add_student(faculty_url_hash: str, data_in: dict[str, Any]) -> dict[str, Any]:
    return _store.add_student(faculty_url_hash, data_in)


def update_student(
    faculty_url_hash: str,
    student_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    return _store.update_student(faculty_url_hash, student_id, updates)


def delete_student(faculty_url_hash: str, student_id: str) -> bool:
    return _store.delete_student(faculty_url_hash, student_id)


def count_students(faculty_url_hash: str) -> int:
    return _store.count_students(faculty_url_hash)


def delete_all_students(faculty_url_hash: str) -> None:
    return _store.delete_all_students(faculty_url_hash)
