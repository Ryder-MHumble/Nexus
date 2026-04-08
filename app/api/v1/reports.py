"""
AI 分析报告 API

提供各维度的智能分析报告生成接口。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.client import get_client
from app.schemas.common import ErrorResponse
from app.schemas.report import (
    ReportGenerateRequest,
    ReportDimensionsListResponse,
    ReportMetadataResponse,
    ReportResponse,
)
from app.services.intel.reports.analyzers.sentiment import SentimentReportAnalyzer
from app.services.intel.reports.generator import ReportGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post(
    "/generate",
    response_model=ReportResponse,
    responses={
        400: {"model": ErrorResponse, "description": "不支持的报告维度"},
        500: {"model": ErrorResponse, "description": "报告生成失败"},
        501: {"model": ErrorResponse, "description": "该报告维度尚未实现"},
    },
)
async def generate_report(request: ReportGenerateRequest):
    """
    生成 AI 分析报告

    支持的维度：
    - sentiment: 舆情监测报告
    - policy: 政策分析报告（待实现）
    - technology: 科技前沿报告（待实现）
    - personnel: 人事情报报告（待实现）
    - university: 高校生态报告（待实现）
    """
    try:
        # 根据维度选择分析器
        if request.dimension == "sentiment":
            return await _generate_sentiment_report(request)
        elif request.dimension == "policy":
            raise HTTPException(
                status_code=501, detail="Policy report not implemented yet"
            )
        elif request.dimension == "technology":
            raise HTTPException(
                status_code=501, detail="Technology report not implemented yet"
            )
        elif request.dimension == "personnel":
            raise HTTPException(
                status_code=501, detail="Personnel report not implemented yet"
            )
        elif request.dimension == "university":
            raise HTTPException(
                status_code=501, detail="University report not implemented yet"
            )
        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown dimension: {request.dimension}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate report", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate report") from e


async def _generate_sentiment_report(
    request: ReportGenerateRequest,
) -> ReportResponse:
    """生成舆情监测报告"""

    # 1. 获取数据
    db = get_client()

    # 解析日期范围
    date_range = None
    start_date = None
    end_date = None
    if request.date_range:
        start_str, end_str = request.date_range
        start_date = datetime.fromisoformat(start_str)
        end_date = datetime.fromisoformat(end_str)
        date_range = (start_date, end_date)

    # 从数据库获取舆情数据
    query = db.table("sentiment_contents").select("*")

    # 限制数量
    query = query.limit(1000)

    result = await query.execute()
    contents = result.data or []

    # sentiment_contents.publish_time is bigint and may contain mixed seconds/ms.
    # Normalize and filter in Python for compatibility across historical data.
    if start_date or end_date:
        filtered: list[dict] = []
        for row in contents:
            raw_ts = row.get("publish_time")
            dt = _parse_publish_time(raw_ts)
            if dt is None:
                continue
            if start_date and dt < start_date:
                continue
            if end_date and dt > end_date:
                continue
            filtered.append(row)
        contents = filtered

    # 2. 生成报告
    analyzer = SentimentReportAnalyzer()
    generator = ReportGenerator(analyzer)

    report_content = await generator.generate(
        data=contents, date_range=date_range, output_format=request.output_format
    )

    # 3. 构建响应
    analysis_result = await analyzer.analyze(contents, date_range)

    return ReportResponse(
        metadata=ReportMetadataResponse(
            title=analysis_result.metadata.title,
            generated_at=analysis_result.metadata.generated_at,
            data_range=analysis_result.metadata.data_range,
            dimension=analysis_result.metadata.dimension,
            total_items=analysis_result.metadata.total_items,
            additional_info=analysis_result.metadata.additional_info,
        ),
        content=report_content,
        format=request.output_format,
    )


def _parse_publish_time(value: int | str | None) -> datetime | None:
    """Parse mixed sentiment publish_time (seconds or milliseconds)."""
    if value is None:
        return None
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    # >= 1e12 is treated as milliseconds.
    if ts >= 1_000_000_000_000:
        ts = ts // 1000
    try:
        return datetime.fromtimestamp(ts)
    except (OverflowError, OSError, ValueError):
        return None


@router.get("/sentiment/latest", response_model=ReportResponse)
async def get_latest_sentiment_report(
    days: int = Query(7, ge=1, le=30, description="最近N天的数据"),
    output_format: str = Query("markdown", description="输出格式"),
):
    """
    获取最新的舆情监测报告

    快捷接口，生成最近N天的舆情报告。
    """
    end_date = datetime.now()
    start_date = end_date.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=days)

    request = ReportGenerateRequest(
        dimension="sentiment",
        date_range=(start_date.isoformat(), end_date.isoformat()),
        output_format=output_format,
    )

    return await generate_report(request)


@router.get("/dimensions", response_model=ReportDimensionsListResponse)
async def list_dimensions():
    """
    列出所有支持的报告维度

    返回各维度的名称、描述和实现状态。
    """
    return {
        "dimensions": [
            {
                "id": "sentiment",
                "name": "舆情监测",
                "description": "社交媒体舆情分析，包含风险预警、正向机会、行动建议",
                "status": "implemented",
            },
            {
                "id": "policy",
                "name": "政策分析",
                "description": "政策文件分析，识别政策机会和影响",
                "status": "planned",
            },
            {
                "id": "technology",
                "name": "科技前沿",
                "description": "技术趋势分析，识别前沿技术和研究热点",
                "status": "planned",
            },
            {
                "id": "personnel",
                "name": "人事情报",
                "description": "人事变动分析，识别人才流动趋势",
                "status": "planned",
            },
            {
                "id": "university",
                "name": "高校生态",
                "description": "高校动态分析，识别合作机会",
                "status": "planned",
            },
        ]
    }
