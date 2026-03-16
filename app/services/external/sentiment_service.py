"""Service layer for sentiment monitoring — reads social media data from main DB."""

from __future__ import annotations

import logging
import math

from app.db.client import get_client
from app.schemas.sentiment import (
    PlatformStats,
    SentimentComment,
    SentimentContentDetail,
    SentimentContentItem,
    SentimentFeedResponse,
    SentimentOverview,
)

logger = logging.getLogger(__name__)

PLATFORM_LABELS: dict[str, str] = {
    "xhs": "小红书",
    "dy": "抖音",
    "bili": "哔哩哔哩",
    "zhihu": "知乎",
}


def _label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)


# ── Feed ───────────────────────────────────────────────────────────────

async def get_feed(
    *,
    platform: str | None = None,
    keyword: str | None = None,
    sort_by: str = "publish_time",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> SentimentFeedResponse:
    """Return a paginated feed of social media content."""
    db = get_client()

    query = db.table("sentiment_contents").select("*", count="exact")

    if platform:
        query = query.eq("platform", platform)
    if keyword:
        query = query.or_(
            f"title.ilike.%{keyword}%,description.ilike.%{keyword}%,"
            f"nickname.ilike.%{keyword}%"
        )

    desc = sort_order == "desc"
    query = query.order(sort_by, desc=desc)

    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    result = await query.execute()
    total = result.count or 0
    items = [SentimentContentItem(**row) for row in (result.data or [])]

    return SentimentFeedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)),
    )


# ── Single content detail with comments ────────────────────────────────

async def get_content_detail(content_id: str) -> SentimentContentDetail | None:
    """Return a single content item with its comments."""
    db = get_client()

    content_result = await (
        db.table("sentiment_contents")
        .select("*")
        .eq("content_id", content_id)
        .limit(1)
        .execute()
    )
    if not content_result.data:
        return None

    content_data = content_result.data[0]

    comments_result = await (
        db.table("sentiment_comments")
        .select("*")
        .eq("content_id", content_id)
        .order("publish_time", desc=False)
        .execute()
    )
    comments = [SentimentComment(**c) for c in (comments_result.data or [])]

    return SentimentContentDetail(**content_data, comments=comments)


# ── Overview statistics ────────────────────────────────────────────────

async def get_overview() -> SentimentOverview:
    """Return dashboard overview statistics."""
    db = get_client()

    contents_result = await (
        db.table("sentiment_contents").select("*", count="exact").limit(0).execute()
    )
    total_contents = contents_result.count or 0

    comments_result = await (
        db.table("sentiment_comments").select("*", count="exact").limit(0).execute()
    )
    total_comments = comments_result.count or 0

    all_contents = await db.table("sentiment_contents").select(
        "id,platform,content_id,content_type,title,description,content_url,"
        "cover_url,nickname,avatar,ip_location,liked_count,comment_count,"
        "share_count,collected_count,source_keyword,publish_time,created_at,"
        "platform_data"
    ).execute()
    rows = all_contents.data or []

    platform_map: dict[str, dict] = {}
    total_engagement = 0
    for row in rows:
        p = row["platform"]
        if p not in platform_map:
            platform_map[p] = {
                "content_count": 0,
                "total_likes": 0,
                "total_comments": 0,
                "total_shares": 0,
                "total_collected": 0,
            }
        pm = platform_map[p]
        pm["content_count"] += 1
        pm["total_likes"] += row.get("liked_count") or 0
        pm["total_comments"] += row.get("comment_count") or 0
        pm["total_shares"] += row.get("share_count") or 0
        pm["total_collected"] += row.get("collected_count") or 0

        engagement = (
            (row.get("liked_count") or 0)
            + (row.get("comment_count") or 0)
            + (row.get("share_count") or 0)
            + (row.get("collected_count") or 0)
        )
        total_engagement += engagement

    platforms = [
        PlatformStats(
            platform=p,
            platform_label=_label(p),
            **stats,
        )
        for p, stats in sorted(
            platform_map.items(), key=lambda x: x[1]["content_count"], reverse=True
        )
    ]

    rows_sorted = sorted(
        rows,
        key=lambda r: (
            (r.get("liked_count") or 0)
            + (r.get("comment_count") or 0)
            + (r.get("share_count") or 0)
            + (r.get("collected_count") or 0)
        ),
        reverse=True,
    )
    top_content = [SentimentContentItem(**r) for r in rows_sorted[:5]]

    keywords = sorted({r["source_keyword"] for r in rows if r.get("source_keyword")})

    return SentimentOverview(
        total_contents=total_contents,
        total_comments=total_comments,
        total_engagement=total_engagement,
        platforms=platforms,
        top_content=top_content,
        keywords=keywords,
    )
