"""Pydantic schemas for AI Daily Briefing (AI 早报) API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MetricItem(BaseModel):
    """A single metric within a metric card."""

    label: str = Field(description="指标标签", examples=["新政策"])
    value: str | int = Field(description="指标值", examples=["3条"])
    variant: Literal["default", "warning", "danger", "success"] | None = Field(
        default=None, description="显示样式"
    )


class MetricCard(BaseModel):
    """A metric card summarizing one module's key numbers."""

    id: str = Field(description="模块 ID", examples=["policy-intel"])
    title: str = Field(description="卡片标题", examples=["政策情报"])
    icon: Literal[
        "policy", "tech", "talent", "university", "building", "users", "calendar"
    ] = Field(description="图标类型")
    metrics: list[MetricItem] = Field(description="指标列表")


class DailyBriefingResponse(BaseModel):
    """AI 早报完整响应。

    paragraphs 字段直接对应前端 BriefingSegment[][] 类型：
    每个 segment 是 string 或 {text: str, moduleId: str, action?: str} 对象。
    """

    generated_at: str = Field(description="生成时间 (ISO 8601)")
    date: str = Field(description="报告日期 (YYYY-MM-DD)")
    paragraphs: list[list[str | dict[str, Any]]] = Field(
        description=(
            "段落数组，每段是 segment 数组。"
            "每个 segment 是 string 或 {text, moduleId, action?} 对象。"
        )
    )
    metric_cards: list[MetricCard] = Field(description="聚合指标卡片列表")
    summary: str | None = Field(
        default=None, description="纯文本摘要（降级用）"
    )
    article_count: int = Field(description="纳入分析的文章总数")
    dimension_counts: dict[str, int] = Field(
        description="各维度文章数",
        examples=[{"technology": 15, "national_policy": 3}],
    )


class MetricsOnlyResponse(BaseModel):
    """仅指标卡片响应（无 LLM 叙事）。"""

    generated_at: str = Field(description="计算时间 (ISO 8601)")
    date: str = Field(description="目标日期 (YYYY-MM-DD)")
    metric_cards: list[MetricCard] = Field(description="聚合指标卡片列表")
    article_count: int = Field(description="文章总数")
    dimension_counts: dict[str, int] = Field(description="各维度文章数")
