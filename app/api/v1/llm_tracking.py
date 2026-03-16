"""LLM API call tracking and statistics endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from app.services.llm.llm_call_tracker import get_tracker

router = APIRouter(prefix="/llm-tracking", tags=["llm-tracking"])


@router.get("/summary")
async def get_llm_summary() -> dict[str, Any]:
    """Get overall LLM usage summary and cost statistics.

    Returns:
        - total_calls: Total number of API calls
        - total_cost_usd: Total cost in USD
        - models: Dict with model names and their statistics
    """
    tracker = get_tracker()
    return tracker.get_summary()


@router.get("/calls-by-stage/{stage}")
async def get_calls_by_stage(stage: str) -> list[dict[str, Any]]:
    """Get all LLM calls for a specific pipeline stage.

    Args:
        stage: Pipeline stage name (policy_tier1, policy_tier2, personnel_enrichment, etc.)

    Returns:
        List of call records for that stage
    """
    tracker = get_tracker()
    calls = tracker.get_calls_by_stage(stage)
    return {
        "stage": stage,
        "call_count": len(calls),
        "calls": calls,
    }


@router.get("/calls-by-article/{article_id}")
async def get_calls_by_article(article_id: str) -> list[dict[str, Any]]:
    """Get all LLM calls for a specific article.

    Args:
        article_id: URL hash of the article

    Returns:
        List of call records for that article
    """
    tracker = get_tracker()
    calls = tracker.get_calls_by_article(article_id)
    return {
        "article_id": article_id,
        "call_count": len(calls),
        "calls": calls,
    }


@router.get("/audit-trail")
async def get_audit_trail(
    limit: int = Query(100, ge=1, le=1000),
    stage: str | None = None,
    start_date: str | None = None,
) -> dict[str, Any]:
    """Export audit trail of LLM calls for review.

    Args:
        limit: Maximum number of records to return (default 100, max 1000)
        stage: Filter by pipeline stage (optional)
        start_date: Filter from ISO date YYYY-MM-DD (optional)

    Returns:
        - record_count: Number of records returned
        - records: List of call records
        - filters_applied: Summary of applied filters
    """
    tracker = get_tracker()
    records = tracker.export_audit_trail(limit=limit, stage=stage, start_date=start_date)

    filters: dict[str, Any] = {}
    if stage:
        filters["stage"] = stage
    if start_date:
        filters["start_date"] = start_date
    filters["limit"] = limit

    return {
        "record_count": len(records),
        "records": records,
        "filters_applied": filters,
    }


@router.get("/cost-by-model")
async def get_cost_by_model() -> dict[str, Any]:
    """Get cost breakdown by model.

    Returns:
        - summary: Overall total cost
        - by_model: Cost breakdown for each model
    """
    tracker = get_tracker()
    summary = tracker.get_summary()

    by_model = {}
    for model_name, stats in summary.get("models", {}).items():
        by_model[model_name] = {
            "call_count": stats.get("call_count", 0),
            "success_count": stats.get("success_count", 0),
            "error_count": stats.get("error_count", 0),
            "total_tokens": (
                stats.get("total_input_tokens", 0) + stats.get("total_output_tokens", 0)
            ),
            "input_tokens": stats.get("total_input_tokens", 0),
            "output_tokens": stats.get("total_output_tokens", 0),
            "total_cost_usd": stats.get("total_cost_usd", 0.0),
            "avg_cost_per_call": (
                stats.get("total_cost_usd", 0.0) / stats.get("call_count", 1)
                if stats.get("call_count", 0) > 0
                else 0.0
            ),
        }

    return {
        "generated_at": datetime.now().isoformat(),
        "total_cost_usd": summary.get("total_cost_usd", 0.0),
        "total_calls": summary.get("total_calls", 0),
        "by_model": by_model,
    }


@router.get("/health")
async def llm_tracking_health() -> dict[str, Any]:
    """Check LLM tracking system health."""
    return {
        "status": "healthy",
        "tracking_enabled": True,
        "message": "LLM API call tracking is active",
    }
