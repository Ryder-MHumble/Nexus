"""Policy Intelligence API endpoints."""
from fastapi import APIRouter, Query

from app.schemas.intel.policy import PolicyFeedResponse, PolicyOpportunitiesResponse
from app.services.intel.policy import service as policy_service

router = APIRouter()


@router.get(
    "/feed",
    response_model=PolicyFeedResponse,
    summary="政策动态 Feed",
    description="获取政策情报动态列表。支持按分类、重要性、匹配度过滤，以及关键词搜索。\n\n"
    "数据经过规则引擎 + LLM 二级管线处理，包含匹配度评分、资金信息、AI 洞察等富化字段。",
)
async def get_policy_feed(
    category: str | None = Query(
        None, description="政策分类: 国家政策 / 北京政策 / 领导讲话 / 政策机会"
    ),
    importance: str | None = Query(
        None, description="重要性级别: 紧急 / 重要 / 关注 / 一般"
    ),
    min_match_score: int | None = Query(
        None, ge=0, le=100, description="最低匹配度得分"
    ),
    keyword: str | None = Query(
        None, description="关键词搜索（标题/摘要/来源/标签）"
    ),
    source_id: str | None = Query(None, description="按单个信源 ID 筛选（精确匹配）"),
    source_ids: str | None = Query(None, description="按多个信源 ID 筛选（逗号分隔，精确匹配）"),
    source_name: str | None = Query(None, description="按单个信源名称筛选（模糊匹配）"),
    source_names: str | None = Query(None, description="按多个信源名称筛选（逗号分隔，模糊匹配）"),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    return policy_service.get_policy_feed(
        category=category,
        importance=importance,
        min_match_score=min_match_score,
        keyword=keyword,
        source_id=source_id,
        source_ids=source_ids,
        source_name=source_name,
        source_names=source_names,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/opportunities",
    response_model=PolicyOpportunitiesResponse,
    summary="政策机会看板",
    description="获取政策申报机会列表，用于情报看板展示。"
    "包含资金规模、截止日期、匹配度评分、紧急状态等关键字段。",
)
async def get_policy_opportunities(
    status: str | None = Query(
        None, description="状态过滤: urgent / active / tracking"
    ),
    min_match_score: int | None = Query(
        None, ge=0, le=100, description="最低匹配度得分"
    ),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    return policy_service.get_policy_opportunities(
        status=status,
        min_match_score=min_match_score,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/stats",
    summary="政策统计",
    description="获取已处理政策数据的汇总统计信息。",
)
async def get_policy_stats():
    return policy_service.get_policy_stats()
