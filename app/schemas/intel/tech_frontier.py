"""Pydantic schemas for Tech Frontier (科技前沿) API.

Aligned 1:1 with Dean-Agent frontend types in lib/types/tech-frontier.ts.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Sub-types (embedded in TechTopic)
# ---------------------------------------------------------------------------


class TrendingPost(BaseModel):
    """信号帖子（X / ArXiv / GitHub 等平台的单条信息）。"""

    id: str = Field(description="帖子 ID (url_hash)")
    title: str = Field(description="标题")
    platform: Literal["X", "YouTube", "ArXiv", "GitHub", "微信公众号", "知乎"] = Field(
        description="来源平台"
    )
    author: str = Field(description="作者")
    date: str = Field(description="发布日期")
    sourceUrl: str = Field(description="原文链接")
    summary: str = Field(description="摘要")
    engagement: str | None = Field(default=None, description="互动指标")


class TrendingKeyword(BaseModel):
    """主题下的热门关键词及关联帖子。"""

    keyword: str = Field(description="关键词")
    postCount: int = Field(description="相关帖子数")
    trend: Literal["surging", "rising", "stable"] = Field(description="趋势")
    posts: list[TrendingPost] = Field(default_factory=list, description="关联帖子")


class TopicNews(BaseModel):
    """主题关联的产业新闻。"""

    id: str = Field(description="新闻 ID (url_hash)")
    title: str = Field(description="标题")
    source: str = Field(description="信源名称")
    sourceUrl: str = Field(description="原文链接")
    type: Literal["投融资", "新产品", "政策", "收购", "合作"] = Field(
        description="新闻类型"
    )
    date: str = Field(description="发布日期")
    impact: Literal["重大", "较大", "一般"] = Field(description="影响力")
    summary: str = Field(description="摘要")
    aiAnalysis: str = Field(default="", description="AI 分析 (Tier 2 LLM)")
    relevance: str = Field(default="", description="与院方的相关性 (Tier 2 LLM)")


class KOLVoice(BaseModel):
    """KOL 言论（来自 Twitter 等渠道）。"""

    id: str = Field(description="言论 ID (url_hash)")
    name: str = Field(description="KOL 姓名 / 账号")
    affiliation: str = Field(default="", description="所属机构")
    influence: Literal["极高", "高", "中"] = Field(
        default="高", description="影响力级别"
    )
    statement: str = Field(description="核心言论")
    platform: Literal["X", "会议", "论文", "博客", "播客"] = Field(
        description="来源平台"
    )
    sourceUrl: str = Field(description="原文链接")
    date: str = Field(description="发布日期")


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------


class TechTopic(BaseModel):
    """技术主题（科技前沿核心对象）。"""

    id: str = Field(description="主题 ID", examples=["embodied_ai"])
    topic: str = Field(description="主题名称", examples=["具身智能"])
    description: str = Field(description="主题描述")
    tags: list[str] = Field(default_factory=list, description="标签")

    # Trend metrics
    heatTrend: Literal["surging", "rising", "stable", "declining"] = Field(
        description="热度趋势"
    )
    heatLabel: str = Field(description="热度标签", examples=["+180%"])
    ourStatus: Literal["deployed", "weak", "none"] = Field(
        description="我院布局状态"
    )
    ourStatusLabel: str = Field(description="布局状态标签", examples=["已布局"])
    gapLevel: Literal["high", "medium", "low"] = Field(
        description="与头部机构差距"
    )

    # Aggregated signals
    trendingKeywords: list[TrendingKeyword] = Field(
        default_factory=list, description="热门关键词 (Tier 2 LLM)"
    )
    relatedNews: list[TopicNews] = Field(
        default_factory=list, description="关联产业新闻"
    )
    kolVoices: list[KOLVoice] = Field(
        default_factory=list, description="KOL 言论"
    )

    # AI synthesis (Tier 2 LLM fills these)
    aiSummary: str = Field(default="", description="AI 周报摘要")
    aiInsight: str = Field(default="", description="AI 战略建议")
    aiRiskAssessment: str | None = Field(
        default=None, description="风险预警 (仅 gapLevel=high)"
    )
    memoSuggestion: str | None = Field(
        default=None, description="内参选题建议"
    )

    # Stats
    totalSignals: int = Field(default=0, description="信号总数")
    signalsSinceLastWeek: int = Field(default=0, description="本周新增信号")
    lastUpdated: str = Field(description="最后更新时间")


class Opportunity(BaseModel):
    """科技前沿机会（会议 / 合作 / 内参）。"""

    id: str = Field(description="机会 ID")
    name: str = Field(description="机会名称")
    type: Literal["合作", "会议", "内参"] = Field(description="类型")
    source: str = Field(description="来源信源")
    priority: Literal["紧急", "高", "中", "低"] = Field(description="优先级")
    deadline: str = Field(default="", description="截止日期")
    summary: str = Field(description="摘要")
    aiAssessment: str = Field(default="", description="AI 评估 (Tier 2 LLM)")
    actionSuggestion: str = Field(default="", description="行动建议 (Tier 2 LLM)")


# ---------------------------------------------------------------------------
# Response wrappers
# ---------------------------------------------------------------------------


class TechFrontierTopicsResponse(BaseModel):
    """科技前沿主题列表响应。"""

    generated_at: str | None = Field(default=None, description="数据生成时间")
    item_count: int = Field(description="主题数")
    items: list[TechTopic] = Field(description="主题列表")


class TechFrontierOpportunitiesResponse(BaseModel):
    """科技前沿机会列表响应。"""

    generated_at: str | None = Field(default=None, description="数据生成时间")
    item_count: int = Field(description="机会数")
    items: list[Opportunity] = Field(description="机会列表")


class TechFrontierStatsResponse(BaseModel):
    """科技前沿 KPI 统计响应。"""

    generated_at: str | None = Field(default=None, description="数据生成时间")
    totalTopics: int = Field(description="主题总数")
    surgingCount: int = Field(description="飙升主题数")
    highGapCount: int = Field(description="高缺口主题数")
    weeklyNewSignals: int = Field(description="本周新增信号总数")
    urgentOpportunities: int = Field(description="紧急机会数")
    totalOpportunities: int = Field(description="机会总数")
    totalArticlesProcessed: int = Field(description="处理文章总数")
    dimensionBreakdown: dict[str, int] = Field(description="按维度统计")
    topicBreakdown: dict[str, int] = Field(description="按主题统计")


class SignalItem(BaseModel):
    """扁平信号条目（news + kol 混合流）。"""

    kind: Literal["news", "kol"] = Field(description="信号类型")
    data: TopicNews | KOLVoice = Field(description="信号数据")
    parentTopicId: str = Field(description="所属主题 ID")
    parentTopicName: str = Field(description="所属主题名称")
    date: str = Field(description="日期")


class TechFrontierSignalsResponse(BaseModel):
    """科技前沿信号流响应。"""

    generated_at: str | None = Field(default=None, description="数据生成时间")
    item_count: int = Field(description="信号总数")
    items: list[SignalItem] = Field(description="信号列表")
