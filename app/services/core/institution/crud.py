"""CRUD operations for institutions.

Handles create, update, and delete operations with validation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.schemas.institution import InstitutionDetailResponse
from app.services.core.institution.classification import (
    normalize_org_type,
    parse_priority,
    resolve_classification_pair,
)
from app.services.core.institution.detail_builder import build_detail_response
from app.services.core.institution.storage import (
    delete_institution_by_id,
    fetch_all_institutions,
    fetch_institution_by_id,
    upsert_institution,
)

logger = logging.getLogger(__name__)

_VALID_ENTITY_TYPES = {"organization", "department"}


class InstitutionAlreadyExistsError(Exception):
    """Raised when attempting to create an institution with an existing ID."""

    pass


def _normalize_name(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _find_conflicting_institution(
    *,
    records: list[dict[str, Any]],
    entity_type: str,
    name: str,
    parent_id: str | None = None,
    exclude_id: str | None = None,
) -> dict[str, Any] | None:
    target = _normalize_name(name)
    if not target:
        return None

    for record in records:
        if record.get("entity_type") != entity_type:
            continue
        if exclude_id and record.get("id") == exclude_id:
            continue
        if entity_type == "department" and record.get("parent_id") != parent_id:
            continue
        if _normalize_name(record.get("name")) == target:
            return record
    return None


def _validate_people_payload(payload: dict[str, Any]) -> None:
    """Validate people-related payload constraints."""
    notable = payload.get("notable_scholars")
    if isinstance(notable, list) and len(notable) > 10:
        raise ValueError("notable_scholars 最多只能配置 10 位学者")


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
    raw_data = dict(inst_data)
    if "secondary_institutions" in raw_data and "departments" not in raw_data:
        raw_data["departments"] = raw_data.get("secondary_institutions")
    _validate_people_payload(raw_data)

    # Set entity_type if not provided.
    if not raw_data.get("entity_type"):
        if raw_data.get("parent_id"):
            raw_data["entity_type"] = "department"
        else:
            raw_data["entity_type"] = "organization"

    entity_type = raw_data.get("entity_type")
    if entity_type not in _VALID_ENTITY_TYPES:
        raise ValueError("entity_type 必须为 organization 或 department")

    if "priority" in raw_data:
        raw_data["priority"] = parse_priority(raw_data.get("priority"))

    raw_data["org_type"] = normalize_org_type(raw_data.get("org_type"))

    classification, sub_classification = resolve_classification_pair(
        raw_data.get("classification"),
        raw_data.get("sub_classification"),
        org_type=raw_data.get("org_type"),
    )
    raw_data["classification"] = classification
    raw_data["sub_classification"] = sub_classification

    if entity_type == "organization":
        raw_data["parent_id"] = None
    else:
        parent_id = str(raw_data.get("parent_id") or "").strip()
        if not parent_id:
            raise ValueError("entity_type=department 时必须提供 parent_id")
        parent = await fetch_institution_by_id(parent_id)
        if not parent:
            raise ValueError(f"Parent institution '{parent_id}' not found")
        if parent.get("entity_type") != "organization":
            raise ValueError("Parent must be an organization")
        raw_data["parent_id"] = parent_id

    # Check duplicate by normalized name.
    all_records = await fetch_all_institutions()
    used_ids = {str(r.get("id") or "") for r in all_records}

    # Generate ID lazily after entity_type / parent_id are finalized.
    if not raw_data.get("id"):
        if entity_type == "department":
            raw_data["id"] = _generate_unique_department_id(
                str(raw_data.get("name") or ""),
                str(raw_data.get("parent_id") or ""),
                used_ids,
            )
        else:
            raw_data["id"] = _generate_institution_id(str(raw_data.get("name") or "")) or "institution"

    # ID uniqueness stays global, but department auto-generated IDs are parent-scoped.
    if str(raw_data["id"]) in used_ids:
        raise InstitutionAlreadyExistsError(f"Institution with ID '{raw_data['id']}' already exists")

    conflict = _find_conflicting_institution(
        records=all_records,
        entity_type=entity_type,
        name=raw_data.get("name"),
        parent_id=raw_data.get("parent_id"),
    )
    if conflict:
        if entity_type == "organization":
            raise InstitutionAlreadyExistsError(
                f"一级机构名称重复: '{raw_data.get('name')}' (existing id={conflict.get('id')})"
            )
        raise InstitutionAlreadyExistsError(
            "二级机构名称重复: "
            f"'{raw_data.get('name')}' 在父机构 '{raw_data.get('parent_id')}' 下已存在 (existing id={conflict.get('id')})"
        )

    # Insert into database
    departments_payload = raw_data.pop("departments", None)
    created = await upsert_institution(raw_data)

    # Handle nested departments if provided
    if departments_payload is not None:
        if entity_type != "organization":
            raise ValueError("只有一级机构（organization）支持维护 departments")
        await _sync_organization_departments(
            parent_id=created["id"],
            department_payloads=departments_payload,
            replace_all=True,
        )

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

    update_data = dict(updates)
    if "secondary_institutions" in update_data and "departments" not in update_data:
        update_data["departments"] = update_data.get("secondary_institutions")
    _validate_people_payload(update_data)
    departments_payload = update_data.pop("departments", None)

    target_entity_type = update_data.get("entity_type", existing.get("entity_type")) or "organization"
    if target_entity_type not in _VALID_ENTITY_TYPES:
        raise ValueError("entity_type 必须为 organization 或 department")

    if "priority" in update_data:
        update_data["priority"] = parse_priority(update_data.get("priority"))

    if "org_type" in update_data:
        update_data["org_type"] = normalize_org_type(update_data.get("org_type"))

    if any(k in update_data for k in ("classification", "sub_classification", "org_type")):
        classification, sub_classification = resolve_classification_pair(
            update_data.get("classification", existing.get("classification")),
            update_data.get("sub_classification", existing.get("sub_classification")),
            org_type=update_data.get("org_type", existing.get("org_type")),
        )
        update_data["classification"] = classification
        update_data["sub_classification"] = sub_classification

    if target_entity_type == "organization":
        update_data["parent_id"] = None
    else:
        parent_id = update_data.get("parent_id", existing.get("parent_id"))
        if not parent_id:
            raise ValueError("entity_type=department 时必须提供 parent_id")
        await _validate_parent_for_department(parent_id, institution_id)
        update_data["parent_id"] = parent_id

        # organization -> department 需要先确保没有子院系
        if existing.get("entity_type") == "organization":
            all_records = await fetch_all_institutions()
            children = [r for r in all_records if r.get("parent_id") == institution_id]
            if children:
                raise ValueError("当前一级机构下存在二级机构，无法直接转换为 department")

    new_name = update_data.get("name", existing.get("name"))
    new_parent_id = update_data.get("parent_id", existing.get("parent_id"))

    # Check duplicate by normalized name after mutation.
    all_records = await fetch_all_institutions()
    conflict = _find_conflicting_institution(
        records=all_records,
        entity_type=target_entity_type,
        name=new_name,
        parent_id=new_parent_id,
        exclude_id=institution_id,
    )
    if conflict:
        if target_entity_type == "organization":
            raise ValueError(
                f"一级机构名称重复: '{new_name}' (existing id={conflict.get('id')})"
            )
        raise ValueError(
            f"二级机构名称重复: '{new_name}' 在父机构 '{new_parent_id}' 下已存在 "
            f"(existing id={conflict.get('id')})"
        )

    # Merge updates
    updated_data = {**existing, **update_data, "id": institution_id}

    # Update in database
    await upsert_institution(updated_data)

    if departments_payload is not None:
        if target_entity_type != "organization":
            raise ValueError("只有一级机构（organization）支持维护 departments")
        await _sync_organization_departments(
            parent_id=institution_id,
            department_payloads=departments_payload,
            replace_all=True,
        )

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


def _generate_unique_department_id(
    department_name: str,
    parent_id: str,
    used_ids: set[str],
) -> str:
    """Generate unique department ID under a parent organization."""
    base = _generate_institution_id(department_name) or "department"
    candidate = f"{parent_id}_{base}"
    suffix = 2
    while candidate in used_ids:
        candidate = f"{parent_id}_{base}_{suffix}"
        suffix += 1
    return candidate


async def _validate_parent_for_department(parent_id: str, institution_id: str | None = None) -> None:
    """Validate parent organization for a department."""
    if parent_id == institution_id:
        raise ValueError("parent_id 不能等于当前机构 id")
    parent = await fetch_institution_by_id(parent_id)
    if not parent:
        raise ValueError(f"Parent institution '{parent_id}' not found")
    if parent.get("entity_type") != "organization":
        raise ValueError("Parent must be an organization")


async def _sync_organization_departments(
    parent_id: str,
    department_payloads: list[dict[str, Any]],
    *,
    replace_all: bool,
) -> None:
    """Synchronize department list under an organization.

    When replace_all=True, existing departments not included in payload
    will be deleted.
    """
    if not isinstance(department_payloads, list):
        raise ValueError("departments 必须是数组")

    all_records = await fetch_all_institutions()
    existing_by_id = {r["id"]: r for r in all_records}
    existing_children = {
        r["id"]: r
        for r in all_records
        if r.get("entity_type") == "department" and r.get("parent_id") == parent_id
    }
    used_ids = set(existing_by_id.keys())
    keep_ids: set[str] = set()

    parent = await fetch_institution_by_id(parent_id)
    if not parent or parent.get("entity_type") != "organization":
        raise ValueError(f"父机构 '{parent_id}' 不存在或不是 organization")

    payload_name_keys: set[str] = set()
    for idx, payload in enumerate(department_payloads):
        if not isinstance(payload, dict):
            raise ValueError(f"departments[{idx}] 必须是对象")

        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError(f"departments[{idx}].name 不能为空")
        name_key = _normalize_name(name)
        if name_key in payload_name_keys:
            raise ValueError(f"departments 中存在重复名称: {name}")
        payload_name_keys.add(name_key)

        raw_id = payload.get("id")
        dept_id = str(raw_id).strip() if raw_id else None

        if dept_id:
            if dept_id in keep_ids:
                raise ValueError(f"departments 中存在重复 id: {dept_id}")
            existing_dept = existing_by_id.get(dept_id)
            if existing_dept:
                if existing_dept.get("entity_type") != "department":
                    raise ValueError(f"id '{dept_id}' 已被非院系机构占用")
                if existing_dept.get("parent_id") != parent_id:
                    raise ValueError(f"院系 id '{dept_id}' 已属于其他一级机构")
        else:
            dept_id = _generate_unique_department_id(name, parent_id, used_ids | keep_ids)

        # Prevent duplicate department names under one parent.
        for existing_child in existing_children.values():
            if existing_child.get("id") == dept_id:
                continue
            if _normalize_name(existing_child.get("name")) == name_key:
                raise ValueError(
                    f"二级机构名称重复: '{name}' 在父机构 '{parent_id}' 下已存在 "
                    f"(existing id={existing_child.get('id')})"
                )

        base = existing_by_id.get(dept_id) or {}
        row: dict[str, Any] = {
            **base,
            "id": dept_id,
            "name": name,
            # Legacy schema requires non-null `type` column.
            "type": "department",
            "entity_type": "department",
            "parent_id": parent_id,
            "org_name": payload.get("org_name", base.get("org_name")),
            "scholar_count": base.get("scholar_count", 0),
            "region": parent.get("region"),
            "org_type": parent.get("org_type"),
            "classification": parent.get("classification"),
            "sub_classification": parent.get("sub_classification"),
        }
        await upsert_institution(row)

        keep_ids.add(dept_id)
        used_ids.add(dept_id)

    if replace_all:
        for dept_id in existing_children:
            if dept_id not in keep_ids:
                await delete_institution_by_id(dept_id)
                logger.info("Deleted department %s during sync (parent=%s)", dept_id, parent_id)


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
