from datetime import datetime

from pydantic import BaseModel, Field


class ArticleBrief(BaseModel):
    """文章摘要信息，用于列表展示。"""

    id: str = Field(description="文章唯一 ID (url_hash)", examples=["a1b2c3d4e5f6"])
    source_id: str = Field(description="所属信源 ID", examples=["tech_arxiv"])
    dimension: str = Field(
        description="所属维度",
        examples=["technology"],
    )
    url: str = Field(
        description="文章原始链接",
        examples=["https://arxiv.org/abs/2401.12345"],
    )
    title: str = Field(
        description="文章标题",
        examples=["Large Language Models for Code Generation: A Survey"],
    )
    author: str | None = Field(
        default=None, description="作者", examples=["张三"]
    )
    published_at: datetime | None = Field(
        default=None, description="发布时间（ISO 8601）"
    )
    crawled_at: datetime | None = Field(
        default=None, description="爬取时间（ISO 8601）"
    )
    tags: list[str] = Field(
        default=[], description="标签列表", examples=[["AI", "LLM", "政策"]]
    )
    is_read: bool = Field(default=False, description="是否已读")
    importance: int | None = Field(
        default=None, description="重要度评分（0-100）", examples=[85]
    )
    custom_fields: dict[str, str] = Field(
        default={}, description="用户自定义字段（key-value 均为字符串）"
    )


class ArticleDetail(ArticleBrief):
    """文章详情，包含正文内容和额外字段。"""

    content: str | None = Field(
        default=None, description="文章正文（纯文本，用于搜索）"
    )
    content_html: str | None = Field(
        default=None, description="文章正文（富文本 HTML，保留图片和格式标签）"
    )
    extra: dict = Field(
        default={},
        description="额外元数据（JSON），不同信源可能包含不同字段",
        examples=[{
            "pdf_url": "https://arxiv.org/pdf/2401.12345",
            "images": [{"src": "https://example.com/fig1.png", "alt": "Figure 1"}],
        }],
    )


class ArticleUpdate(BaseModel):
    """文章更新请求体。"""

    is_read: bool | None = Field(
        default=None, description="标记为已读/未读"
    )
    importance: int | None = Field(
        default=None, description="设置重要度评分（0-100）", examples=[90]
    )
    custom_fields: dict[str, str | None] | None = Field(
        default=None,
        description="自定义字段更新（浅合并：新 key 添加，null 值删除对应 key）",
    )


class ArticleSearchParams(BaseModel):
    """文章搜索参数（内部使用）。"""

    dimension: str | None = None
    source_id: str | None = None
    source_ids: str | None = None
    source_name: str | None = None
    source_names: str | None = None
    tags: list[str] | None = None
    keyword: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    sort_by: str = "crawled_at"
    order: str = "desc"
    page: int = 1
    page_size: int = 20
    custom_field_key: str | None = None
    custom_field_value: str | None = None


class ArticleStats(BaseModel):
    """文章统计信息。"""

    group: str = Field(
        description="分组名称（维度名或信源 ID）",
        examples=["technology"],
    )
    count: int = Field(description="该分组下的文章总数", examples=[342])
