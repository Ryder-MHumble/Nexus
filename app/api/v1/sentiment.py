"""Sentiment monitoring API — social media data from Supabase."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.sentiment import (
    SentimentContentDetail,
    SentimentFeedResponse,
    SentimentOverview,
)
from app.services import sentiment_service

router = APIRouter()


@router.get(
    "/overview",
    response_model=SentimentOverview,
    summary="舆情概览统计",
    description="返回社媒舆情的整体统计数据：各平台内容数量、互动指标汇总、热门内容 Top5、"
    "监测关键词列表。",
)
async def overview():
    return await sentiment_service.get_overview()


@router.get(
    "/feed",
    response_model=SentimentFeedResponse,
    summary="社媒内容信息流",
    description="分页返回社媒内容列表，支持按平台和关键词过滤，按时间或互动量排序。",
)
async def feed(
    platform: str | None = Query(None, description="平台过滤: xhs / dy / bilibili / weibo"),
    keyword: str | None = Query(None, description="标题/描述/作者关键词搜索"),
    sort_by: str = Query(
        "publish_time",
        description="排序字段: publish_time / liked_count / comment_count / share_count",
    ),
    sort_order: str = Query("desc", description="排序方向: asc / desc"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    return await sentiment_service.get_feed(
        platform=platform,
        keyword=keyword,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/content/{content_id}",
    response_model=SentimentContentDetail,
    summary="内容详情 + 评论",
    description="返回单条社媒内容的完整信息及其全部评论。",
    responses={404: {"description": "Content not found"}},
)
async def content_detail(content_id: str):
    result = await sentiment_service.get_content_detail(content_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Content not found")
    return result
