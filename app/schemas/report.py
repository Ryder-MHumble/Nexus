"""
报告相关的 Pydantic schemas
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReportGenerateRequest(BaseModel):
    """报告生成请求"""

    dimension: str = Field(..., description="维度：sentiment/policy/technology/personnel/university")
    date_range: Optional[tuple[str, str]] = Field(None, description="日期范围 (start, end)")
    output_format: str = Field("markdown", description="输出格式：markdown/json/html")
    filters: Dict[str, Any] = Field(default_factory=dict, description="额外过滤条件")


class ReportMetadataResponse(BaseModel):
    """报告元数据响应"""

    title: str
    generated_at: datetime
    data_range: str
    dimension: str
    total_items: int
    additional_info: Dict[str, Any] = Field(default_factory=dict)


class ReportSectionResponse(BaseModel):
    """报告章节响应"""

    title: str
    content: str
    order: int


class ReportResponse(BaseModel):
    """报告响应"""

    metadata: ReportMetadataResponse
    content: str = Field(..., description="格式化后的报告内容")
    format: str = Field(..., description="输出格式")


class ReportDimensionItemResponse(BaseModel):
    """单个报告维度定义。"""

    id: str = Field(description="维度 ID", examples=["sentiment"])
    name: str = Field(description="维度名称", examples=["舆情监测"])
    description: str = Field(description="维度说明")
    status: str = Field(description="实现状态", examples=["implemented"])


class ReportDimensionsListResponse(BaseModel):
    """GET /reports/dimensions 响应。"""

    dimensions: List[ReportDimensionItemResponse] = Field(
        description="支持的报告维度列表",
    )


class ReportListItem(BaseModel):
    """报告列表项"""

    id: str
    title: str
    dimension: str
    generated_at: datetime
    data_range: str
    total_items: int


class ReportListResponse(BaseModel):
    """报告列表响应"""

    reports: List[ReportListItem]
    total: int
