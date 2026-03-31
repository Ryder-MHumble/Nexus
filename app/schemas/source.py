from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceResponse(BaseModel):
    """信源详情。"""

    id: str = Field(description="信源唯一 ID", examples=["tech_arxiv"])
    name: str = Field(description="信源名称", examples=["ArXiv AI Papers"])
    url: str = Field(
        description="信源 URL",
        examples=["https://arxiv.org/list/cs.AI/recent"],
    )
    dimension: str = Field(description="所属维度", examples=["technology"])
    crawl_method: str = Field(
        description="爬取方式: static / dynamic / rss / snapshot / custom",
        examples=["static"],
    )
    schedule: str = Field(
        description="调度频率: hourly / daily / twice_daily 等",
        examples=["daily"],
    )
    is_enabled: bool = Field(description="是否启用", examples=[True])
    priority: int = Field(description="优先级（1-5，1 最高）", examples=[2])
    last_crawl_at: datetime | None = Field(
        default=None, description="上次爬取时间"
    )
    last_success_at: datetime | None = Field(
        default=None, description="上次成功爬取时间"
    )
    consecutive_failures: int = Field(
        default=0, description="连续失败次数", examples=[0]
    )
    source_file: str | None = Field(
        default=None, description="来源配置文件名", examples=["technology.yaml"]
    )
    group: str | None = Field(
        default=None, description="信源分组", examples=["university_leadership_official"]
    )
    tags: list[str] = Field(
        default_factory=list, description="信源标签", examples=[["personnel", "leadership"]]
    )
    crawler_class: str | None = Field(
        default=None, description="自定义 crawler_class（如有）", examples=["twitter_search"]
    )
    dimension_name: str | None = Field(
        default=None, description="维度中文名", examples=["对人事"]
    )
    dimension_description: str | None = Field(
        default=None, description="维度说明"
    )
    health_status: Literal["healthy", "warning", "failing", "unknown"] = Field(
        default="unknown", description="健康状态（基于连续失败次数与爬取记录）"
    )
    is_enabled_overridden: bool = Field(
        default=False, description="是否被运行时启停覆盖（非 YAML 原始状态）"
    )


class SourceUpdate(BaseModel):
    """信源更新请求体。"""

    is_enabled: bool | None = Field(
        default=None, description="启用或禁用信源"
    )


class SourceFacetItem(BaseModel):
    """分面聚合项。"""

    key: str = Field(description="分面值")
    label: str | None = Field(default=None, description="分面展示名")
    count: int = Field(description="数量")


class SourceDimensionFacetItem(SourceFacetItem):
    """维度分面（含启用数）。"""

    enabled_count: int = Field(description="启用数")


class SourceFacetsResponse(BaseModel):
    """信源筛选分面。"""

    dimensions: list[SourceDimensionFacetItem] = Field(default_factory=list)
    groups: list[SourceFacetItem] = Field(default_factory=list)
    tags: list[SourceFacetItem] = Field(default_factory=list)
    crawl_methods: list[SourceFacetItem] = Field(default_factory=list)
    schedules: list[SourceFacetItem] = Field(default_factory=list)
    health_statuses: list[SourceFacetItem] = Field(default_factory=list)


class SourceCatalogResponse(BaseModel):
    """信源目录响应。"""

    generated_at: datetime = Field(description="生成时间（UTC）")
    total_sources: int = Field(description="全量信源数")
    filtered_sources: int = Field(description="过滤后信源数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")
    items: list[SourceResponse] = Field(default_factory=list)
    facets: SourceFacetsResponse | None = Field(
        default=None, description="分面统计（仅 include_facets=true 时返回）"
    )
    applied_filters: dict[str, Any] = Field(
        default_factory=dict, description="本次实际生效的筛选条件"
    )
