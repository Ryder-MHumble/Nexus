"""Service layer: expose pipeline state, results, and trigger."""
from __future__ import annotations

import asyncio

from app.schemas.intel.paper_transfer import (
    PaperTransferResults,
    PipelineRunState,
    RunRequest,
    RunResponse,
)
from app.services.intel.paper_transfer.pipeline import (
    is_running,
    load_results,
    load_state,
    run_pipeline,
)


def get_status() -> PipelineRunState:
    """Return the current pipeline run state."""
    return load_state()


def get_results(
    grade: str | None = None,
    school: str | None = None,
    keyword: str | None = None,
) -> PaperTransferResults | None:
    """Load cached results and apply optional filters.

    Filtering is done in-memory after loading the JSON file.
    The aggregate stats (total_papers_analyzed, grade_counts) reflect the
    full unfiltered run; only `items` is narrowed down.
    """
    results = load_results()
    if results is None:
        return None

    items = results.items

    if grade:
        items = [c for c in items if c.grade == grade.upper()]

    if school:
        sf = school.lower()
        items = [c for c in items if sf in c.student.school_cn.lower()]

    if keyword:
        kw = keyword.lower()
        items = [
            c
            for c in items
            if kw in c.paper.title.lower()
            or (c.recommendation_reason and kw in c.recommendation_reason.lower())
        ]

    results.items = items
    return results


async def trigger_run(req: RunRequest) -> RunResponse:
    """Trigger a background pipeline run.

    Returns immediately. If a run is already active, returns "already_running".
    """
    if is_running():
        return RunResponse(
            status="already_running",
            message="Pipeline is already running. Poll GET /status for progress.",
        )
    asyncio.create_task(run_pipeline(req.date_from, req.school, req.max_papers, req.batch_size))
    return RunResponse(
        status="started",
        message=(
            "Pipeline started in background. "
            "Poll GET /status for progress and GET /results when completed."
        ),
    )
