"""
论文产业转化分析 API

端点列表：
  POST /paper-transfer/run     — 触发后台分析 Pipeline
  GET  /paper-transfer/status  — 查询 Pipeline 运行状态
  GET  /paper-transfer/results — 获取论文转化分析卡片列表
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.intel.paper_transfer import (
    PaperTransferResults,
    PipelineRunState,
    RunRequest,
    RunResponse,
)
from app.services.intel.paper_transfer import service as svc

router = APIRouter()


@router.post(
    "/run",
    response_model=RunResponse,
    summary="触发论文转化分析 Pipeline",
)
async def run_pipeline(req: RunRequest) -> RunResponse:
    """
    触发后台 Pipeline：

    1. 从外部 API 获取全部学生列表
    2. 逐一拉取每位学生的论文（可按发表日期和学校筛选）
    3. 为含 arxiv_id 的论文异步补全摘要
    4. 调用 Gemini LLM 进行分级（A/B/C）和转化分析
    5. 将结果保存至本地，供 GET /results 查询

    **参数说明：**
    - `date_from`: 论文发表起始日期（YYYY-MM-DD），默认为近 6 个月
    - `school`: 按学生所属学校模糊筛选（如 `北京大学`），为空则处理全部学生
    - `max_papers`: 最多处理的论文数（默认 500，可调高但会增加 LLM 成本）

    **返回：** `started`（已启动）或 `already_running`（已有运行中的任务）
    """
    return await svc.trigger_run(req)


@router.get(
    "/status",
    response_model=PipelineRunState,
    summary="查询 Pipeline 运行状态",
)
async def get_status() -> PipelineRunState:
    """
    返回最近一次 Pipeline 的运行状态和实时进度。

    **status 枚举值：** `idle` / `running` / `completed` / `failed`

    **progress 字段：**
    - `students_fetched`: 已获取的学生数
    - `papers_fetched`: 已拉取的论文数（含学生维度）
    - `abstracts_fetched`: 成功补全摘要的论文数
    - `papers_analyzed`: LLM 已完成分析的论文数
    """
    return svc.get_status()


@router.get(
    "/results",
    response_model=PaperTransferResults,
    summary="获取论文转化分析结果",
)
async def get_results(
    grade: str | None = Query(
        None, description="按档位筛选：A（主动跟进）/ B（保持关注）/ C（暂不处理）"
    ),
    school: str | None = Query(None, description="按学生所属学校模糊筛选，如 `北京大学`"),
    keyword: str | None = Query(
        None, description="关键词搜索，匹配论文标题、摘要或推荐理由"
    ),
) -> PaperTransferResults:
    """
    返回最近一次 Pipeline 处理后的论文转化分析卡片列表。

    **排序规则：** A 档优先，同档内按商业化梯队（第一梯队最优先）升序排列。

    **卡片字段说明（A/B 档才有 LLM 生成内容）：**
    - `grade` / `grade_reason`: 分级及原因
    - `content_type`: 成果类型（applied / theoretical / mixed）
    - `commercialization_tier`: 商业化梯队（1/2/3）
    - `matched_signals`: 命中的关键词信号列表
    - `tech_summary`: 非学术语言的一句话技术描述
    - `transformation_directions`: 1-3 个产业转化建议方向
    - `maturity_level`: 转化成熟度（接近可用 / 需要工程化 / 还在早期）
    - `negotiation_angle`: 建议的接触切入角度
    - `recommendation_reason`: 综合推荐理由
    """
    results = svc.get_results(grade=grade, school=school, keyword=keyword)
    if results is None:
        raise HTTPException(
            status_code=404,
            detail="No results available. Trigger a run first via POST /paper-transfer/run.",
        )
    return results
