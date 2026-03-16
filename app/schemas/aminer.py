"""Pydantic schemas for AMiner API responses."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Organization schemas
# ---------------------------------------------------------------------------


class OrganizationItem(BaseModel):
    """Single organization from institution.json."""

    name_zh: str = Field(description="中文名称")
    name_en: str = Field(description="英文名称")
    org_id: str = Field(description="AMiner 机构 ID")
    org_name: str = Field(description="AMiner org_name（用于学者搜索）")
    category: str = Field(default="", description="机构类别")
    priority: str = Field(default="", description="优先级")


class OrganizationListResponse(BaseModel):
    """Response for GET /aminer/organizations."""

    total: int = Field(description="匹配的机构总数")
    items: list[OrganizationItem]


# ---------------------------------------------------------------------------
# Scholar search schemas
# ---------------------------------------------------------------------------


class ScholarSearchItem(BaseModel):
    """Single scholar from AMiner person/search API."""

    id: str = Field(description="AMiner 学者 ID")
    name: str = Field(description="学者姓名")
    name_zh: str = Field(default="", description="中文姓名")
    avatar: str = Field(default="", description="头像 URL")
    org: str = Field(default="", description="所属机构")
    position: str = Field(default="", description="职称")
    h_index: int = Field(default=-1, description="H 指数")


class ScholarSearchResponse(BaseModel):
    """Response for GET /aminer/scholars/search."""

    total: int = Field(description="搜索结果总数")
    items: list[ScholarSearchItem]


# ---------------------------------------------------------------------------
# Scholar detail schemas
# ---------------------------------------------------------------------------


class ScholarDetailResponse(BaseModel):
    """Response for GET /aminer/scholars/{id}."""

    id: str = Field(description="AMiner 学者 ID")
    name: str = Field(description="学者姓名")
    name_zh: str = Field(default="", description="中文姓名")
    avatar: str = Field(default="", description="头像 URL")
    org: str = Field(default="", description="所属机构")
    position: str = Field(default="", description="职称")
    bio: str = Field(default="", description="个人简介")
    email: str = Field(default="", description="邮箱")
    homepage: str = Field(default="", description="个人主页")
    h_index: int = Field(default=-1, description="H 指数")
    citations: int = Field(default=-1, description="总被引次数")
    # Raw data from AMiner API (education, publications, etc.)
    raw_data: dict = Field(default_factory=dict, description="AMiner 原始数据")
