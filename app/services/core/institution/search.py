"""Institution search and fuzzy matching logic."""

from __future__ import annotations

from typing import Any

from app.services.core.institution.classification import normalize_org_type
from app.services.core.institution.storage import fetch_all_institutions


async def search_institutions(
    query: str,
    *,
    limit: int = 10,
    region: str | None = None,
    org_type: str | None = None,
) -> list[dict[str, Any]]:
    """Search institutions by name with fuzzy matching.

    Matching algorithm:
    1. Exact match (highest priority)
    2. Starts with query
    3. Contains query (case-insensitive)
    4. Score by relevance

    Args:
        query: Search query string
        limit: Maximum number of results to return
        region: Optional region filter (国内/国际)
        org_type: Optional org_type filter (高校/企业/研究机构/其他)

    Returns:
        List of institution dicts sorted by relevance
    """
    if not query or not query.strip():
        return []

    query_lower = query.strip().lower()

    # Fetch all institutions
    all_institutions = await fetch_all_institutions()

    # Apply filters
    filtered = all_institutions
    if region:
        filtered = [inst for inst in filtered if inst.get("region") == region]
    if org_type:
        normalized_org_type = normalize_org_type(org_type)
        filtered = [
            inst
            for inst in filtered
            if normalize_org_type(inst.get("org_type")) == normalized_org_type
        ]

    # Score and rank results
    scored_results: list[tuple[int, dict[str, Any]]] = []

    for inst in filtered:
        name = inst.get("name", "")
        name_lower = name.lower()

        # Calculate relevance score (higher is better)
        score = 0

        # Exact match (highest priority)
        if name_lower == query_lower:
            score = 1000
        # Starts with query
        elif name_lower.startswith(query_lower):
            score = 500
        # Contains query
        elif query_lower in name_lower:
            score = 100
        # Check if query is in name (character by character for Chinese)
        elif all(c in name for c in query):
            score = 50
        else:
            continue  # No match

        # Boost score for organizations (vs departments)
        if inst.get("entity_type") == "organization":
            score += 10

        # Boost score by scholar count (more scholars = more relevant)
        scholar_count = inst.get("scholar_count", 0)
        score += min(scholar_count, 50)  # Cap at 50 bonus points

        scored_results.append((score, inst))

    # Sort by score (descending) and take top N
    scored_results.sort(key=lambda x: x[0], reverse=True)
    results = [inst for _, inst in scored_results[:limit]]

    return results


async def suggest_institution(university_name: str) -> dict[str, Any]:
    """Find best match for a university name.

    This is used when editing a scholar to find the canonical institution name.

    Args:
        university_name: University name from scholar record

    Returns:
        Dict with:
        - matched: Best matching institution (or None)
        - suggestions: List of alternative matches
    """
    if not university_name or not university_name.strip():
        return {"matched": None, "suggestions": []}

    # Search with the full name
    results = await search_institutions(university_name, limit=5)

    if not results:
        return {"matched": None, "suggestions": []}

    # First result is the best match
    best_match = results[0]

    # Check if it's a strong match (exact or starts with)
    name_lower = best_match.get("name", "").lower()
    query_lower = university_name.strip().lower()

    is_strong_match = (
        name_lower == query_lower or
        name_lower.startswith(query_lower) or
        query_lower.startswith(name_lower)
    )

    return {
        "matched": best_match if is_strong_match else None,
        "suggestions": results,
    }


def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity between two strings (0.0 to 1.0).

    Uses a simple character overlap metric.
    For more sophisticated matching, consider using python-Levenshtein.

    Args:
        str1: First string
        str2: Second string

    Returns:
        Similarity score (0.0 = no match, 1.0 = identical)
    """
    if not str1 or not str2:
        return 0.0

    str1_lower = str1.lower()
    str2_lower = str2.lower()

    # Exact match
    if str1_lower == str2_lower:
        return 1.0

    # Character overlap
    set1 = set(str1_lower)
    set2 = set(str2_lower)
    intersection = set1 & set2
    union = set1 | set2

    if not union:
        return 0.0

    return len(intersection) / len(union)
