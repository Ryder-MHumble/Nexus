"""Twitter KOL crawler — fetches recent tweets from configured thought leaders.

Config fields (in YAML):
  - twitter_accounts: list[str | dict], optional inline account config
  - twitter_accounts_file: YAML file path under `sources/` (recommended)
  - max_tweets_per_account: max tweets per account (default 20)
  - min_likes: minimum like count to include a tweet (default 0)
  - fetch_profiles: whether to also fetch user profiles (default true)

Supported account item format:
  - "karpathy"
  - {name: "Andrej Karpathy", username: "karpathy"}
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from app.config import settings
from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash
from app.services.external.twitter_service import twitter_client

logger = logging.getLogger(__name__)


class TwitterKOLCrawler(BaseCrawler):
    """Crawl tweets from a curated list of KOL Twitter accounts."""

    @staticmethod
    def _clean_username(raw: Any) -> str:
        return str(raw or "").strip().lstrip("@")

    @classmethod
    def _parse_account_item(cls, raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, str):
            username = cls._clean_username(raw)
            if not username:
                return None
            return {"username": username, "name": username}

        if not isinstance(raw, dict):
            return None

        username = cls._clean_username(
            raw.get("username")
            or raw.get("user_name")
            or raw.get("userName")
            or raw.get("handle")
            or raw.get("account")
        )
        if not username:
            return None

        name = str(
            raw.get("name")
            or raw.get("display_name")
            or raw.get("displayName")
            or username
        ).strip()
        return {
            "username": username,
            "name": name or username,
            "category": str(raw.get("category") or "").strip() or None,
            "cohort": str(raw.get("cohort") or "").strip() or None,
            "tags": raw.get("tags") if isinstance(raw.get("tags"), list) else [],
        }

    def _load_accounts_from_file(self, raw_path: str) -> list[dict[str, Any]]:
        file_path = Path(raw_path)
        if not file_path.is_absolute():
            file_path = settings.SOURCES_DIR / file_path

        if not file_path.exists():
            logger.warning(
                "twitter_accounts_file not found for %s: %s",
                self.source_id,
                file_path,
            )
            return []

        try:
            with file_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.warning("Failed to load twitter_accounts_file %s: %s", file_path, e)
            return []

        raw_accounts: list[Any]
        if isinstance(data, dict):
            raw_accounts = data.get("accounts", [])
        elif isinstance(data, list):
            raw_accounts = data
        else:
            raw_accounts = []

        parsed: list[dict[str, Any]] = []
        for item in raw_accounts:
            parsed_item = self._parse_account_item(item)
            if parsed_item:
                parsed.append(parsed_item)
        return parsed

    def _resolve_accounts(self) -> list[dict[str, Any]]:
        accounts: list[dict[str, Any]] = []

        accounts_file = str(self.config.get("twitter_accounts_file") or "").strip()
        if accounts_file:
            accounts.extend(self._load_accounts_from_file(accounts_file))

        raw_inline = self.config.get("twitter_accounts", [])
        if isinstance(raw_inline, list):
            for item in raw_inline:
                parsed_item = self._parse_account_item(item)
                if parsed_item:
                    accounts.append(parsed_item)

        dedup: dict[str, dict[str, Any]] = {}
        for item in accounts:
            key = item["username"].lower()
            if key not in dedup:
                dedup[key] = item

        return list(dedup.values())

    async def fetch_and_parse(self) -> list[CrawledItem]:
        if not twitter_client.is_configured:
            raise RuntimeError("TWITTER_API_KEY not configured in .env")

        accounts = self._resolve_accounts()
        max_per = self.config.get("max_tweets_per_account", 20)
        min_likes = self.config.get("min_likes", 0)
        fetch_profiles = self.config.get("fetch_profiles", True)

        if not accounts:
            logger.warning("No twitter accounts configured for %s", self.source_id)
            return []

        all_items: list[CrawledItem] = []

        for account in accounts:
            username = account["username"]
            configured_name = account.get("name")

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
                if configured_name:
                    extra["configured_kol_name"] = configured_name
                if account.get("category"):
                    extra["configured_kol_category"] = account.get("category")
                if account.get("cohort"):
                    extra["configured_kol_cohort"] = account.get("cohort")
                if account.get("tags"):
                    extra["configured_kol_tags"] = account.get("tags")

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
