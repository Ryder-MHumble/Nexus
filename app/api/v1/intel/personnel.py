"""Personnel Intelligence API endpoints."""
from fastapi import APIRouter, HTTPException, Query

from app.schemas.intel.personnel import (
    PersonnelChangesResponse,
    PersonnelEnrichedFeedResponse,
    PersonnelEnrichedStatsResponse,
    PersonnelFeedResponse,
)
from app.services.intel.intel_store import IntelDataLoadError
from app.services.intel.personnel import service as personnel_service

router = APIRouter()


def _call_personnel_service(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except IntelDataLoadError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/feed",
    response_model=PersonnelFeedResponse,
    summary="人事动态 Feed",
    description="获取人事情报动态列表（文章级别）。每条记录对应一篇人事相关文章，"
    "包含从文章中自动提取的任免变动列表。",
)
async def get_personnel_feed(
    importance: str | None = Query(
        None, description="重要性级别: 紧急 / 重要 / 关注 / 一般"
    ),
    min_match_score: int | None = Query(
        None, ge=0, le=100, description="最低匹配度得分"
    ),
    keyword: str | None = Query(
        None, description="关键词搜索（标题/姓名/职务）"
    ),
    source_id: str | None = Query(None, description="按单个信源 ID 筛选（精确匹配）"),
    source_ids: str | None = Query(None, description="按多个信源 ID 筛选（逗号分隔，精确匹配）"),
    source_name: str | None = Query(None, description="按单个信源名称筛选（模糊匹配）"),
    source_names: str | None = Query(None, description="按多个信源名称筛选（逗号分隔，模糊匹配）"),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    return _call_personnel_service(
        personnel_service.get_personnel_feed,
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
    "/changes",
    response_model=PersonnelChangesResponse,
    summary="结构化任免变动",
    description="获取结构化的人事任免变动列表，每条记录对应一个人员的一次任免动作。"
    "支持按部门、任免类型过滤。",
)
async def get_personnel_changes(
    department: str | None = Query(None, description="按部门过滤"),
    action: str | None = Query(None, description="任免类型: 任命 / 免去"),
    keyword: str | None = Query(
        None, description="关键词搜索（姓名/职务/部门）"
    ),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    return _call_personnel_service(
        personnel_service.get_personnel_changes,
        department=department,
        action=action,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/stats",
    summary="人事统计",
    description="获取人事数据的汇总统计信息。",
)
async def get_personnel_stats():
    return _call_personnel_service(personnel_service.get_personnel_stats)


@router.get(
    "/enriched-feed",
    response_model=PersonnelEnrichedFeedResponse,
    summary="LLM 富化人事动态",
    description="获取经 LLM 分析富化后的人事变动列表。相比基础 Feed，额外包含：\n\n"
    "- **relevance**: 与平台关注主题的相关性得分（0-100）\n"
    "- **group**: action（需行动）/ watch（关注即可）\n"
    "- **actionSuggestion**: LLM 建议的行动方案\n"
    "- **background**: 人员背景信息\n"
    "- **aiInsight**: AI 综合分析洞察",
)
async def get_enriched_feed(
    group: str | None = Query(
        None, description="分组过滤: action（需行动）/ watch（关注即可）"
    ),
    importance: str | None = Query(
        None, description="重要性级别: 紧急 / 重要 / 关注 / 一般"
    ),
    min_relevance: int | None = Query(
        None, ge=0, le=100, description="最低相关性得分"
    ),
    keyword: str | None = Query(
        None, description="关键词搜索（姓名/职务/部门/备注）"
    ),
    source_id: str | None = Query(None, description="按单个信源 ID 筛选（精确匹配）"),
    source_ids: str | None = Query(None, description="按多个信源 ID 筛选（逗号分隔，精确匹配）"),
    source_name: str | None = Query(None, description="按单个信源名称筛选（模糊匹配）"),
    source_names: str | None = Query(None, description="按多个信源名称筛选（逗号分隔，模糊匹配）"),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    return await personnel_service.get_enriched_feed(
        group=group,
        importance=importance,
        min_relevance=min_relevance,
        keyword=keyword,
        source_id=source_id,
        source_ids=source_ids,
        source_name=source_name,
        source_names=source_names,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/enriched-stats",
    response_model=PersonnelEnrichedStatsResponse,
    summary="富化数据统计",
    description="获取 LLM 富化人事数据的汇总统计，包括按部门/类型分布和高相关性记录数。",
)
async def get_enriched_stats():
    return await personnel_service.get_enriched_stats()
