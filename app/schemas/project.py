"""Pydantic schemas for the Project API (/api/v1/projects/).

项目库字段设计参照「项目导入模板.xlsx」并扩展：
  - 原始字段：项目名称、项目负责人、负责人单位、资助机构、资助金额、开始/结束年份、项目状态、项目类别、项目简介
  - 扩展字段：related_scholars（相关老师列表）、tags（标签）、keywords（关键词）、
              cooperation_institution（合作机构）、output_papers/patents（成果）、
              created_at/updated_at（元数据）
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enum-like constants (documented in Field descriptions)
# ---------------------------------------------------------------------------
# project_status: 申请中 | 在研 | 已结题 | 暂停 | 终止
# project_category: 国家级 | 省部级 | 横向课题 | 院内课题 | 国际合作 | 其他


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ProjectScholar(BaseModel):
    """项目相关学者（负责人或参与老师）"""

    name: str = Field(description="姓名")
    role: str | None = Field(default=None, description="角色（负责人/参与者/合作导师等）")
    institution: str | None = Field(default=None, description="所属单位")
    scholar_id: str | None = Field(default=None, description="系统内学者 ID（可选，用于关联）")


class ProjectOutput(BaseModel):
    """项目成果（论文/专利/软著等）"""

    type: str = Field(description="成果类型（论文/专利/软件著作权/报告/其他）")
    title: str = Field(description="成果标题")
    year: int | None = Field(default=None, description="发表/授权年份")
    authors: list[str] = Field(default_factory=list, description="作者列表")
    venue: str | None = Field(default=None, description="发表期刊/会议/专利号")
    url: str | None = Field(default=None, description="链接")


# ---------------------------------------------------------------------------
# List item (lightweight)
# ---------------------------------------------------------------------------


class ProjectListItem(BaseModel):
    """项目列表项 — 关键字段（用于列表页）"""

    id: str = Field(description="项目唯一 ID（系统自动生成）")
    name: str = Field(description="项目名称")
    pi_name: str = Field(description="项目负责人姓名")
    pi_institution: str | None = Field(default=None, description="负责人所属单位")
    funder: str | None = Field(default=None, description="资助机构")
    funding_amount: float | None = Field(default=None, description="资助金额（元）")
    start_year: int | None = Field(default=None, description="开始年份")
    end_year: int | None = Field(default=None, description="结束年份")
    status: str = Field(description="项目状态：申请中 | 在研 | 已结题 | 暂停 | 终止")
    category: str | None = Field(default=None, description="项目类别：国家级 | 省部级 | 横向课题 | 院内课题 | 国际合作 | 其他")
    tags: list[str] = Field(default_factory=list, description="标签列表")


class ProjectListResponse(BaseModel):
    """GET /projects/ 分页响应"""

    total: int = Field(description="符合条件的总项目数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")
    items: list[ProjectListItem]


# ---------------------------------------------------------------------------
# Detail response
# ---------------------------------------------------------------------------


class ProjectDetailResponse(BaseModel):
    """完整项目记录"""

    # 基本信息
    id: str = Field(description="项目唯一 ID")
    name: str = Field(description="项目名称")
    status: str = Field(description="项目状态：申请中 | 在研 | 已结题 | 暂停 | 终止")
    category: str | None = Field(default=None, description="项目类别")

    # 负责人与资助信息
    pi_name: str = Field(description="项目负责人姓名")
    pi_institution: str | None = Field(default=None, description="负责人所属单位")
    funder: str | None = Field(default=None, description="资助机构")
    funding_amount: float | None = Field(default=None, description="资助金额（元）")
    start_year: int | None = Field(default=None, description="开始年份")
    end_year: int | None = Field(default=None, description="结束年份")

    # 描述与分类
    description: str | None = Field(default=None, description="项目简介")
    keywords: list[str] = Field(default_factory=list, description="关键词列表")
    tags: list[str] = Field(default_factory=list, description="标签列表")

    # 相关人员
    related_scholars: list[ProjectScholar] = Field(
        default_factory=list, description="相关学者列表（含负责人及参与老师）"
    )

    # 合作信息
    cooperation_institutions: list[str] = Field(
        default_factory=list, description="合作机构列表"
    )

    # 项目成果
    outputs: list[ProjectOutput] = Field(
        default_factory=list, description="项目成果（论文/专利/软著等）"
    )

    # 元数据
    created_at: str | None = Field(default=None, description="创建时间 ISO8601")
    updated_at: str | None = Field(default=None, description="最后更新时间 ISO8601")
    extra: dict[str, Any] = Field(default_factory=dict, description="扩展字段（导入时保留原始数据）")
    custom_fields: dict[str, str] = Field(default_factory=dict, description="用户自定义字段")


# ---------------------------------------------------------------------------
# Stats response
# ---------------------------------------------------------------------------


class ProjectStatsResponse(BaseModel):
    """GET /projects/stats 统计响应"""

    total: int = Field(description="项目总数")
    by_status: list[dict[str, Any]] = Field(description="按状态统计 [{status, count}]")
    by_category: list[dict[str, Any]] = Field(description="按类别统计 [{category, count}]")
    by_funder: list[dict[str, Any]] = Field(description="按资助机构统计 [{funder, count, total_amount}]")
    total_funding: float = Field(description="资助总金额（元）")
    active_count: int = Field(description="在研项目数")


# ---------------------------------------------------------------------------
# Write request schemas
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    """POST /projects/ — 创建项目"""

    # 必填
    name: str = Field(description="项目名称")
    pi_name: str = Field(description="项目负责人姓名")
    status: str = Field(
        default="在研",
        description="项目状态：申请中 | 在研 | 已结题 | 暂停 | 终止",
    )

    # 选填
    pi_institution: str | None = Field(default=None, description="负责人所属单位")
    funder: str | None = Field(default=None, description="资助机构")
    funding_amount: float | None = Field(default=None, description="资助金额（元）")
    start_year: int | None = Field(default=None, description="开始年份")
    end_year: int | None = Field(default=None, description="结束年份")
    category: str | None = Field(default=None, description="项目类别")
    description: str | None = Field(default=None, description="项目简介")
    keywords: list[str] | None = Field(default=None, description="关键词")
    tags: list[str] | None = Field(default=None, description="标签")
    related_scholars: list[ProjectScholar] | None = Field(default=None, description="相关学者")
    cooperation_institutions: list[str] | None = Field(default=None, description="合作机构")
    outputs: list[ProjectOutput] | None = Field(default=None, description="项目成果")
    extra: dict[str, Any] | None = Field(default=None, description="扩展字段")
    custom_fields: dict[str, str] | None = Field(
        default=None,
        description="用户自定义字段（KV 键值对，字段名和值均为字符串）",
    )


class ProjectUpdate(BaseModel):
    """PATCH /projects/{id} — 更新项目（所有字段可选）"""

    name: str | None = Field(default=None)
    pi_name: str | None = Field(default=None)
    pi_institution: str | None = Field(default=None)
    funder: str | None = Field(default=None)
    funding_amount: float | None = Field(default=None)
    start_year: int | None = Field(default=None)
    end_year: int | None = Field(default=None)
    status: str | None = Field(default=None)
    category: str | None = Field(default=None)
    description: str | None = Field(default=None)
    keywords: list[str] | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    related_scholars: list[ProjectScholar] | None = Field(default=None)
    cooperation_institutions: list[str] | None = Field(default=None)
    outputs: list[ProjectOutput] | None = Field(default=None)
    extra: dict[str, Any] | None = Field(default=None)
    custom_fields: dict[str, str | None] | None = Field(
        default=None,
        description="用户自定义字段（浅合并：传入 key 覆盖，值为 null 删除该 key）",
    )
