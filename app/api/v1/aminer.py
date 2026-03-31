"""AMiner API endpoints — /api/v1/aminer/

Endpoints:
  GET  /aminer/organizations                查询机构信息（本地 JSON）
  GET  /aminer/scholars/search              搜索学者基础信息（AMiner API）
  GET  /aminer/scholars/{aminer_id}         获取学者详细信息（代理详情接口）
"""
from __future__ import annotations

import httpx
from typing import Any

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


def _pick_int(*candidates: Any, default: int = -1) -> int:
    """Return the first candidate that can be safely converted to int."""
    for value in candidates:
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            try:
                return int(float(text))
            except ValueError:
                continue
    return default


def _pick_text(*candidates: Any) -> str:
    """Return the first non-empty text value."""
    for value in candidates:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        return text
    return ""


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
    description=(
        "通过详情聚合接口获取学者完整 profile（教育经历、论文、专利等）。"
        "该接口仅需学者 id，不依赖 AMINER_API_KEY。"
    ),
)
async def get_scholar_detail(
    aminer_id: str,
    force_refresh: bool = Query(False, description="是否强制刷新上游缓存"),
):
    """Get scholar detail by scholar ID."""
    try:
        client = get_aminer_client()
        result = await client.get_scholar_detail(aminer_id, force_refresh=force_refresh)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Scholar '{aminer_id}' not found",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Scholar detail API error: {exc.response.status_code}",
        ) from exc

    # Compatible with both wrapped payload ({data: {...}}) and direct payload ({...}).
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, dict):
        data = result if isinstance(result, dict) else {}

    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Scholar '{aminer_id}' not found",
        )

    indices = data.get("indices", {})
    if not isinstance(indices, dict):
        indices = {}

    org = _pick_text(data.get("org"))
    if not org:
        orgs = data.get("orgs", [])
        if isinstance(orgs, list):
            org = _pick_text(orgs)

    return ScholarDetailResponse(
        id=data.get("id", ""),
        name=_pick_text(data.get("name")),
        name_zh=_pick_text(data.get("name_zh")),
        avatar=_pick_text(data.get("avatar")),
        org=org,
        position=_pick_text(data.get("position")),
        bio=_pick_text(data.get("bio"), data.get("bio_zh")),
        email=_pick_text(data.get("email"), data.get("emails")),
        homepage=_pick_text(data.get("homepage"), data.get("home_page")),
        h_index=_pick_int(
            data.get("h_index"),
            data.get("hindex"),
            indices.get("hindex"),
            indices.get("h_index"),
            default=-1,
        ),
        citations=_pick_int(
            data.get("citations"),
            data.get("n_citation"),
            data.get("ncitation"),
            indices.get("citations"),
            indices.get("n_citation"),
            indices.get("ncitation"),
            default=-1,
        ),
        raw_data=data,
    )
