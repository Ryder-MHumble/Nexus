"""Data storage layer for institutions.

Handles reading from and writing to Supabase database.
"""

from __future__ import annotations

from app.db.client import get_client


async def fetch_all_institutions() -> list[dict]:
    """Fetch all institution records from database.

    Returns:
        List of institution records as dicts
    """
    client = get_client()
    resp = await client.table("institutions").select("*").execute()
    return resp.data


async def fetch_institution_by_id(institution_id: str) -> dict | None:
    """Fetch a single institution by ID.

    Args:
        institution_id: Institution ID

    Returns:
        Institution record or None if not found
    """
    client = get_client()
    resp = await client.table("institutions").select("*").eq("id", institution_id).execute()
    return resp.data[0] if resp.data else None


async def upsert_institution(institution_data: dict) -> dict:
    """Insert or update an institution record.

    Args:
        institution_data: Institution data dict (must include 'id')

    Returns:
        Upserted institution record
    """
    client = get_client()
    resp = await client.table("institutions").upsert(institution_data).execute()
    return resp.data[0]


async def delete_institution_by_id(institution_id: str) -> bool:
    """Delete an institution by ID.

    Args:
        institution_id: Institution ID

    Returns:
        True if deleted, False if not found
    """
    client = get_client()
    resp = await client.table("institutions").delete().eq("id", institution_id).execute()
    return len(resp.data) > 0
