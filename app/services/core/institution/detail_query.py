"""Detail query logic for individual institutions.

Fetches and builds detailed information for a single institution.
"""

from __future__ import annotations

from app.schemas.institution import InstitutionDetailResponse
from app.services.core.institution.detail_builder import build_detail_response
from app.services.core.institution.storage import fetch_all_institutions, fetch_institution_by_id


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

    # Build and return response
    return build_detail_response(record, departments)
