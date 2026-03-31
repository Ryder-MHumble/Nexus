"""Institution synchronization logic for scholar updates."""

from __future__ import annotations

import logging
from typing import Any

from app.db.client import get_client
from app.services.scholar._filters import (
    _derive_affiliation_type_from_university,
    _derive_region_from_university,
)

logger = logging.getLogger(__name__)


def _generate_institution_id(name: str) -> str:
    """Generate institution ID from name.

    Rules:
    - Remove spaces and special characters
    - Convert to lowercase
    - Truncate to 50 characters

    Args:
        name: Institution name

    Returns:
        Institution ID
    """
    import re

    # Remove special characters, keep only alphanumeric and Chinese
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", name)
    # Convert to lowercase
    cleaned = cleaned.lower()
    # Remove leading/trailing underscores
    cleaned = cleaned.strip("_")
    # Truncate
    return cleaned[:50]


async def sync_institution_on_scholar_update(
    old_university: str | None,
    new_university: str | None,
    old_department: str | None,
    new_department: str | None,
) -> dict[str, Any]:
    """Synchronize institutions table when scholar data changes.

    This function is called when a scholar's university or department is updated.
    It ensures that:
    1. The new university exists in the institutions table (creates if not)
    2. The new department exists under the university (creates if not)
    3. Scholar counts are updated for affected institutions

    Args:
        old_university: Previous university name (or None)
        new_university: New university name (or None)
        old_department: Previous department name (or None)
        new_department: New department name (or None)

    Returns:
        Dict with sync results:
        - created_organization: bool - Whether organization was created
        - created_department: bool - Whether department was created
        - organization_id: str | None - Organization ID
        - department_id: str | None - Department ID
    """
    result = {
        "created_organization": False,
        "created_department": False,
        "organization_id": None,
        "department_id": None,
    }

    # If university didn't change, nothing to sync
    if old_university == new_university and old_department == new_department:
        return result

    if not new_university:
        return result

    client = get_client()

    # Step 1: Check if organization exists
    org_result = await client.table("institutions").select("*").eq("name", new_university).eq("entity_type", "organization").execute()

    organization = None
    if org_result.data:
        organization = org_result.data[0]
        result["organization_id"] = organization["id"]
        logger.info("Found existing organization: %s (id=%s)", new_university, organization["id"])
    else:
        # Create new organization
        org_id = _generate_institution_id(new_university)
        region = _derive_region_from_university(new_university)
        org_type = _derive_affiliation_type_from_university(new_university)

        # Determine type based on org_type
        type_mapping = {
            "高校": "university",
            "企业": "company",
            "研究机构": "research_institute",
            "行业学会": "association",
            "其他": "other",
        }
        inst_type = type_mapping.get(org_type, "other")

        new_org = {
            "id": org_id,
            "name": new_university,
            "entity_type": "organization",
            "type": inst_type,
            "region": region,
            "org_type": org_type,
            "scholar_count": 0,  # Will be recalculated
            "parent_id": None,
        }

        try:
            insert_result = await client.table("institutions").insert(new_org).execute()
            organization = insert_result.data[0]
            result["created_organization"] = True
            result["organization_id"] = organization["id"]
            logger.info(
                "Created new organization: %s (id=%s, region=%s, org_type=%s, type=%s)",
                new_university,
                org_id,
                region,
                org_type,
                inst_type,
            )
        except Exception as e:
            logger.exception("Failed to create organization %s: %s", new_university, e)
            # If creation fails (e.g., ID conflict), try to fetch again
            org_result = await client.table("institutions").select("*").eq("name", new_university).eq("entity_type", "organization").execute()
            if org_result.data:
                organization = org_result.data[0]
                result["organization_id"] = organization["id"]

    # Step 2: Check if department exists (if department is provided)
    if new_department and organization:
        dept_result = (
            await client.table("institutions")
            .select("*")
            .eq("name", new_department)
            .eq("entity_type", "department")
            .eq("parent_id", organization["id"])
            .execute()
        )

        if dept_result.data:
            department = dept_result.data[0]
            result["department_id"] = department["id"]
            logger.info(
                "Found existing department: %s under %s (id=%s)",
                new_department,
                new_university,
                department["id"],
            )
        else:
            # Create new department
            dept_id = f"{organization['id']}_{_generate_institution_id(new_department)}"

            new_dept = {
                "id": dept_id,
                "name": new_department,
                "entity_type": "department",
                "type": organization.get("type", "other"),  # Inherit type from parent
                "region": organization.get("region"),
                "org_type": organization.get("org_type"),
                "parent_id": organization["id"],
                "scholar_count": 0,  # Will be recalculated
            }

            try:
                insert_result = await client.table("institutions").insert(new_dept).execute()
                department = insert_result.data[0]
                result["created_department"] = True
                result["department_id"] = department["id"]
                logger.info(
                    "Created new department: %s under %s (id=%s)",
                    new_department,
                    new_university,
                    dept_id,
                )
            except Exception as e:
                logger.exception(
                    "Failed to create department %s under %s: %s",
                    new_department,
                    new_university,
                    e,
                )

    # Step 3: Recalculate scholar counts
    # This is done asynchronously to avoid blocking the scholar update
    # The counts will be eventually consistent
    try:
        await _recalculate_scholar_counts_for_institutions(
            [old_university, new_university] if old_university != new_university else [new_university]
        )
    except Exception as e:
        logger.exception("Failed to recalculate scholar counts: %s", e)

    return result


