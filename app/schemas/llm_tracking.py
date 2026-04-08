"""Pydantic schemas for LLM tracking endpoints."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LLMModelSummary(BaseModel):
    call_count: int = Field(default=0, description="调用次数")
    success_count: int = Field(default=0, description="成功次数")
    error_count: int = Field(default=0, description="失败次数")
    total_input_tokens: int = Field(default=0, description="累计输入 token")
    total_output_tokens: int = Field(default=0, description="累计输出 token")
    total_cost_usd: float = Field(default=0.0, description="累计成本（USD）")


class LLMSummaryResponse(BaseModel):
    total_calls: int = Field(default=0, description="总调用次数")
    total_cost_usd: float = Field(default=0.0, description="总成本（USD）")
    last_updated: datetime | None = Field(
        default=None,
        description="最后更新时间（ISO 8601）",
    )
    models: dict[str, LLMModelSummary] = Field(
        default_factory=dict,
        description="按模型汇总的调用统计",
    )


class LLMCallRecord(BaseModel):
    timestamp: datetime = Field(description="调用时间（ISO 8601）")
    model: str = Field(description="模型标识")
    stage: str = Field(description="管线阶段")
    article_id: str | None = Field(default=None, description="文章 ID/url_hash")
    article_title: str | None = Field(default=None, description="文章标题")
    source_id: str | None = Field(default=None, description="信源 ID")
    dimension: str | None = Field(default=None, description="数据维度")
    input_tokens: int = Field(default=0, description="输入 token")
    output_tokens: int = Field(default=0, description="输出 token")
    total_tokens: int = Field(default=0, description="总 token")
    cost_usd: float = Field(default=0.0, description="单次调用成本（USD）")
    duration_ms: float | None = Field(default=None, description="耗时（毫秒）")
    success: bool = Field(description="是否成功")
    error_message: str | None = Field(default=None, description="失败原因")
    prompt_length: int = Field(default=0, description="prompt 长度")
    system_prompt_length: int = Field(default=0, description="system prompt 长度")
    response_length: int = Field(default=0, description="响应长度")


class LLMCallsByStageResponse(BaseModel):
    stage: str = Field(description="管线阶段")
    call_count: int = Field(description="调用条数")
    calls: list[LLMCallRecord] = Field(description="调用记录")


class LLMCallsByArticleResponse(BaseModel):
    article_id: str = Field(description="文章 ID/url_hash")
    call_count: int = Field(description="调用条数")
    calls: list[LLMCallRecord] = Field(description="调用记录")


class LLMAuditTrailFilters(BaseModel):
    limit: int = Field(description="返回上限")
    stage: str | None = Field(default=None, description="阶段过滤")
    start_date: str | None = Field(default=None, description="起始日期过滤")


class LLMAuditTrailResponse(BaseModel):
    record_count: int = Field(description="返回记录数")
    records: list[LLMCallRecord] = Field(description="审计记录")
    filters_applied: LLMAuditTrailFilters = Field(description="已应用的过滤条件")


class LLMCostByModelItem(BaseModel):
    call_count: int = Field(default=0, description="调用次数")
    success_count: int = Field(default=0, description="成功次数")
    error_count: int = Field(default=0, description="失败次数")
    total_tokens: int = Field(default=0, description="总 token")
    input_tokens: int = Field(default=0, description="输入 token")
    output_tokens: int = Field(default=0, description="输出 token")
    total_cost_usd: float = Field(default=0.0, description="总成本（USD）")
    avg_cost_per_call: float = Field(default=0.0, description="平均单次成本（USD）")


class LLMCostByModelResponse(BaseModel):
    generated_at: datetime = Field(description="生成时间（ISO 8601）")
    total_cost_usd: float = Field(default=0.0, description="总成本（USD）")
    total_calls: int = Field(default=0, description="总调用数")
    by_model: dict[str, LLMCostByModelItem] = Field(
        default_factory=dict,
        description="按模型拆分的成本统计",
    )


class LLMTrackingHealthResponse(BaseModel):
    status: str = Field(description="健康状态", examples=["healthy"])
    tracking_enabled: bool = Field(description="是否启用调用跟踪")
    message: str = Field(description="状态说明")
