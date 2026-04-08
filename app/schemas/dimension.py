from pydantic import BaseModel, Field


class DimensionSummary(BaseModel):
    """维度概览信息。"""

    id: str = Field(description="维度 ID", examples=["national_policy"])
    name: str = Field(description="维度显示名称", examples=["对国家"])
    article_count: int = Field(description="当前维度文章数", examples=[128])
    last_updated: str | None = Field(
        default=None,
        description="最近一次抓取/更新的 ISO 8601 时间",
        examples=["2026-04-08T09:30:00+08:00"],
    )
