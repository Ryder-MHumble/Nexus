from fastapi import APIRouter, Query

from app.schemas.article import ArticleBrief, ArticleSearchParams
from app.schemas.common import PaginatedResponse
from app.schemas.dimension import DimensionSummary
from app.services import article_service, dimension_service

router = APIRouter()


@router.get(
    "",
    response_model=list[DimensionSummary],
    summary="维度列表",
    description="列出当前系统支持的全部维度，并返回每个维度的文章数量和最近更新时间。",
)
async def list_dimensions():
    return await dimension_service.list_dimensions()


@router.get(
    "/{dimension}",
    response_model=PaginatedResponse[ArticleBrief],
    summary="维度文章",
    description="获取指定维度下的文章列表，支持关键词搜索、排序和分页。\n\n"
    "可用维度: `national_policy`, `beijing_policy`, `regional_policy`, `technology`, `talent`, "
    "`industry`, `universities`, `events`, `personnel`, `twitter`",
)
async def get_dimension_articles(
    dimension: str,
    keyword: str | None = Query(None),
    sort_by: str = Query("crawled_at"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    params = ArticleSearchParams(
        dimension=dimension,
        keyword=keyword,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
    )
    return await article_service.list_articles(params)
