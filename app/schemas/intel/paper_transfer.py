"""Schemas for paper industry transformation analysis pipeline."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PaperMeta(BaseModel):
    paper_id: str
    title: str
    url: str | None = None
    publication_date: str | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    student_name_list: list[str] = Field(
        default_factory=list,
        description="该论文的合作学生姓名列表（系统内已收录的共同作者）",
    )


class StudentContact(BaseModel):
    email: str | None = None
    phone: str | None = None
    wechat: str | None = None


class StudentMeta(BaseModel):
    student_id: str
    name: str
    name_cn: str
    name_en: str
    school: str
    school_cn: str
    contact: StudentContact = Field(default_factory=StudentContact)


class TransformationCard(BaseModel):
    paper: PaperMeta
    student: StudentMeta
    grade: str = Field(description="A=主动跟进 / B=保持关注 / C=暂不处理")
    grade_reason: str
    content_type: str = Field(description="applied / theoretical / mixed")
    commercialization_tier: int = Field(description="1=第一梯队 / 2=第二梯队 / 3=第三梯队")
    matched_signals: list[str]
    # LLM-generated fields (null for C-grade papers)
    tech_summary: str | None = None
    transformation_directions: list[str] | None = None
    maturity_level: str | None = Field(None, description="接近可用 / 需要工程化 / 还在早期")
    negotiation_angle: str | None = None
    recommendation_reason: str | None = None


class PipelineProgress(BaseModel):
    students_fetched: int = 0
    papers_fetched: int = 0
    abstracts_fetched: int = 0
    papers_analyzed: int = 0
    total_batches: int = 0
    current_batch: int = 0


class PipelineRunState(BaseModel):
    status: str = Field(description="idle / running / completed / failed")
    started_at: str | None = None
    completed_at: str | None = None
    progress: PipelineProgress = Field(default_factory=PipelineProgress)
    error: str | None = None
    date_from: str | None = None
    school_filter: str | None = None
    max_papers: int = 5000
    batch_size: int = 200


class PaperTransferResults(BaseModel):
    generated_at: str
    total_students_processed: int
    total_papers_fetched: int
    total_papers_analyzed: int
    grade_counts: dict[str, int] = Field(description='e.g. {"A": 5, "B": 12, "C": 83}')
    batch_count: int = Field(1, description="本次分析拆分的批次数")
    items: list[TransformationCard]


class RunRequest(BaseModel):
    date_from: str | None = Field(None, description="论文发表起始日期 YYYY-MM-DD，默认近 6 个月")
    school: str | None = Field(
        None, description="按学校名称模糊筛选（如 北京大学），为空则处理全部学生"
    )
    max_papers: int = Field(5000, description="最多处理论文数（默认 5000，通常覆盖全量）")
    batch_size: int = Field(200, description="每批处理论文数，各批串行执行（默认 200）")


class RunResponse(BaseModel):
    status: str = Field(description="started / already_running")
    message: str
