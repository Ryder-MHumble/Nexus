"""AMiner API endpoints — /api/v1/aminer/

Endpoints:
  GET  /aminer/organizations                查询机构信息（本地 JSON）
  GET  /aminer/scholars/search              搜索学者基础信息（AMiner API）
  GET  /aminer/scholars/{aminer_id}         获取学者详细信息（AMiner API）
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.schemas.aminer import (
    OrganizationItem,
    OrganizationListResponse,
    ScholarDetailResponse,
    ScholarSearchItem,
    ScholarSearchResponse,
)
from app.services.core.institution import search_institutions_for_aminer
from app.services.external.aminer_client import get_aminer_client

router = APIRouter()


@router.get(
    "/organizations",
    response_model=OrganizationListResponse,
    summary="查询机构信息",
    description="从本地 data/institution.json 查询机构信息（模糊匹配 name_zh）",
)
async def search_organizations(
    name: str = Query(..., description="机构名称（支持模糊匹配）"),
):
    """Search organizations from local institution.json."""
    matches = search_institutions_for_aminer(name)

    items = []
    for org in matches:
        items.append(
            OrganizationItem(
                name_zh=org.get("name", ""),
                name_en=org.get("name_en", ""),
                org_id=org.get("org_id", ""),
                org_name=org.get("org_name", ""),
                category=org.get("category", ""),
                priority=org.get("priority", ""),
            )
        )

    return OrganizationListResponse(total=len(items), items=items)


@router.get(
    "/scholars/search",
    response_model=ScholarSearchResponse,
    summary="搜索学者基础信息",
    description="调用 AMiner API 搜索学者，返回候选列表（包含 id, name, org 等基础字段）",
)
async def search_scholars(
    name: str = Query(..., description="学者姓名"),
    org: str = Query(..., description="机构 org_name（从机构查询接口获取）"),
    size: int = Query(10, ge=1, le=100, description="返回结果数量"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
):
    """Search scholars via AMiner API."""
    try:
        client = get_aminer_client()
        result = await client.search_scholars(name, org, size, offset)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AMiner API error: {exc.response.status_code}",
        ) from exc

    # Parse AMiner response
    data = result.get("data", [])
    items = []
    for scholar in data:
        items.append(
            ScholarSearchItem(
                id=scholar.get("id", ""),
                name=scholar.get("name", ""),
                name_zh=scholar.get("name_zh", ""),
                avatar=scholar.get("avatar", ""),
                org=scholar.get("org", ""),
                position=scholar.get("position", ""),
                h_index=scholar.get("indices", {}).get("hindex", -1),
            )
        )

    return ScholarSearchResponse(total=len(items), items=items)


@router.get(
    "/scholars/{aminer_id}",
    response_model=ScholarDetailResponse,
    summary="获取学者详细信息",
    description="调用 AMiner API 获取学者完整 profile（教育经历、论文、专利等）",
)
async def get_scholar_detail(aminer_id: str):
    """Get scholar detail via AMiner API."""
    try:
        client = get_aminer_client()
        result = await client.get_scholar_detail(aminer_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Scholar '{aminer_id}' not found in AMiner",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"AMiner API error: {exc.response.status_code}",
        ) from exc

    # Parse AMiner response
    data = result.get("data", {})
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Scholar '{aminer_id}' not found in AMiner",
        )

    return ScholarDetailResponse(
        id=data.get("id", ""),
        name=data.get("name", ""),
        name_zh=data.get("name_zh", ""),
        avatar=data.get("avatar", ""),
        org=data.get("org", ""),
        position=data.get("position", ""),
        bio=data.get("bio", ""),
        email=data.get("email", ""),
        homepage=data.get("homepage", ""),
        h_index=data.get("indices", {}).get("hindex", -1),
        citations=data.get("indices", {}).get("citations", -1),
        raw_data=data,
    )
