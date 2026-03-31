"""Personnel processing pipeline — callable from orchestrator.

Rules-only extraction + optional LLM enrichment.
Reuses service-layer functions directly.
Self-contained hash tracking and output logic (no imports from scripts/).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.config import BASE_DIR
from app.services.intel.personnel.rules import change_id, enrich_by_rules
from app.services.intel.personnel.source_scope import filter_personnel_scoped_articles
from app.services.intel.pipeline.base import HashTracker, save_output_json
from app.services.intel.shared import article_date
from app.services.stores.json_reader import get_articles

logger = logging.getLogger(__name__)

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

DIMENSION = "personnel"
PROCESSED_DIR = BASE_DIR / "data" / "processed" / "personnel_intel"
ENRICHED_DIR = PROCESSED_DIR / "_enriched"

_hash_tracker = HashTracker(PROCESSED_DIR / "_processed_hashes.json", PROCESSED_DIR)
_enrich_tracker = HashTracker(PROCESSED_DIR / "_enriched_hashes.json", PROCESSED_DIR)


# ---------------------------------------------------------------------------
# Output builder
# ---------------------------------------------------------------------------

def _article_date(a: dict) -> str:
    return article_date(a)


def _build_feed_item(article: dict, enrichment: dict) -> dict:
    return {
        "id": article.get("url_hash", ""),
        "title": article.get("title", ""),
        "date": _article_date(article),
        "source": article.get("source_name", ""),
        "source_id": article.get("source_id", ""),
        "source_name": article.get("source_name", ""),
        "importance": enrichment.get("importance", "一般"),
        "matchScore": enrichment.get("matchScore", 0),
        "changes": enrichment.get("changes", []),
        "sourceUrl": article.get("url", ""),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def process_personnel_pipeline(
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Run personnel processing pipeline (rules only, no LLM).

    Returns summary dict for the pipeline orchestrator.
    """
    articles = await get_articles(DIMENSION)
    articles = filter_personnel_scoped_articles(articles)
    logger.info("Personnel pipeline: loaded %d articles", len(articles))

    # Deduplicate by url_hash
    seen: set[str] = set()
    unique: list[dict] = []
    for a in articles:
        h = a.get("url_hash", "")
        if h and h not in seen:
            seen.add(h)
            unique.append(a)

    # Filter already-processed (incremental)
    processed_hashes = set() if force else _hash_tracker.load()
    new_articles = [
        a for a in unique if a.get("url_hash", "") not in processed_hashes
    ]

    logger.info(
        "Personnel pipeline: %d unique, %d new (previously processed: %d)",
        len(unique), len(new_articles), len(processed_hashes),
    )

    # Track new hashes
    new_count = 0
    if new_articles:
        for article in new_articles:
            h = article.get("url_hash", "")
            if h:
                processed_hashes.add(h)
                new_count += 1
        _hash_tracker.save(processed_hashes)

    # Rebuild output files from ALL unique articles
    feed_items: list[dict] = []
    all_changes: list[dict] = []
    for article in unique:
        enrichment = enrich_by_rules(article)
        feed_items.append(_build_feed_item(article, enrichment))
        all_changes.extend(enrichment.get("changes", []))

    feed_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    all_changes.sort(key=lambda x: x.get("date", ""), reverse=True)

    save_output_json(PROCESSED_DIR, "feed.json", feed_items)
    save_output_json(PROCESSED_DIR, "changes.json", all_changes)

    logger.info(
        "Personnel output: %d feed items, %d changes",
        len(feed_items), len(all_changes),
    )

    return {
        "total_articles": len(articles),
        "unique": len(unique),
        "new_processed": new_count,
        "previously_processed": len(processed_hashes) - new_count,
        "feed_items": len(feed_items),
        "changes_extracted": len(all_changes),
    }


# ---------------------------------------------------------------------------
# LLM enrichment helpers
# ---------------------------------------------------------------------------



