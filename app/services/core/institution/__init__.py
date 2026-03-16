"""Institution service module - modularized architecture.

Public API exports for institution management.
"""

from __future__ import annotations

# CRUD operations
from app.services.core.institution.crud import (
    InstitutionAlreadyExistsError,
    create_institution,
    delete_institution,
    update_institution,
)

# Detail queries
from app.services.core.institution.detail_query import get_institution_detail

# Legacy compatibility
from app.services.core.institution.legacy import (
    get_institution_list,
    search_institutions_for_aminer,
)

# List queries
from app.services.core.institution.list_query import get_institutions_unified

# Taxonomy and stats
from app.services.core.institution.taxonomy import (
    get_institution_stats,
    get_institution_taxonomy,
)

__all__ = [
    # CRUD
    "create_institution",
    "update_institution",
    "delete_institution",
    "InstitutionAlreadyExistsError",
    # Queries
    "get_institution_detail",
    "get_institutions_unified",
    "get_institution_list",  # Legacy
    # Stats
    "get_institution_stats",
    "get_institution_taxonomy",
    # AMiner
    "search_institutions_for_aminer",  # Legacy
]
