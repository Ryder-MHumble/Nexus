from fastapi import APIRouter, HTTPException

from app.schemas.common import ErrorResponse
from app.schemas.crawl_log import CrawlLogResponse
from app.schemas.source import SourceResponse, SourceUpdate
from app.services import crawl_service, source_service

router = APIRouter()


@router.get(
    "",
    response_model=list[SourceResponse],
    summary="信源列表",
    description="查询所有信源及其状态信息，可按维度过滤。",
)
async def list_sources(
    dimension: str | None = None,
):
    return await source_service.list_sources(dimension)


@router.get(
    "/{source_id}",
    response_model=SourceResponse,
    summary="信源详情",
    description="根据信源 ID 获取详细配置和运行状态。",
    responses={404: {"model": ErrorResponse, "description": "信源不存在"}},
)
async def get_source(
    source_id: str,
):
    source = await source_service.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.get(
    "/{source_id}/logs",
    response_model=list[CrawlLogResponse],
    summary="爬取日志",
    description="获取指定信源的最近爬取日志，默认返回最近 20 条。",
)
async def get_source_logs(
    source_id: str,
    limit: int = 20,
):
    return await crawl_service.get_crawl_logs(source_id=source_id, limit=limit)


@router.patch(
    "/{source_id}",
    response_model=SourceResponse,
    summary="启用/禁用信源",
    description="更新信源的启用状态。禁用后调度器将不再为该信源创建爬取任务。",
    responses={404: {"model": ErrorResponse, "description": "信源不存在"}},
)
async def update_source(
    source_id: str,
    data: SourceUpdate,
):
    source = await source_service.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if data.is_enabled is not None:
        return await source_service.update_source(source_id, data.is_enabled)
    return source


@router.post(
    "/{source_id}/trigger",
    summary="手动触发爬取",
    description="立即触发指定信源的一次爬取任务，不影响定时调度。",
    responses={
        404: {"model": ErrorResponse, "description": "信源不存在"},
        503: {"model": ErrorResponse, "description": "调度器未运行"},
    },
)
async def trigger_crawl(source_id: str):
    source = await source_service.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    from app.scheduler.manager import get_scheduler_manager

    manager = get_scheduler_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Scheduler not running")
    await manager.trigger_source(source_id)
    return {"status": "triggered", "source_id": source_id}
