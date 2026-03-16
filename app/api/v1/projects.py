"""Project API — /api/v1/projects/

项目库增删改查接口。

Endpoints:
  GET    /projects/              项目列表（分页 + 过滤）
  GET    /projects/stats         统计信息
  GET    /projects/{id}          项目详情
  POST   /projects/              创建项目
  PATCH  /projects/{id}          更新项目
  DELETE /projects/{id}          删除项目
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.schemas.project import (
    ProjectCreate,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectStatsResponse,
    ProjectUpdate,
)
from app.services.core import project_service as svc

logger = logging.getLogger(__name__)

router = APIRouter()


class ProjectBatchRequest(BaseModel):
    items: list[ProjectCreate]
    skip_duplicates: bool = True


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="项目列表",
    description=(
        "获取项目库列表，支持多维度过滤和分页。\n\n"
        "**过滤参数：**\n"
        "- `status`: 项目状态（申请中/在研/已结题/暂停/终止）\n"
        "- `category`: 项目类别（国家级/省部级/横向课题/院内课题/国际合作/其他）\n"
        "- `funder`: 资助机构（模糊匹配）\n"
        "- `pi_name`: 负责人姓名（模糊匹配）\n"
        "- `tag`: 标签（精确匹配）\n"
        "- `keyword`: 全文搜索（匹配项目名称/简介/关键词）\n"
    ),
)
async def list_projects(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    status: str | None = Query(default=None, description="项目状态"),
    category: str | None = Query(default=None, description="项目类别"),
    funder: str | None = Query(default=None, description="资助机构（模糊匹配）"),
    pi_name: str | None = Query(default=None, description="负责人姓名（模糊匹配）"),
    tag: str | None = Query(default=None, description="标签（精确匹配）"),
    keyword: str | None = Query(default=None, description="全文关键词搜索"),
    custom_field_key: str | None = Query(default=None, description="自定义字段名（需配合 custom_field_value 使用）"),
    custom_field_value: str | None = Query(default=None, description="自定义字段值"),
):
    return await svc.list_projects(
        page=page,
        page_size=page_size,
        status=status,
        category=category,
        funder=funder,
        pi_name=pi_name,
        tag=tag,
        keyword=keyword,
        custom_field_key=custom_field_key,
        custom_field_value=custom_field_value,
    )


@router.get(
    "/stats",
    response_model=ProjectStatsResponse,
    summary="项目统计",
    description="返回项目库的聚合统计信息：按状态、类别、资助机构分布，以及资助总金额和在研项目数。",
)
async def get_stats():
    return await svc.get_stats()


@router.get(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="项目详情",
    description=(
        "根据项目 ID 获取完整项目记录，包含：\n"
        "- 基本信息（名称、负责人、资助机构、金额、年份、状态）\n"
        "- 项目简介与关键词\n"
        "- 相关学者列表（负责人 + 参与老师）\n"
        "- 合作机构\n"
        "- 项目成果（论文/专利等）\n"
    ),
)
async def get_project(project_id: str):
    result = await svc.get_project(project_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return result


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ProjectDetailResponse,
    summary="创建项目",
    description=(
        "创建新的项目记录。\n\n"
        "**必填字段：** `name`（项目名称）、`pi_name`（负责人）\n\n"
        "**项目 ID** 由系统自动生成（12 位随机 hex），无需手动传入。\n\n"
        "**状态枚举：** 申请中 | 在研（默认）| 已结题 | 暂停 | 终止\n\n"
        "**类别枚举：** 国家级 | 省部级 | 横向课题 | 院内课题 | 国际合作 | 其他"
    ),
    status_code=201,
)
async def create_project(body: ProjectCreate):
    result = await svc.create_project(body.model_dump())
    return result


@router.post(
    "/batch",
    summary="批量创建项目",
    description=(
        "通过 JSON 列表批量创建项目。\n\n"
        "**重复判定：** 相同项目名称 + 相同负责人（name + pi_name，大小写不敏感）视为重复，"
        "skip_duplicates=true 时跳过，false 时报错。\n\n"
        "**返回：** 每条记录的处理结果汇总。"
    ),
    status_code=200,
)
async def batch_create_projects(body: ProjectBatchRequest):
    items = [item.model_dump() for item in body.items]
    return await svc.batch_create_projects(items=items, skip_duplicates=body.skip_duplicates)


@router.patch(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="更新项目",
    description="更新指定项目的字段。所有字段均可选，仅传入需要修改的字段。",
)
async def update_project(project_id: str, body: ProjectUpdate):
    updates = body.model_dump(exclude_none=True)
    result = await svc.update_project(project_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return result


@router.delete(
    "/{project_id}",
    summary="删除项目",
    description="删除指定项目记录。",
    status_code=204,
)
async def delete_project(project_id: str):
    deleted = await svc.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
