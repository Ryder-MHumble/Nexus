import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import get_scalar_api_reference

from app.api.v1.router import v1_router
from app.config import BASE_DIR, settings
from app.db.client import close_client, init_client
from app.scheduler.manager import SchedulerManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenAPI tag metadata — controls grouping & descriptions in Scalar / Apifox
# ---------------------------------------------------------------------------
TAG_METADATA = [
    {
        "name": "articles",
        "description": "文章管理 — 查询、搜索、统计和更新爬取到的文章。支持按维度、信源、关键词、"
        "日期范围过滤，以及分页排序。",
    },
    {
        "name": "sources",
        "description": "信源管理 — 查看信源配置与状态，启用/禁用信源，手动触发爬取，查看爬取日志。"
        "系统共 134 个信源（109 个启用），覆盖 9 个维度。",
    },
    {
        "name": "crawler-control",
        "description": "爬虫控制 — 前端 UI 专用接口，支持批量启动爬取、实时状态监控、"
        "自定义领域过滤、多格式导出（JSON/CSV/数据库）。",
    },
    {
        "name": "dimensions",
        "description": "维度视图 — 按 9 大维度（国家政策、北京政策、技术动态、人才政策、"
        "产业动态、高校动态、活动会议、人事变动、Twitter）浏览文章汇总。",
    },
    {
        "name": "health",
        "description": "系统健康 — 调度器状态、全局爬取健康度概览。",
    },
    {
        "name": "policy-intel",
        "description": "政策智能 — 基于规则引擎 + LLM 二级管线处理的政策情报。"
        "提供政策动态 Feed、政策机会看板（含资金/截止日/匹配度评分）和汇总统计。",
    },
    {
        "name": "personnel-intel",
        "description": "人事情报 — 自动提取任免信息，LLM 富化分析。"
        "提供人事动态 Feed、结构化任免变动、LLM 富化 Feed（含相关性评分/行动建议）和统计。",
    },
    {
        "name": "daily-briefing",
        "description": "AI 早报 — LLM 生成的每日简报，包含叙事段落（带交互链接）和聚合指标卡片。"
        "数据来自全部 9 个维度的爬取结果和已处理的政策/人事情报。",
    },
    {
        "name": "university-eco",
        "description": "高校生态 — 45 所高校及 AI 研究机构新闻动态监测。"
        "提供总览仪表盘、分页文章 Feed（支持分组/信源/关键词/日期过滤）、"
        "文章详情和信源状态。",
    },
    {
        "name": "sentiment",
        "description": "舆情监测 — 国内社媒平台（小红书、抖音等）内容与评论监测。"
        "数据存储于 Supabase，提供内容信息流、互动统计、评论分析等功能。",
    },
    {
        "name": "venues",
        "description": "学术社群 — AI 领域顶会与期刊知识库。"
        "维护顶会（AAAI/NeurIPS/CVPR 等）和期刊（Nature/TPAMI/JMLR 等）的级别、"
        "H5 指数、录用率、影响因子等元数据，支持按类型/级别/领域过滤。",
    },
]


async def _validate_startup() -> dict[str, str]:
    """Validate critical dependencies at startup. Returns issues dict."""
    issues: dict[str, str] = {}

    # 1. Data directories (create if missing)
    for subdir in [
        "data/raw",
        "data/processed/policy_intel",
        "data/processed/personnel_intel",
        "data/processed/tech_frontier",
        "data/processed/university_eco",
        "data/processed/daily_briefing",
        "data/state",
        "data/logs",
    ]:
        (BASE_DIR / subdir).mkdir(parents=True, exist_ok=True)
    logger.info("Startup check: data directories OK")

    # 2. Playwright browser (non-blocking)
    try:
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        await browser.close()
        await pw.stop()
        logger.info("Startup check: Playwright browser OK")
    except Exception as e:
        issues["playwright"] = str(e)
        logger.warning(
            "Startup check: Playwright unavailable: %s (dynamic crawls will fail)", e
        )

    return issues


