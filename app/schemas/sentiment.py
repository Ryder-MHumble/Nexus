"""Pydantic schemas for sentiment monitoring (social media data from main DB)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# ── Feed item (list view) ──────────────────────────────────────────────

class SentimentContentItem(BaseModel):
    """A single social media content item for the feed."""

    model_config = {"extra": "ignore"}

    id: int = Field(description="Database row ID")
    platform: str = Field(description="Platform code: xhs / dy / bili / zhihu")
    content_id: str = Field(description="Platform-native content ID")
    content_type: str | None = Field(default=None, description="Content type: video / normal / 0")
    title: str | None = Field(default=None, description="Content title")
    description: str | None = Field(default=None, description="Content description / body text")
    content_url: str | None = Field(default=None, description="Link to original content")
    cover_url: str | None = Field(default=None, description="Cover image URL")

    # Author fields (matching source DB column names)
    user_id: str | None = Field(default=None, description="Platform user ID")
    nickname: str | None = Field(default=None, description="Author nickname")
    avatar: str | None = Field(default=None, description="Author avatar URL")
    ip_location: str | None = Field(default=None, description="Author IP location")

    # Engagement
    liked_count: int = Field(default=0, description="Like count")
    comment_count: int = Field(default=0, description="Comment count")
    share_count: int = Field(default=0, description="Share/forward count")
    collected_count: int = Field(default=0, description="Collection/bookmark count")

    # Crawl metadata
    source_keyword: str | None = Field(default=None, description="Search keyword used")
    crawl_task_id: str | None = Field(default=None, description="Crawl task ID")
    platform_data: dict | None = Field(
        default=None,
        description="Platform-specific extra data (tags, video_url, images, etc.)",
    )

    # Timestamps (BIGINT ms from source)
    publish_time: int | None = Field(default=None, description="Publish timestamp (ms)")
    add_ts: int | None = Field(default=None, description="Add timestamp (ms)")
    last_modify_ts: int | None = Field(default=None, description="Last modify timestamp (ms)")
    created_at: str | None = Field(default=None, description="DB insert time (ISO)")
    updated_at: str | None = Field(default=None, description="DB update time (ISO)")


# ── Comment ────────────────────────────────────────────────────────────

class SentimentComment(BaseModel):
    """A comment on a content item."""

    model_config = {"extra": "ignore"}

    id: int
    platform: str
    comment_id: str
    content_id: str
    parent_comment_id: str | None = Field(default=None, description="None or '0' = top-level")
    content: str | None = Field(default=None, description="Comment text")
    pictures: str | None = Field(default=None, description="Attached picture URLs")
    user_id: str | None = Field(default=None)
    nickname: str | None = Field(default=None)
    avatar: str | None = Field(default=None)
    ip_location: str | None = Field(default=None)
    like_count: int = Field(default=0)
    dislike_count: int = Field(default=0)
    sub_comment_count: int = Field(default=0)
    platform_data: dict | None = Field(default=None)
    publish_time: int | None = Field(default=None)
    add_ts: int | None = Field(default=None)
    last_modify_ts: int | None = Field(default=None)
    created_at: str | None = Field(default=None)
    updated_at: str | None = Field(default=None)


# ── Content detail (with comments) ────────────────────────────────────

class SentimentContentDetail(SentimentContentItem):
    """Full content detail including comments."""

    comments: list[SentimentComment] = Field(
        default=[], description="Comments on this content"
    )


# ── Stats / overview ──────────────────────────────────────────────────

class PlatformStats(BaseModel):
    """Stats for a single platform."""

    platform: str = Field(description="Platform code")
    platform_label: str = Field(description="Platform display name")
    content_count: int = Field(description="Total content count")
    total_likes: int = Field(default=0)
    total_comments: int = Field(default=0)
    total_shares: int = Field(default=0)
    total_collected: int = Field(default=0)


class SentimentOverview(BaseModel):
    """Overview statistics for sentiment dashboard."""

    total_contents: int = Field(description="Total content count across all platforms")
    total_comments: int = Field(description="Total comments in DB")
    total_engagement: int = Field(
        description="Sum of likes + comments + shares + collections"
    )
    platforms: list[PlatformStats] = Field(description="Per-platform breakdown")
    top_content: list[SentimentContentItem] = Field(
        default=[], description="Top content by engagement"
    )
    keywords: list[str] = Field(
        default=[], description="Distinct source keywords used"
    )


# ── Feed response ─────────────────────────────────────────────────────

class SentimentFeedResponse(BaseModel):
    """Paginated feed response."""

    items: list[SentimentContentItem] = Field(description="Content items")
    total: int = Field(description="Total matching count")
    page: int = Field(default=1)
    page_size: int = Field(default=20)
    total_pages: int = Field(default=1)
