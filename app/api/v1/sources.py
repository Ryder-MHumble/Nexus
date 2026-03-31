from fastapi import APIRouter, HTTPException, Query

from app.schemas.common import ErrorResponse
from app.schemas.crawl_log import CrawlLogResponse
from app.schemas.source import (
    SourceCatalogResponse,
    SourceFacetsResponse,
    SourceResponse,
    SourceUpdate,
)
from app.services import crawl_service, source_service

router = APIRouter()


@router.get(
    "",
    response_model=list[SourceResponse],
    summary="信源列表",
    description="查询所有信源及其状态信息，可按维度过滤。",
)
async def list_sources(
    dimension: str | None = Query(default=None, description="按单个维度过滤"),
    dimensions: str | None = Query(default=None, description="按多个维度过滤（逗号分隔）"),
    group: str | None = Query(default=None, description="按单个分组过滤"),
    groups: str | None = Query(default=None, description="按多个分组过滤（逗号分隔）"),
    tag: str | None = Query(default=None, description="按单个标签过滤"),
    tags: str | None = Query(default=None, description="按多个标签过滤（逗号分隔，OR 关系）"),
    crawl_method: str | None = Query(default=None, description="按爬取方式过滤"),
    schedule: str | None = Query(default=None, description="按调度频率过滤"),
    is_enabled: bool | None = Query(default=None, description="按启用状态过滤"),
    health_status: str | None = Query(default=None, description="按健康状态过滤"),
    health_statuses: str | None = Query(
        default=None, description="按多个健康状态过滤（逗号分隔）"
    ),
    keyword: str | None = Query(default=None, description="关键词（匹配 ID/名称/分组/标签/URL）"),
    sort_by: str = Query(default="dimension_priority", description="排序字段"),
    order: str = Query(default="asc", description="排序方向: asc | desc"),
):
    return await source_service.list_sources(
        dimension,
        dimensions=dimensions,
        group=group,
        groups=groups,
        tag=tag,
        tags=tags,
        crawl_method=crawl_method,
        schedule=schedule,
        is_enabled=is_enabled,
        health_status=health_status,
        health_statuses=health_statuses,
        keyword=keyword,
        sort_by=sort_by,
        order=order,
    )


@router.get(
    "/catalog",
    response_model=SourceCatalogResponse,
    summary="信源目录（分页 + 分面）",
    description=(
        "信源全景目录接口。支持多维筛选、分页、排序，并返回分面聚合，适合前端/Agent 构建"
        "“按维度快速理解信源结构”的检索体验。"
    ),
)
async def list_sources_catalog(
    dimension: str | None = Query(default=None, description="按单个维度过滤"),
    dimensions: str | None = Query(default=None, description="按多个维度过滤（逗号分隔）"),
    group: str | None = Query(default=None, description="按单个分组过滤"),
    groups: str | None = Query(default=None, description="按多个分组过滤（逗号分隔）"),
    tag: str | None = Query(default=None, description="按单个标签过滤"),
    tags: str | None = Query(default=None, description="按多个标签过滤（逗号分隔，OR 关系）"),
    crawl_method: str | None = Query(default=None, description="按爬取方式过滤"),
    schedule: str | None = Query(default=None, description="按调度频率过滤"),
    is_enabled: bool | None = Query(default=None, description="按启用状态过滤"),
    health_status: str | None = Query(default=None, description="按健康状态过滤"),
    health_statuses: str | None = Query(
        default=None, description="按多个健康状态过滤（逗号分隔）"
    ),
    keyword: str | None = Query(default=None, description="关键词（匹配 ID/名称/分组/标签/URL）"),
    sort_by: str = Query(default="dimension_priority", description="排序字段"),
    order: str = Query(default="asc", description="排序方向: asc | desc"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=100, ge=1, le=500, description="每页条数"),
    include_facets: bool = Query(default=True, description="是否返回分面统计"),
):
    return await source_service.list_sources_catalog(
        dimension,
        dimensions=dimensions,
        group=group,
        groups=groups,
        tag=tag,
        tags=tags,
        crawl_method=crawl_method,
        schedule=schedule,
        is_enabled=is_enabled,
        health_status=health_status,
        health_statuses=health_statuses,
        keyword=keyword,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
        include_facets=include_facets,
    )


@router.get(
    "/facets",
    response_model=SourceFacetsResponse,
    summary="信源筛选分面",
    description="返回当前筛选条件下的维度/分组/标签/爬取方式/频率/健康状态分布。",
)
async def get_source_facets(
    dimension: str | None = Query(default=None, description="按单个维度过滤"),
    dimensions: str | None = Query(default=None, description="按多个维度过滤（逗号分隔）"),
    group: str | None = Query(default=None, description="按单个分组过滤"),
    groups: str | None = Query(default=None, description="按多个分组过滤（逗号分隔）"),
    tag: str | None = Query(default=None, description="按单个标签过滤"),
    tags: str | None = Query(default=None, description="按多个标签过滤（逗号分隔，OR 关系）"),
    crawl_method: str | None = Query(default=None, description="按爬取方式过滤"),
    schedule: str | None = Query(default=None, description="按调度频率过滤"),
    is_enabled: bool | None = Query(default=None, description="按启用状态过滤"),
    health_status: str | None = Query(default=None, description="按健康状态过滤"),
    health_statuses: str | None = Query(
        default=None, description="按多个健康状态过滤（逗号分隔）"
    ),
    keyword: str | None = Query(default=None, description="关键词（匹配 ID/名称/分组/标签/URL）"),
):
    return await source_service.list_source_facets(
        dimension,
        dimensions=dimensions,
        group=group,
        groups=groups,
        tag=tag,
        tags=tags,
        crawl_method=crawl_method,
        schedule=schedule,
        is_enabled=is_enabled,
        health_status=health_status,
        health_statuses=health_statuses,
        keyword=keyword,
    )


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