def _save_enriched_article(article: dict, enriched_changes: list[dict]) -> None:
    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
    url_hash = article.get("url_hash", "unknown")
    out = {
        "article": {
            "url_hash": url_hash,
            "title": article.get("title"),
            "url": article.get("url"),
            "published_at": article.get("published_at"),
            "source_id": article.get("source_id"),
            "source_name": article.get("source_name"),
        },
        "enriched_changes": enriched_changes,
    }
    path = ENRICHED_DIR / f"{url_hash}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def _load_all_enriched_changes() -> list[dict]:
    if not ENRICHED_DIR.exists():
        return []
    all_changes: list[dict] = []
    for path in ENRICHED_DIR.glob("*.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            all_changes.extend(data.get("enriched_changes", []))
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning("Skipping invalid enriched file %s: %s", path.name, e)
    return all_changes


def _build_enriched_change(
    change: dict, article: dict, llm_enrichment: dict,
) -> dict:
    return {
        "id": change_id(change),
        "name": change.get("name", ""),
        "action": change.get("action", ""),
        "position": change.get("position", ""),
        "department": change.get("department"),
        "date": change.get("date", _article_date(article)),
        "source": article.get("source_name", ""),
        "source_id": article.get("source_id", ""),
        "source_name": article.get("source_name", ""),
        "sourceUrl": article.get("url"),
        "relevance": llm_enrichment.get("relevance", 10),
        "importance": llm_enrichment.get("importance", "一般"),
        "group": llm_enrichment.get("group", "watch"),
        "note": llm_enrichment.get("note"),
        "actionSuggestion": llm_enrichment.get("actionSuggestion"),
        "background": llm_enrichment.get("background"),
        "signals": llm_enrichment.get("signals", []),
        "aiInsight": llm_enrichment.get("aiInsight"),
    }


# ---------------------------------------------------------------------------
# LLM enrichment public API
# ---------------------------------------------------------------------------

async def process_personnel_llm_enrichment(
    *,
    concurrency: int = 3,
) -> dict[str, Any]:
    """Tier 2: LLM enrichment for personnel changes.

    Reads raw articles, extracts changes via rules, then enriches via LLM.
    Incremental: tracks enriched article hashes.

    Returns summary dict for the pipeline orchestrator.
    """
    from app.services.intel.personnel.llm import (
        enrich_changes_batch,
    )

    articles = await get_articles(DIMENSION)
    articles = filter_personnel_scoped_articles(articles)

    # Deduplicate
    seen: set[str] = set()
    unique: list[dict] = []
    for a in articles:
        h = a.get("url_hash", "")
        if h and h not in seen:
            seen.add(h)
            unique.append(a)

    # Extract changes via rules for all articles with changes
    articles_with_changes: list[tuple[dict, list[dict]]] = []
    total_changes = 0
    for article in unique:
        enrichment = enrich_by_rules(article)
        changes = enrichment.get("changes", [])
        if changes:
            articles_with_changes.append((article, changes))
            total_changes += len(changes)

    logger.info(
        "Personnel LLM: %d articles with %d changes (from %d unique)",
        len(articles_with_changes), total_changes, len(unique),
    )

    if not articles_with_changes:
        return {"skipped": True, "reason": "no changes to enrich"}

    # Filter already-enriched (incremental)
    enriched_hashes = _enrich_tracker.load()
    new_articles = [
        (a, c) for a, c in articles_with_changes
        if a.get("url_hash", "") not in enriched_hashes
    ]

    logger.info(
        "Personnel LLM: %d new articles to enrich (previously: %d)",
        len(new_articles), len(enriched_hashes),
    )

    # Run LLM enrichment
    llm_count = 0
    if new_articles:
        sem = asyncio.Semaphore(concurrency)

        async def _enrich_one(
            article: dict, changes: list[dict],
        ) -> None:
            nonlocal llm_count
            async with sem:
                enrichments = await enrich_changes_batch(changes, article)
                enriched = [
                    _build_enriched_change(change, article, enrich)
                    for change, enrich in zip(changes, enrichments)
                ]
                _save_enriched_article(article, enriched)
                h = article.get("url_hash", "")
                if h:
                    enriched_hashes.add(h)
                llm_count += 1

        tasks = [_enrich_one(a, c) for a, c in new_articles]
        await asyncio.gather(*tasks)
        _enrich_tracker.save(enriched_hashes)

    # Rebuild enriched_feed.json from all cached enriched data
    all_enriched = _load_all_enriched_changes()
    all_enriched.sort(
        key=lambda x: (
            0 if x.get("group") == "action" else 1,
            -(x.get("relevance") or 0),
            x.get("date", ""),
        ),
    )

    action_count = sum(1 for x in all_enriched if x.get("group") == "action")

    save_output_json(
        PROCESSED_DIR, "enriched_feed.json", all_enriched,
        extra={
            "total_count": len(all_enriched),
            "action_count": action_count,
            "watch_count": len(all_enriched) - action_count,
        },
    )

    logger.info(
        "Personnel LLM output: %d enriched changes (action=%d, watch=%d)",
        len(all_enriched), action_count, len(all_enriched) - action_count,
    )

    return {
        "llm_enriched_articles": llm_count,
        "total_enriched_changes": len(all_enriched),
        "action_count": action_count,
        "watch_count": len(all_enriched) - action_count,
    }
