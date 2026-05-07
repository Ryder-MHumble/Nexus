from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from app.config import BASE_DIR
from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.parsers._talent_scout_common import (
    build_blocked_item,
    build_crawled_item,
    build_review_item,
    build_talent_signal,
    extract_records,
    fetch_options,
    get_track,
    is_obvious_non_person_candidate_name,
)
from app.crawlers.utils.http_client import fetch_bytes, fetch_json, fetch_page

_HEADER_ALIASES = {
    "candidate_name": ("姓名", "学生", "获奖学生", "学生姓名", "队员", "成员"),
    "university": ("学校", "高校", "参赛学校", "学校名称"),
    "department": ("二级学院", "学院", "院系", "所在学院"),
    "award_level": ("国家获奖", "等次", "获奖等级", "奖项", "获奖情况", "国家奖项"),
    "provincial_award_level": ("省市获奖", "省赛获奖", "省级奖项", "省奖项"),
    "ranking": ("序号", "排名", "名次"),
    "team_name": ("团队", "队名", "作品", "项目名称"),
    "subject": ("科目", "赛项", "竞赛项目", "竞赛名称"),
    "competition_group": ("组别", "类别"),
    "instructor": ("导师", "指导教师", "指导老师"),
    "notes": ("备注", "说明"),
}
_LANQIAO_AWARD_RE = re.compile(r"(一等奖|二等奖|三等奖|优秀奖)$")
_LANQIAO_LINE_RE = re.compile(
    r"^(?P<exam_no>\d{6,})\s+(?P<body>.+?)\s+(?P<award>一等奖|二等奖|三等奖|优秀奖)$"
)


class CompetitionSourceCrawler(BaseCrawler):
    async def fetch_and_parse(self) -> list[CrawledItem]:
        capture_mode = self.config.get("capture_mode")
        if capture_mode == "semi_structured":
            try:
                items = await self._parse_rank_table()
            except Exception as exc:
                if self.config.get("fallback_mode") == "evidence_only":
                    return [
                        build_blocked_item(
                            self.config,
                            notes=str(exc),
                            signal_type="competition",
                        )
                    ]
                raise
            if items or self.config.get("fallback_mode") != "evidence_only":
                return items
            return [
                build_review_item(
                    self.config,
                    notes="no semi-structured competition records",
                    signal_type="competition",
                )
            ]

        adapter_key = str(self.config.get("adapter_key") or "")
        if adapter_key == "tianchi_rank_list":
            return await self._fetch_tianchi_rank_list()
        if adapter_key == "lanqiao_archive":
            return await self._fetch_lanqiao_archive()
        if adapter_key == "kaggle_rankings_v2":
            return await self._fetch_kaggle_rankings()
        if adapter_key == "ctftime_top_teams":
            return await self._fetch_ctftime_top_teams()
        if adapter_key == "casp_groups":
            return await self._fetch_casp_groups()
        if adapter_key == "competition_history_json":
            return await self._fetch_competition_history_json()
        if adapter_key == "talent_signal_json":
            return await self._fetch_talent_signal_json()

        try:
            payload = await fetch_json(self._source_url(), **fetch_options(self.config))
        except Exception as exc:
            if self.config.get("fallback_mode") == "evidence_only":
                return [
                    build_blocked_item(
                        self.config,
                        notes=str(exc),
                        signal_type="competition",
                    )
                ]
            raise

        items = self._parse_structured_records(payload)
        if items:
            return items
        if self.config.get("fallback_mode") == "evidence_only":
            return [
                build_review_item(
                    self.config,
                    notes="no structured competition records",
                    signal_type="competition",
                )
            ]
        return []

    async def _fetch_tianchi_rank_list(self) -> list[CrawledItem]:
        race_id = self._clean(self.config.get("race_id"))
        if not race_id:
            return [
                build_blocked_item(
                    self.config,
                    notes="race_id is required for tianchi_rank_list",
                    signal_type="competition",
                )
            ]

        max_pages = max(1, int(self.config.get("max_pages", 1)))
        records: list[dict[str, Any]] = []
        for page_num in range(1, max_pages + 1):
            try:
                payload = await fetch_json(
                    "https://tianchi.aliyun.com/v3/proxy/competition/api/race/rank/list",
                    params={"raceId": race_id, "pageNum": str(page_num)},
                    headers={
                        "Accept": "application/json, text/plain, */*",
                        "Referer": self._source_url(),
                    },
                    **fetch_options(self.config),
                )
            except Exception as exc:
                if records:
                    break
                return [
                    build_blocked_item(
                        self.config,
                        notes=str(exc),
                        signal_type="competition",
                    )
                ]

            data = payload.get("data") if isinstance(payload, dict) else {}
            rows = data.get("list") if isinstance(data, dict) else []
            if not isinstance(rows, list) or not rows:
                break
            records.extend(row for row in rows if isinstance(row, dict))
            page_size = int(data.get("pageSize") or len(rows) or 1)
            total = int(data.get("total") or 0)
            if total and page_num * page_size >= total:
                break

        return self._tianchi_records_to_items(records)

    async def _fetch_ctftime_top_teams(self) -> list[CrawledItem]:
        headers = {
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (compatible; CTFtimeCrawler/1.0; "
                "+https://github.com/openclaw)"
            )
        }
        max_results = max(1, int(self.config.get("max_results", 25)))
        payload = await fetch_json(
            "https://ctftime.org/api/v1/top/",
            params={"limit": str(max_results)},
            headers=headers,
            **fetch_options(self.config),
        )

        current_year = str(
            int(self.config.get("season_year") or datetime.now(timezone.utc).year)
        )
        previous_year = str(int(current_year) - 1)
        teams = payload.get(current_year)
        resolved_year = int(current_year)
        if not teams:
            teams = payload.get(previous_year) or []
            resolved_year = int(previous_year)
        if not isinstance(teams, list) or not teams:
            return [
                build_review_item(
                    self.config,
                    notes="no CTFtime top teams returned from public API",
                    signal_type="competition",
                )
            ]

        items: list[CrawledItem] = []
        for index, team in enumerate(teams[:max_results], start=1):
            if not isinstance(team, dict):
                continue
            detail = await self._fetch_ctftime_team_detail(
                team.get("team_id"),
                headers=headers,
            )
            item = self._ctftime_team_to_item(
                team,
                detail=detail,
                ranking=index,
                season_year=resolved_year,
            )
            if item is not None:
                items.append(item)

        if items:
            return items
        return [
            build_review_item(
                self.config,
                notes="no CTFtime team-level signals mapped into talent rows",
                signal_type="competition",
            )
        ]

    async def _fetch_ctftime_team_detail(
        self,
        team_id: Any,
        *,
        headers: dict[str, str],
    ) -> dict[str, Any] | None:
        if team_id in ("", None):
            return None
        try:
            detail = await fetch_json(
                f"https://ctftime.org/api/v1/teams/{team_id}/",
                headers=headers,
                **fetch_options(self.config),
            )
        except Exception:
            return None
        return detail if isinstance(detail, dict) else None

    def _ctftime_team_to_item(
        self,
        record: dict[str, Any],
        *,
        detail: dict[str, Any] | None,
        ranking: int,
        season_year: int,
    ) -> CrawledItem | None:
        detail = detail or {}
        team_name = self._clean(
            detail.get("name")
            or record.get("team_name")
            or record.get("name")
            or detail.get("primary_alias")
        )
        if not team_name:
            return None

        rating = detail.get("rating") if isinstance(detail.get("rating"), dict) else {}
        evidence_url = (
            f"https://ctftime.org/team/{detail.get('id')}"
            if detail.get("id")
            else self._source_url()
        )
        notes = "team-level signal parsed from CTFtime public API"
        talent_signal = build_talent_signal(
            signal_type="competition",
            record_status="structured",
            evidence_url=evidence_url,
            candidate_name=team_name,
            track=get_track(self.config),
            confidence=0.66,
            identity_hints={
                key: value
                    for key, value in {
                        "team_id": detail.get("id") or record.get("team_id"),
                        "primary_alias": self._clean(detail.get("primary_alias")),
                        "aliases": (
                            detail.get("aliases")
                            if isinstance(detail.get("aliases"), list)
                            else None
                        ),
                        "country": self._clean(detail.get("country")),
                        "academic": detail.get("academic"),
                    }.items()
                if value not in ("", None, [])
            },
            source_metrics={
                key: value
                for key, value in {
                    "ranking": ranking,
                    "points": record.get("points"),
                    "rating_points": (
                        rating.get("rating_points") if isinstance(rating, dict) else None
                    ),
                    "country_place": (
                        rating.get("country_place") if isinstance(rating, dict) else None
                    ),
                    "organizer_points": (
                        rating.get("organizer_points") if isinstance(rating, dict) else None
                    ),
                }.items()
                if value not in ("", None)
            },
            evidence_title=(
                self.config.get("competition_name")
                or self.config.get("name")
                or self.source_id
            ),
            notes=notes,
        )
        return build_crawled_item(
            self.config,
            title=team_name,
            url=evidence_url,
            talent_signal=talent_signal,
            extra={
                "competition_name": self.config.get("competition_name") or self.config.get("name"),
                "season_year": season_year,
                "award_level": "",
                "ranking": str(ranking),
                "team_name": team_name,
                "entity_kind": "team",
                "country": self._clean(detail.get("country")),
                "academic": detail.get("academic"),
                "primary_alias": self._clean(detail.get("primary_alias")),
            },
        )

    async def _fetch_casp_groups(self) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        for source_ref in self._source_refs():
            source_url = str(source_ref["url"])
            html = await fetch_page(source_url, **fetch_options(self.config))
            items.extend(
                self._parse_casp_groups_html(
                    html,
                    source_url=source_url,
                    source_ref=source_ref,
                )
            )

        if items:
            return items
        return [
            build_review_item(
                self.config,
                notes="no CASP groups parsed from official table pages",
                signal_type="competition",
            )
        ]

    async def _fetch_competition_history_json(self) -> list[CrawledItem]:
        data_path = self._resolve_local_results_path(self.config.get("local_results_path"))
        if data_path is None:
            return [
                build_blocked_item(
                    self.config,
                    notes="local_results_path is required for competition_history_json",
                    signal_type="competition",
                )
            ]

        payload = json.loads(data_path.read_text(encoding="utf-8"))
        competitions = payload.get("competitions")
        if not isinstance(competitions, list):
            return [
                build_review_item(
                    self.config,
                    notes="competition history payload does not contain competitions[]",
                    signal_type="competition",
                )
            ]

        matched = [
            comp
            for comp in competitions
            if self._history_competition_matches(comp)
        ]
        if not matched:
            return [
                build_review_item(
                    self.config,
                    notes="no competition history matched current source config",
                    signal_type="competition",
                )
            ]

        items: list[CrawledItem] = []
        for competition in matched:
            items.extend(self._competition_history_to_items(competition))

        if items:
            return items
        return [
            build_review_item(
                self.config,
                notes="no competition history items mapped into talent rows",
                signal_type="competition",
            )
        ]

    async def _fetch_talent_signal_json(self) -> list[CrawledItem]:
        data_path = self._resolve_local_results_path(self.config.get("local_results_path"))
        if data_path is None:
            return [
                build_blocked_item(
                    self.config,
                    notes="local_results_path is required for talent_signal_json",
                    signal_type="competition",
                )
            ]

        try:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return [
                build_blocked_item(
                    self.config,
                    notes=str(exc),
                    signal_type="competition",
                )
            ]

        source_ids = self._configured_local_source_ids()
        rows = extract_records(payload)
        items: list[CrawledItem] = []
        for row in rows:
            row_source_id = self._clean(row.get("source_id"))
            if source_ids and row_source_id not in source_ids:
                continue
            item = self._talent_signal_row_to_competition_item(row)
            if item is not None:
                items.append(item)

        if items:
            return items
        return [
            build_review_item(
                self.config,
                notes="no local talent signal rows matched current source",
                signal_type="competition",
            )
        ]

    async def _fetch_lanqiao_archive(self) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        last_exc: Exception | None = None
        for source_ref in self._source_refs():
            source_url = str(source_ref["url"])
            if not self._is_archive_url(source_url):
                continue
            try:
                archive_bytes = await fetch_bytes(source_url, **fetch_options(self.config))
                pdf_texts = self._extract_archive_pdf_texts(archive_bytes)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue

            for pdf_path, text in pdf_texts:
                subject_name = self._lanqiao_subject_from_pdf_path(pdf_path)
                for record in self._parse_lanqiao_pdf_text(text, subject_name=subject_name):
                    item = self._lanqiao_record_to_item(
                        record,
                        source_url=source_url,
                        source_ref=source_ref,
                        pdf_path=pdf_path,
                    )
                    if item is not None:
                        items.append(item)

        if items:
            return items
        if last_exc is not None:
            return [
                build_blocked_item(
                    self.config,
                    notes=str(last_exc),
                    signal_type="competition",
                )
            ]
        return [
            build_review_item(
                self.config,
                notes="no Lanqiao archive records",
                signal_type="competition",
            )
        ]

    async def _fetch_kaggle_rankings(self) -> list[CrawledItem]:
        try:
            payload = await self._fetch_kaggle_rankings_payload()
        except Exception as exc:  # noqa: BLE001
            return [
                build_blocked_item(
                    self.config,
                    notes=str(exc),
                    signal_type="competition",
                )
            ]

        records = payload.get("userRankings") if isinstance(payload, dict) else []
        if not isinstance(records, list) or not records:
            return [
                build_review_item(
                    self.config,
                    notes="no Kaggle ranking records",
                    signal_type="competition",
                )
            ]
        max_results = int(self.config.get("max_results") or len(records))
        return self._kaggle_rankings_to_items(records[:max_results])

    async def _fetch_kaggle_rankings_payload(self) -> dict[str, Any]:
        source_url = self._source_url()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        async with httpx.AsyncClient(
            timeout=float(self.config.get("request_timeout", 10.0)),
            follow_redirects=True,
            headers=headers,
        ) as client:
            home_response = await client.get(source_url)
            home_response.raise_for_status()
            xsrf_token = client.cookies.get("XSRF-TOKEN") or client.cookies.get("CSRF-TOKEN")
            api_headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://www.kaggle.com",
                "Referer": source_url,
            }
            if xsrf_token:
                api_headers["X-XSRF-TOKEN"] = xsrf_token
            api_response = await client.post(
                "https://www.kaggle.com/api/i/users.RankingService/GetUserRankingsV2",
                headers=api_headers,
                json={"type": "competitions"},
            )
            api_response.raise_for_status()
            return api_response.json()

    def _kaggle_rankings_to_items(self, records: list[dict[str, Any]]) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        evidence_url = self._source_url()
        competition_name = (
            self.config.get("competition_name")
            or self.config.get("name")
            or self.source_id
        )
        for record in records:
            candidate_name = self._clean(record.get("displayName"))
            user_url = self._clean(record.get("userUrl"))
            if not candidate_name or not user_url:
                continue
            profile_url = f"https://www.kaggle.com{user_url}"
            ranking = self._clean(record.get("currentRanking"))
            tier = self._clean(record.get("tierForAchievementType") or record.get("tier"))

            talent_signal = build_talent_signal(
                signal_type="competition",
                record_status="structured",
                evidence_url=profile_url,
                candidate_name=candidate_name,
                track=get_track(self.config),
                confidence=0.76,
                identity_hints={
                    key: value
                    for key, value in {
                        "kaggle_user_id": record.get("userId"),
                        "kaggle_user_url": user_url,
                        "tier": tier,
                    }.items()
                    if value not in ("", None)
                },
                source_metrics={
                    key: value
                    for key, value in {
                        "ranking": ranking,
                        "points": record.get("points"),
                        "gold_medals": record.get("totalGoldMedals"),
                        "silver_medals": record.get("totalSilverMedals"),
                        "bronze_medals": record.get("totalBronzeMedals"),
                    }.items()
                    if value not in ("", None)
                },
                evidence_title=competition_name,
                notes="parsed from Kaggle RankingService competition rankings API",
            )
            items.append(
                build_crawled_item(
                    self.config,
                    title=candidate_name,
                    url=profile_url,
                    talent_signal=talent_signal,
                    extra={
                        "competition_name": competition_name,
                        "season_year": self.config.get("season_year"),
                        "award_level": tier,
                        "ranking": ranking,
                        "team_name": "",
                        "points": record.get("points"),
                        "source_rankings_url": evidence_url,
                    },
                )
            )
        return items

    def _lanqiao_record_to_item(
        self,
        record: dict[str, str],
        *,
        source_url: str,
        source_ref: dict[str, Any],
        pdf_path: str,
    ) -> CrawledItem | None:
        candidate_name = record.get("candidate_name", "")
        if not candidate_name:
            return None

        competition_name = (
            self.config.get("competition_name")
            or self.config.get("name")
            or self.source_id
        )
        season_year = source_ref.get("season_year", self.config.get("season_year"))
        evidence_title = (
            self._clean(source_ref.get("evidence_title"))
            or f"{competition_name} {record.get('subject', '')}".strip()
        )
        evidence_url = f"{source_url}#{quote(pdf_path)}:{record.get('exam_no', '')}"

        talent_signal = build_talent_signal(
            signal_type="competition",
            record_status="structured",
            evidence_url=evidence_url,
            candidate_name=candidate_name,
            university=record.get("university", ""),
            track=get_track(self.config),
            confidence=0.9,
            identity_hints={
                key: value
                for key, value in {
                    "exam_no": record.get("exam_no"),
                    "subject": record.get("subject"),
                    "source_pdf": pdf_path,
                }.items()
                if value
            },
            source_metrics={
                "award_level": record.get("award_level", ""),
            },
            evidence_title=evidence_title,
            notes="parsed from official Lanqiao national final PDF archive",
        )

        return build_crawled_item(
            self.config,
            title=candidate_name,
            url=evidence_url,
            talent_signal=talent_signal,
            extra={
                "competition_name": competition_name,
                "season_year": season_year,
                "award_level": record.get("award_level", ""),
                "ranking": "",
                "team_name": "",
                "subject": record.get("subject", ""),
                "exam_no": record.get("exam_no", ""),
                "source_pdf": pdf_path,
            },
        )

    def _tianchi_records_to_items(self, records: list[dict[str, Any]]) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        competition_name = (
            self.config.get("competition_name")
            or self.config.get("name")
            or self.source_id
        )
        evidence_url = self._source_url()

        for record in records:
            members = record.get("teamMemberList")
            if not isinstance(members, list) or not members:
                members = [{"nickName": record.get("teamName")}]

            for member in members:
                if not isinstance(member, dict):
                    continue
                candidate_name = self._clean(member.get("nickName"))
                if not candidate_name:
                    continue

                team_name = self._clean(record.get("teamName"))
                ranking = self._clean(record.get("rank"))
                organization = self._clean(record.get("teamLeaderOrganization"))
                user_id = member.get("userId")
                score = record.get("score")

                talent_signal = build_talent_signal(
                    signal_type="competition",
                    record_status="structured",
                    evidence_url=evidence_url,
                    candidate_name=candidate_name,
                    university=organization,
                    track=get_track(self.config),
                    confidence=0.78,
                    identity_hints={
                        key: value
                        for key, value in {
                            "team_name": team_name,
                            "user_id": user_id,
                            "is_student": member.get("isStudent"),
                        }.items()
                        if value not in ("", None)
                    },
                    source_metrics={
                        key: value
                        for key, value in {
                            "ranking": ranking,
                            "score": score,
                            "submit_count": record.get("submitCount"),
                            "gmt_submit": record.get("gmtSubmit"),
                        }.items()
                        if value not in ("", None)
                    },
                    evidence_title=str(competition_name),
                    notes="parsed from Tianchi public rank list API",
                )

                items.append(
                    build_crawled_item(
                        self.config,
                        title=candidate_name,
                        url=evidence_url,
                        talent_signal=talent_signal,
                        extra={
                            "competition_name": competition_name,
                            "season_year": self.config.get("season_year"),
                            "ranking": ranking,
                            "team_name": team_name,
                            "score": score,
                            "submit_count": record.get("submitCount"),
                            "gmt_submit": record.get("gmtSubmit"),
                        },
                    )
                )

        if items:
            return items
        return [
            build_review_item(
                self.config,
                notes="no Tianchi rank list records",
                signal_type="competition",
            )
        ]

    async def _parse_rank_table(self) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        last_exc: Exception | None = None
        for source_ref in self._source_refs():
            source_url = str(source_ref["url"])
            try:
                html = await fetch_page(source_url, **fetch_options(self.config))
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue

            soup = BeautifulSoup(html, "lxml")
            items.extend(self._parse_rank_table_html(soup, source_url, source_ref))

        if items:
            return items
        if last_exc is not None:
            raise last_exc
        return []

    def _parse_rank_table_html(
        self,
        soup: BeautifulSoup,
        source_url: str,
        source_ref: dict[str, Any],
    ) -> list[CrawledItem]:
        selectors = self.config.get("selectors", {})
        if not selectors.get("candidate_name"):
            return self._parse_auto_tables(soup, source_url, source_ref)

        row_selector = selectors.get("row", "tr")

        items: list[CrawledItem] = []
        for row in soup.select(row_selector):
            candidate_name = self._extract_text(row, selectors.get("candidate_name"))
            if not candidate_name or is_obvious_non_person_candidate_name(candidate_name):
                continue

            university = self._extract_text(row, selectors.get("university"))
            award_level = self._extract_text(row, selectors.get("award_level"))
            ranking = self._extract_text(row, selectors.get("ranking"))
            team_name = self._extract_text(row, selectors.get("team_name"))
            evidence_url = source_url
            competition_name = (
                self.config.get("competition_name")
                or self.config.get("name")
                or self.source_id
            )

            talent_signal = build_talent_signal(
                signal_type="competition",
                record_status="partial",
                evidence_url=evidence_url,
                candidate_name=candidate_name,
                university=university,
                track=get_track(self.config),
                confidence=0.7,
                identity_hints={"team_name": team_name} if team_name else {},
                source_metrics={
                    "ranking": ranking,
                    "award_level": award_level,
                },
                evidence_title=competition_name,
                notes="parsed from semi-structured competition ranking table",
            )

            items.append(
                build_crawled_item(
                    self.config,
                    title=candidate_name,
                    url=evidence_url,
                    talent_signal=talent_signal,
                    extra={
                        "competition_name": competition_name,
                        "season_year": self.config.get("season_year"),
                        "award_level": award_level,
                        "ranking": ranking,
                        "team_name": team_name,
                    },
                )
            )

        return items

    def _parse_auto_tables(
        self,
        soup: BeautifulSoup,
        source_url: str,
        source_ref: dict[str, Any],
    ) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        for table in soup.select("table"):
            rows = self._table_rows(table)
            header_index, columns = self._detect_header(rows)
            if header_index is None:
                continue

            for cells in rows[header_index + 1:]:
                row_data = self._cells_to_record(cells, columns)
                candidate_names = self._split_candidate_names(row_data.get("candidate_name"))
                for candidate_name in candidate_names:
                    item = self._auto_record_to_item(
                        row_data,
                        candidate_name=candidate_name,
                        source_url=source_url,
                        source_ref=source_ref,
                    )
                    if item is not None:
                        items.append(item)
        return items

    def _auto_record_to_item(
        self,
        row_data: dict[str, str],
        *,
        candidate_name: str,
        source_url: str,
        source_ref: dict[str, Any],
    ) -> CrawledItem | None:
        if not candidate_name or is_obvious_non_person_candidate_name(candidate_name):
            return None

        competition_name = (
            row_data.get("competition_name")
            or self.config.get("competition_name")
            or self.config.get("name")
            or self.source_id
        )
        university = (
            row_data.get("university")
            or self._clean(source_ref.get("source_university"))
            or self._clean(self.config.get("source_university"))
        )
        department = row_data.get("department", "")
        award_level = row_data.get("award_level") or row_data.get("provincial_award_level", "")
        ranking = row_data.get("ranking", "")
        team_name = row_data.get("team_name", "")
        subject = row_data.get("subject", "")
        competition_group = row_data.get("competition_group", "")
        instructor = row_data.get("instructor", "")
        notes = row_data.get("notes", "")
        provincial_award_level = row_data.get("provincial_award_level", "")
        season_year = source_ref.get("season_year", self.config.get("season_year"))
        evidence_title = (
            self._clean(source_ref.get("evidence_title"))
            or self._clean(self.config.get("name"))
            or competition_name
        )

        talent_signal = build_talent_signal(
            signal_type="competition",
            record_status="partial",
            evidence_url=source_url,
            candidate_name=candidate_name,
            university=university,
            department=department,
            track=get_track(self.config),
            confidence=0.72,
            identity_hints={
                key: value
                for key, value in {
                    "team_name": team_name,
                    "instructor": instructor,
                    "subject": subject,
                    "competition_group": competition_group,
                }.items()
                if value
            },
            source_metrics={
                key: value
                for key, value in {
                    "ranking": ranking,
                    "award_level": award_level,
                    "provincial_award_level": provincial_award_level,
                }.items()
                if value
            },
            evidence_title=evidence_title,
            notes=notes or "parsed from auto-detected competition award table",
        )

        return build_crawled_item(
            self.config,
            title=candidate_name,
            url=source_url,
            talent_signal=talent_signal,
            extra={
                "competition_name": competition_name,
                "season_year": season_year,
                "award_level": award_level,
                "provincial_award_level": provincial_award_level,
                "ranking": ranking,
                "team_name": team_name,
                "subject": subject,
                "competition_group": competition_group,
                "instructor": instructor,
                "notes": notes,
            },
        )

    def _parse_casp_groups_html(
        self,
        html: str,
        *,
        source_url: str,
        source_ref: dict[str, Any],
    ) -> list[CrawledItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[CrawledItem] = []
        for table in soup.select("table"):
            rows = table.select("tr")
            if len(rows) < 2:
                continue
            for row in rows[1:]:
                cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
                if len(cells) < 3:
                    continue
                ranking = self._clean(cells[0])
                gr_number = self._clean(cells[1])
                team_name = self._clean(cells[2])
                if not ranking.isdigit() or not team_name:
                    continue
                domains_count = self._clean(cells[3] if len(cells) > 3 else "")
                avg_gdt_ts = self._clean(cells[6] if len(cells) > 6 else "")
                institution = self._infer_competition_institution(team_name)
                country = self._infer_competition_country(team_name)
                season_year = source_ref.get("season_year", self.config.get("season_year"))
                evidence_title = (
                    self._clean(source_ref.get("evidence_title"))
                    or self._clean(self.config.get("name"))
                    or self.source_id
                )
                talent_signal = build_talent_signal(
                    signal_type="competition",
                    record_status="structured",
                    evidence_url=source_url,
                    candidate_name=team_name,
                    university=institution,
                    track=get_track(self.config),
                    confidence=0.82,
                    identity_hints={
                        key: value
                        for key, value in {
                            "gr_number": re.sub(r"[A-Za-z]", "", gr_number),
                            "is_server": gr_number.lower().endswith("s"),
                            "country": country,
                        }.items()
                        if value not in ("", None)
                    },
                    source_metrics={
                        key: value
                        for key, value in {
                            "ranking": ranking,
                            "domains_count": domains_count,
                            "avg_gdt_ts": avg_gdt_ts,
                        }.items()
                        if value not in ("", None)
                    },
                    evidence_title=evidence_title,
                    notes="team-level signal parsed from CASP official groups table",
                )
                items.append(
                    build_crawled_item(
                        self.config,
                        title=team_name,
                        url=source_url,
                        talent_signal=talent_signal,
                        extra={
                            "competition_name": evidence_title,
                            "season_year": season_year,
                            "award_level": self._casp_award_level(int(ranking)),
                            "ranking": ranking,
                            "team_name": team_name,
                            "entity_kind": "team",
                            "country": country,
                            "gr_number": re.sub(r"[A-Za-z]", "", gr_number),
                            "domains_count": domains_count,
                            "avg_gdt_ts": avg_gdt_ts,
                        },
                    )
                )
        return items

    def _parse_structured_records(self, payload: Any) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        competition_name = (
            self.config.get("competition_name")
            or self.config.get("name")
            or self.source_id
        )

        for record in extract_records(payload):
            candidate_name = self._clean(record.get("candidate_name"))
            evidence_url = self._clean(record.get("evidence_url")) or self._source_url()
            if not candidate_name or not evidence_url:
                continue

            university = self._clean(record.get("university"))
            department = self._clean(record.get("department"))
            email = self._clean(record.get("email"))
            award_level = self._clean(record.get("award_level"))
            ranking = self._clean(record.get("ranking"))
            team_name = self._clean(record.get("team_name"))

            talent_signal = build_talent_signal(
                signal_type="competition",
                record_status="structured",
                evidence_url=evidence_url,
                candidate_name=candidate_name,
                university=university,
                department=department,
                email=email,
                track=get_track(self.config),
                confidence=float(record.get("confidence", 0.9)),
                identity_hints={k: v for k, v in {"team_name": team_name}.items() if v},
                source_metrics={
                    "ranking": ranking,
                    "award_level": award_level,
                },
                evidence_title=self._clean(record.get("evidence_title")) or competition_name,
                notes=self._clean(record.get("notes")),
            )

            items.append(
                build_crawled_item(
                    self.config,
                    title=candidate_name,
                    url=evidence_url,
                    talent_signal=talent_signal,
                    extra={
                        "competition_name": competition_name,
                        "season_year": record.get("season_year", self.config.get("season_year")),
                        "award_level": award_level,
                        "ranking": ranking,
                        "team_name": team_name,
                    },
                )
            )

        return items

    def _talent_signal_row_to_competition_item(
        self,
        record: dict[str, Any],
    ) -> CrawledItem | None:
        candidate_name = self._clean(record.get("candidate_name"))
        evidence_url = self._clean(record.get("evidence_url")) or self._source_url()
        if (
            not candidate_name
            or not evidence_url
            or is_obvious_non_person_candidate_name(candidate_name)
        ):
            return None

        competition_name = (
            self._clean(record.get("source_name"))
            or self.config.get("competition_name")
            or self.config.get("name")
            or self.source_id
        )
        original_status = self._clean(record.get("record_status"))
        record_status = "structured" if original_status == "verified" else "partial"
        season_year = self._extract_year(record.get("time_info"))
        award_level = self._clean(record.get("result_label"))
        ranking = self._clean(record.get("ranking"))
        team_name = self._clean(record.get("team_name"))
        notes = self._clean(record.get("notes"))

        talent_signal = build_talent_signal(
            signal_type="competition",
            record_status=record_status,
            evidence_url=evidence_url,
            candidate_name=candidate_name,
            university=self._clean(record.get("university")),
            department=self._clean(record.get("department")),
            email=self._clean(record.get("email")),
            track=self._clean(record.get("track")) or get_track(self.config),
            confidence=float(record.get("confidence", 0.65) or 0.65),
            identity_hints={
                key: value
                for key, value in {
                    "original_source_id": self._clean(record.get("source_id")),
                    "team_name": team_name,
                    "source_platform": self._clean(record.get("source_platform")),
                }.items()
                if value
            },
            source_metrics={
                key: value
                for key, value in {
                    "ranking": ranking,
                    "award_level": award_level,
                    "time_info": self._clean(record.get("time_info")),
                }.items()
                if value
            },
            evidence_title=self._clean(record.get("evidence_title")) or str(competition_name),
            notes=notes,
        )

        return build_crawled_item(
            self.config,
            title=candidate_name,
            url=evidence_url,
            talent_signal=talent_signal,
            extra={
                "competition_name": competition_name,
                "season_year": season_year,
                "award_level": award_level,
                "ranking": ranking,
                "team_name": team_name,
                "notes": notes,
                "time_info": self._clean(record.get("time_info")),
                "original_source_id": self._clean(record.get("source_id")),
                "original_record_status": original_status,
            },
        )

    def _competition_history_to_items(self, competition: dict[str, Any]) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        competition_name = self._clean(competition.get("name")) or (
            self.config.get("competition_name")
            or self.config.get("name")
            or self.source_id
        )
        competition_url = self._clean(competition.get("url")) or self._source_url()

        if isinstance(competition.get("years"), list):
            for season in competition.get("years", []):
                if not isinstance(season, dict):
                    continue
                season_year = season.get("year", self.config.get("season_year"))
                for team in season.get("teams", []):
                    if isinstance(team, dict):
                        item = self._history_team_to_item(
                            team,
                            competition_name=competition_name,
                            competition_url=competition_url,
                            season_year=season_year,
                        )
                        if item is not None:
                            items.append(item)
            return items

        if isinstance(competition.get("teams"), list):
            season_year = competition.get("year", self.config.get("season_year"))
            for team in competition.get("teams", []):
                if isinstance(team, dict):
                    item = self._history_team_to_item(
                        team,
                        competition_name=competition_name,
                        competition_url=competition_url,
                        season_year=season_year,
                    )
                    if item is not None:
                        items.append(item)
            return items

        if isinstance(competition.get("awardees"), list):
            season_year = competition.get("year", self.config.get("season_year"))
            for awardee in competition.get("awardees", []):
                if isinstance(awardee, dict):
                    item = self._history_awardee_to_item(
                        awardee,
                        competition_name=competition_name,
                        competition_url=competition_url,
                        season_year=season_year,
                    )
                    if item is not None:
                        items.append(item)
        return items

    def _history_team_to_item(
        self,
        team: dict[str, Any],
        *,
        competition_name: str,
        competition_url: str,
        season_year: Any,
    ) -> CrawledItem | None:
        team_name = self._clean(team.get("name"))
        if not team_name:
            return None
        rank = self._clean(team.get("rank"))
        school = self._clean(team.get("school"))
        country = self._clean(team.get("country"))
        members = team.get("members") if isinstance(team.get("members"), list) else []
        talent_signal = build_talent_signal(
            signal_type="competition",
            record_status="structured",
            evidence_url=competition_url,
            candidate_name=team_name,
            university=school,
            track=get_track(self.config),
            confidence=0.74,
            identity_hints={
                key: value
                for key, value in {
                    "country": country,
                    "members": members or None,
                }.items()
                if value not in ("", None, [])
            },
            source_metrics={"ranking": rank} if rank else {},
            evidence_title=competition_name,
            notes="team-level signal imported from curated competition history",
        )
        return build_crawled_item(
            self.config,
            title=team_name,
            url=competition_url,
            talent_signal=talent_signal,
            extra={
                "competition_name": competition_name,
                "season_year": season_year,
                "award_level": rank,
                "ranking": rank,
                "team_name": team_name,
                "entity_kind": "team",
                "country": country,
                "source_members": members,
            },
        )

    def _history_awardee_to_item(
        self,
        awardee: dict[str, Any],
        *,
        competition_name: str,
        competition_url: str,
        season_year: Any,
    ) -> CrawledItem | None:
        candidate_name = self._clean(awardee.get("name"))
        if not candidate_name:
            return None
        school = self._clean(awardee.get("school"))
        award_level = self._clean(awardee.get("award"))
        ranking = self._clean(awardee.get("rank"))
        source_link = self._clean(awardee.get("source_link")) or competition_url
        talent_signal = build_talent_signal(
            signal_type="competition",
            record_status="partial",
            evidence_url=source_link,
            candidate_name=candidate_name,
            university=school,
            track=get_track(self.config),
            confidence=0.64,
            source_metrics={
                key: value
                for key, value in {
                    "ranking": ranking,
                    "award_level": award_level,
                }.items()
                if value
            },
            evidence_title=competition_name,
            notes="competition awardee imported from curated historical crawler output",
        )
        return build_crawled_item(
            self.config,
            title=candidate_name,
            url=source_link,
            talent_signal=talent_signal,
            extra={
                "competition_name": competition_name,
                "season_year": season_year,
                "award_level": award_level,
                "ranking": ranking,
                "team_name": "",
            },
        )

    def _source_url(self) -> str:
        refs = self._source_refs()
        if refs:
            return str(refs[0]["url"])
        return str(self.config.get("url") or "")

    def _source_refs(self) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for value in self.config.get("seed_urls") or []:
            if isinstance(value, str) and value.strip():
                refs.append({"url": value.strip()})
            elif isinstance(value, dict):
                url = self._clean(value.get("url"))
                if url:
                    ref = dict(value)
                    ref["url"] = url
                    refs.append(ref)
        if not refs:
            url = self._clean(self.config.get("url"))
            if url:
                refs.append({"url": url})
        return refs

    def _configured_local_source_ids(self) -> set[str]:
        raw_value = self.config.get("local_source_ids")
        values: list[str] = []
        if isinstance(raw_value, str):
            values = [raw_value]
        elif isinstance(raw_value, list):
            values = [value for value in raw_value if isinstance(value, str)]
        if not values:
            values = [self.source_id]
        return {value.strip() for value in values if value.strip()}

    @staticmethod
    def _extract_text(row: Any, selector: str | None) -> str:
        if not selector:
            return ""
        node = row.select_one(selector)
        if not node:
            return ""
        return node.get_text(" ", strip=True)

    @staticmethod
    def _clean(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _extract_year(value: Any) -> int | None:
        match = re.search(r"(19|20)\d{2}", str(value or ""))
        return int(match.group(0)) if match else None

    @staticmethod
    def _table_rows(table: Any) -> list[list[str]]:
        rows: list[list[str]] = []
        for row in table.select("tr"):
            cells = [
                cell.get_text(" ", strip=True)
                for cell in row.select("th,td")
            ]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(cells)
        return rows

    @classmethod
    def _detect_header(cls, rows: list[list[str]]) -> tuple[int | None, dict[str, int]]:
        for index, cells in enumerate(rows):
            columns = cls._map_header_columns(cells)
            if "candidate_name" not in columns:
                continue
            has_competition_signal = any(
                field in columns
                for field in (
                    "award_level",
                    "provincial_award_level",
                    "subject",
                    "competition_group",
                    "instructor",
                )
            )
            if has_competition_signal:
                return index, columns
        return None, {}

    @staticmethod
    def _map_header_columns(cells: list[str]) -> dict[str, int]:
        columns: dict[str, int] = {}
        for index, raw_header in enumerate(cells):
            header = re.sub(r"\s+", "", raw_header)
            for field, aliases in _HEADER_ALIASES.items():
                if field in columns:
                    continue
                if any(alias in header for alias in aliases):
                    columns[field] = index
        return columns

    @staticmethod
    def _cells_to_record(cells: list[str], columns: dict[str, int]) -> dict[str, str]:
        record: dict[str, str] = {}
        for field, index in columns.items():
            record[field] = cells[index].strip() if index < len(cells) else ""
        return record

    @classmethod
    def _split_candidate_names(cls, raw_value: Any) -> list[str]:
        value = cls._clean_candidate_name(raw_value)
        if not value:
            return []
        pieces = re.split(r"[、，,；;]+", value)
        names: list[str] = []
        for piece in pieces:
            name = cls._clean_candidate_name(piece)
            if name and not is_obvious_non_person_candidate_name(name):
                names.append(name)
        return names

    @staticmethod
    def _clean_candidate_name(raw_value: Any) -> str:
        value = "" if raw_value is None else str(raw_value)
        value = re.sub(r"\s+", " ", value).strip()
        if not value:
            return ""
        if re.search(r"[:：]\s*[A-Za-z0-9]", value):
            value = re.split(r"[:：]", value, maxsplit=1)[0]
        value = re.sub(r"[\(（][^()（）]*(学号|编号|ID|id)[^()（）]*[\)）]", "", value)
        value = re.sub(r"(同学|学生)$", "", value).strip()
        return value

    @staticmethod
    def _is_archive_url(url: str) -> bool:
        return url.lower().split("?", 1)[0].endswith((".rar", ".zip"))

    @staticmethod
    def _extract_archive_pdf_texts(archive_bytes: bytes) -> list[tuple[str, str]]:
        if not shutil.which("bsdtar"):
            raise RuntimeError("bsdtar is required to extract Lanqiao archive files")

        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("pypdf is required to parse Lanqiao PDF files") from exc

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            archive_path = tmp_path / "lanqiao_archive"
            extract_dir = tmp_path / "extract"
            extract_dir.mkdir()
            archive_path.write_bytes(archive_bytes)
            subprocess.run(
                ["bsdtar", "-xf", str(archive_path), "-C", str(extract_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

            pdf_texts: list[tuple[str, str]] = []
            for pdf_path in sorted(extract_dir.rglob("*.pdf")):
                reader = PdfReader(str(pdf_path))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
                pdf_texts.append((str(pdf_path.relative_to(extract_dir)), text))
            return pdf_texts

    @classmethod
    def _parse_lanqiao_pdf_text(
        cls,
        text: str,
        *,
        subject_name: str,
    ) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for line in cls._merge_lanqiao_pdf_lines(text):
            record = cls._parse_lanqiao_pdf_record_line(line, subject_name=subject_name)
            if record:
                records.append(record)
        return records

    @staticmethod
    def _merge_lanqiao_pdf_lines(text: str) -> list[str]:
        lines: list[str] = []
        pending = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if pending:
                pending = f"{pending} {line}"
                if _LANQIAO_AWARD_RE.search(line):
                    lines.append(pending)
                    pending = ""
                continue
            if not re.match(r"^\d{6,}\b", line):
                continue
            if _LANQIAO_AWARD_RE.search(line):
                lines.append(line)
            else:
                pending = line
        if pending:
            lines.append(pending)
        return lines

    @classmethod
    def _parse_lanqiao_pdf_record_line(
        cls,
        line: str,
        *,
        subject_name: str,
    ) -> dict[str, str] | None:
        match = _LANQIAO_LINE_RE.match(line.strip())
        if not match:
            return None

        tokens = match.group("body").split()
        subject_key = cls._normalize_lanqiao_subject(subject_name)
        for subject_start in range(1, len(tokens)):
            suffix = cls._normalize_lanqiao_subject("".join(tokens[subject_start:]))
            if suffix != subject_key:
                continue
            if subject_start < 2:
                return None
            return {
                "exam_no": match.group("exam_no"),
                "university": "".join(tokens[: subject_start - 1]),
                "candidate_name": tokens[subject_start - 1],
                "subject": " ".join(tokens[subject_start:]),
                "award_level": match.group("award"),
            }
        return None

    @staticmethod
    def _lanqiao_subject_from_pdf_path(pdf_path: str) -> str:
        stem = Path(pdf_path).stem
        stem = re.sub(r"^(软件赛|电子赛)-", "", stem)
        stem = stem.replace("总决赛获奖名单", "")
        return stem.replace("CC++", "C/C++")

    @staticmethod
    def _normalize_lanqiao_subject(value: str) -> str:
        return re.sub(r"[\s/]+", "", value or "")

    def _history_competition_matches(self, competition: dict[str, Any]) -> bool:
        target_name = self._clean(self.config.get("history_name"))
        prefix = self._clean(self.config.get("history_name_prefix"))
        competition_name = self._clean(competition.get("name"))
        if target_name and competition_name == target_name:
            return True
        if prefix and competition_name.startswith(prefix):
            return True
        return False

    @staticmethod
    def _resolve_local_results_path(raw_path: Any) -> Path | None:
        if raw_path in ("", None):
            return None
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = BASE_DIR / path
        return path if path.exists() else None

    @staticmethod
    def _casp_award_level(rank: int) -> str:
        if rank == 1:
            return "Gold Medal / Top Performer"
        if rank <= 3:
            return "Silver Medal / Top 3"
        if rank <= 10:
            return "Bronze Medal / Top 10"
        if rank <= 20:
            return "Top 20"
        return "Participant"

    @staticmethod
    def _infer_competition_institution(team_name: str) -> str:
        hints = {
            "AlphaFold": "DeepMind",
            "BAKER": "University of Washington",
            "Zhang": "University of Michigan",
            "MULTICOM": "University of Missouri",
            "McGuffin": "University of Reading",
            "Elofsson": "Stockholm University",
            "Kiharalab": "University of Kansas",
            "ShanghaiTech": "ShanghaiTech University",
            "Gonglab-THU": "Tsinghua University",
            "BeijingAIProtein": "Beijing AI Protein",
            "Yang": "Yang Lab",
            "UM-TBM": "University of Michigan",
            "PEZY": "PEZY Computing",
            "RaptorX": "RaptorX",
            "ColabFold": "Google/Colab",
            "FEIG": "Michigan State University",
            "MESHI": "Weizmann Institute",
            "Wallner": "Stockholm University",
            "Venclovas": "Vilnius University",
        }
        for token, institution in hints.items():
            if token.lower() in team_name.lower():
                return institution
        return ""

    @staticmethod
    def _infer_competition_country(team_name: str) -> str:
        hints = {
            "ShanghaiTech": "China",
            "Tsinghua": "China",
            "Beijing": "China",
            "Gonglab": "China",
            "Yang": "China",
            "PEZY": "Japan",
            "Kiharalab": "USA",
            "BAKER": "USA",
            "Zhang": "USA",
            "DeepMind": "UK",
            "AlphaFold": "UK",
            "Stockholm": "Sweden",
            "Elofsson": "Sweden",
            "Wallner": "Sweden",
            "Reading": "UK",
            "McGuffin": "UK",
            "Michigan": "USA",
            "Missouri": "USA",
            "Vilnius": "Lithuania",
            "Weizmann": "Israel",
        }
        for token, country in hints.items():
            if token.lower() in team_name.lower():
                return country
        return ""
