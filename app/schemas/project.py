"""Pydantic schemas for the Project API (/api/v1/projects/).

项目在当前系统中按「分类标签」管理：
- 一级分类：教育培养 / 科研学术 / 人才引育
- 二级子类：如 学术委员会 / 科研立项 / 卓工公派 等

每条项目记录用于承载一个筛选标签及其关联学者。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectListItem(BaseModel):
    """项目标签列表项（用于列表页）"""

    id: str = Field(description="项目标签唯一 ID")
    category: str = Field(default="", description="一级分类标签")
    subcategory: str = Field(default="", description="二级子分类标签")
    title: str = Field(description="项目标签标题")
    summary: str = Field(default="", description="项目标签摘要")
    scholar_count: int = Field(default=0, description="关联学者数量")
    created_at: str = Field(default="", description="创建时间 ISO8601")


class ProjectListResponse(BaseModel):
    """GET /projects/ 分页响应"""

    total: int = Field(description="符合条件的总项目标签数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")
    items: list[ProjectListItem]


class ProjectDetailResponse(BaseModel):
    """完整项目标签记录"""

    id: str = Field(description="项目标签唯一 ID")
    category: str = Field(default="", description="一级分类标签")
    subcategory: str = Field(default="", description="二级子分类标签")
    title: str = Field(description="项目标签标题")
    summary: str = Field(default="", description="项目标签摘要")
    scholar_ids: list[str] = Field(default_factory=list, description="关联学者 ID 列表")
    created_at: str | None = Field(default=None, description="创建时间 ISO8601")
    updated_at: str | None = Field(default=None, description="更新时间 ISO8601")
    custom_fields: dict[str, str] = Field(default_factory=dict, description="用户自定义字段")
    extra: dict[str, Any] = Field(default_factory=dict, description="兼容字段")


class ProjectStatsResponse(BaseModel):
    """GET /projects/stats 统计响应"""

    total: int = Field(description="项目标签总数")
    by_category: list[dict[str, Any]] = Field(description="按一级分类统计 [{category, count}]")
    by_subcategory: list[dict[str, Any]] = Field(description="按二级子类统计 [{subcategory, count}]")
    total_related_scholars: int = Field(description="项目-学者关联总数（含重复）")


class ProjectCreate(BaseModel):
    """POST /projects/ — 创建项目标签"""

    category: str = Field(description="一级分类标签（教育培养/科研学术/人才引育）")
    subcategory: str = Field(description="二级子分类标签（如 学术委员会）")
    title: str = Field(description="项目标签标题")
    summary: str = Field(default="", description="项目标签摘要")
    scholar_ids: list[str] = Field(default_factory=list, description="关联学者 ID 列表")
    custom_fields: dict[str, str] | None = Field(
        default=None,
        description="用户自定义字段（KV 键值对）",
    )


class ProjectUpdate(BaseModel):
    """PATCH /projects/{id} — 更新项目标签（所有字段可选）"""

    category: str | None = Field(default=None, description="一级分类标签")
    subcategory: str | None = Field(default=None, description="二级子分类标签")
    title: str | None = Field(default=None, description="项目标签标题")
    summary: str | None = Field(default=None, description="项目标签摘要")
    scholar_ids: list[str] | None = Field(default=None, description="关联学者 ID 列表")
    custom_fields: dict[str, str | None] | None = Field(
        default=None,
        description="用户自定义字段（浅合并：值为 null 删除该 key）",
    )


class ProjectTaxonomySubCategory(BaseModel):
    """项目分类二级节点。"""

    id: str = Field(description="节点标识")
    name: str = Field(description="节点名称")
    sort_order: int = Field(default=0, description="排序权重")


class ProjectTaxonomyCategory(BaseModel):
    """项目分类一级节点。"""

    id: str = Field(description="节点标识")
    name: str = Field(description="节点名称")
    sort_order: int = Field(default=0, description="排序权重")
    children: list[ProjectTaxonomySubCategory] = Field(default_factory=list, description="二级子类")


class ProjectTaxonomyTree(BaseModel):
    """项目分类树。"""

    total_l1: int = Field(description="一级分类数量")
    total_l2: int = Field(description="二级子类数量")
    items: list[ProjectTaxonomyCategory] = Field(description="完整分类树")
