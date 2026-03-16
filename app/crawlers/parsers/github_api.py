"""GitHub API crawler — fetches trending AI repositories."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.crawlers.utils.http_client import fetch_json

logger = logging.getLogger(__name__)

_GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


class GitHubAPICrawler(BaseCrawler):
    """
    Fetch trending AI repositories from GitHub Search API.

    Config fields:
      - max_results: number of repos to return (default 20)
      - search_query: custom search query (default "AI language:python")
      - sort: sort field (default "stars")
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        max_results = self.config.get("max_results", 20)
        query = self.config.get("search_query", "AI language:python")
        sort = self.config.get("sort", "stars")

        data: dict[str, Any] = await fetch_json(
            _GITHUB_SEARCH_URL,
            params={
                "q": query,
                "sort": sort,
                "order": "desc",
                "per_page": str(max_results),
            },
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=30.0,
        )

        items: list[CrawledItem] = []
        for repo in data.get("items", [])[:max_results]:
            title = repo.get("full_name", "")
            url = repo.get("html_url", "")
            if not title or not url:
                continue

            description = repo.get("description", "") or ""
            content_hash = compute_content_hash(description) if description else None

            published_at = None
            if pushed := repo.get("pushed_at"):
                try:
                    published_at = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
                except ValueError:
                    pass

            topics = repo.get("topics", [])

            items.append(
                CrawledItem(
                    title=title,
                    url=url,
                    published_at=published_at,
                    author=repo.get("owner", {}).get("login"),
                    content=description or None,
                    content_hash=content_hash,
                    source_id=self.source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []) + topics[:5],
                    extra={
                        "stars": repo.get("stargazers_count", 0),
                        "forks": repo.get("forks_count", 0),
                        "language": repo.get("language"),
                    },
                )
            )

        return items
