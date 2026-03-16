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
    category: str = Field(default="", description="一级分类（教育培养/科研学术/人才引育）")
    series: str = Field(default="", description="二级分类/活动系列（如：XAI智汇讲坛、国际AI科学家大会）")
    event_type: str = Field(default="", description="活动类型（讲座/前沿沙龙等）")
    title: str = Field(description="活动/讲座题目")
    speaker_name: str = Field(description="讲者姓名")
    speaker_organization: str = Field(default="", description="讲者单位")
    event_date: str = Field(description="活动日期 ISO8601")
    location: str = Field(default="", description="地点")
    series_number: str = Field(default="", description="系列期数")
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

    # 基本信息
    id: str
    category: str = Field(default="", description="一级分类（教育培养/科研学术/人才引育）")
    series: str = Field(default="", description="二级分类/活动系列（如：XAI智汇讲坛、国际AI科学家大会）")
    event_type: str = Field(default="", description="活动类型（讲座/前沿沙龙等）")
    series_number: str = ""

    # 讲者信息
    speaker_name: str
    speaker_organization: str = ""
    speaker_position: str = ""
    speaker_bio: str = ""
    speaker_photo_url: str = ""

    # 活动信息
    title: str
    abstract: str = ""
    event_date: str
    duration: float = 0.0
    location: str = ""

    # 关联信息
    scholar_ids: list[str] = Field(default_factory=list)

    # 管理信息
    publicity: str = ""
    needs_email_invitation: bool = False
    certificate_number: str = ""
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""
    audit_status: str = ""
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
    by_type: list[dict[str, Any]] = Field(
        description="按活动类型统计 [{event_type, count}]"
    )
    by_month: list[dict[str, Any]] = Field(
        description="按月份统计 [{month, count}]"
    )
    total_speakers: int = Field(description="总讲者数（去重）")
    avg_duration: float = Field(description="平均时长（小时）")


# ---------------------------------------------------------------------------
# Write request schemas
# ---------------------------------------------------------------------------


class EventCreate(BaseModel):
    """POST /events/ — create new event."""

    category: str = Field(default="", description="一级分类（教育培养/科研学术/人才引育）")
    series: str = Field(default="", description="二级分类/活动系列（如：XAI智汇讲坛）")
    event_type: str = Field(default="", description="活动类型（如：学术前沿讲座/前沿沙龙）")
    series_number: str = Field(default="", description="系列期数")

    # 讲者信息
    speaker_name: str = Field(description="讲者姓名")
    speaker_organization: str = Field(default="", description="讲者单位")
    speaker_position: str = Field(default="", description="讲者职务")
    speaker_bio: str = Field(default="", description="讲者简介")
    speaker_photo_url: str = Field(default="", description="讲者照片URL")

    # 活动信息
    title: str = Field(description="活动/讲座题目")
    abstract: str = Field(default="", description="摘要")
    event_date: str = Field(description="活动日期 ISO8601")
    duration: float = Field(default=1.0, description="时长（小时）")
    location: str = Field(default="", description="地点")

    # 关联信息
    scholar_ids: list[str] = Field(default_factory=list, description="关联学者 url_hash 列表")

    # 管理信息
    publicity: str = Field(default="", description="公关传播")
    needs_email_invitation: bool = Field(default=False, description="是否需要邮件邀请")
    certificate_number: str = Field(default="", description="纪念证书编号")
    created_by: str = Field(default="user", description="创建人")
    audit_status: str = Field(default="pending", description="审核状态")
    custom_fields: dict[str, str] | None = Field(
        default=None, description="用户自定义字段（KV 键值对）",
    )


class EventUpdate(BaseModel):
    """PATCH /events/{id} — update event (all fields optional)."""

    category: str | None = Field(default=None, description="一级分类")
    series: str | None = Field(default=None, description="二级分类/活动系列")
    event_type: str | None = Field(default=None, description="活动类型")
    series_number: str | None = Field(default=None, description="系列期数")

    # 讲者信息
    speaker_name: str | None = Field(default=None, description="讲者姓名")
    speaker_organization: str | None = Field(default=None, description="讲者单位")
    speaker_position: str | None = Field(default=None, description="讲者职务")
    speaker_bio: str | None = Field(default=None, description="讲者简介")
    speaker_photo_url: str | None = Field(default=None, description="讲者照片URL")

    # 活动信息
    title: str | None = Field(default=None, description="活动/讲座题目")
    abstract: str | None = Field(default=None, description="摘要")
    event_date: str | None = Field(default=None, description="活动日期 ISO8601")
    duration: float | None = Field(default=None, description="时长（小时）")
    location: str | None = Field(default=None, description="地点")

    # 关联信息
    scholar_ids: list[str] | None = Field(default=None, description="关联学者 url_hash 列表")

    # 管理信息
    publicity: str | None = Field(default=None, description="公关传播")
    needs_email_invitation: bool | None = Field(default=None, description="是否需要邮件邀请")
    certificate_number: str | None = Field(default=None, description="纪念证书编号")
    audit_status: str | None = Field(default=None, description="审核状态")
    updated_by: str = Field(default="user", description="更新人")
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
