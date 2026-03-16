from __future__ import annotations

import importlib
import logging
from typing import Any

from app.crawlers.base import BaseCrawler

logger = logging.getLogger(__name__)

# Template crawler type mapping (loaded lazily to avoid circular imports)
_TEMPLATE_MAP: dict[str, str] = {
    "rss": "app.crawlers.templates.rss_crawler.RSSCrawler",
    "static": "app.crawlers.templates.static_crawler.StaticHTMLCrawler",
    "snapshot": "app.crawlers.templates.snapshot_crawler.SnapshotDiffCrawler",
    "dynamic": "app.crawlers.templates.dynamic_crawler.DynamicPageCrawler",
    "social": "app.crawlers.templates.social_crawler.SocialMediaCrawler",
    "faculty": "app.crawlers.templates.faculty_crawler.ScholarCrawler",
}

# Custom parser mapping
_CUSTOM_MAP: dict[str, str] = {
    "gov_json_api": "app.crawlers.parsers.gov_json_api.GovJSONAPICrawler",
    "arxiv_api": "app.crawlers.parsers.arxiv_api.ArxivAPICrawler",
    "hacker_news_api": "app.crawlers.parsers.hacker_news_api.HackerNewsAPICrawler",
    "github_api": "app.crawlers.parsers.github_api.GitHubAPICrawler",
    "semantic_scholar": "app.crawlers.parsers.semantic_scholar.SemanticScholarCrawler",
    "twitter_kol": "app.crawlers.parsers.twitter_kol.TwitterKOLCrawler",
    "twitter_search": "app.crawlers.parsers.twitter_search.TwitterSearchCrawler",
    "hunyuan_api": "app.crawlers.parsers.hunyuan_api.HunyuanAPICrawler",
    "sjtu_cs_faculty": "app.crawlers.parsers.sjtu_cs_faculty.SJTUCSFacultyCrawler",
    "sjtu_ai_faculty": "app.crawlers.parsers.sjtu_ai_faculty.SJTUAIFacultyCrawler",
    "iscas_faculty": "app.crawlers.parsers.iscas_faculty.ISCASFacultyCrawler",
    "zju_cyber_faculty": "app.crawlers.parsers.zju_cyber_faculty.ZJUCyberFacultyCrawler",
    "ymsc_faculty": "app.crawlers.parsers.ymsc_faculty.YMSCFacultyCrawler",
    "llm_faculty": "app.crawlers.parsers.llm_faculty.LLMFacultyCrawler",
    "tsinghua_cs_faculty": "app.crawlers.parsers.tsinghua_cs_faculty.TsinghuaCsFacultyCrawler",
    "samr_api": "app.crawlers.parsers.samr_api.SamrAPICrawler",
}


def _import_class(dotted_path: str) -> type[BaseCrawler]:
    """Import a class from a dotted module path like 'app.crawlers.templates.rss_crawler.RSSCrawler'."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class CrawlerRegistry:
    """Resolves source configs to instantiated crawler objects."""

    @staticmethod
    def create_crawler(
        source_config: dict[str, Any],
        domain_keywords: list[str] | None = None,
    ) -> BaseCrawler:
        # Custom parser takes priority
        if custom_key := source_config.get("crawler_class"):
            dotted_path = _CUSTOM_MAP.get(custom_key)
            if dotted_path is None:
                raise ValueError(f"Unknown custom crawler_class: {custom_key}")
            cls = _import_class(dotted_path)
            return cls(source_config, domain_keywords=domain_keywords)

        # Fall back to template by crawl_method
        method = source_config.get("crawl_method")
        if method is None:
            raise ValueError(f"Source {source_config.get('id')} has no crawl_method")
        dotted_path = _TEMPLATE_MAP.get(method)
        if dotted_path is None:
            raise ValueError(f"Unknown crawl_method: {method}")
        cls = _import_class(dotted_path)
        return cls(source_config, domain_keywords=domain_keywords)

    @staticmethod
    def list_available_methods() -> list[str]:
        return list(_TEMPLATE_MAP.keys())

    @staticmethod
    def list_custom_parsers() -> list[str]:
        return list(_CUSTOM_MAP.keys())


# 模块级兼容别名，供旧代码 `from app.crawlers.registry import create_crawler` 使用
def create_crawler(
    source_config: dict[str, Any],
    domain_keywords: list[str] | None = None,
) -> "BaseCrawler":
    return CrawlerRegistry.create_crawler(source_config, domain_keywords=domain_keywords)
