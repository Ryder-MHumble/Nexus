"""Venues API — 顶会/期刊（学术社群）."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.venue import (
    VenueBatchResult,
    VenueCreate,
    VenueDetailResponse,
    VenueListResponse,
    VenueStatsResponse,
    VenueUpdate,
)
from app.services.core import venue_service as svc

router = APIRouter()


@router.get(
    "",
    response_model=VenueListResponse,
    summary="获取顶会/期刊列表",
    description="分页查询 venues 列表，支持按类型、级别、研究领域、关键词过滤。",
)
async def list_venues(
    type: str | None = Query(None, description="类型过滤：conference（顶会）| journal（期刊）"),
    rank: str | None = Query(None, description="级别过滤：A* | A | B | C"),
    field: str | None = Query(None, description="研究领域过滤（精确匹配，如 机器学习）"),
    keyword: str | None = Query(None, description="关键词模糊搜索（name/full_name/description）"),
    is_active: bool | None = Query(None, description="是否活跃"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
):
    return await svc.get_venue_list(
        type=type,
        rank=rank,
        field=field,
        keyword=keyword,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/stats",
    response_model=VenueStatsResponse,
    summary="顶会/期刊统计",
    description="返回按类型、级别、研究领域的聚合统计。",
)
async def get_venue_stats():
    return await svc.get_venue_stats()


@router.get(
    "/{venue_id}",
    response_model=VenueDetailResponse,
    summary="获取顶会/期刊详情",
)
async def get_venue(venue_id: str):
    result = await svc.get_venue_detail(venue_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Venue '{venue_id}' not found")
    return result


@router.post(
    "",
    response_model=VenueDetailResponse,
    status_code=201,
    summary="创建顶会/期刊",
)
async def create_venue(data: VenueCreate):
    return await svc.create_venue(data)


@router.patch(
    "/{venue_id}",
    response_model=VenueDetailResponse,
    summary="更新顶会/期刊",
    description="部分更新，仅传入需要修改的字段。custom_fields 支持浅合并（值为 null 删除 key）。",
)
async def update_venue(venue_id: str, data: VenueUpdate):
    result = await svc.update_venue(venue_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Venue '{venue_id}' not found")
    return result


@router.delete(
    "/{venue_id}",
    status_code=204,
    summary="删除顶会/期刊",
)
async def delete_venue(venue_id: str):
    ok = await svc.delete_venue(venue_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Venue '{venue_id}' not found")


@router.post(
    "/batch",
    response_model=VenueBatchResult,
    status_code=200,
    summary="批量导入顶会/期刊",
    description="批量创建，已存在（同名）的条目自动跳过。",
)
async def batch_create_venues(items: list[VenueCreate]):
    return await svc.batch_create_venues([item.model_dump() for item in items])