async def _recalculate_scholar_counts_for_institutions(university_names: list[str | None]) -> None:
    """Recalculate scholar counts for given universities.

    This queries the scholars table and updates the scholar_count field
    in the institutions table.

    Args:
        university_names: List of university names to recalculate
    """
    client = get_client()

    for university_name in university_names:
        if not university_name:
            continue

        try:
            # Count scholars for this university
            scholars_result = (
                await client.table("scholars")
                .select("id", count="exact")
                .eq("university", university_name)
                .execute()
            )

            scholar_count = scholars_result.count or 0

            # Update organization scholar count
            await client.table("institutions").update({"scholar_count": scholar_count}).eq("name", university_name).eq("entity_type", "organization").execute()

            logger.info(
                "Updated scholar count for %s: %d scholars",
                university_name,
                scholar_count,
            )

            # Also update department counts
            # Get all departments for this university
            org_result = (
                await client.table("institutions")
                .select("id")
                .eq("name", university_name)
                .eq("entity_type", "organization")
                .execute()
            )

            if org_result.data:
                org_id = org_result.data[0]["id"]

                # Get all departments
                dept_result = (
                    await client.table("institutions")
                    .select("id, name")
                    .eq("parent_id", org_id)
                    .eq("entity_type", "department")
                    .execute()
                )

                for dept in dept_result.data:
                    # Count scholars in this department
                    dept_scholars_result = (
                        await client.table("scholars")
                        .select("id", count="exact")
                        .eq("university", university_name)
                        .eq("department", dept["name"])
                        .execute()
                    )

                    dept_scholar_count = dept_scholars_result.count or 0

                    # Update department scholar count
                    await client.table("institutions").update({"scholar_count": dept_scholar_count}).eq("id", dept["id"]).execute()

                    logger.info(
                        "Updated scholar count for %s - %s: %d scholars",
                        university_name,
                        dept["name"],
                        dept_scholar_count,
                    )

        except Exception as e:
            logger.exception(
                "Failed to recalculate scholar count for %s: %s",
                university_name,
                e,
            )


async def ensure_institution_exists(
    university: str,
    department: str | None = None,
) -> dict[str, str | None]:
    """Ensure institution and department exist in the database.

    This is a convenience function that can be called before creating/updating a scholar.

    Args:
        university: University name
        department: Department name (optional)

    Returns:
        Dict with:
        - organization_id: Organization ID
        - department_id: Department ID (or None)
    """
    result = await sync_institution_on_scholar_update(
        old_university=None,
        new_university=university,
        old_department=None,
        new_department=department,
    )

    return {
        "organization_id": result["organization_id"],
        "department_id": result["department_id"],
    }