async def _check_needs_initial_data() -> bool:
    """Check if processed intel data is missing and pipeline should run.

    Returns True if ANY of these processed output files are missing,
    meaning the pipeline processing stages have never completed successfully.
    This handles the case where raw data exists (from individual crawl jobs)
    but processed data was never generated.
    """
    required_files = [
        "data/processed/policy_intel/feed.json",
        "data/processed/personnel_intel/feed.json",
        "data/processed/tech_frontier/topics.json",
        "data/processed/university_eco/feed.json",
    ]
    for rel_path in required_files:
        if not (BASE_DIR / rel_path).exists():
            logger.info("Missing processed file: %s — pipeline needed", rel_path)
            return True
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of scheduler and other resources."""
    logger.info("=" * 60)
    logger.info("  Information Crawler starting")
    logger.info("=" * 60)

    # Step 0: Initialize Supabase client (optional — skipped if not configured)
    try:
        if settings.SUPABASE_URL and settings.SUPABASE_KEY:
            await init_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            logger.info("Supabase client initialized")
    except Exception as e:
        logger.warning("Supabase client initialization failed: %s", e)

    # Step 1: Validate dependencies
    startup_issues = await _validate_startup()

    # Step 2: Start scheduler
    scheduler = SchedulerManager()
    try:
        await scheduler.start()
    except Exception as e:
        logger.error("Scheduler failed to start: %s", e)
        scheduler = None

    # Step 3: Initial data population (if fresh install)
    if scheduler and settings.STARTUP_CRAWL_ENABLED:
        try:
            needs_initial = await _check_needs_initial_data()
            if needs_initial:
                logger.info(
                    "Processed data missing — triggering initial pipeline"
                )
                await scheduler.trigger_pipeline()
        except Exception as e:
            logger.warning("Initial data check failed: %s", e)

    # Step 4: Build scholar institutions data (only if missing)
    try:
        from pathlib import Path
        institutions_file = Path("data/scholars/institutions.json")
        if not institutions_file.exists():
            from app.services.institution_builder import save_institutions_data
            save_institutions_data()
            logger.info("Scholar institutions data built (first time)")
        else:
            logger.info("Scholar institutions data already exists, skipping rebuild")
    except Exception as e:
        logger.warning("Failed to build scholar institutions data: %s", e)

    # Step 5: Summary
    if startup_issues:
        logger.warning("Startup completed with issues: %s", list(startup_issues))
    else:
        logger.info("Application startup complete — all checks passed")

    yield

    # Shutdown
    await close_client()

    if scheduler:
        try:
            await scheduler.stop()
        except Exception as e:
            logger.error("Scheduler failed to stop cleanly: %s", e)

    try:
        from app.crawlers.utils.playwright_pool import close_browser

        await close_browser()
    except Exception as e:
        logger.warning("Failed to close Playwright: %s", e)

    logger.info("Application shutdown complete")


app = FastAPI(
    title="Nexus — Data Intelligence API",
    summary="Production-grade data pipeline for AI-ready structured knowledge",
    description=(
        "## Overview\n\n"
        "Nexus API — automatically crawls **181 data sources** (138 active) across **9 dimensions**, "
        "transforming unstructured web content into structured, AI-ready knowledge.\n\n"
        "## Modules\n\n"
        "| Module | Description |\n"
        "|--------|-------------|\n"
        "| **Articles** | Full-text article search, filter, and statistics |\n"
        "| **Sources** | Source configuration, status monitoring, manual trigger |\n"
        "| **Dimensions** | Aggregate article views across 9 domains |\n"
        "| **Policy Intel** | Rule engine + LLM pipeline for policy opportunity mining |\n"
        "| **Personnel** | Auto-extraction of appointments/changes with LLM analysis |\n"
        "| **Scholars** | Academic knowledge graph (profiles, institutions, projects) |\n"
        "| **Health** | Scheduler, crawler, and database health monitoring |\n\n"
        "## Dimensions\n\n"
        "- `national_policy` — National policy (configure for your target country)\n"
        "- `beijing_policy` — Regional policy (configure for your target region)\n"
        "- `technology` — Tech trends (arXiv, GitHub Trending, Hacker News, etc.)\n"
        "- `talent` — Talent & recruitment policies\n"
        "- `industry` — Industry reports & company news\n"
        "- `universities` — Academic institution news\n"
        "- `events` — Conferences & seminars\n"
        "- `personnel` — Leadership changes & appointments\n"
        "- `twitter` — Twitter/X KOL monitoring\n\n"
        "## Tech Stack\n\n"
        "FastAPI + Supabase PostgreSQL + APScheduler + httpx + BeautifulSoup4 + Playwright"
    ),
    version="0.2.0",
    openapi_tags=TAG_METADATA,
    contact={
        "name": "Nexus",
        "url": "https://github.com/yourusername/nexus",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
    # Keep default /docs (Swagger UI) and add Scalar at /scalar
    docs_url="/swagger",
    redoc_url=None,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Register API routes
app.include_router(v1_router)

# Mount static files for frontend UI
from pathlib import Path
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(frontend_dir), html=True), name="ui")
    logger.info("Frontend UI mounted at /ui")


@app.get("/", tags=["default"], summary="API 入口", include_in_schema=False)
async def root():
    return {
        "message": "Information Crawler API",
        "version": "0.2.0",
        "docs": "/docs",
        "swagger": "/swagger",
        "openapi": "/openapi.json",
        "ui": "/ui",
    }


# ---------------------------------------------------------------------------
# Scalar API Reference — modern, beautiful API documentation UI
# ---------------------------------------------------------------------------
@app.get("/docs", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )
