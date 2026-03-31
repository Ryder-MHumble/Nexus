"""Twitter Search crawler — monitors tweets by search query.

Config fields (in YAML):
  - twitter_query: search query string (supports Twitter advanced search syntax)
  - twitter_query_type: "Latest" or "Top" (default "Latest")
  - max_tweets: max tweets to return (default 20)
  - min_likes: minimum like count (default 0)

Example YAML:
  - id: twitter_ai_sentiment
    dimension: sentiment
    group: social_media
    crawler_class: twitter_search
    twitter_query: '("open source AI" OR "LLM platform") (launch OR release OR open source)'
    twitter_query_type: Latest
    max_tweets: 20
"""
from __future__ import annotations

import logging
from typing import Any

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.services.external.twitter_service import twitter_client

logger = logging.getLogger(__name__)


class TwitterSearchCrawler(BaseCrawler):
    """Crawl tweets matching a search query via Twitter advanced search."""

    async def fetch_and_parse(self) -> list[CrawledItem]:
        if not twitter_client.is_configured:
            raise RuntimeError("TWITTER_API_KEY not configured in .env")

        query = self.config.get("twitter_query", "")
        query_type = self.config.get("twitter_query_type", "Latest")
        max_tweets = self.config.get("max_tweets", 20)
        min_likes = self.config.get("min_likes", 0)

        if not query:
            logger.warning("No twitter_query configured for %s", self.source_id)
            return []

        try:
            tweets, _ = await twitter_client.search_tweets(
                query=query, query_type=query_type,
            )
        except Exception as e:
            logger.error("Twitter search failed for %s: %s", self.source_id, e)
            raise

        items: list[CrawledItem] = []
        for tweet in tweets[:max_tweets]:
            if tweet.like_count < min_likes:
                continue

            text = tweet.text.strip()
            title = text[:120] + ("..." if len(text) > 120 else "")

            extra: dict[str, Any] = {
                "tweet_id": tweet.id,
                "like_count": tweet.like_count,
                "retweet_count": tweet.retweet_count,
                "reply_count": tweet.reply_count,
                "view_count": tweet.view_count,
                "bookmark_count": tweet.bookmark_count,
                "author_username": tweet.author_username,
                "author_followers": tweet.author_followers,
                "lang": tweet.lang,
                "search_query": query,
            }

            tags = list(self.config.get("tags", []))
            tags.append(f"@{tweet.author_username}")

            items.append(CrawledItem(
                title=title,
                url=tweet.url,
                published_at=tweet.created_at,
                author=f"{tweet.author_name} (@{tweet.author_username})",
                content=text,
                content_hash=compute_content_hash(text) if text else None,
                source_id=self.source_id,
                dimension=self.config.get("dimension"),
                tags=tags,
                extra=extra,
            ))

        logger.info(
            "TwitterSearch: found %d tweets for query '%s' (%s)",
            len(items), query, self.source_id,
        )
        return items
