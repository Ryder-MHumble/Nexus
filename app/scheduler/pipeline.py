"""Unified daily pipeline: crawl → process → LLM enrich → index → briefing.

Registered as a single APScheduler job. Each stage runs sequentially and
logs progress. If crawling fails, processing still runs on existing data/raw/.

Stage 4 (LLM enrichment) is conditional on ENABLE_LLM_ENRICHMENT + API key.
Stage 5 (index generation) always runs.
Stage 6 (daily briefing) always runs — uses LLM when available, fallback otherwise.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    """Result of a single pipeline stage."""

    name: str
    status: str = "pending"  # pending | running | success | failed
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float = 0.0
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class PipelineResult:
    """Result of a full pipeline run."""

    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    stages: list[StageResult] = field(default_factory=list)

    @property
    def status(self) -> str:
        statuses = {s.status for s in self.stages}
        if "failed" in statuses:
            return "partial_failure"
        if statuses <= {"success", "skipped"}:
            return "success"
        return "unknown"

    @property
    def duration_seconds(self) -> float:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": (
                self.finished_at.isoformat() if self.finished_at else None
            ),
            "duration_seconds": round(self.duration_seconds, 1),
            "stages": [
                {
                    "name": s.name,
                    "status": s.status,
                    "duration_seconds": round(s.duration_seconds, 1),
                    "summary": s.summary,
                    "error": s.error,
                }
                for s in self.stages
            ],
        }


# Module-level reference for last pipeline result (queryable via health API)
_last_pipeline_result: PipelineResult | None = None


def get_last_pipeline_result() -> PipelineResult | None:
    """Get the result of the most recent pipeline run."""
    return _last_pipeline_result


# ---------------------------------------------------------------------------
# Stage runner
# ---------------------------------------------------------------------------

async def _run_stage(name: str, func, **kwargs) -> StageResult:
    """Run a pipeline stage with timing and error isolation."""
    stage = StageResult(name=name, status="running")
    stage.started_at = datetime.now(timezone.utc)
    logger.info("=" * 70)
    logger.info("  Pipeline Stage: %s", name)
    logger.info("=" * 70)
    try:
        summary = await func(**kwargs)
        stage.status = "success"
        stage.summary = summary or {}
        logger.info("✓ Stage [%s] completed: %s", name, stage.summary)
    except Exception as e:
        stage.status = "failed"
        stage.error = str(e)
        logger.exception("✗ Stage [%s] failed: %s", name, e)
    finally:
        stage.finished_at = datetime.now(timezone.utc)
        stage.duration_seconds = (
            stage.finished_at - stage.started_at
        ).total_seconds()
        logger.info("  Duration: %.1fs", stage.duration_seconds)
    return stage


# ---------------------------------------------------------------------------
# Individual stages (lazy imports to avoid circular deps)
# ---------------------------------------------------------------------------

async def _stage_crawl_all() -> dict[str, Any]:
    """Stage 1: Crawl all enabled sources (JSON only, no DB)."""
    import sys
    from pathlib import Path

    # Ensure project root is importable for scripts/
    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from scripts.crawl.run_all import run_all

    logger.info("Stage 1: 开始爬取所有启用信源...")
    result = await run_all(strategy="grouped")
    return result or {}


async def _stage_process_policy() -> dict[str, Any]:
    """Stage 2: Process policy intelligence (rules-based)."""
    from app.services.intel.pipeline.policy_processor import (
        process_policy_pipeline,
    )

    return await process_policy_pipeline()


async def _stage_process_personnel() -> dict[str, Any]:
    """Stage 3: Process personnel intelligence (rules only)."""
    from app.services.intel.pipeline.personnel_processor import (
        process_personnel_pipeline,
    )

    return await process_personnel_pipeline()


async def _stage_enrich_policy_llm() -> dict[str, Any]:
    """Stage 4a: LLM enrichment for policy articles (conditional)."""
    from app.services.intel.pipeline.policy_processor import (
        process_policy_llm_enrichment,
    )

    return await process_policy_llm_enrichment()


async def _stage_enrich_personnel_llm() -> dict[str, Any]:
    """Stage 4b: LLM enrichment for personnel changes (conditional)."""
    from app.services.intel.pipeline.personnel_processor import (
        process_personnel_llm_enrichment,
    )

    return await process_personnel_llm_enrichment()


async def _stage_process_university_eco() -> dict[str, Any]:
    """Stage 3b: Process university ecosystem (keyword classification)."""
    from app.services.intel.pipeline.university_eco_processor import (
        process_university_eco_pipeline,
    )

    return await process_university_eco_pipeline()


async def _stage_process_tech_frontier() -> dict[str, Any]:
    """Stage 3c: Process tech frontier (topic classification + heat)."""
    from app.services.intel.pipeline.tech_frontier_processor import (
        process_tech_frontier_pipeline,
    )

    return await process_tech_frontier_pipeline()


async def _stage_enrich_tech_frontier_llm() -> dict[str, Any]:
    """Stage 4c: LLM enrichment for tech frontier topics (conditional)."""
    from app.services.intel.pipeline.tech_frontier_processor import (
        process_tech_frontier_llm_enrichment,
    )

    return await process_tech_frontier_llm_enrichment()


async def _stage_rebuild_institutions() -> dict[str, Any]:
    """Stage 4d: Rebuild institutions.json from scholar data."""
    import asyncio

    from app.services.core.institution_builder import (
        build_institutions_data,
        save_institutions_data,
    )

    data = await asyncio.to_thread(build_institutions_data)
    output_path = await asyncio.to_thread(save_institutions_data, data)

    universities = data.get("universities", [])
    total_universities = len(universities)
    total_departments = sum(len(u.get("departments", [])) for u in universities)
    total_scholars = sum(u.get("scholar_count", 0) for u in universities)

    return {
        "output_path": str(output_path),
        "total_universities": total_universities,
        "total_departments": total_departments,
        "total_scholars": total_scholars,
    }


async def _stage_generate_index() -> dict[str, Any]:
    """Stage 5: Generate data/index.json for frontend."""
    import asyncio
    import json
    import sys
    from pathlib import Path

    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from scripts.data.generate_index import INDEX_PATH, generate_index

    index = await asyncio.to_thread(generate_index)
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return {
        "total_sources": index["total_sources"],
        "total_enabled": index["total_enabled"],
        "total_articles": index["total_articles"],
        "dimensions": len(index["dimensions"]),
    }


async def _stage_generate_briefing() -> dict[str, Any]:
    """Stage 6: Generate AI daily briefing."""
    from app.services.intel.pipeline.briefing_processor import (
        process_daily_briefing,
    )

    return await process_daily_briefing()


def _skipped_stage(name: str, reason: str) -> StageResult:
    """Create a skipped stage result."""
    now = datetime.now(timezone.utc)
    return StageResult(
        name=name,
        status="skipped",
        started_at=now,
        finished_at=now,
        summary={"skipped": True, "reason": reason},
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def execute_daily_pipeline() -> PipelineResult:
    """Execute the full daily pipeline (10 stages).

    Stage 1:  Crawl all enabled sources
    Stage 2:  Process policy intelligence (rules)
    Stage 3:  Process personnel intelligence (rules)
    Stage 3b: Process university ecosystem (keyword classification)
    Stage 3c: Process tech frontier (topic classification + heat)
    Stage 4:  LLM enrichment — policy + personnel + tech_frontier (conditional)
    Stage 4d: Rebuild institutions.json from scholar data
    Stage 5:  Generate data index
    Stage 6:  Generate AI daily briefing

    Called by APScheduler daily. Each stage runs sequentially.
    If crawling fails, processing stages still run on existing data.
    """
    global _last_pipeline_result

    from app.config import settings

    pipeline = PipelineResult()

    logger.info("=" * 70)
    logger.info("  DAILY PIPELINE STARTING")
    logger.info("=" * 70)

    # Stage 1: Crawl all enabled sources
    crawl_stage = await _run_stage("crawl_all", _stage_crawl_all)
    pipeline.stages.append(crawl_stage)

    if crawl_stage.status == "failed":
        logger.warning(
            "Crawl stage failed — processing will run on existing data"
        )

    # Stage 2: Policy processing (rules)
    policy_stage = await _run_stage("process_policy", _stage_process_policy)
    pipeline.stages.append(policy_stage)

    # Stage 3: Personnel processing (rules)
    personnel_stage = await _run_stage(
        "process_personnel", _stage_process_personnel,
    )
    pipeline.stages.append(personnel_stage)

    # Stage 3b: University ecosystem processing (keyword classification)
    uni_eco_stage = await _run_stage(
        "process_university_eco", _stage_process_university_eco,
    )
    pipeline.stages.append(uni_eco_stage)

    # Stage 3c: Tech frontier processing (topic classification + heat)
    tf_stage = await _run_stage(
        "process_tech_frontier", _stage_process_tech_frontier,
    )
    pipeline.stages.append(tf_stage)

    # Stage 4: LLM enrichment (conditional)
    llm_enabled = settings.ENABLE_LLM_ENRICHMENT and settings.OPENROUTER_API_KEY
    if llm_enabled:
        llm_policy = await _run_stage(
            "enrich_policy_llm", _stage_enrich_policy_llm,
        )
        pipeline.stages.append(llm_policy)

        llm_personnel = await _run_stage(
            "enrich_personnel_llm", _stage_enrich_personnel_llm,
        )
        pipeline.stages.append(llm_personnel)

        llm_tech_frontier = await _run_stage(
            "enrich_tech_frontier_llm", _stage_enrich_tech_frontier_llm,
        )
        pipeline.stages.append(llm_tech_frontier)
    else:
        reason = (
            "OPENROUTER_API_KEY not set"
            if not settings.OPENROUTER_API_KEY
            else "ENABLE_LLM_ENRICHMENT=false"
        )
        pipeline.stages.append(_skipped_stage("enrich_policy_llm", reason))
        pipeline.stages.append(_skipped_stage("enrich_personnel_llm", reason))
        pipeline.stages.append(
            _skipped_stage("enrich_tech_frontier_llm", reason),
        )

    # Stage 4d: Rebuild institutions.json (always runs)
    institutions_stage = await _run_stage(
        "rebuild_institutions", _stage_rebuild_institutions,
    )
    pipeline.stages.append(institutions_stage)

    # Stage 5: Generate index (always runs)
    index_stage = await _run_stage("generate_index", _stage_generate_index)
    pipeline.stages.append(index_stage)

    # Stage 6: Generate daily briefing (always runs, fallback if no LLM)
    briefing_stage = await _run_stage(
        "generate_briefing", _stage_generate_briefing,
    )
    pipeline.stages.append(briefing_stage)

    pipeline.finished_at = datetime.now(timezone.utc)
    _last_pipeline_result = pipeline

    logger.info("=" * 70)
    logger.info(
        "  DAILY PIPELINE COMPLETE: %s (%.0fs)",
        pipeline.status, pipeline.duration_seconds,
    )
    for stage in pipeline.stages:
        if stage.status == "skipped":
            icon = "SKIP"
        elif stage.status == "success":
            icon = "OK"
        else:
            icon = "FAIL"
        logger.info(
            "    [%4s] %s (%.0fs)%s",
            icon, stage.name, stage.duration_seconds,
            f" ERROR: {stage.error}" if stage.error else "",
        )
    logger.info("=" * 70)

    return pipeline
