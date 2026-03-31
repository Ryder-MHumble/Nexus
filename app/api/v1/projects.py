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
    ProjectTaxonomyTree,
    ProjectUpdate,
)
from app.services.core import project_service as svc
from app.services.core import project_taxonomy_service as taxonomy_svc

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
        "获取项目标签列表，支持分类和学者关联过滤。\n\n"
        "**过滤参数：**\n"
        "- `category`: 一级分类（教育培养/科研学术/人才引育）\n"
        "- `subcategory`: 二级子类（如 学术委员会）\n"
        "- `scholar_id`: 关联学者 ID\n"
        "- `keyword`: 标题/摘要关键词\n"
    ),
)
async def list_projects(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    category: str | None = Query(default=None, description="一级分类"),
    subcategory: str | None = Query(default=None, description="二级子类"),
    scholar_id: str | None = Query(default=None, description="关联学者 ID"),
    keyword: str | None = Query(default=None, description="全文关键词搜索"),
    custom_field_key: str | None = Query(default=None, description="自定义字段名（需配合 custom_field_value 使用）"),
    custom_field_value: str | None = Query(default=None, description="自定义字段值"),
):
    return await svc.list_projects(
        page=page,
        page_size=page_size,
        category=category,
        subcategory=subcategory,
        scholar_id=scholar_id,
        keyword=keyword,
        custom_field_key=custom_field_key,
        custom_field_value=custom_field_value,
    )


@router.get(
    "/stats",
    response_model=ProjectStatsResponse,
    summary="项目统计",
    description="返回项目标签的聚合统计信息：按一级分类、二级子类分布，以及项目-学者关联总数。",
)
async def get_stats():
    return await svc.get_stats()


@router.get(
    "/taxonomy",
    response_model=ProjectTaxonomyTree,
    summary="项目分类树",
    description="返回项目的二级分类树（一级分类 + 二级子类），用于前端筛选按钮渲染。",
)
async def get_taxonomy():
    return taxonomy_svc.get_taxonomy_tree()


@router.get(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="项目详情",
    description=(
        "根据项目 ID 获取完整项目标签记录，包含：\n"
        "- 分类信息（category/subcategory）\n"
        "- 标题与摘要\n"
        "- 关联学者列表\n"
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
        "创建新的项目标签记录。\n\n"
        "**必填字段：** `category`、`subcategory`、`title`\n\n"
        "**项目 ID** 由系统自动生成，无需手动传入。"
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
        "通过 JSON 列表批量创建项目标签。\n\n"
        "**重复判定：** 相同标题 + 相同一级分类 + 相同二级子类视为重复，"
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
