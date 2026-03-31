import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import get_scalar_api_reference

from app.api.v1.router import v1_router
from app.config import BASE_DIR, settings
from app.db.client import close_client, init_client
from app.db.pool import close_pool, init_pool
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
        "支持目录化筛选（维度/分组/标签/健康状态）与分面统计。",
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
    {
        "name": "leadership",
        "description": "高校领导 — 高校领导列表与机构领导详情查询。",
    },
    {
        "name": "reports",
        "description": "AI 分析报告 — 基于爬取数据生成多维度智能分析报告。"
        "支持舆情监测、政策分析、科技前沿、人事情报、高校生态等维度，"
        "提供数据洞察、风险预警、机会识别和行动建议。",
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
    logger.info("  Nexus starting")
    logger.info("=" * 60)

    # Step 0: Initialize database client
    try:
        backend = settings.DB_BACKEND.strip().lower()
        if backend in {"postgres", "postgresql", "local"}:
            if settings.POSTGRES_DSN:
                await init_pool(dsn=settings.POSTGRES_DSN)
            else:
                await init_pool(
                    host=settings.POSTGRES_HOST,
                    port=settings.POSTGRES_PORT,
                    user=settings.POSTGRES_USER,
                    password=settings.POSTGRES_PASSWORD,
                    database=settings.POSTGRES_DB,
                )
            await init_client(backend="postgres")
            logger.info(
                "PostgreSQL client initialized (%s:%s/%s)",
                settings.POSTGRES_HOST,
                settings.POSTGRES_PORT,
                settings.POSTGRES_DB,
            )
        elif settings.SUPABASE_URL and settings.SUPABASE_KEY:
            await init_client(settings.SUPABASE_URL, settings.SUPABASE_KEY, backend="supabase")
            logger.info("Supabase client initialized")
        else:
            logger.warning("No database backend configured; DB features will fallback to local JSON")
    except Exception as e:
        logger.warning("Database client initialization failed: %s", e)

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
    await close_pool()

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
    title="Nexus Data Intelligence API",
    summary="Structured knowledge infrastructure for AI applications",
    description=(
        "## Overview\n\n"
        "Nexus turns multi-source web content into structured, queryable knowledge for "
        "AI applications. The platform combines configurable crawlers, scheduled "
        "processing pipelines, domain-specific intelligence modules, and management APIs.\n\n"
        "## Modules\n\n"
        "| Module | Description |\n"
        "|--------|-------------|\n"
        "| **Articles** | Search, filter, inspect, and analyze crawled content |\n"
        "| **Sources** | Source catalog, runtime overrides, health status, and facets |\n"
        "| **Crawler Control** | Batch crawl triggers, progress tracking, export workflows |\n"
        "| **Knowledge Graph** | Scholars, institutions, projects, students, events, leadership |\n"
        "| **Intelligence** | Policy, personnel, tech frontier, university, sentiment, reports |\n"
        "| **System Health** | Scheduler, pipeline, and storage diagnostics |\n\n"
        "## Data Dimensions\n\n"
        "- `national_policy` — National policy and regulation tracking\n"
        "- `beijing_policy` — Regional policy monitoring\n"
        "- `technology` — Research and technology frontier signals\n"
        "- `talent` — Talent and recruitment developments\n"
        "- `industry` — Industry trends and company activity\n"
        "- `universities` — University and research institution activity\n"
        "- `events` — Conferences, salons, and seminars\n"
        "- `personnel` — Leadership and appointment changes\n"
        "- `twitter` — Social/KOL monitoring\n"
        "- `scholars` — Scholar and faculty knowledge imports\n"
        "- `sentiment` — Social sentiment intelligence\n\n"
        "## Runtime\n\n"
        "FastAPI + APScheduler + httpx + BeautifulSoup4 + Playwright + "
        "PostgreSQL/Supabase-compatible data access"
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
        "message": "Nexus Data Intelligence API",
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
