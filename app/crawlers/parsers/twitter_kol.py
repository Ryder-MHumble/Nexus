"""Twitter KOL crawler — fetches recent tweets from AI thought leaders.

Config fields (in YAML):
  - twitter_accounts: list of Twitter usernames to monitor
  - max_tweets_per_account: max tweets per account (default 20)
  - min_likes: minimum like count to include a tweet (default 0)
  - fetch_profiles: whether to also fetch user profiles (default true)

Example YAML:
  - id: twitter_ai_kol
    dimension: technology
    group: kol
    crawler_class: twitter_kol
    twitter_accounts:
      - ylecun
      - kaboraAI
      - jimfan_
    max_tweets_per_account: 20
    min_likes: 10
"""
from __future__ import annotations

import logging
from typing import Any

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.services.external.twitter_service import twitter_client

logger = logging.getLogger(__name__)


class TwitterKOLCrawler(BaseCrawler):
    """Crawl tweets from a curated list of AI KOL Twitter accounts."""

    async def fetch_and_parse(self) -> list[CrawledItem]:
        if not twitter_client.is_configured:
            raise RuntimeError("TWITTER_API_KEY not configured in .env")

        accounts: list[str] = self.config.get("twitter_accounts", [])
        max_per = self.config.get("max_tweets_per_account", 20)
        min_likes = self.config.get("min_likes", 0)
        fetch_profiles = self.config.get("fetch_profiles", True)

        if not accounts:
            logger.warning("No twitter_accounts configured for %s", self.source_id)
            return []

        all_items: list[CrawledItem] = []

        for username in accounts:
            try:
                tweets, _ = await twitter_client.get_user_tweets(username)
            except Exception as e:
                logger.warning("Failed to fetch tweets for @%s: %s", username, e)
                continue

            # Optionally fetch profile for richer metadata
            profile = None
            if fetch_profiles:
                try:
                    profile = await twitter_client.get_user_info(username)
                except Exception:
                    pass

            for tweet in tweets[:max_per]:
                if tweet.is_reply or tweet.is_retweet:
                    continue
                if tweet.like_count < min_likes:
                    continue

                # Build a meaningful title from tweet text
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
                }

                if profile:
                    extra["author_bio"] = profile.description
                    extra["author_location"] = profile.location

                if tweet.quoted_tweet_text:
                    extra["quoted_text"] = tweet.quoted_tweet_text[:500]

                tags = list(self.config.get("tags", []))
                tags.append(f"@{tweet.author_username}")
                if tweet.lang:
                    tags.append(f"lang:{tweet.lang}")

                content_hash = compute_content_hash(text) if text else None

                all_items.append(CrawledItem(
                    title=title,
                    url=tweet.url,
                    published_at=tweet.created_at,
                    author=f"{tweet.author_name} (@{tweet.author_username})",
                    content=text,
                    content_hash=content_hash,
                    source_id=self.source_id,
                    dimension=self.config.get("dimension"),
                    tags=tags,
                    extra=extra,
                ))

        # Sort by engagement (like_count) desc
        all_items.sort(
            key=lambda x: x.extra.get("like_count", 0), reverse=True,
        )

        logger.info(
            "TwitterKOL: fetched %d tweets from %d accounts for %s",
            len(all_items), len(accounts), self.source_id,
        )
        return all_items
