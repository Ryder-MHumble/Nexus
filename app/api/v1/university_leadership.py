"""University leadership API — 独立分类。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.institution import (
    UniversityLeadershipAllResponse,
    UniversityLeadershipCurrentResponse,
    UniversityLeadershipListResponse,
)

router = APIRouter()


@router.get(
    "",
    response_model=UniversityLeadershipListResponse,
    summary="高校领导列表",
    description="返回高校领导数据列表（分页），用于高校领导模块列表渲染。",
)
async def list_university_leadership_endpoint(
    keyword: str | None = Query(default=None, description="高校名/信源名关键词"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
):
    from app.services.core.institution import list_university_leadership_current

    return await list_university_leadership_current(
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/all",
    response_model=UniversityLeadershipAllResponse,
    summary="高校领导全量数据",
    description="返回当前库中全部高校领导数据。",
)
async def get_all_university_leadership_endpoint(
    keyword: str | None = Query(default=None, description="高校名/信源名关键词"),
):
    from app.services.core.institution import get_all_university_leadership_current

    return await get_all_university_leadership_current(keyword=keyword)


@router.get(
    "/{institution_id}",
    response_model=UniversityLeadershipCurrentResponse,
    summary="高校领导当前数据",
    description="返回该机构对应高校的最新领导信息（用于机构-高校-大学领导模块渲染）。",
)
async def get_university_leadership_current_endpoint(institution_id: str):
    from app.services.core.institution import get_university_leadership_current

    result = await get_university_leadership_current(institution_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No leadership data for '{institution_id}'")
    return result
