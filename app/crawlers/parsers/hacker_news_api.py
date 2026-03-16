"""Hacker News Firebase API crawler — fetches top stories and filters by AI keywords."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.crawlers.utils.http_client import fetch_json

logger = logging.getLogger(__name__)

_DEFAULT_AI_KEYWORDS = [
    "AI", "artificial intelligence", "machine learning", "deep learning",
    "LLM", "GPT", "neural network", "transformer", "diffusion",
    "人工智能", "大模型", "机器学习",
]

_HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
_HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"


class HackerNewsAPICrawler(BaseCrawler):
    """
    Fetch top stories from Hacker News via the public Firebase API.

    Config fields:
      - max_results: number of top stories to check (default 30)
      - keyword_filter: list of keywords to filter (default AI-related)
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        max_results = self.config.get("max_results", 30)
        keywords = self.config.get("keyword_filter", _DEFAULT_AI_KEYWORDS)

        # Get top story IDs
        story_ids: list[int] = await fetch_json(_HN_TOP_URL)
        story_ids = story_ids[:max_results]

        # Fetch story details concurrently (batched)
        items: list[CrawledItem] = []
        batch_size = 10
        for i in range(0, len(story_ids), batch_size):
            batch = story_ids[i : i + batch_size]
            tasks = [self._fetch_story(sid) for sid in batch]
            stories = await asyncio.gather(*tasks, return_exceptions=True)

            for story in stories:
                if isinstance(story, Exception):
                    logger.warning("Failed to fetch HN story: %s", story)
                    continue
                if story is None:
                    continue

                # Keyword filter on title
                title = story.get("title", "")
                if keywords and not any(
                    kw.lower() in title.lower() for kw in keywords
                ):
                    continue

                url = story.get("url") or f"https://news.ycombinator.com/item?id={story['id']}"
                published_at = None
                if ts := story.get("time"):
                    published_at = datetime.fromtimestamp(ts, tz=timezone.utc)

                text = story.get("text", "")
                content_hash = compute_content_hash(text) if text else None

                items.append(
                    CrawledItem(
                        title=title,
                        url=url,
                        published_at=published_at,
                        author=story.get("by"),
                        content=text or None,
                        content_hash=content_hash,
                        source_id=self.source_id,
                        dimension=self.config.get("dimension"),
                        tags=self.config.get("tags", []),
                        extra={
                            "score": story.get("score", 0),
                            "comments": story.get("descendants", 0),
                        },
                    )
                )

        return items

    async def _fetch_story(self, story_id: int) -> dict[str, Any] | None:
        url = _HN_ITEM_URL.format(id=story_id)
        data = await fetch_json(url, max_retries=2, timeout=10.0, request_delay=0.1)
        if data and data.get("type") == "story" and not data.get("deleted"):
            return data
        return None
