from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PaperAffiliationMapping(BaseModel):
    author_order: int
    author_name: str
    affiliation: str


class PaperSourceRef(BaseModel):
    type: str
    name: str
    source_id: str
    raw_id: str | None = None
    detail_url: str | None = None
    pdf_url: str | None = None
    venue: str | None = None
    venue_year: int | None = None
    track: str | None = None


class PaperIngestPayload(BaseModel):
    paper_id: str | None = None
    title: str
    doi: str | None = None
    abstract: str | None = None
    publication_date: str | None = None
    authors: list[str] = Field(default_factory=list)
    affiliations: list[PaperAffiliationMapping] = Field(default_factory=list)
    source: PaperSourceRef
    raw_id: str | None = None
    detail_url: str | None = None
    pdf_url: str | None = None
    venue: str | None = None
    venue_year: int | None = None
    track: str | None = None


class PaperRecord(BaseModel):
    paper_id: str
    canonical_uid: str = ""
    doi: str | None = None
    title: str
    abstract: str | None = None
    publication_date: str | None = None
    authors: list[str] = Field(default_factory=list)
    affiliations: list[PaperAffiliationMapping] = Field(default_factory=list)
    source: PaperSourceRef
    detail_url: str | None = None
    pdf_url: str | None = None
    venue: str | None = None
    venue_year: int | None = None
    track: str | None = None
    ingested_at: str | None = None
    updated_at: str | None = None


class PaperListResponse(BaseModel):
    items: list[PaperRecord]
    total: int
    page: int = 1
    page_size: int = 20


class PaperSourceStatus(BaseModel):
    source_id: str
    name: str
    source_type: str
    crawler_class: str = ""
    is_enabled: bool = False
    paper_count: int = 0
    latest_run: dict[str, Any] | None = None


class PaperSourceListResponse(BaseModel):
    items: list[PaperSourceStatus]
    total: int


class PaperIngestRunRecord(BaseModel):
    run_id: str
    source_id: str = ""
    status: str
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    filtered_chinese_count: int = 0
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class PaperIngestRunListResponse(BaseModel):
    items: list[PaperIngestRunRecord]
    total: int
    page: int = 1
    page_size: int = 20


class PaperCrawlResponse(BaseModel):
    source_id: str
    status: str
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    filtered_chinese_count: int = 0
    run_id: str | None = None
    error_message: str | None = None
