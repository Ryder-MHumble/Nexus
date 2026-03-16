"""University Ecosystem (高校生态) API endpoints."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.schemas.intel.university import (
    ResearchOutputsResponse,
    UniversityArticleDetail,
    UniversityFeedResponse,
    UniversityOverviewResponse,
    UniversitySourcesResponse,
)
from app.services.intel.university import service as uni_service

router = APIRouter()


@router.get(
    "/overview",
    response_model=UniversityOverviewResponse,
    summary="高校生态总览",
    description="获取高校生态仪表盘数据：各分组文章数、今日新增、信源数。",
)
async def get_overview():
    return await uni_service.get_overview()


@router.get(
    "/feed",
    response_model=UniversityFeedResponse,
    summary="高校动态 Feed",
    description=(
        "获取高校动态分页文章列表。支持按分组、信源、关键词、日期范围过滤，"
        "按发布时间倒序排列。"
    ),
)
async def get_feed(
    group: str | None = Query(
        None, description="按分组过滤 (university_news/ai_institutes 等)",
    ),
    source_id: str | None = Query(None, description="按单个信源 ID 筛选（精确匹配）"),
    source_ids: str | None = Query(None, description="按多个信源 ID 筛选（逗号分隔，精确匹配）"),
    source_name: str | None = Query(None, description="按单个信源名称筛选（模糊匹配）"),
    source_names: str | None = Query(None, description="按多个信源名称筛选（逗号分隔，模糊匹配）"),
    keyword: str | None = Query(None, description="标题关键词搜索"),
    date_from: date | None = Query(None, description="起始日期 (YYYY-MM-DD)"),
    date_to: date | None = Query(None, description="截止日期 (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数"),
):
    return await uni_service.get_feed(
        group=group,
        source_id=source_id,
        source_ids=source_ids,
        source_name=source_name,
        source_names=source_names,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/article/{url_hash}",
    response_model=UniversityArticleDetail,
    summary="高校文章详情",
    description="根据 url_hash 获取单篇文章的完整内容，包含富文本 HTML 和图片列表。",
    responses={404: {"description": "文章未找到"}},
)
async def get_article(url_hash: str):
    result = await uni_service.get_article_detail(url_hash)
    if result is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return result


@router.get(
    "/sources",
    response_model=UniversitySourcesResponse,
    summary="高校信源列表",
    description="获取高校维度下所有信源的配置及最新爬取状态。",
)
async def get_sources(
    group: str | None = Query(None, description="按分组过滤"),
):
    return await uni_service.get_sources(group=group)


@router.get(
    "/research",
    response_model=ResearchOutputsResponse,
    summary="高校科研成果",
    description=(
        "获取经规则引擎分类的科研成果列表（论文/专利/获奖）。"
        "数据来自 data/processed/university_eco/research_outputs.json，"
        "由 process_university_eco 管线生成。"
    ),
)
async def get_research(
    type: str | None = Query(
        None, description="按成果类型过滤 (论文/专利/获奖)",
    ),
    influence: str | None = Query(
        None, description="按影响力过滤 (高/中/低)",
    ),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页条数"),
):
    return uni_service.get_research_outputs(
        rtype=type,
        influence=influence,
        page=page,
        page_size=page_size,
    )
