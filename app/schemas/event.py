"""Pydantic schemas for the Event API (/api/v1/events/)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# List item (for GET /events/)
# ---------------------------------------------------------------------------


class EventListItem(BaseModel):
    """Single event in the list."""

    id: str = Field(description="活动唯一标识")
    category: str = Field(default="", description="一级分类标签（教育培养/科研学术/人才引育）")
    series: str = Field(default="", description="活动系列标签（如：XAI智汇讲坛）")
    event_type: str = Field(default="", description="活动类型标签（子分类按钮）")
    title: str = Field(description="活动标题")
    abstract: str = Field(default="", description="活动摘要")
    event_date: str = Field(description="活动日期 YYYY-MM-DD")
    event_time: str = Field(default="", description="活动时间（可选，如 14:00-17:00）")
    location: str = Field(default="", description="地点")
    cover_image_url: str = Field(default="", description="活动照片 URL")
    scholar_count: int = Field(default=0, description="关联学者数量")
    created_at: str = Field(default="", description="创建时间")


class EventListResponse(BaseModel):
    """Response for GET /events/."""

    total: int = Field(description="符合条件的总活动数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")
    items: list[EventListItem]


# ---------------------------------------------------------------------------
# Detail response (full event record)
# ---------------------------------------------------------------------------


class EventDetailResponse(BaseModel):
    """Full event record."""

    # 标签信息
    id: str
    category: str = Field(default="", description="一级分类标签")
    series: str = Field(default="", description="活动系列标签")
    event_type: str = Field(default="", description="活动类型标签（子分类）")
    title: str = Field(description="活动标题")
    abstract: str = ""
    event_date: str = Field(description="活动日期 YYYY-MM-DD")
    event_time: str = Field(default="", description="活动时间")
    location: str = ""
    cover_image_url: str = ""

    # 学者关联
    scholar_ids: list[str] = Field(default_factory=list)

    # 元信息
    created_at: str = ""
    updated_at: str = ""
    custom_fields: dict[str, str] = Field(default_factory=dict, description="用户自定义字段")


# ---------------------------------------------------------------------------
# Stats response (for GET /events/stats)
# ---------------------------------------------------------------------------


class EventStatsResponse(BaseModel):
    """Statistics for events."""

    total: int = Field(description="总活动数")
    by_category: list[dict[str, Any]] = Field(
        description="按一级分类统计 [{category, count}]"
    )
    by_series: list[dict[str, Any]] = Field(
        description="按活动系列统计 [{series, count}]"
    )
    by_type: list[dict[str, Any]] = Field(
        description="按活动类型统计 [{event_type, count}]"
    )
    by_month: list[dict[str, Any]] = Field(
        description="按月份统计 [{month, count}]"
    )
    total_related_scholars: int = Field(description="活动-学者关联总数（含重复）")


# ---------------------------------------------------------------------------
# Write request schemas
# ---------------------------------------------------------------------------


class EventCreate(BaseModel):
    """POST /events/ — create new event."""

    category: str = Field(description="一级分类标签（教育培养/科研学术/人才引育）")
    series: str = Field(default="", description="活动系列标签（如：XAI智汇讲坛）")
    event_type: str = Field(default="", description="活动类型标签（子分类）")
    title: str = Field(description="活动标题")
    abstract: str = Field(default="", description="摘要")
    event_date: str = Field(description="活动日期 YYYY-MM-DD")
    event_time: str = Field(default="", description="活动时间（可选）")
    location: str = Field(default="", description="地点")
    cover_image_url: str = Field(default="", description="活动照片 URL")

    # 学者关联
    scholar_ids: list[str] = Field(default_factory=list, description="关联学者 url_hash 列表")

    custom_fields: dict[str, str] | None = Field(
        default=None, description="用户自定义字段（KV 键值对）",
    )


class EventUpdate(BaseModel):
    """PATCH /events/{id} — update event (all fields optional)."""

    category: str | None = Field(default=None, description="一级分类")
    series: str | None = Field(default=None, description="二级分类/活动系列")
    event_type: str | None = Field(default=None, description="活动类型")

    # 活动信息
    title: str | None = Field(default=None, description="活动标题")
    abstract: str | None = Field(default=None, description="摘要")
    event_date: str | None = Field(default=None, description="活动日期 YYYY-MM-DD")
    event_time: str | None = Field(default=None, description="活动时间")
    location: str | None = Field(default=None, description="地点")
    cover_image_url: str | None = Field(default=None, description="活动照片 URL")

    # 关联信息
    scholar_ids: list[str] | None = Field(default=None, description="关联学者 url_hash 列表")

    custom_fields: dict[str, str | None] | None = Field(
        default=None, description="用户自定义字段（浅合并：值为 null 删除该 key）",
    )


class ScholarAssociation(BaseModel):
    """POST /events/{id}/scholars — add scholar association."""

    scholar_id: str = Field(description="学者 url_hash")


# ---------------------------------------------------------------------------
# Taxonomy schemas (3-level category tree)
# ---------------------------------------------------------------------------


class TaxonomyNode(BaseModel):
    """Single node in the taxonomy tree."""

    id: str = Field(description="节点 UUID")
    level: int = Field(description="层级：1=一级分类, 2=二级系列, 3=活动类型")
    name: str = Field(description="节点名称")
    parent_id: str | None = Field(default=None, description="父节点 UUID（L1 为 null）")
    sort_order: int = Field(default=0, description="排序权重（越小越靠前）")
    created_at: str = Field(default="", description="创建时间")


class TaxonomyL3(TaxonomyNode):
    """L3 活动类型节点（叶子节点）。"""


class TaxonomyL2(TaxonomyNode):
    """L2 系列节点，含下级活动类型列表。"""

    children: list[TaxonomyL3] = Field(default_factory=list, description="活动类型列表")


class TaxonomyL1(TaxonomyNode):
    """L1 一级分类节点，含下级系列列表。"""

    children: list[TaxonomyL2] = Field(default_factory=list, description="系列列表")


class TaxonomyTree(BaseModel):
    """完整的三级分类树（GET /events/taxonomy 响应）。"""

    total_l1: int = Field(description="一级分类数量")
    total_l2: int = Field(description="二级系列数量")
    total_l3: int = Field(description="活动类型数量")
    items: list[TaxonomyL1] = Field(description="一级分类列表（含完整子树）")


class TaxonomyCreate(BaseModel):
    """POST /events/taxonomy — 新增分类节点。"""

    level: int = Field(description="层级：1=一级分类, 2=二级系列, 3=活动类型", ge=1, le=3)
    name: str = Field(description="节点名称", min_length=1)
    parent_id: str | None = Field(
        default=None,
        description="父节点 UUID（L1 留空；L2 填一级分类 ID；L3 填二级系列 ID）",
    )
    sort_order: int = Field(default=0, description="排序权重")


class TaxonomyUpdate(BaseModel):
    """PATCH /events/taxonomy/{id} — 更新分类节点。"""

    name: str | None = Field(default=None, description="新名称")
    sort_order: int | None = Field(default=None, description="排序权重")
