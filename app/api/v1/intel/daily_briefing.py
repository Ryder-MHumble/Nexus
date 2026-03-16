"""Daily Briefing API endpoints — AI 早报."""
from datetime import date

from fastapi import APIRouter, Query

from app.schemas.intel.daily_briefing import DailyBriefingResponse, MetricsOnlyResponse
from app.services.intel.daily_briefing import service as briefing_service

router = APIRouter()


@router.get(
    "/report",
    response_model=DailyBriefingResponse,
    summary="获取 AI 早报",
    description=(
        "获取 AI 生成的每日早报。包含叙事段落（带交互链接）和聚合指标卡片。\n\n"
        "默认返回今日报告。如果今日报告尚未生成（Pipeline 未运行），将实时生成。\n\n"
        "段落格式为 `BriefingSegment[][]`，每个 segment 是字符串或 "
        "`{text, moduleId, action?}` 链接对象。"
    ),
)
async def get_daily_briefing(
    target_date: date | None = Query(
        None,
        description="目标日期（默认今天），格式 YYYY-MM-DD",
    ),
    force: bool = Query(
        False,
        description="强制重新生成（忽略缓存）",
    ),
):
    return await briefing_service.get_daily_briefing(
        target_date=target_date,
        force_regenerate=force,
    )


@router.get(
    "/metrics",
    response_model=MetricsOnlyResponse,
    summary="获取早报指标卡片",
    description="仅获取聚合指标卡片数据（无 LLM 叙事），实时计算。",
)
async def get_briefing_metrics(
    target_date: date | None = Query(
        None,
        description="目标日期（默认今天），格式 YYYY-MM-DD",
    ),
):
    return await briefing_service.get_metric_cards_only(target_date=target_date)
