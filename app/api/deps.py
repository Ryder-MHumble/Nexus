from fastapi import Query

from app.schemas.article import ArticleSearchParams


def get_article_search_params(
    dimension: str | None = Query(None, description="Filter by dimension"),
    source_id: str | None = Query(None, description="按单个信源 ID 筛选（精确匹配）"),
    source_ids: str | None = Query(None, description="按多个信源 ID 筛选（逗号分隔，精确匹配）"),
    source_name: str | None = Query(None, description="按单个信源名称筛选（模糊匹配）"),
    source_names: str | None = Query(None, description="按多个信源名称筛选（逗号分隔，模糊匹配）"),
    keyword: str | None = Query(None, description="Keyword filter in title/content"),
    date_from: str | None = Query(None, description="Start date (ISO format)"),
    date_to: str | None = Query(None, description="End date (ISO format)"),
    sort_by: str = Query("crawled_at", description="Sort field"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    custom_field_key: str | None = Query(None, description="按自定义字段 key 过滤"),
    custom_field_value: str | None = Query(
        None, description="自定义字段 value（需配合 custom_field_key）"
    ),
) -> ArticleSearchParams:
    return ArticleSearchParams(
        dimension=dimension,
        source_id=source_id,
        source_ids=source_ids,
        source_name=source_name,
        source_names=source_names,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
        custom_field_key=custom_field_key,
        custom_field_value=custom_field_value,
    )
