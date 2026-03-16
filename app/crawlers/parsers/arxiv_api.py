"""ArXiv API crawler — fetches recent AI papers via the ArXiv Atom API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.crawlers.utils.http_client import fetch_page

logger = logging.getLogger(__name__)

_ARXIV_API_URL = "http://export.arxiv.org/api/query"


class ArxivAPICrawler(BaseCrawler):
    """
    Fetch recent papers from ArXiv using the Atom API.

    Config fields:
      - search_query: ArXiv search query (default "cat:cs.AI")
      - max_results: number of papers (default 20)
      - sort_by: "submittedDate" or "relevance" (default "submittedDate")
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        search_query = self.config.get("search_query", "cat:cs.AI")
        max_results = self.config.get("max_results", 20)
        sort_by = self.config.get("sort_by", "submittedDate")

        query_url = (
            f"{_ARXIV_API_URL}?search_query={search_query}"
            f"&sortBy={sort_by}&sortOrder=descending"
            f"&max_results={max_results}"
        )

        raw = await fetch_page(query_url, timeout=30.0, max_retries=2)
        feed = feedparser.parse(raw)

        if feed.bozo and not feed.entries:
            logger.warning("ArXiv feed parse error: %s", feed.bozo_exception)

        items: list[CrawledItem] = []
        for entry in feed.entries[:max_results]:
            title = entry.get("title", "").strip().replace("\n", " ")
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            # Parse authors
            authors = [a.get("name", "") for a in entry.get("authors", [])]
            author_str = ", ".join(authors[:5])
            if len(authors) > 5:
                author_str += f" et al. ({len(authors)} authors)"

            # Parse abstract
            abstract = entry.get("summary", "").strip().replace("\n", " ")
            content_hash = compute_content_hash(abstract) if abstract else None

            # Parse date
            published_at = None
            if pub := entry.get("published_parsed"):
                try:
                    published_at = datetime(*pub[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            # Extract categories
            categories = [t.get("term", "") for t in entry.get("tags", [])]

            # Construct PDF URL from abstract page URL
            # https://arxiv.org/abs/2501.00001 -> https://arxiv.org/pdf/2501.00001.pdf
            pdf_url = None
            if "/abs/" in link:
                arxiv_id = link.split("/abs/")[-1]
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            items.append(
                CrawledItem(
                    title=title,
                    url=link,
                    published_at=published_at,
                    author=author_str or None,
                    content=abstract or None,
                    content_hash=content_hash,
                    source_id=self.source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []) + categories[:3],
                    extra={
                        "categories": categories,
                        "pdf_url": pdf_url,
                    },
                )
            )

        return items
