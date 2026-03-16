from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_article_search_params
from app.schemas.article import (
    ArticleBrief,
    ArticleDetail,
    ArticleSearchParams,
    ArticleStats,
    ArticleUpdate,
)
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.services import article_service

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedResponse[ArticleBrief],
    summary="文章列表",
    description="查询文章列表，支持按维度、信源、关键词、日期范围过滤，以及字段排序和分页。",
)
async def list_articles(
    params: ArticleSearchParams = Depends(get_article_search_params),
):
    return await article_service.list_articles(params)


@router.get(
    "/search",
    response_model=PaginatedResponse[ArticleBrief],
    summary="全文搜索",
    description="在文章标题和正文中进行关键词搜索，参数与列表接口相同。",
)
async def search_articles(
    params: ArticleSearchParams = Depends(get_article_search_params),
):
    return await article_service.list_articles(params)


@router.get(
    "/stats",
    response_model=list[ArticleStats],
    summary="文章统计",
    description="获取文章聚合统计，默认按维度分组。可选按信源分组。",
)
async def get_stats(
    group_by: str = "dimension",
):
    return await article_service.get_article_stats(group_by)


@router.get(
    "/{article_id}",
    response_model=ArticleDetail,
    summary="文章详情",
    description="根据文章 ID (url_hash) 获取完整文章内容，包含正文和额外元数据。",
    responses={404: {"model": ErrorResponse, "description": "文章不存在"}},
)
async def get_article(
    article_id: str,
):
    article = await article_service.get_article(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.patch(
    "/{article_id}",
    response_model=ArticleDetail,
    summary="更新文章",
    description="更新文章元数据，如标记已读状态或设置重要度评分。",
    responses={404: {"model": ErrorResponse, "description": "文章不存在"}},
)
async def update_article(
    article_id: str,
    data: ArticleUpdate,
):
    article = await article_service.update_article(article_id, data)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
