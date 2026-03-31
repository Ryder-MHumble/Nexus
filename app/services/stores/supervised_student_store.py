"""DB-first supervised student store with JSON fallback.

Primary storage is `supervised_students` table.
Fallback storage remains `data/state/supervised_students.json` for resilience.
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
    "major",
    "degree_type",
    "enrollment_year",
    "expected_graduation_year",
    "status",
    "email",
    "phone",
    "notes",
    "mentor_name",
})


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_added_by(raw_added_by: Any) -> str:
    token = _clean_text(raw_added_by)
    if not token:
        return "user:unknown"
    if token.startswith("user:"):
        return token
    return f"user:{token}"


def _to_year(value: Any) -> int | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        year = int(float(text))
    except ValueError:
        return None
    if year < 1900 or year > 2100:
        return None
    return year


def _normalize_db_row(row: dict[str, Any]) -> dict[str, Any]:
    def _iso(v: Any) -> str:
        if v is None:
            return ""
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return _clean_text(v)

    enrollment_year = row.get("enrollment_year")
    expected_graduation_year = row.get("expected_graduation_year")
    return {
        "id": _clean_text(row.get("id")),
        "student_no": _clean_text(row.get("student_no")),
        "name": _clean_text(row.get("name")),
        "home_university": _clean_text(row.get("home_university")),
        "major": _clean_text(row.get("major")),
        "degree_type": _clean_text(row.get("degree_type")),
        "enrollment_year": "" if enrollment_year is None else str(enrollment_year),
        "expected_graduation_year": "" if expected_graduation_year is None else str(expected_graduation_year),
        "status": _clean_text(row.get("status")) or "在读",
        "email": _clean_text(row.get("email")),
        "phone": _clean_text(row.get("phone")),
        "notes": _clean_text(row.get("notes")),
        "mentor_name": _clean_text(row.get("mentor_name")),
        "added_by": _normalize_added_by(row.get("added_by")),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


class _FallbackJSONStore(BaseJSONStore):
    """Fallback local JSON store for supervised students."""

    def list_students(self, faculty_url_hash: str) -> list[dict[str, Any]]:
        with self._lock:
            data = self._load()
        return data.get(faculty_url_hash, [])

    def get_student(self, faculty_url_hash: str, student_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._load()
        for student in data.get(faculty_url_hash, []):
            if student.get("id") == student_id:
                return student
        return None

    def add_student(self, faculty_url_hash: str, data_in: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        record: dict[str, Any] = {
            "id": str(uuid4()),
            "student_no": _clean_text(data_in.get("student_no")),
            "name": _clean_text(data_in.get("name")),
            "home_university": _clean_text(data_in.get("home_university")),
            "major": _clean_text(data_in.get("major")),
            "degree_type": _clean_text(data_in.get("degree_type")),
            "enrollment_year": _clean_text(data_in.get("enrollment_year")),
            "expected_graduation_year": _clean_text(data_in.get("expected_graduation_year")),
            "status": _clean_text(data_in.get("status")) or "在读",
            "email": _clean_text(data_in.get("email")),
            "phone": _clean_text(data_in.get("phone")),
            "notes": _clean_text(data_in.get("notes")),
            "mentor_name": _clean_text(data_in.get("mentor_name")),
            "added_by": _normalize_added_by(data_in.get("added_by")),
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            data = self._load()
            data.setdefault(faculty_url_hash, []).append(record)
            self._save(data)
        return record

    def update_student(self, faculty_url_hash: str, student_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            data = self._load()
            for student in data.get(faculty_url_hash, []):
                if student.get("id") == student_id:
                    for key, val in updates.items():
                        if key in _MUTABLE_FIELDS and val is not None:
                            student[key] = _clean_text(val)
                    student["updated_at"] = datetime.now(timezone.utc).isoformat()
                    self._save(data)
                    return student
        return None

    def delete_student(self, faculty_url_hash: str, student_id: str) -> bool:
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
        with self._lock:
            data = self._load()
        return len(data.get(faculty_url_hash, []))

    def delete_all_students(self, faculty_url_hash: str) -> None:
        with self._lock:
            data = self._load()
            if faculty_url_hash in data:
                del data[faculty_url_hash]
                self._save(data)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_fallback_store = _FallbackJSONStore(STUDENTS_FILE)


# ---------------------------------------------------------------------------
# Public async CRUD (DB-first)
# ---------------------------------------------------------------------------


async def list_students(faculty_url_hash: str) -> list[dict[str, Any]]:
    try:
        from app.db.client import get_client  # noqa: PLC0415

        client = get_client()
        res = (
            await client.table("supervised_students")
            .select("*")
            .eq("scholar_id", faculty_url_hash)
            .order("enrollment_year", desc=True)
            .order("created_at", desc=True)
            .execute()
        )
        return [_normalize_db_row(dict(row)) for row in (res.data or [])]
    except Exception as exc:
        logger.warning("DB list_students failed, fallback to JSON store: %s", exc)
        return _fallback_store.list_students(faculty_url_hash)


async def get_student(faculty_url_hash: str, student_id: str) -> dict[str, Any] | None:
    try:
        from app.db.client import get_client  # noqa: PLC0415

        client = get_client()
        res = (
            await client.table("supervised_students")
            .select("*")
            .eq("scholar_id", faculty_url_hash)
            .eq("id", student_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        return _normalize_db_row(dict(res.data[0]))
    except Exception as exc:
        logger.warning("DB get_student failed, fallback to JSON store: %s", exc)
        return _fallback_store.get_student(faculty_url_hash, student_id)


async def add_student(faculty_url_hash: str, data_in: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.db.client import get_client  # noqa: PLC0415

        client = get_client()
        payload = {
            "scholar_id": faculty_url_hash,
            "student_no": _clean_text(data_in.get("student_no")) or None,
            "name": _clean_text(data_in.get("name")),
            "home_university": _clean_text(data_in.get("home_university")) or None,
            "major": _clean_text(data_in.get("major")) or None,
            "degree_type": _clean_text(data_in.get("degree_type")) or None,
            "enrollment_year": _to_year(data_in.get("enrollment_year")),
            "expected_graduation_year": _to_year(data_in.get("expected_graduation_year")),
            "status": _clean_text(data_in.get("status")) or "在读",
            "email": _clean_text(data_in.get("email")) or None,
            "phone": _clean_text(data_in.get("phone")) or None,
            "notes": _clean_text(data_in.get("notes")) or None,
            "mentor_name": _clean_text(data_in.get("mentor_name")) or None,
            "added_by": _normalize_added_by(data_in.get("added_by")),
        }
        res = await client.table("supervised_students").insert(payload).execute()
        if res.data:
            return _normalize_db_row(dict(res.data[0]))

        # Defensive fallback if insert doesn't return rows.
        rows = await list_students(faculty_url_hash)
        if rows:
            return rows[0]
    except Exception as exc:
        logger.warning("DB add_student failed, fallback to JSON store: %s", exc)
    return _fallback_store.add_student(faculty_url_hash, data_in)


async def update_student(
    faculty_url_hash: str,
    student_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        from app.db.client import get_client  # noqa: PLC0415

        client = get_client()
        patch: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        for key, val in updates.items():
            if key not in _MUTABLE_FIELDS or val is None:
                continue
            if key in {"enrollment_year", "expected_graduation_year"}:
                patch[key] = _to_year(val)
            else:
                patch[key] = _clean_text(val)
        res = (
            await client.table("supervised_students")
            .update(patch)
            .eq("scholar_id", faculty_url_hash)
            .eq("id", student_id)
            .execute()
        )
        if not res.data:
            return None
        return _normalize_db_row(dict(res.data[0]))
    except Exception as exc:
        logger.warning("DB update_student failed, fallback to JSON store: %s", exc)
        return _fallback_store.update_student(faculty_url_hash, student_id, updates)


async def delete_student(faculty_url_hash: str, student_id: str) -> bool:
    try:
        from app.db.client import get_client  # noqa: PLC0415

        client = get_client()
        res = (
            await client.table("supervised_students")
            .delete()
            .eq("scholar_id", faculty_url_hash)
            .eq("id", student_id)
            .execute()
        )
        return bool(res.data)
    except Exception as exc:
        logger.warning("DB delete_student failed, fallback to JSON store: %s", exc)
        return _fallback_store.delete_student(faculty_url_hash, student_id)


async def count_students(faculty_url_hash: str) -> int:
    try:
        from app.db.client import get_client  # noqa: PLC0415

        client = get_client()
        res = (
            await client.table("supervised_students")
            .select("id", count="exact")
            .eq("scholar_id", faculty_url_hash)
            .limit(1)
            .execute()
        )
        if res.count is not None:
            return int(res.count)
        return len(res.data or [])
    except Exception as exc:
        logger.warning("DB count_students failed, fallback to JSON store: %s", exc)
        return _fallback_store.count_students(faculty_url_hash)


async def delete_all_students(faculty_url_hash: str) -> None:
    try:
        from app.db.client import get_client  # noqa: PLC0415

        client = get_client()
        await client.table("supervised_students").delete().eq("scholar_id", faculty_url_hash).execute()
        return None
    except Exception as exc:
        logger.warning("DB delete_all_students failed, fallback to JSON store: %s", exc)
        _fallback_store.delete_all_students(faculty_url_hash)
