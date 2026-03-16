from datetime import datetime

from pydantic import BaseModel, Field


class SourceResponse(BaseModel):
    """信源详情。"""

    id: str = Field(description="信源唯一 ID", examples=["tech_arxiv"])
    name: str = Field(description="信源名称", examples=["ArXiv AI Papers"])
    url: str = Field(
        description="信源 URL",
        examples=["https://arxiv.org/list/cs.AI/recent"],
    )
    dimension: str = Field(description="所属维度", examples=["technology"])
    crawl_method: str = Field(
        description="爬取方式: static / dynamic / rss / snapshot / custom",
        examples=["static"],
    )
    schedule: str = Field(
        description="调度频率: hourly / daily / twice_daily 等",
        examples=["daily"],
    )
    is_enabled: bool = Field(description="是否启用", examples=[True])
    priority: int = Field(description="优先级（1-5，1 最高）", examples=[2])
    last_crawl_at: datetime | None = Field(
        default=None, description="上次爬取时间"
    )
    last_success_at: datetime | None = Field(
        default=None, description="上次成功爬取时间"
    )
    consecutive_failures: int = Field(
        default=0, description="连续失败次数", examples=[0]
    )


class SourceUpdate(BaseModel):
    """信源更新请求体。"""

    is_enabled: bool | None = Field(
        default=None, description="启用或禁用信源"
    )
