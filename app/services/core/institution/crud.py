"""CRUD operations for institutions.

Handles create, update, and delete operations with validation.
"""

from __future__ import annotations

import logging
import re

from app.schemas.institution import InstitutionDetailResponse
from app.services.core.institution.detail_builder import build_detail_response
from app.services.core.institution.storage import (
    delete_institution_by_id,
    fetch_all_institutions,
    fetch_institution_by_id,
    upsert_institution,
)

logger = logging.getLogger(__name__)


class InstitutionAlreadyExistsError(Exception):
    """Raised when attempting to create an institution with an existing ID."""

    pass


async def create_institution(inst_data: dict) -> InstitutionDetailResponse:
    """Create a new institution.

    Args:
        inst_data: Institution data dict

    Returns:
        Created institution as InstitutionDetailResponse

    Raises:
        InstitutionAlreadyExistsError: If ID already exists
        ValueError: If validation fails
    """
    # Generate ID if not provided
    if not inst_data.get("id"):
        inst_data["id"] = _generate_institution_id(inst_data["name"])

    # Check if ID already exists
    existing = await fetch_institution_by_id(inst_data["id"])
    if existing:
        raise InstitutionAlreadyExistsError(f"Institution with ID '{inst_data['id']}' already exists")

    # Validate parent_id if provided
    if inst_data.get("parent_id"):
        parent = await fetch_institution_by_id(inst_data["parent_id"])
        if not parent:
            raise ValueError(f"Parent institution '{inst_data['parent_id']}' not found")
        if parent.get("entity_type") != "organization":
            raise ValueError("Parent must be an organization")

    # Set entity_type if not provided
    if not inst_data.get("entity_type"):
        if inst_data.get("parent_id"):
            inst_data["entity_type"] = "department"
        else:
            inst_data["entity_type"] = "organization"

    # Insert into database
    created = await upsert_institution(inst_data)

    # Handle nested departments if provided
    if inst_data.get("departments") and inst_data["entity_type"] == "organization":
        for dept_data in inst_data["departments"]:
            dept_data["parent_id"] = created["id"]
            dept_data["entity_type"] = "department"
            if not dept_data.get("id"):
                dept_data["id"] = _generate_institution_id(dept_data["name"])
            await upsert_institution(dept_data)

    # Return detail response
    return await _get_detail_after_mutation(created["id"])


async def update_institution(
    institution_id: str, updates: dict
) -> InstitutionDetailResponse | None:
    """Update an existing institution.

    Args:
        institution_id: Institution ID
        updates: Dict of fields to update

    Returns:
        Updated institution or None if not found
    """
    # Check if exists
    existing = await fetch_institution_by_id(institution_id)
    if not existing:
        return None

    # Convert priority from "P0"/"P1"/"P2"/"P3" to integer 0/1/2/3
    if "priority" in updates and isinstance(updates["priority"], str):
        priority_str = updates["priority"]
        if priority_str and priority_str.startswith("P"):
            try:
                updates["priority"] = int(priority_str[1:])
            except (ValueError, IndexError):
                pass  # Keep original value if conversion fails

    # Merge updates
    updated_data = {**existing, **updates, "id": institution_id}

    # Update in database
    await upsert_institution(updated_data)

    # Return detail response
    return await _get_detail_after_mutation(institution_id)


async def delete_institution(institution_id: str) -> bool:
    """Delete an institution.

    If deleting an organization, also deletes all its departments.

    Args:
        institution_id: Institution ID

    Returns:
        True if deleted, False if not found
    """
    # Check if exists
    existing = await fetch_institution_by_id(institution_id)
    if not existing:
        return False

    # If organization, delete all departments first
    if existing.get("entity_type") == "organization":
        all_records = await fetch_all_institutions()
        departments = [r for r in all_records if r.get("parent_id") == institution_id]
        for dept in departments:
            await delete_institution_by_id(dept["id"])
            logger.info(f"Deleted department {dept['id']} (parent: {institution_id})")

    # Delete the institution itself
    deleted = await delete_institution_by_id(institution_id)
    if deleted:
        logger.info(f"Deleted institution {institution_id}")

    return deleted


def _generate_institution_id(name: str) -> str:
    """Generate institution ID from name.

    Converts Chinese characters to pinyin and creates a URL-safe ID.

    Args:
        name: Institution name

    Returns:
        Generated ID
    """
    # Simple ID generation: lowercase, remove special chars, replace spaces with underscores
    # For production, consider using pypinyin for Chinese → pinyin conversion
    id_str = name.lower()
    id_str = re.sub(r"[^\w\s-]", "", id_str)
    id_str = re.sub(r"[\s_]+", "_", id_str)
    id_str = id_str.strip("_")

    # Truncate if too long
    if len(id_str) > 50:
        id_str = id_str[:50]

    return id_str


async def _get_detail_after_mutation(institution_id: str) -> InstitutionDetailResponse:
    """Helper to fetch and build detail response after create/update.

    Args:
        institution_id: Institution ID

    Returns:
        InstitutionDetailResponse
    """
    record = await fetch_institution_by_id(institution_id)
    if not record:
        raise RuntimeError(f"Institution {institution_id} not found after mutation")

    # Fetch departments if organization
    departments = None
    if record.get("entity_type") == "organization":
        all_records = await fetch_all_institutions()
        departments = [r for r in all_records if r.get("parent_id") == institution_id]

    return build_detail_response(record, departments)
