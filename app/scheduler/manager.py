from __future__ import annotations

import logging
import random
from typing import Any

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level reference for access from API routes
_scheduler_manager: SchedulerManager | None = None


def get_scheduler_manager() -> SchedulerManager | None:
    return _scheduler_manager


def _make_trigger(config: dict[str, Any]) -> IntervalTrigger | CronTrigger | None:
    cron_cfg = config.get("cron")
    if isinstance(cron_cfg, dict) and cron_cfg:
        # 允许在 YAML 中直接配置 cron 细节（如北京时间 4 点）
        return CronTrigger(**cron_cfg)

    schedule_key = str(config.get("schedule", "daily")).strip().lower()
    mapping = {
        "2h": lambda: IntervalTrigger(hours=2),
        "4h": lambda: IntervalTrigger(hours=4),
        "daily": lambda: CronTrigger(hour=6, minute=0),
        "daily_bj_4": lambda: CronTrigger(hour=4, minute=0, timezone="Asia/Shanghai"),
        "weekly": lambda: CronTrigger(day_of_week="mon", hour=3),
        "monthly": lambda: CronTrigger(day=1, hour=2),
    }
    factory = mapping.get(schedule_key)
    return factory() if factory else None


def is_schedulable_source(config: dict[str, Any]) -> bool:
    """Whether this source should participate in timed crawl scheduling/catalog."""
    dimension = str(config.get("dimension") or "").strip().lower()
    crawl_method = str(config.get("crawl_method") or "").strip().lower()

    # scholars/faculty 数据源不走定时爬虫调度与信源状态目录
    if dimension == "scholars":
        return False
    if crawl_method == "faculty":
        return False
    return True


def load_all_source_configs() -> list[dict[str, Any]]:
    """Load all YAML source config files and return a flat list."""
    all_sources: list[dict[str, Any]] = []
    sources_dir = settings.SOURCES_DIR
    if not sources_dir.exists():
        logger.warning("Sources directory not found: %s", sources_dir)
        return all_sources

    for yaml_file in sorted(sources_dir.glob("*.yaml")):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        if data is None:
            continue

        dimension = data.get("dimension", yaml_file.stem)
        dimension_name = data.get("dimension_name")
        dimension_description = data.get("description")
        default_keywords = data.get("default_keyword_filter", [])
        default_blacklist = data.get("default_keyword_blacklist", [])

        for source in data.get("sources", []):
            source.setdefault("dimension", dimension)
            source.setdefault("dimension_name", dimension_name)
            source.setdefault("dimension_description", dimension_description)
            source.setdefault("source_file", yaml_file.name)
            if "keyword_filter" not in source:
                source["keyword_filter"] = default_keywords
            if "keyword_blacklist" not in source:
                source["keyword_blacklist"] = default_blacklist
            all_sources.append(source)

    logger.info("Loaded %d source configs from %s", len(all_sources), sources_dir)
    return all_sources


class SchedulerManager:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(
            job_defaults={"coalesce": True, "max_instances": 1}
        )
        self._source_configs: list[dict[str, Any]] = []

    async def start(self) -> None:
        global _scheduler_manager
        _scheduler_manager = self

        self._source_configs = [
            cfg for cfg in load_all_source_configs() if is_schedulable_source(cfg)
        ]

        # Import job function here to avoid circular imports
        from app.scheduler.jobs import execute_crawl_job

        for config in self._source_configs:
            if not config.get("is_enabled", True):
                continue

            schedule_key = config.get("schedule", "daily")
            trigger = _make_trigger(config)
            if trigger is None:
                logger.warning(
                    "Unknown schedule '%s' (cron=%s) for source '%s'",
                    schedule_key,
                    config.get("cron"),
                    config["id"],
                )
                continue

            # Add jitter to prevent thundering herd
            jitter = random.randint(0, 300)

            job_id = f"crawl_{config['id']}"
            self.scheduler.add_job(
                execute_crawl_job,
                trigger=trigger,
                id=job_id,
                kwargs={"source_config": config},
                replace_existing=True,
                jitter=jitter,
            )
            logger.debug("Registered crawl job: %s (schedule=%s)", job_id, schedule_key)

        # Register daily pipeline job (5 stages)
        from app.scheduler.jobs import execute_university_leadership_monthly_job
        from app.scheduler.pipeline import execute_daily_pipeline

        self.scheduler.add_job(
            execute_university_leadership_monthly_job,
            trigger=CronTrigger(day=1, hour=2, minute=30),
            id="monthly_university_leadership_full",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        self.scheduler.add_job(
            execute_daily_pipeline,
            trigger=CronTrigger(
                hour=settings.PIPELINE_CRON_HOUR,
                minute=settings.PIPELINE_CRON_MINUTE,
            ),
            id="daily_pipeline",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        self.scheduler.start()
        enabled_count = len(
            [c for c in self._source_configs if c.get("is_enabled", True)]
        )
        logger.info(
            "Scheduler started with %d source jobs + monthly leadership full crawl + "
            "daily pipeline (%02d:%02d UTC)",
            enabled_count,
            settings.PIPELINE_CRON_HOUR,
            settings.PIPELINE_CRON_MINUTE,
        )

    async def stop(self) -> None:
        global _scheduler_manager
        self.scheduler.shutdown(wait=False)
        _scheduler_manager = None
        logger.info("Scheduler stopped")

    async def trigger_pipeline(self) -> None:
        """Manually trigger the full daily pipeline."""
        from app.scheduler.pipeline import execute_daily_pipeline

        self.scheduler.add_job(
            execute_daily_pipeline,
            id="manual_pipeline",
            replace_existing=True,
        )
        logger.info("Manually triggered daily pipeline")

    async def trigger_source(self, source_id: str) -> None:
        """Manually trigger a crawl for one source."""
        config = next((c for c in self._source_configs if c["id"] == source_id), None)
        if config is None:
            raise ValueError(f"Source not found: {source_id}")

        from app.scheduler.jobs import execute_crawl_job

        self.scheduler.add_job(execute_crawl_job, kwargs={"source_config": config})
        logger.info("Manually triggered crawl for source: %s", source_id)

    @property
    def source_configs(self) -> list[dict[str, Any]]:
        return self._source_configs
