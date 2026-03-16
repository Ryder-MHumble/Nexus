from fastapi import APIRouter

from app.api.v1 import (
    aminer,
    articles,
    crawler_control,
    dimensions,
    events,
    health,
    institutions,
    llm_tracking,
    projects,
    scholars,
    sentiment,
    sources,
    venues,
)
from app.api.v1.intel.router import intel_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(articles.router, prefix="/articles", tags=["articles"])
v1_router.include_router(sources.router, prefix="/sources", tags=["sources"])
v1_router.include_router(crawler_control.router, prefix="/crawler", tags=["crawler-control"])
v1_router.include_router(health.router, prefix="/health", tags=["health"])
v1_router.include_router(dimensions.router, prefix="/dimensions", tags=["dimensions"])
v1_router.include_router(intel_router, prefix="/intel", tags=["intel"])
v1_router.include_router(sentiment.router, prefix="/sentiment", tags=["sentiment"])
v1_router.include_router(llm_tracking.router)
v1_router.include_router(scholars.router, prefix="/scholars", tags=["scholars"])
v1_router.include_router(events.router, prefix="/events", tags=["events"])
v1_router.include_router(aminer.router, prefix="/aminer", tags=["aminer"])
v1_router.include_router(projects.router, prefix="/projects", tags=["projects"])
v1_router.include_router(venues.router, prefix="/venues", tags=["venues"])
# institutions.router 包含 /{institution_id} 通配符路由，必须最后注册
v1_router.include_router(institutions.router, prefix="/institutions", tags=["institutions"])
