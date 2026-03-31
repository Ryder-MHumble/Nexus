"""Personnel source scope helpers.

Ensure personnel intel only uses channels defined in `sources/personnel.yaml`.
"""
from __future__ import annotations

from functools import lru_cache

from app.scheduler.manager import load_all_source_configs


@lru_cache(maxsize=1)
def get_personnel_source_ids() -> set[str]:
    """Return allowed source IDs for personnel intel from personnel.yaml only."""
    ids: set[str] = set()
    for source in load_all_source_configs():
        if source.get("source_file") != "personnel.yaml":
            continue
        sid = str(source.get("id") or "").strip()
        if sid:
            ids.add(sid)
    return ids


def filter_personnel_scoped_articles(articles: list[dict]) -> list[dict]:
    """Filter article list to personnel.yaml sources only."""
    allowed = get_personnel_source_ids()
    if not allowed:
        return articles
    return [a for a in articles if str(a.get("source_id") or "") in allowed]

