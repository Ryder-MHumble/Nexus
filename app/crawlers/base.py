from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CrawlStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    NO_NEW_CONTENT = "no_new_content"


@dataclass
class CrawledItem:
    """A single article/item extracted by a crawler."""

    title: str
    url: str
    published_at: datetime | None = None
    author: str | None = None
    content: str | None = None
    content_html: str | None = None
    content_hash: str | None = None
    source_id: str | None = None
    dimension: str | None = None
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CrawlResult:
    """Result of a single crawl execution for one source."""

    source_id: str
    status: CrawlStatus = CrawlStatus.SUCCESS
    items: list[CrawledItem] = field(default_factory=list)
    items_all: list[CrawledItem] = field(default_factory=list)
    items_new: int = 0
    items_total: int = 0
    error_message: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    duration_seconds: float = 0.0


class BaseCrawler(ABC):
    """Abstract base for all crawlers."""

    def __init__(
        self,
        source_config: dict[str, Any],
        domain_keywords: Optional[list[str]] = None,
    ) -> None:
        self.config = source_config
        self.source_id: str = source_config["id"]
        self.domain_keywords = domain_keywords  # 命令行传入的领域关键词

    def _get_filter_keywords(self) -> list[str]:
        """
        获取最终使用的过滤关键词

        优先级：
        1. 命令行传入的 domain_keywords（最高优先级）
        2. YAML 配置的 keyword_filter
        3. 空列表（不过滤）
        """
        # 优先使用命令行传入的领域关键词
        if self.domain_keywords is not None:
            return self.domain_keywords

        # 其次使用 YAML 配置的 keyword_filter
        return self.config.get("keyword_filter", [])

    def _filter_by_keywords(self, items: list[CrawledItem]) -> list[CrawledItem]:
        """
        根据关键词过滤条目

        Args:
            items: 待过滤的条目列表

        Returns:
            过滤后的条目列表
        """
        keywords = self._get_filter_keywords()

        # 空关键词列表表示不过滤
        if not keywords:
            return items

        filtered_items = []
        for item in items:
            # 检查标题和正文
            text = (item.title or "") + " " + (item.content or "")
            if any(kw.lower() in text.lower() for kw in keywords):
                filtered_items.append(item)

        logger.info(
            f"Filtered {len(items)} items to {len(filtered_items)} items using keywords: {keywords[:5]}..."
        )
        return filtered_items

    async def run(self) -> CrawlResult:
        """Orchestrate: timing, error handling, logging."""
        result = CrawlResult(source_id=self.source_id)
        result.started_at = datetime.now(timezone.utc)
        try:
            items = await self.fetch_and_parse()

            # 应用领域过滤
            filtered_items = self._filter_by_keywords(items)

            result.items_total = len(items)
            result.items_all = items
            result.items = filtered_items
            result.items_new = len(filtered_items)

            if filtered_items:
                result.status = CrawlStatus.SUCCESS
            else:
                result.status = CrawlStatus.NO_NEW_CONTENT
        except Exception as e:
            logger.exception("Crawl failed for source %s", self.source_id)
            result.status = CrawlStatus.FAILED
            result.error_message = str(e)
        finally:
            result.finished_at = datetime.now(timezone.utc)
            result.duration_seconds = (result.finished_at - result.started_at).total_seconds()
        return result

    @abstractmethod
    async def fetch_and_parse(self) -> list[CrawledItem]:
        """Subclasses implement: fetch the source, parse, return items."""
        ...
