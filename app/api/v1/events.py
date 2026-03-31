"""Event API — /api/v1/events/

Endpoints:
  GET    /events/                          活动列表（分页 + 筛选）
  GET    /events/stats                     统计数据
  GET    /events/taxonomy                  获取三级分类树
  POST   /events/taxonomy                  新增分类节点
  PATCH  /events/taxonomy/{node_id}        更新分类节点
  DELETE /events/taxonomy/{node_id}        删除分类节点（级联删子节点）
  GET    /events/{id}                      活动详情
  POST   /events/                          创建活动
  POST   /events/batch                     批量创建活动
  PATCH  /events/{id}                      更新活动
  DELETE /events/{id}                      删除活动
  GET    /events/{id}/scholars             获取关联学者列表
  POST   /events/{id}/scholars             添加学者关联
  DELETE /events/{id}/scholars/{scholar_id} 移除学者关联
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.schemas.event import (
    EventCreate,
    EventDetailResponse,
    EventListResponse,
    EventStatsResponse,
    EventUpdate,
    ScholarAssociation,
    TaxonomyCreate,
    TaxonomyNode,
    TaxonomyTree,
    TaxonomyUpdate,
)
from app.services import event_service as svc

router = APIRouter()


class EventBatchRequest(BaseModel):
    items: list[EventCreate]
    skip_duplicates: bool = True


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=EventListResponse,
    summary="活动列表",
    description=(
        "获取活动列表，支持三级分类筛选（category/series/event_type）、日期范围、"
        "关联学者、关键词筛选，按日期倒序排列。"
    ),
)
async def list_events(
    category: str | None = Query(None, description="一级分类筛选（精确匹配，如：科研学术/教育培养/人才引育）"),
    event_type: str | None = Query(None, description="活动类型筛选（精确匹配，如：学术前沿讲座/前沿沙龙）"),
    series: str | None = Query(None, description="二级系列筛选（精确匹配，如：XAI智汇讲坛/国际AI科学家大会）"),
    start_date: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    scholar_id: str | None = Query(None, description="按关联学者筛选"),
    keyword: str | None = Query(None, description="关键词搜索（标题/摘要/讲者）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
    custom_field_key: str | None = Query(None, description="自定义字段名"),
    custom_field_value: str | None = Query(None, description="自定义字段值"),
):
    return await svc.get_event_list(
        category=category,
        event_type=event_type,
        series=series,
        start_date=start_date,
        end_date=end_date,
        scholar_id=scholar_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
        custom_field_key=custom_field_key,
        custom_field_value=custom_field_value,
    )


@router.get(
    "/stats",
    response_model=EventStatsResponse,
    summary="活动统计",
    description="返回活动总览统计：总数、按一级分类/系列/类型/月份分布、活动-学者关联总数。",
)
async def get_stats():
    return await svc.get_event_stats()


# ---------------------------------------------------------------------------
# Taxonomy endpoints (must be before /{event_id} to avoid route conflict)
# ---------------------------------------------------------------------------


@router.get(
    "/taxonomy",
    response_model=TaxonomyTree,
    summary="获取三级分类树",
    description=(
        "返回完整的三级活动分类树。\n\n"
        "- **L1**：一级分类（教育培养 / 科研学术 / 人才引育），可自定义新增\n"
        "- **L2**：二级系列/品牌（XAI智汇讲坛 / 国际AI科学家大会 等），隶属某个一级分类\n"
        "- **L3**：活动类型（学术前沿讲座 / 前沿沙龙 等），隶属某个二级系列\n\n"
        "前端左侧导航栏可直接用此接口渲染。"
    ),
)
async def get_taxonomy():
    return await svc.get_taxonomy_tree()


@router.post(
    "/taxonomy",
    response_model=TaxonomyNode,
    summary="新增分类节点",
    description=(
        "新增一个分类节点（L1/L2/L3）。\n\n"
        "- 新增一级分类：`level=1`，`parent_id` 留空\n"
        "- 新增二级系列：`level=2`，`parent_id` 填一级分类的 UUID\n"
        "- 新增活动类型：`level=3`，`parent_id` 填二级系列的 UUID\n\n"
        "同层同父节点下名称不能重复。"
    ),
    status_code=201,
)
async def create_taxonomy_node(body: TaxonomyCreate):
    try:
        return await svc.create_taxonomy_node(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.patch(
    "/taxonomy/{node_id}",
    response_model=TaxonomyNode,
    summary="更新分类节点",
    description="更新分类节点的名称或排序权重（sort_order）。",
)
async def update_taxonomy_node(node_id: str, body: TaxonomyUpdate):
    result = await svc.update_taxonomy_node(node_id, body.model_dump(exclude_none=True))
    if result is None:
        raise HTTPException(status_code=404, detail=f"Taxonomy node '{node_id}' not found")
    return result


@router.delete(
    "/taxonomy/{node_id}",
    summary="删除分类节点",
    description=(
        "删除指定分类节点。\n\n"
        "**注意**：删除一级分类会级联删除其下所有二级系列和活动类型；"
        "删除二级系列会级联删除其下所有活动类型。"
        "已关联该分类的活动数据**不会**被删除，仅分类定义被移除。"
    ),
    status_code=204,
)
async def delete_taxonomy_node(node_id: str):
    deleted = await svc.delete_taxonomy_node(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Taxonomy node '{node_id}' not found")


# ---------------------------------------------------------------------------
# Event detail / write endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{event_id}",
    response_model=EventDetailResponse,
    summary="活动详情",
    description="根据活动 ID 获取完整活动信息（分类、时间地点、摘要、关联学者等）。",
)
async def get_event(event_id: str):
    result = await svc.get_event_detail(event_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return result


@router.post(
    "",
    response_model=EventDetailResponse,
    summary="创建活动",
    description=(
        "创建新的活动记录。ID 自动生成（UUID）。\n\n"
        "建议先调用 `GET /events/taxonomy` 获取可用的 category/series/event_type 标签值，"
        "再填入对应字段并关联学者。"
    ),
    status_code=201,
)
async def create_event(body: EventCreate):
    return await svc.create_event(body.model_dump())


@router.post(
    "/batch",
    summary="批量创建活动",
    description=(
        "通过 JSON 列表批量创建活动。\n\n"
        "**重复判定：** 相同标题 + 相同日期 + 相同系列 + 相同活动类型视为重复，"
        "skip_duplicates=true 时跳过，false 时报错。\n\n"
        "**返回：** 每条记录的处理结果汇总。"
    ),
    status_code=200,
)
async def batch_create_events(body: EventBatchRequest):
    items = [item.model_dump() for item in body.items]
    return await svc.batch_create_events(items=items, skip_duplicates=body.skip_duplicates)


@router.patch(
    "/{event_id}",
    response_model=EventDetailResponse,
    summary="更新活动",
    description="更新指定活动的信息。所有字段均可选，仅传入需要修改的字段。",
)
async def update_event(event_id: str, body: EventUpdate):
    updates = body.model_dump(exclude_none=True)
    result = await svc.update_event(event_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return result


@router.delete(
    "/{event_id}",
    summary="删除活动",
    description="删除指定的活动记录。",
    status_code=204,
)
async def delete_event(event_id: str):
    deleted = await svc.delete_event(event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")


# ---------------------------------------------------------------------------
# Scholar association endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{event_id}/scholars",
    response_model=list[str],
    summary="获取活动关联的学者列表",
    description="返回指定活动关联的所有学者 url_hash 列表。",
)
async def get_event_scholars(event_id: str):
    result = await svc.get_event_scholars(event_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return result


@router.post(
    "/{event_id}/scholars",
    response_model=EventDetailResponse,
    summary="添加学者关联",
    description="为指定活动添加学者关联。如果学者已关联则不重复添加。",
    status_code=201,
)
async def add_scholar_to_event(event_id: str, body: ScholarAssociation):
    result = await svc.add_scholar_to_event(event_id, body.scholar_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return result


@router.delete(
    "/{event_id}/scholars/{scholar_id}",
    response_model=EventDetailResponse,
    summary="移除学者关联",
    description="移除指定活动与学者的关联关系。",
)
async def remove_scholar_from_event(event_id: str, scholar_id: str):
    result = await svc.remove_scholar_from_event(event_id, scholar_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
    return result
