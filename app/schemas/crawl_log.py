from datetime import datetime

from pydantic import BaseModel, Field


class CrawlLogResponse(BaseModel):
    """单次爬取任务的日志记录。"""

    source_id: str = Field(description="信源 ID", examples=["tech_arxiv"])
    status: str = Field(
        description="爬取状态: success / partial / failed",
        examples=["success"],
    )
    items_total: int = Field(description="本次解析到的条目总数", examples=[25])
    items_new: int = Field(description="新增的条目数", examples=[12])
    error_message: str | None = Field(
        default=None, description="错误信息（成功时为 null）"
    )
    started_at: datetime | None = Field(
        default=None, description="任务开始时间"
    )
    finished_at: datetime | None = Field(
        default=None, description="任务结束时间"
    )
    duration_seconds: float | None = Field(
        default=None, description="耗时（秒）", examples=[3.45]
    )


class CrawlHealthResponse(BaseModel):
    """全局爬取健康度概览。"""

    total_sources: int = Field(description="信源总数", examples=[129])
    enabled_sources: int = Field(description="启用的信源数", examples=[105])
    healthy: int = Field(description="健康的信源数（最近成功）", examples=[98])
    warning: int = Field(
        description="告警的信源数（偶发失败）", examples=[5]
    )
    failing: int = Field(
        description="失败的信源数（连续失败）", examples=[2]
    )
    last_24h_crawls: int = Field(
        description="过去 24 小时的爬取任务数", examples=[312]
    )
    last_24h_new_articles: int = Field(
        description="过去 24 小时新增文章数", examples=[876]
    )
