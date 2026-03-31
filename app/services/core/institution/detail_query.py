"""Detail query logic for individual institutions.

Fetches and builds detailed information for a single institution.
"""

from __future__ import annotations

from app.db.pool import get_pool
from app.schemas.institution import InstitutionDetailResponse
from app.services.core.institution.detail_builder import build_detail_response
from app.services.core.institution.storage import fetch_all_institutions, fetch_institution_by_id


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


async def _load_student_metrics_for_institution(
    institution_name: str,
    *,
    org_name: str | None = None,
) -> dict[str, object]:
    pool = get_pool()
    names = [_normalize_text(institution_name), _normalize_text(org_name)]
    names = [name for name in names if name]

    if not names:
        return {
            "student_count_24": 0,
            "student_count_25": 0,
            "student_counts_by_year": {},
            "student_count_total": 0,
        }

    async def _query_year_counts(
        where_sql: str,
        *params: object,
    ) -> tuple[dict[str, int], int]:
        rows = await pool.fetch(
            f"""
            SELECT enrollment_year, COUNT(*)::int AS student_count
            FROM supervised_students
            WHERE {where_sql}
            GROUP BY enrollment_year
            """,
            *params,
        )
        year_counts: dict[str, int] = {}
        total_count = 0
        for row in rows:
            year = row.get("enrollment_year")
            count = int(row.get("student_count") or 0)
            total_count += count
            if year is None or count <= 0:
                continue
            year_counts[str(int(year))] = count
        return year_counts, total_count

    year_counts, total = await _query_year_counts(
        "COALESCE(home_university, '') = ANY($1::text[])",
        names,
    )
    if total == 0:
        year_counts, total = await _query_year_counts(
            "COALESCE(home_university, '') ILIKE ('%' || $1 || '%')",
            _normalize_text(institution_name),
        )

    return {
        "student_count_24": int(year_counts.get("2024") or 0),
        "student_count_25": int(year_counts.get("2025") or 0),
        "student_counts_by_year": year_counts,
        "student_count_total": total,
    }


async def get_institution_detail(institution_id: str) -> InstitutionDetailResponse | None:
    """Get detailed information for a single institution.

    Args:
        institution_id: Institution ID

    Returns:
        InstitutionDetailResponse or None if not found
    """
    # Fetch the institution
    record = await fetch_institution_by_id(institution_id)
    if not record:
        return None

    # If it's an organization, fetch its departments
    departments = None
    if record.get("entity_type") == "organization":
        all_records = await fetch_all_institutions()
        departments = [r for r in all_records if r.get("parent_id") == institution_id]

    metrics = await _load_student_metrics_for_institution(
        _normalize_text(record.get("name")),
        org_name=_normalize_text(record.get("org_name")) or None,
    )
    enriched_record = {
        **record,
        "student_count_24": metrics["student_count_24"],
        "student_count_25": metrics["student_count_25"],
        "student_counts_by_year": metrics["student_counts_by_year"],
        "student_count_total": metrics["student_count_total"],
    }

    # Build and return response
    return build_detail_response(enriched_record, departments)
