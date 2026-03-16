"""Twitter API service using twitterapi.io for KOL monitoring and search.

Usage:
    from app.services.twitter_service import twitter_client

    # Get user's recent tweets
    tweets = await twitter_client.get_user_tweets("ylecun")

    # Search tweets
    tweets = await twitter_client.search_tweets("AI breakthrough", query_type="Latest")

    # Get user profile
    profile = await twitter_client.get_user_info("ylecun")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.twitterapi.io/twitter"


@dataclass
class Tweet:
    """Normalized tweet data."""
    id: str
    text: str
    url: str
    author_name: str
    author_username: str
    author_followers: int = 0
    author_profile_pic: str = ""
    created_at: datetime | None = None
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    view_count: int = 0
    bookmark_count: int = 0
    lang: str = ""
    is_reply: bool = False
    is_retweet: bool = False
    quoted_tweet_text: str | None = None
    source: str = ""


@dataclass
class TwitterUser:
    """Normalized Twitter user profile."""
    id: str
    name: str
    username: str
    description: str = ""
    location: str = ""
    url: str = ""
    followers: int = 0
    following: int = 0
    tweet_count: int = 0
    profile_pic: str = ""
    is_verified: bool = False
    created_at: str = ""


class TwitterClient:
    """Async client for twitterapi.io API."""

    def __init__(self) -> None:
        self._api_key = settings.TWITTER_API_KEY
        self._proxy = settings.TWITTER_API_PROXY or None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=30.0,
            proxy=self._proxy,
            headers={
                "x-api-key": self._api_key,
                "Accept": "application/json",
            },
        )

    async def get_user_tweets(
        self,
        username: str,
        cursor: str | None = None,
    ) -> tuple[list[Tweet], str | None]:
        """
        Get a user's recent tweets (up to 20 per page).

        Returns (tweets, next_cursor). Pass next_cursor for pagination.
        """
        params: dict[str, str] = {"userName": username}
        if cursor:
            params["cursor"] = cursor

        async with self._get_client() as client:
            resp = await client.get(f"{_BASE_URL}/user/last_tweets", params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            logger.warning("Twitter API error for %s: %s", username, data.get("msg"))
            return [], None

        tweets_data = data.get("data", {})
        raw_tweets = tweets_data.get("tweets", [])
        next_cursor = tweets_data.get("next_cursor")

        tweets = [self._parse_tweet(t) for t in raw_tweets if t.get("type") == "tweet"]
        return tweets, next_cursor

    async def search_tweets(
        self,
        query: str,
        query_type: str = "Latest",
        cursor: str | None = None,
    ) -> tuple[list[Tweet], str | None]:
        """
        Advanced search for tweets.

        query_type: "Latest" | "Top"
        Returns (tweets, next_cursor).
        """
        params: dict[str, str] = {"query": query, "queryType": query_type}
        if cursor:
            params["cursor"] = cursor

        async with self._get_client() as client:
            resp = await client.get(
                f"{_BASE_URL}/tweet/advanced_search", params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        raw_tweets = data.get("tweets", [])
        next_cursor = data.get("next_cursor")

        tweets = [self._parse_tweet(t) for t in raw_tweets if t.get("type") == "tweet"]
        return tweets, next_cursor

    async def get_user_info(self, username: str) -> TwitterUser | None:
        """Get a Twitter user's profile information."""
        async with self._get_client() as client:
            resp = await client.get(
                f"{_BASE_URL}/user/info", params={"userName": username},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            return None

        user_data = data.get("data", {})
        return TwitterUser(
            id=user_data.get("id", ""),
            name=user_data.get("name", ""),
            username=user_data.get("userName", ""),
            description=user_data.get("description", ""),
            location=user_data.get("location", ""),
            url=user_data.get("url", ""),
            followers=user_data.get("followers", 0),
            following=user_data.get("following", 0),
            tweet_count=user_data.get("statusesCount", 0),
            profile_pic=user_data.get("profilePicture", ""),
            is_verified=user_data.get("isBlueVerified", False),
            created_at=user_data.get("createdAt", ""),
        )

    def _parse_tweet(self, raw: dict[str, Any]) -> Tweet:
        """Parse raw API tweet into normalized Tweet dataclass."""
        author = raw.get("author", {})

        created_at = None
        if raw_date := raw.get("createdAt"):
            try:
                created_at = datetime.strptime(
                    raw_date, "%a %b %d %H:%M:%S %z %Y",
                )
            except ValueError:
                pass

        return Tweet(
            id=raw.get("id", ""),
            text=raw.get("text", ""),
            url=raw.get("url", ""),
            author_name=author.get("name", ""),
            author_username=author.get("userName", ""),
            author_followers=author.get("followers", 0),
            author_profile_pic=author.get("profilePicture", ""),
            created_at=created_at,
            like_count=raw.get("likeCount", 0),
            retweet_count=raw.get("retweetCount", 0),
            reply_count=raw.get("replyCount", 0),
            quote_count=raw.get("quoteCount", 0),
            view_count=raw.get("viewCount", 0),
            bookmark_count=raw.get("bookmarkCount", 0),
            lang=raw.get("lang", ""),
            is_reply=raw.get("isReply", False),
            is_retweet=raw.get("type") == "retweet",
            quoted_tweet_text=(raw.get("quoted_tweet") or {}).get("text"),
            source=raw.get("source", ""),
        )


# Singleton client
twitter_client = TwitterClient()
