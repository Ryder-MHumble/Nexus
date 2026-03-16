"""Venue schemas — 顶会/期刊（学术社群）."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# List item (lightweight)
# ---------------------------------------------------------------------------

class VenueListItem(BaseModel):
    id: str = Field(description="唯一标识符")
    name: str = Field(description="缩写/简称，如 AAAI、Nature")
    full_name: str | None = Field(default=None, description="全称")
    type: str = Field(description="类型：conference（顶会）| journal（期刊）")
    rank: str | None = Field(default=None, description="级别：A* | A | B | C")
    fields: list[str] = Field(default_factory=list, description="研究领域标签")
    description: str | None = Field(default=None, description="简介")
    h5_index: int | None = Field(default=None, description="H5 指数")
    acceptance_rate: float | None = Field(default=None, description="录用率（0-1，如 0.20 表示 20%）")
    impact_factor: float | None = Field(default=None, description="影响因子（期刊专用）")
    is_active: bool = Field(default=True, description="是否活跃（仍在举办/出版）")


# ---------------------------------------------------------------------------
# Detail response (full record)
# ---------------------------------------------------------------------------

class VenueDetailResponse(BaseModel):
    id: str = Field(description="唯一标识符")
    name: str = Field(description="缩写/简称，如 AAAI、Nature")
    full_name: str | None = Field(default=None, description="全称")
    type: str = Field(description="类型：conference（顶会）| journal（期刊）")
    rank: str | None = Field(default=None, description="级别：A* | A | B | C")
    fields: list[str] = Field(default_factory=list, description="研究领域标签")
    description: str | None = Field(default=None, description="简介")
    h5_index: int | None = Field(default=None, description="H5 指数")
    acceptance_rate: float | None = Field(default=None, description="录用率（0-1，如 0.20 表示 20%）")
    impact_factor: float | None = Field(default=None, description="影响因子（期刊专用）")
    publisher: str | None = Field(default=None, description="出版商/主办方")
    website: str | None = Field(default=None, description="官网 URL")
    issn: str | None = Field(default=None, description="ISSN（期刊专用）")
    frequency: str | None = Field(default=None, description="出版频率，如 annual / biennial / monthly")
    is_active: bool = Field(default=True, description="是否活跃")
    custom_fields: dict[str, Any] = Field(default_factory=dict, description="用户自定义字段")
    created_at: str | None = Field(default=None, description="创建时间 ISO8601")
    updated_at: str | None = Field(default=None, description="更新时间 ISO8601")


# ---------------------------------------------------------------------------
# List response (paginated)
# ---------------------------------------------------------------------------

class VenueListResponse(BaseModel):
    total: int = Field(description="符合条件的总数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")
    items: list[VenueListItem]


# ---------------------------------------------------------------------------
# Stats response
# ---------------------------------------------------------------------------

class VenueStatsResponse(BaseModel):
    total: int = Field(description="总数")
    by_type: list[dict[str, Any]] = Field(description="按类型统计（conference/journal）")
    by_rank: list[dict[str, Any]] = Field(description="按级别统计（A*/A/B/C）")
    by_field: list[dict[str, Any]] = Field(description="按研究领域统计")


# ---------------------------------------------------------------------------
# Create / Update requests
# ---------------------------------------------------------------------------

class VenueCreate(BaseModel):
    name: str = Field(description="缩写/简称（必填）")
    full_name: str | None = Field(default=None, description="全称")
    type: str = Field(description="类型：conference | journal（必填）")
    rank: str | None = Field(default=None, description="级别：A* | A | B | C")
    fields: list[str] = Field(default_factory=list, description="研究领域标签")
    description: str | None = Field(default=None, description="简介")
    h5_index: int | None = Field(default=None, description="H5 指数")
    acceptance_rate: float | None = Field(default=None, description="录用率（0-1）")
    impact_factor: float | None = Field(default=None, description="影响因子")
    publisher: str | None = Field(default=None, description="出版商/主办方")
    website: str | None = Field(default=None, description="官网 URL")
    issn: str | None = Field(default=None, description="ISSN")
    frequency: str | None = Field(default=None, description="出版频率")
    is_active: bool = Field(default=True, description="是否活跃")
    custom_fields: dict[str, Any] = Field(default_factory=dict, description="用户自定义字段")


class VenueUpdate(BaseModel):
    name: str | None = Field(default=None)
    full_name: str | None = Field(default=None)
    type: str | None = Field(default=None)
    rank: str | None = Field(default=None)
    fields: list[str] | None = Field(default=None)
    description: str | None = Field(default=None)
    h5_index: int | None = Field(default=None)
    acceptance_rate: float | None = Field(default=None)
    impact_factor: float | None = Field(default=None)
    publisher: str | None = Field(default=None)
    website: str | None = Field(default=None)
    issn: str | None = Field(default=None)
    frequency: str | None = Field(default=None)
    is_active: bool | None = Field(default=None)
    custom_fields: dict[str, Any] | None = Field(
        default=None,
        description="浅合并：值为 null 删除该 key",
    )


# ---------------------------------------------------------------------------
# Batch create response
# ---------------------------------------------------------------------------

class VenueBatchResult(BaseModel):
    success: int = Field(description="成功数")
    skipped: int = Field(description="跳过（已存在）数")
    failed: int = Field(description="失败数")
    items: list[dict[str, Any]] = Field(description="每条记录的处理结果")
