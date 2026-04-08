"""Pydantic schemas for Policy Intelligence API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PolicyFeedItem(BaseModel):
    """政策动态 Feed 中的单条记录。"""

    id: str = Field(description="记录 ID", examples=["pol_20240115_001"])
    title: str = Field(
        description="政策标题",
        examples=["关于印发《新一代人工智能发展规划》的通知"],
    )
    summary: str | None = Field(default=None, description="政策摘要")
    category: (
        Literal["国家政策", "北京政策", "区域政策", "人才政策", "高校政策", "政策机会", "一般"]
        | None
    ) = Field(
        default=None, description="政策分类"
    )
    importance: Literal["紧急", "重要", "关注", "一般"] | None = Field(
        default=None, description="重要性级别"
    )
    date: str | None = Field(default=None, description="发布日期", examples=["2024-01-15"])
    source: str | None = Field(default=None, description="来源名称", examples=["国务院"])
    tags: list[str] = Field(
        default=[], description="标签", examples=[["人工智能", "规划"]]
    )
    matchScore: int | None = Field(
        default=None, description="与平台关注主题的匹配度（0-100）", examples=[92]
    )
    funding: str | None = Field(
        default=None, description="涉及资金规模", examples=["5000万元"]
    )
    daysLeft: int | None = Field(
        default=None, description="截止日倒计时（天，负数表示已过期）", examples=[15]
    )
    leader: str | None = Field(
        default=None, description="相关领导", examples=["张某某"]
    )
    relevance: int | None = Field(
        default=None, description="LLM 评估的相关性得分（0-100）", examples=[88]
    )
    signals: list[str] | None = Field(
        default=None,
        description="关键信号词列表",
        examples=[["人工智能", "专项资金", "算力"]],
    )
    sourceUrl: str | None = Field(
        default=None, description="原文链接"
    )
    aiInsight: str | None = Field(
        default=None, description="AI 分析洞察"
    )
    detail: str | None = Field(
        default=None, description="详细说明"
    )
    content: str | None = Field(
        default=None, description="原文正文"
    )


class PolicyItem(BaseModel):
    """政策机会看板中的单条记录。"""

    id: str = Field(description="机会 ID", examples=["opp_20240115_001"])
    name: str = Field(
        description="政策/项目名称",
        examples=["北京市人工智能产业创新发展专项"],
    )
    agency: str = Field(
        description="发布机构", examples=["北京市科委"]
    )
    agencyType: Literal["national", "beijing", "regional", "ministry"] | None = Field(
        default=None,
        description=(
            "机构级别: national（国家）/ beijing（北京）/"
            " regional（区域）/ ministry（部委）"
        ),
    )
    matchScore: int | None = Field(
        default=None, description="匹配度得分（0-100）", examples=[95]
    )
    funding: str | None = Field(default=None, description="资金规模", examples=["3000万元"])
    deadline: str | None = Field(
        default=None, description="申报截止日", examples=["2024-03-31"]
    )
    daysLeft: int | None = Field(
        default=None,
        description="距截止日天数（负数表示已过期）",
        examples=[45],
    )
    status: Literal["urgent", "active", "tracking", "expired"] | None = Field(
        default=None,
        description=(
            "状态: urgent（紧急）/ active（进行中）/"
            " tracking（跟踪中）/ expired（已过期）"
        ),
    )
    aiInsight: str | None = Field(default=None, description="AI 分析建议")
    detail: str | None = Field(default=None, description="详细描述")
    sourceUrl: str | None = Field(
        default=None, description="原文链接"
    )


class PolicyFeedResponse(BaseModel):
    """政策动态 Feed 响应。"""

    generated_at: str | None = Field(
        default=None, description="数据生成时间", examples=["2024-01-15T10:30:00"]
    )
    item_count: int = Field(description="返回的记录数", examples=[25])
    items: list[PolicyFeedItem] = Field(description="政策动态列表")


class PolicyOpportunitiesResponse(BaseModel):
    """政策机会列表响应。"""

    generated_at: str | None = Field(
        default=None, description="数据生成时间", examples=["2024-01-15T10:30:00"]
    )
    item_count: int = Field(description="返回的记录数", examples=[8])
    items: list[PolicyItem] = Field(description="政策机会列表")
