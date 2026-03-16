"""Backward-compatible facade — delegates to app.services.faculty subpackage.

All implementation now lives in app/services/faculty/:
  __init__.py      — public API
  _data.py         — raw JSON loading and annotation merging
  _filters.py      — filtering helpers
  _transformers.py — response shape converters
"""
from app.services.scholar import (  # noqa: F401
    add_scholar_update,
    batch_create_scholars,
    create_scholar,
    delete_scholar,
    delete_scholar_update,
    get_scholar_detail,
    get_scholar_list,
    get_scholar_stats,
    import_scholars_async,
    update_scholar_achievements,
    update_scholar_basic,
    update_scholar_relation,
)
