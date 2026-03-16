"""Pydantic schemas for University Ecosystem (高校生态) API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class GroupStats(BaseModel):
    """单个分组的统计数据。"""

    group: str = Field(description="分组 ID", examples=["university_news"])
    group_name: str = Field(description="分组中文名", examples=["高校新闻"])
    total_articles: int = Field(description="该分组文章总数")
    new_today: int = Field(description="今日新增文章数")
    source_count: int = Field(description="该分组有数据的信源数")


class UniversityOverviewResponse(BaseModel):
    """高校生态总览响应。"""

    generated_at: str = Field(description="数据生成时间 (ISO 8601)")
    total_articles: int = Field(description="大学维度文章总数")
    new_today: int = Field(description="今日新增文章总数")
    active_source_count: int = Field(description="有数据的信源数")
    total_source_count: int = Field(description="大学维度总信源数（含禁用）")
    groups: list[GroupStats] = Field(description="按分组统计")
    latest_crawl_at: str | None = Field(
        default=None, description="最近一次爬取时间"
    )


class ImageItem(BaseModel):
    """文章中的图片。"""

    src: str = Field(description="图片 URL")
    alt: str | None = Field(default=None, description="替代文本")


class UniversityFeedItem(BaseModel):
    """高校动态 Feed 中的单条文章。"""

    id: str = Field(description="文章 ID (url_hash)")
    title: str = Field(description="文章标题")
    url: str = Field(description="原文链接")
    published_at: str | None = Field(default=None, description="发布时间")
    source_id: str = Field(description="信源 ID")
    source_name: str = Field(description="信源名称")
    group: str | None = Field(default=None, description="所属分组")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    has_content: bool = Field(description="是否有正文内容")
    thumbnail: str | None = Field(
        default=None, description="缩略图 URL（取文章首张图片）"
    )
    is_new: bool = Field(default=False, description="本次爬取是否为新增文章")
    content: str | None = Field(default=None, description="正文纯文本")
    images: list[ImageItem] = Field(
        default_factory=list, description="文章中的图片列表"
    )


class UniversityFeedResponse(BaseModel):
    """高校动态 Feed 分页响应。"""

    generated_at: str = Field(description="数据生成时间 (ISO 8601)")
    total: int = Field(description="符合条件的总记录数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")
    items: list[UniversityFeedItem] = Field(description="文章列表")


class UniversityArticleDetail(BaseModel):
    """高校文章详情。"""

    id: str = Field(description="文章 ID (url_hash)")
    title: str = Field(description="文章标题")
    url: str = Field(description="原文链接")
    published_at: str | None = Field(default=None, description="发布时间")
    source_id: str = Field(description="信源 ID")
    source_name: str = Field(description="信源名称")
    group: str | None = Field(default=None, description="所属分组")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    content: str | None = Field(default=None, description="正文纯文本")
    images: list[ImageItem] = Field(
        default_factory=list, description="文章中的图片列表"
    )
    is_new: bool = Field(default=False, description="是否为新增文章")


class ResearchOutputItem(BaseModel):
    """科研成果条目（经规则引擎分类）。"""

    id: str = Field(description="文章 ID (url_hash)")
    title: str = Field(description="文章标题")
    url: str = Field(description="原文链接")
    date: str = Field(description="发布日期 (YYYY-MM-DD)")
    source_id: str = Field(description="信源 ID")
    source_name: str = Field(description="信源名称")
    group: str | None = Field(default=None, description="所属分组")
    institution: str = Field(description="所属机构")
    type: str = Field(description="成果类型: 论文/专利/获奖")
    influence: str = Field(description="影响力: 高/中/低")
    field: str = Field(description="研究领域")
    authors: str = Field(description="作者/团队")
    aiAnalysis: str = Field(description="AI 分析摘要")
    detail: str = Field(description="正文摘要片段")
    matchScore: int = Field(description="关键词匹配分 (0-100)")
    content: str | None = Field(default=None, description="正文纯文本")
    images: list[ImageItem] = Field(
        default_factory=list, description="文章中的图片列表"
    )


class ResearchOutputsResponse(BaseModel):
    """科研成果列表响应。"""

    generated_at: str = Field(description="数据生成时间 (ISO 8601)")
    item_count: int = Field(description="科研成果总数")
    type_stats: dict[str, int] = Field(
        description="按类型统计: {论文: N, 专利: N, 获奖: N}"
    )
    items: list[ResearchOutputItem] = Field(description="科研成果列表")


class UniversitySourceItem(BaseModel):
    """高校信源状态。"""

    source_id: str = Field(description="信源 ID")
    source_name: str = Field(description="信源名称")
    group: str = Field(description="所属分组")
    url: str = Field(description="信源 URL")
    item_count: int = Field(description="当前最新数据条数")
    new_item_count: int = Field(description="最近一次新增条数")
    last_crawled_at: str | None = Field(
        default=None, description="最近爬取时间"
    )
    is_enabled: bool = Field(description="是否启用")


class UniversitySourcesResponse(BaseModel):
    """高校信源列表响应。"""

    generated_at: str = Field(description="数据生成时间 (ISO 8601)")
    total_sources: int = Field(description="信源总数")
    enabled_sources: int = Field(description="启用的信源数")
    items: list[UniversitySourceItem] = Field(description="信源列表")
