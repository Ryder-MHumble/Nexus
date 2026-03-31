"""Pydantic schemas for Personnel Intelligence API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PersonnelChange(BaseModel):
    """单条人事任免记录。"""

    name: str = Field(description="人员姓名", examples=["李某某"])
    action: Literal["任命", "免去"] = Field(description="任免类型")
    position: str = Field(
        description="职务", examples=["人工智能研究中心主任"]
    )
    department: str | None = Field(
        default=None, description="所属部门/机构", examples=["科技部"]
    )
    date: str | None = Field(default=None, description="任免日期", examples=["2024-01-15"])
    source_article_id: str | None = Field(
        default=None, description="来源文章 ID", examples=["art_20240115_001"]
    )


class PersonnelFeedItem(BaseModel):
    """人事动态 Feed 中的单条记录（文章级）。"""

    id: str = Field(description="记录 ID", examples=["per_20240115_001"])
    title: str = Field(
        description="文章标题", examples=["科技部发布最新人事任免通知"]
    )
    date: str | None = Field(default=None, description="发布日期", examples=["2024-01-15"])
    source: str | None = Field(default=None, description="来源", examples=["中国政府网"])
    importance: Literal["紧急", "重要", "关注", "一般"] | None = Field(
        default=None, description="重要性级别"
    )
    matchScore: int | None = Field(
        default=None, description="匹配度得分（0-100）", examples=[78]
    )
    changes: list[PersonnelChange] = Field(
        default=[], description="从该文章中提取的任免变动列表"
    )
    sourceUrl: str | None = Field(
        default=None, description="原文链接"
    )


class PersonnelFeedResponse(BaseModel):
    """人事动态 Feed 响应。"""

    generated_at: str | None = Field(
        default=None, description="数据生成时间", examples=["2024-01-15T10:30:00"]
    )
    item_count: int = Field(description="返回的记录数", examples=[12])
    items: list[PersonnelFeedItem] = Field(description="人事动态列表")


class PersonnelChangesResponse(BaseModel):
    """结构化人事变动列表响应。"""

    generated_at: str | None = Field(
        default=None, description="数据生成时间", examples=["2024-01-15T10:30:00"]
    )
    item_count: int = Field(description="返回的记录数", examples=[30])
    items: list[PersonnelChange] = Field(description="人事变动列表")


# ---------------------------------------------------------------------------
# Enriched personnel schemas (with LLM-generated fields)
# ---------------------------------------------------------------------------


class PersonnelChangeEnriched(BaseModel):
    """LLM 富化后的人事变动记录，包含相关性分析和行动建议。"""

    id: str = Field(description="记录 ID", examples=["enr_20240115_001"])
    name: str = Field(description="人员姓名", examples=["李某某"])
    action: Literal["任命", "免去", "动态"] = Field(
        description="变动类型: 任命 / 免去 / 动态（非明确任免的人事新闻）"
    )
    position: str = Field(
        description="职务", examples=["人工智能研究中心主任"]
    )
    department: str | None = Field(
        default=None, description="所属部门/机构", examples=["科技部"]
    )
    date: str | None = Field(default=None, description="日期", examples=["2024-01-15"])
    source: str | None = Field(default=None, description="来源", examples=["中国政府网"])
    sourceUrl: str | None = Field(
        default=None, description="原文链接"
    )
    # LLM enriched fields
    relevance: int = Field(
        default=0,
        description="与平台关注主题的相关性得分（0-100，LLM 评估）",
        examples=[85],
    )
    importance: Literal["紧急", "重要", "关注", "一般"] = Field(
        default="一般", description="重要性级别（LLM 评估）"
    )
    group: Literal["action", "watch"] = Field(
        default="watch",
        description="分组: action（需行动）/ watch（关注即可）",
    )
    note: str | None = Field(
        default=None, description="LLM 生成的简要说明"
    )
    actionSuggestion: str | None = Field(
        default=None, description="LLM 建议的行动方案"
    )
    background: str | None = Field(
        default=None, description="人员背景信息（LLM 补充）"
    )
    signals: list[str] = Field(
        default=[],
        description="关键信号词",
        examples=[["AI领域", "重点岗位", "新任命"]],
    )
    aiInsight: str | None = Field(
        default=None, description="AI 综合分析洞察"
    )


class PersonnelEnrichedFeedResponse(BaseModel):
    """LLM 富化人事动态响应。"""

    generated_at: str | None = Field(
        default=None, description="数据生成时间", examples=["2024-01-15T10:30:00"]
    )
    total_count: int = Field(description="总记录数", examples=[45])
    action_count: int = Field(
        default=0, description="需行动的记录数", examples=[8]
    )
    watch_count: int = Field(
        default=0, description="仅关注的记录数", examples=[37]
    )
    items: list[PersonnelChangeEnriched] = Field(
        description="富化后的人事变动列表"
    )


class PersonnelEnrichedStatsResponse(BaseModel):
    """LLM 富化人事数据统计。"""

    total_changes: int = Field(description="变动总数", examples=[45])
    action_count: int = Field(description="需行动数", examples=[8])
    watch_count: int = Field(description="仅关注数", examples=[37])
    by_department: dict[str, int] = Field(
        default={},
        description="按部门统计",
        examples=[{"科技部": 5, "教育部": 3, "工信部": 2}],
    )
    by_action: dict[str, int] = Field(
        default={},
        description="按变动类型统计",
        examples=[{"任命": 25, "免去": 15, "动态": 5}],
    )
    high_relevance_count: int = Field(
        default=0, description="高相关性记录数（relevance >= 70）", examples=[12]
    )
    generated_at: str | None = Field(
        default=None, description="数据生成时间", examples=["2024-01-15T10:30:00"]
    )
