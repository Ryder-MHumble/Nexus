"""Service for controlling crawler execution from frontend UI."""
import asyncio
import csv
import dataclasses
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from app.config import BASE_DIR
from app.crawlers.registry import create_crawler
from app.scheduler.manager import load_all_source_configs
from app.crawlers.utils.json_storage import save_crawl_result_json

logger = logging.getLogger(__name__)


class CrawlerControlService:
    """Service for managing manual crawler execution."""

    def __init__(self):
        self._is_running = False
        self._should_stop = False
        self._current_source: str | None = None
        self._completed_sources: list[str] = []
        self._failed_sources: list[str] = []
        self._total_items = 0
        self._result_file: Path | None = None
        self._all_results: list[dict[str, Any]] = []

    def is_running(self) -> bool:
        """Check if a crawl job is currently running."""
        return self._is_running

    def get_status(self) -> dict[str, Any]:
        """Get current crawl job status."""
        total = len(self._completed_sources) + len(self._failed_sources)
        if self._current_source:
            total += 1

        progress = 0.0
        if total > 0:
            progress = len(self._completed_sources) / total

        return {
            "is_running": self._is_running,
            "current_source": self._current_source,
            "completed_sources": self._completed_sources,
            "failed_sources": self._failed_sources,
            "total_items": self._total_items,
            "progress": progress,
        }

    def stop_crawl(self):
        """Request to stop the current crawl job."""
        self._should_stop = True
        logger.info("Crawl stop requested")

    def get_result_file(self) -> Path | None:
        """Get the path to the latest result file.

        Falls back to the most recent file in the exports directory
        if the in-memory reference was lost (e.g. after a server restart).
        """
        if self._result_file is not None and self._result_file.exists():
            return self._result_file

        exports_dir = BASE_DIR / "data" / "exports"
        if not exports_dir.exists():
            return None

        candidates = sorted(
            exports_dir.glob("crawl_results_*.*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None

    async def start_crawl(
        self,
        source_ids: list[str],
        keyword_filter: list[str] | None = None,
        keyword_blacklist: list[str] | None = None,
        export_format: Literal["json", "csv", "database"] = "json",
    ):
        """Start a crawl job with specified sources and filters."""
        self._is_running = True
        self._should_stop = False
        self._current_source = None
        self._completed_sources = []
        self._failed_sources = []
        self._total_items = 0
        self._all_results = []

        logger.info(
            "Starting manual crawl: %d sources, format=%s",
            len(source_ids),
            export_format,
        )

        try:
            # Load all source configs
            all_configs = load_all_source_configs()
            config_map = {cfg["id"]: cfg for cfg in all_configs}

            # Filter to requested sources
            selected_configs = [
                config_map[sid] for sid in source_ids if sid in config_map
            ]

            if not selected_configs:
                logger.warning("No valid source configs found")
                return

            # Execute crawls
            for config in selected_configs:
                if self._should_stop:
                    logger.info("Crawl stopped by user")
                    break

                source_id = config["id"]
                self._current_source = source_id

                try:
                    # Apply custom filters if provided
                    if keyword_filter is not None:
                        config["keyword_filter"] = keyword_filter
                    if keyword_blacklist is not None:
                        config["keyword_blacklist"] = keyword_blacklist

                    # Create and execute crawler
                    crawler = create_crawler(config)
                    items = await crawler.fetch_and_parse()

                    # Convert to dict format (CrawledItem is a dataclass, not Pydantic)
                    items_dict = [dataclasses.asdict(item) for item in items]
                    self._all_results.extend(items_dict)
                    self._total_items += len(items_dict)

                    # Save to database if format is database
                    if export_format == "database":
                        from types import SimpleNamespace
                        await save_crawl_result_json(SimpleNamespace(items=items, items_all=items), config)

                    self._completed_sources.append(source_id)
                    logger.info(
                        "Completed %s: %d items", source_id, len(items_dict)
                    )

                except Exception as e:
                    logger.error("Failed to crawl %s: %s", source_id, e)
                    self._failed_sources.append(source_id)

                finally:
                    self._current_source = None

            # Export results
            if export_format in ("json", "csv") and self._all_results:
                self._result_file = await self._export_results(
                    self._all_results, export_format
                )
                logger.info("Results exported to %s", self._result_file)

        finally:
            self._is_running = False
            logger.info(
                "Crawl finished: %d completed, %d failed, %d total items",
                len(self._completed_sources),
                len(self._failed_sources),
                self._total_items,
            )

    async def _export_results(
        self, results: list[dict[str, Any]], format: Literal["json", "csv"]
    ) -> Path:
        """Export crawl results to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = BASE_DIR / "data" / "exports"
        output_dir.mkdir(parents=True, exist_ok=True)

        def _json_default(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

        if format == "json":
            file_path = output_dir / f"crawl_results_{timestamp}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=_json_default)

        elif format == "csv":
            file_path = output_dir / f"crawl_results_{timestamp}.csv"
            if results:
                # Get all unique keys
                all_keys = set()
                for item in results:
                    all_keys.update(item.keys())
                fieldnames = sorted(all_keys)

                with open(file_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(results)

        return file_path
