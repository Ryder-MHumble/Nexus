"""Intel sub-router — aggregates all business intelligence endpoints."""
from fastapi import APIRouter

from app.api.v1.intel import (
    daily_briefing,
    paper_transfer,
    personnel,
    policy,
    tech_frontier,
    university,
)

intel_router = APIRouter()

intel_router.include_router(policy.router, prefix="/policy", tags=["policy-intel"])
intel_router.include_router(personnel.router, prefix="/personnel", tags=["personnel-intel"])
intel_router.include_router(
    daily_briefing.router, prefix="/daily-briefing", tags=["daily-briefing"],
)
intel_router.include_router(
    university.router, prefix="/university", tags=["university-eco"],
)
intel_router.include_router(
    tech_frontier.router, prefix="/tech-frontier", tags=["tech-frontier"],
)
intel_router.include_router(
    paper_transfer.router, prefix="/paper-transfer", tags=["paper-transfer"],
)
