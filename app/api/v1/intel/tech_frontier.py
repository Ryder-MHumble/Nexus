"""Tech Frontier (科技前沿) API endpoints."""
from fastapi import APIRouter, HTTPException, Query

from app.schemas.intel.tech_frontier import (
    TechFrontierOpportunitiesResponse,
    TechFrontierSignalsResponse,
    TechFrontierStatsResponse,
    TechFrontierTopicsResponse,
)
from app.services.intel.tech_frontier import service as tf_service

router = APIRouter()


@router.get(
    "/topics",
    response_model=TechFrontierTopicsResponse,
    summary="科技前沿主题列表",
    description="获取 8 个技术主题的完整数据，包含热度趋势、产业新闻、KOL 言论、AI 分析等。"
    "支持按热度趋势、院方布局状态和关键词过滤。",
)
async def get_topics(
    heat_trend: str | None = Query(
        None, description="热度趋势: surging / rising / stable / declining"
    ),
    our_status: str | None = Query(
        None, description="院方布局状态: deployed / weak / none"
    ),
    keyword: str | None = Query(
        None, description="关键词搜索（主题名/描述/标签）"
    ),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    return tf_service.get_topics(
        heat_trend=heat_trend,
        our_status=our_status,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/topics/{topic_id}",
    summary="单个主题详情",
    description="获取指定技术主题的完整详情，包含所有内嵌信号数据。",
)
async def get_topic_detail(topic_id: str):
    topic = tf_service.get_topic_detail(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    return topic


@router.get(
    "/opportunities",
    response_model=TechFrontierOpportunitiesResponse,
    summary="科技前沿机会列表",
    description="获取检测到的科技前沿机会（会议、合作、内参），支持按优先级和类型过滤。",
)
async def get_opportunities(
    priority: str | None = Query(
        None, description="优先级: 紧急 / 高 / 中 / 低"
    ),
    type: str | None = Query(
        None, alias="type", description="类型: 合作 / 会议 / 内参"
    ),
    keyword: str | None = Query(
        None, description="关键词搜索（名称/摘要）"
    ),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    return tf_service.get_opportunities(
        priority=priority,
        opp_type=type,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/stats",
    response_model=TechFrontierStatsResponse,
    summary="科技前沿 KPI 统计",
    description="获取科技前沿 KPI 汇总统计，包含主题数、飙升主题、缺口数、"
    "信号总量、机会数以及维度/主题分布。",
)
async def get_stats():
    return tf_service.get_stats()


@router.get(
    "/signals",
    response_model=TechFrontierSignalsResponse,
    summary="扁平信号流",
    description="获取所有主题的产业新闻和 KOL 言论，按时间倒序排列的扁平列表。"
    "支持按主题、信号类型和关键词过滤。",
)
async def get_signals(
    topic_id: str | None = Query(
        None, description="主题 ID 过滤"
    ),
    signal_type: str | None = Query(
        None, description="信号类型: news / kol"
    ),
    keyword: str | None = Query(
        None, description="关键词搜索"
    ),
    source_id: str | None = Query(None, description="按单个信源 ID 筛选（精确匹配）"),
    source_ids: str | None = Query(None, description="按多个信源 ID 筛选（逗号分隔，精确匹配）"),
    source_name: str | None = Query(None, description="按单个信源名称筛选（模糊匹配）"),
    source_names: str | None = Query(None, description="按多个信源名称筛选（逗号分隔，模糊匹配）"),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    return tf_service.get_signals(
        topic_id=topic_id,
        signal_type=signal_type,
        keyword=keyword,
        source_id=source_id,
        source_ids=source_ids,
        source_name=source_name,
        source_names=source_names,
        limit=limit,
        offset=offset,
    )
