"""Crawler control API for frontend UI."""
import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.schemas.common import ErrorResponse
from app.services.crawler_control_service import CrawlerControlService

logger = logging.getLogger(__name__)
router = APIRouter()

# Global service instance
_control_service: CrawlerControlService | None = None


def get_control_service() -> CrawlerControlService:
    """Get or create the crawler control service singleton."""
    global _control_service
    if _control_service is None:
        _control_service = CrawlerControlService()
    return _control_service


class CrawlRequest(BaseModel):
    """Request to start a crawl job."""
    source_ids: list[str]
    keyword_filter: list[str] | None = None
    keyword_blacklist: list[str] | None = None
    export_format: Literal["json", "csv", "database"] = "json"


class CrawlStatusResponse(BaseModel):
    """Current crawl job status."""
    is_running: bool
    current_source: str | None = None
    completed_sources: list[str] = []
    failed_sources: list[str] = []
    total_items: int = 0
    progress: float = 0.0  # 0.0 to 1.0


@router.post(
    "/start",
    summary="启动爬取任务",
    description="启动一个新的爬取任务，可指定信源、关键词过滤和导出格式。",
    responses={
        400: {"model": ErrorResponse, "description": "已有任务在运行"},
    },
)
async def start_crawl(request: CrawlRequest):
    """Start a new crawl job."""
    service = get_control_service()

    if service.is_running():
        raise HTTPException(status_code=400, detail="A crawl job is already running")

    # Start crawl in background
    asyncio.create_task(
        service.start_crawl(
            source_ids=request.source_ids,
            keyword_filter=request.keyword_filter,
            keyword_blacklist=request.keyword_blacklist,
            export_format=request.export_format,
        )
    )

    return {"status": "started", "source_count": len(request.source_ids)}


@router.post(
    "/stop",
    summary="停止爬取任务",
    description="停止当前正在运行的爬取任务。",
    responses={
        400: {"model": ErrorResponse, "description": "没有任务在运行"},
    },
)
async def stop_crawl():
    """Stop the current crawl job."""
    service = get_control_service()

    if not service.is_running():
        raise HTTPException(status_code=400, detail="No crawl job is running")

    service.stop_crawl()
    return {"status": "stopped"}


@router.get(
    "/status",
    response_model=CrawlStatusResponse,
    summary="获取爬取状态",
    description="获取当前爬取任务的实时状态。",
)
async def get_status():
    """Get current crawl job status."""
    service = get_control_service()
    return service.get_status()


@router.get(
    "/download",
    summary="下载爬取结果",
    description="下载最近一次爬取任务的结果文件。",
    responses={
        404: {"model": ErrorResponse, "description": "没有可下载的文件"},
    },
)
async def download_result():
    """Download the latest crawl result file."""
    service = get_control_service()
    file_path = service.get_result_file()

    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404, detail="No result file available")

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )
