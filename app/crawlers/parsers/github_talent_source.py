from __future__ import annotations

from typing import Any

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.parsers._talent_scout_common import (
    build_blocked_item,
    build_crawled_item,
    build_review_item,
    build_talent_signal,
    extract_records,
    fetch_options,
    get_track,
)
from app.crawlers.utils.http_client import fetch_json

_GITHUB_HEADERS = {"Accept": "application/vnd.github+json"}
_GITHUB_REPOSITORY_SEARCH_URL = "https://api.github.com/search/repositories"
_GITHUB_USER_API_ROOT = "https://api.github.com/users"


class GitHubTalentSourceCrawler(BaseCrawler):
    async def fetch_and_parse(self) -> list[CrawledItem]:
        adapter_key = str(self.config.get("adapter_key") or "")
        if adapter_key == "github_users":
            return await self._fetch_users()
        if adapter_key == "github_contributors":
            return await self._fetch_contributors()

        try:
            payload = await fetch_json(self._source_url(), **fetch_options(self.config))
        except Exception as exc:
            if self.config.get("fallback_mode") == "evidence_only":
                return [
                    build_blocked_item(
                        self.config,
                        notes=str(exc),
                        signal_type="github_contributor",
                    )
                ]
            raise

        items = self._records_to_items(extract_records(payload))
        if items:
            return items
        if self.config.get("fallback_mode") == "evidence_only":
            return [
                build_review_item(
                    self.config,
                    notes="no structured github contributor records",
                    signal_type="github_contributor",
                )
            ]
        return []

    async def _fetch_users(self) -> list[CrawledItem]:
        try:
            payload = await fetch_json(
                self._source_url(),
                params={
                    "q": str(self.config.get("search_query") or "machine learning"),
                    "per_page": str(int(self.config.get("max_results", 10))),
                },
                headers=_GITHUB_HEADERS,
                **fetch_options(self.config),
            )
        except Exception as exc:
            return [
                build_blocked_item(
                    self.config,
                    notes=str(exc),
                    signal_type="github_contributor",
                )
            ]

        records = [
            {
                "candidate_name": item.get("login"),
                "github_login": item.get("login"),
                "followers": item.get("followers"),
                "evidence_url": item.get("html_url"),
                "confidence": 0.65,
            }
            for item in payload.get("items", [])
            if isinstance(item, dict)
        ]
        records = await self._maybe_enrich_profiles(records)
        return self._records_or_review(records)

    async def _fetch_contributors(self) -> list[CrawledItem]:
        repo_seeds = self._configured_repo_seeds()
        if not repo_seeds and self._has_repo_discovery_config():
            try:
                repo_seeds = await self._discover_repo_seeds()
            except Exception as exc:
                return [
                    build_blocked_item(
                        self.config,
                        notes=str(exc),
                        signal_type="github_contributor",
                    )
                ]
        if repo_seeds:
            records = await self._fetch_contributor_records(repo_seeds)
            return self._records_or_review(records)

        try:
            payload = await fetch_json(self._source_url(), **fetch_options(self.config))
        except Exception as exc:
            return [
                build_blocked_item(
                    self.config,
                    notes=str(exc),
                    signal_type="github_contributor",
                )
            ]

        records = extract_records(payload)
        records = await self._maybe_enrich_profiles(records)
        return self._records_or_review(records)

    async def _fetch_contributor_records(
        self,
        repo_seeds: list[str],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        min_contributions = int(self.config.get("min_contributions", 1))

        for repo_full_name in repo_seeds[: int(self.config.get("max_repos", 3))]:
            url = f"https://api.github.com/repos/{repo_full_name}/contributors"
            try:
                contributors = await fetch_json(
                    url,
                    params={"per_page": str(int(self.config.get("max_results_per_repo", 8)))},
                    headers=_GITHUB_HEADERS,
                    **fetch_options(self.config),
                )
            except Exception:
                continue
            if not isinstance(contributors, list):
                continue
            for contributor in contributors:
                if not isinstance(contributor, dict):
                    continue
                if int(contributor.get("contributions") or 0) < min_contributions:
                    continue
                records.append(
                    {
                        "candidate_name": contributor.get("login"),
                        "github_login": contributor.get("login"),
                        "repo_full_name": repo_full_name,
                        "contributions": contributor.get("contributions"),
                        "evidence_url": contributor.get("html_url"),
                        "confidence": 0.75,
                    }
                )

        return await self._maybe_enrich_profiles(records)

    async def _discover_repo_seeds(self) -> list[str]:
        repo_seeds: list[str] = []
        seen: set[str] = set()
        max_repos = int(self.config.get("max_repos", 3))

        for query in self._repo_search_queries():
            remaining = max_repos - len(repo_seeds)
            if remaining <= 0:
                break

            payload = await fetch_json(
                _GITHUB_REPOSITORY_SEARCH_URL,
                params={
                    "q": query,
                    "sort": str(self.config.get("repo_sort") or "stars"),
                    "order": str(self.config.get("repo_order") or "desc"),
                    "per_page": str(remaining),
                },
                headers=_GITHUB_HEADERS,
                **fetch_options(self.config),
            )
            if not isinstance(payload, dict):
                continue

            for repo in payload.get("items", []):
                if not isinstance(repo, dict):
                    continue
                repo_full_name = self._clean(repo.get("full_name"))
                if not repo_full_name or repo_full_name in seen:
                    continue
                seen.add(repo_full_name)
                repo_seeds.append(repo_full_name)
                if len(repo_seeds) >= max_repos:
                    break

        return repo_seeds

    async def _maybe_enrich_profiles(
        self,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self._profile_enrichment_enabled():
            return records

        max_profiles = int(
            self.config.get(
                "max_profile_enrichment",
                self.config.get("max_profile_fetches", 5),
            )
        )
        if max_profiles <= 0:
            return records

        profile_cache: dict[str, dict[str, Any]] = {}
        fetched_profiles = 0

        for record in records:
            github_login = self._clean(record.get("github_login"))
            if not github_login or not self._needs_profile_enrichment(record):
                continue

            profile = profile_cache.get(github_login)
            if profile is None:
                if fetched_profiles >= max_profiles:
                    continue
                profile = await self._fetch_profile(github_login)
                profile_cache[github_login] = profile
                fetched_profiles += 1

            if not profile:
                continue
            for key in ("followers", "company", "blog"):
                current_value = record.get(key)
                if current_value not in (None, ""):
                    continue
                if profile.get(key) is not None:
                    record[key] = profile.get(key)

        return records

    async def _fetch_profile(self, github_login: str) -> dict[str, Any]:
        try:
            profile = await fetch_json(
                f"{_GITHUB_USER_API_ROOT}/{github_login}",
                headers=_GITHUB_HEADERS,
                **fetch_options(self.config),
            )
        except Exception:
            return {}
        return profile if isinstance(profile, dict) else {}

    def _configured_repo_seeds(self) -> list[str]:
        repo_seeds = self.config.get("repo_seeds")
        if not isinstance(repo_seeds, list):
            return []
        return [
            repo_full_name
            for repo_full_name in (
                self._clean(value) for value in repo_seeds if isinstance(value, str)
            )
            if repo_full_name
        ]

    def _has_repo_discovery_config(self) -> bool:
        return bool(self._repo_search_queries())

    def _repo_search_queries(self) -> list[str]:
        base_query = self._clean(self.config.get("search_query"))
        topics = self._configured_topics()
        if topics:
            return [
                " ".join(part for part in (f"topic:{topic}", base_query) if part)
                for topic in topics
            ]
        if base_query:
            return [base_query]
        return []

    def _configured_topics(self) -> list[str]:
        topics: list[str] = []
        for key in ("topic", "topics", "search_topics", "repo_topics"):
            raw_value = self.config.get(key)
            if isinstance(raw_value, str):
                topics.append(self._clean(raw_value))
            elif isinstance(raw_value, list):
                topics.extend(
                    self._clean(value) for value in raw_value if isinstance(value, str)
                )
        return [topic for topic in topics if topic]

    def _profile_enrichment_enabled(self) -> bool:
        return bool(
            self.config.get("profile_enrichment")
            or self.config.get("enrich_profiles")
            or self.config.get("fetch_user_profiles")
        )

    @staticmethod
    def _needs_profile_enrichment(record: dict[str, Any]) -> bool:
        if record.get("followers") is None:
            return True
        return any(not str(record.get(key) or "").strip() for key in ("company", "blog"))

    def _records_or_review(self, records: list[dict[str, Any]]) -> list[CrawledItem]:
        items = self._records_to_items(records)
        if items:
            return items
        return [
            build_review_item(
                self.config,
                notes="no github contributor records",
                signal_type="github_contributor",
            )
        ]

    def _records_to_items(self, records: list[dict[str, Any]]) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        for record in records:
            item = self._record_to_item(record)
            if item is not None:
                items.append(item)
        return items

    def _record_to_item(self, record: dict[str, Any]) -> CrawledItem | None:
        candidate_name = self._clean(record.get("candidate_name"))
        evidence_url = self._clean(record.get("evidence_url")) or self._source_url()
        if not candidate_name or not evidence_url:
            return None

        github_login = self._clean(record.get("github_login"))
        repo_full_name = self._clean(record.get("repo_full_name"))
        company = self._clean(record.get("company"))
        blog = self._clean(record.get("blog"))

        talent_signal = build_talent_signal(
            signal_type="github_contributor",
            record_status="structured",
            evidence_url=evidence_url,
            candidate_name=candidate_name,
            track=get_track(self.config),
            confidence=float(record.get("confidence", 0.92)),
            identity_hints={
                key: value
                for key, value in {
                    "github_login": github_login,
                    "company": company,
                    "blog": blog,
                }.items()
                if value
            },
            source_metrics={
                key: value
                for key, value in {
                    "contributions": record.get("contributions"),
                    "followers": record.get("followers"),
                }.items()
                if value is not None
            },
            evidence_title=(
                repo_full_name
                or github_login
                or self.config.get("name")
                or self.source_id
            ),
            notes=self._clean(record.get("notes")),
        )

        return build_crawled_item(
            self.config,
            title=candidate_name,
            url=evidence_url,
            talent_signal=talent_signal,
            extra={
                "github_login": github_login,
                "repo_full_name": repo_full_name,
                "contributions": record.get("contributions"),
                "followers": record.get("followers"),
                "company": company,
                "blog": blog,
            },
        )

    def _source_url(self) -> str:
        seed_urls = self.config.get("seed_urls") or []
        return seed_urls[0] if seed_urls else str(self.config.get("url") or "")

    @staticmethod
    def _clean(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()
