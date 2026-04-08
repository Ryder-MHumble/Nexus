"""Backward-compatible re-exports for intel shared utilities.

All symbols are now defined in focused sub-modules:
  - scoring.py     — keyword_score, clamp_score, compute_importance, clamp_value
  - extractors.py  — FUNDING_PATTERNS, DEADLINE_PATTERNS, LEADER_NAME_RE,
                     extract_funding, extract_deadline, extract_leader, compute_days_left
  - date_utils.py  — article_date, article_datetime, parse_date_str, str_or_none
  - intel_store.py — load_intel_json, get_intel_stats, deduplicate_articles
  - source_filter.py — resolve_source_ids_by_names, parse_source_filter

Existing ``from app.services.intel.shared import ...`` statements continue to work.
Prefer importing directly from sub-modules in new code.
"""
from __future__ import annotations

from app.services.intel.date_utils import (  # noqa: F401
    article_date,
    article_datetime,
    parse_date_str,
    str_or_none,
)
from app.services.intel.extractors import (  # noqa: F401
    DEADLINE_PATTERNS,
    FUNDING_PATTERNS,
    LEADER_NAME_RE,
    compute_days_left,
    extract_deadline,
    extract_funding,
    extract_leader,
)
from app.services.intel.intel_store import (  # noqa: F401
    IntelDataLoadError,
    _EMPTY_RESPONSE,
    PROCESSED_BASE,
    deduplicate_articles,
    get_intel_stats,
    load_intel_json,
    load_required_intel_json,
)
from app.services.intel.scoring import (  # noqa: F401
    clamp_score,
    clamp_value,
    compute_importance,
    keyword_score,
)
from app.services.intel.source_filter import (  # noqa: F401
    parse_source_filter,
    resolve_source_ids_by_names,
)

__all__ = [
    # scoring
    "keyword_score",
    "clamp_score",
    "compute_importance",
    "clamp_value",
    # extractors
    "FUNDING_PATTERNS",
    "DEADLINE_PATTERNS",
    "LEADER_NAME_RE",
    "extract_funding",
    "extract_deadline",
    "extract_leader",
    "compute_days_left",
    # date_utils
    "article_date",
    "article_datetime",
    "parse_date_str",
    "str_or_none",
    # intel_store
    "PROCESSED_BASE",
    "_EMPTY_RESPONSE",
    "IntelDataLoadError",
    "load_intel_json",
    "load_required_intel_json",
    "get_intel_stats",
    "deduplicate_articles",
    # source_filter
    "resolve_source_ids_by_names",
    "parse_source_filter",
]
