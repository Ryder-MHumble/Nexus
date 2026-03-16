"""Semantic Scholar API crawler — fetches AI research papers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.crawlers.utils.http_client import fetch_json

logger = logging.getLogger(__name__)

_S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


class SemanticScholarCrawler(BaseCrawler):
    """
    Fetch AI research papers from Semantic Scholar API.

    Config fields:
      - search_query: search keywords (default "artificial intelligence")
      - max_results: number of papers (default 20)
      - fields: comma-separated fields (default covers title, abstract, authors, etc.)
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        query = self.config.get("search_query", "artificial intelligence")
        max_results = self.config.get("max_results", 20)
        fields = self.config.get(
            "fields",
            "title,abstract,authors,year,url,citationCount,publicationDate",
        )

        data: dict[str, Any] = await fetch_json(
            _S2_SEARCH_URL,
            params={
                "query": query,
                "limit": str(max_results),
                "fields": fields,
            },
            timeout=30.0,
        )

        items: list[CrawledItem] = []
        for paper in data.get("data", []):
            title = paper.get("title", "").strip()
            paper_url = paper.get("url", "")
            if not title or not paper_url:
                continue

            # Parse authors
            authors = paper.get("authors", [])
            author_names = [a.get("name", "") for a in authors[:5]]
            author_str = ", ".join(author_names)
            if len(authors) > 5:
                author_str += f" et al. ({len(authors)} authors)"

            # Abstract
            abstract = paper.get("abstract", "") or ""
            content_hash = compute_content_hash(abstract) if abstract else None

            # Date
            published_at = None
            if pub_date := paper.get("publicationDate"):
                try:
                    published_at = datetime.strptime(pub_date, "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    pass
            elif year := paper.get("year"):
                try:
                    published_at = datetime(int(year), 1, 1, tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

            items.append(
                CrawledItem(
                    title=title,
                    url=paper_url,
                    published_at=published_at,
                    author=author_str or None,
                    content=abstract or None,
                    content_hash=content_hash,
                    source_id=self.source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []),
                    extra={
                        "citation_count": paper.get("citationCount", 0),
                        "paper_id": paper.get("paperId"),
                    },
                )
            )

        return items
