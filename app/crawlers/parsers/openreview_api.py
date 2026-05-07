"""OpenReview API 爬虫 — api2.openreview.net

覆盖：ICLR / ICML / NeurIPS（2023+）+ 各 workshop
数据源：OpenReview API v2
特点：
- JSON API，支持大批量拉取
- 带 venueid + primary_area + keywords 等细粒度字段
- 接受/拒稿/撤稿状态可过滤

Venue ID 映射（YAML 里配置）：
    ICLR.cc/2024/Conference       → ICLR 2024 主会
    ICML.cc/2024/Conference       → ICML 2024
    NeurIPS.cc/2024/Conference    → NeurIPS 2024
    ICLR.cc/2024/Workshop/XXX     → workshop

⚠️ 限流：匿名 ~100 req/min。爬 note 列表用一次分页 API 即可（每页 1000 篇），
   所以一个 venue 只需 ~5-10 个 API 请求，极少触发限流。
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

try:
    from app.crawlers.base import BaseCrawler, CrawledItem
    from app.crawlers.utils.http_client import fetch_page
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from base import BaseCrawler, CrawledItem  # type: ignore

    async def fetch_page(url: str, timeout: float = 30.0, max_retries: int = 3) -> str:
        import httpx
        last_err = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    headers={"User-Agent": "Mozilla/5.0 (research data crawler)"},
                    follow_redirects=True,
                ) as client:
                    r = await client.get(url)
                    r.raise_for_status()
                    return r.text
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    # 429 退避更久
                    delay = 30 if "429" in str(e) else (2 ** attempt)
                    await asyncio.sleep(delay)
        raise last_err


logger = logging.getLogger(__name__)


class OpenReviewCrawler(BaseCrawler):
    """OpenReview venue 论文抓取。

    YAML 字段：
        id: iclr-2024
        crawler_class: openreview
        venue: ICLR
        year: 2024
        venue_id: ICLR.cc/2024/Conference       # OpenReview 系统内的 venue 标识
        api_version: 2                           # 1 或 2，默认 2
        track_label: Main Conference             # 展示名
        is_main_track: true
        is_workshop: false
        page_size: 1000                          # 每次请求论文数
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        for cfg in self._iter_year_configs():
            items.extend(await self._fetch_single_year(cfg))
        return items

    def _iter_year_configs(self) -> list[dict[str, Any]]:
        raw = self.config.get("year_configs")
        if isinstance(raw, list) and raw:
            return [{**self.config, **item} for item in raw if isinstance(item, dict)]
        return [self.config]

    async def _fetch_single_year(self, cfg: dict[str, Any]) -> list[CrawledItem]:
        if cfg.get("source_format") == "icml_virtual":
            return await self._fetch_icml_virtual_year(cfg)

        venue: str = cfg["venue"]
        year: int = int(cfg["year"])
        venue_id: str = cfg["venue_id"]
        api_version: int = int(cfg.get("api_version", 2))
        track_label: str = cfg.get("track_label", "Main Conference")
        is_main_track: bool = cfg.get("is_main_track", True)
        is_workshop: bool = cfg.get("is_workshop", False)
        page_size: int = int(cfg.get("page_size", 1000))

        api_host = "https://api2.openreview.net" if api_version == 2 else "https://api.openreview.net"

        # 翻页抓所有 notes
        all_notes: list[dict] = []
        offset = 0
        while True:
            url = (f"{api_host}/notes?"
                   f"content.venueid={venue_id}"
                   f"&limit={page_size}&offset={offset}")
            logger.info(f"[{self.source_id}] fetching offset={offset}")
            raw = await fetch_page(url, timeout=30.0, max_retries=4)
            data = json.loads(raw)
            notes = data.get("notes", [])
            if not notes:
                break
            all_notes.extend(notes)
            if len(notes) < page_size:
                break
            offset += page_size
            await asyncio.sleep(0.6)  # 礼貌间隔

        logger.info(f"[{self.source_id}] fetched {len(all_notes)} notes")

        now = datetime.now(timezone.utc)
        items: list[CrawledItem] = []

        for note in all_notes:
            try:
                item = self._note_to_item(
                    note, venue, year, venue_id, track_label,
                    is_main_track, is_workshop, api_version, now, cfg
                )
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning(f"  ⚠️ parse note {note.get('id')}: {e}")

        return items

    async def _fetch_icml_virtual_year(self, cfg: dict[str, Any]) -> list[CrawledItem]:
        venue: str = cfg["venue"]
        year: int = int(cfg["year"])
        data_url = str(cfg["data_url"])
        track_label: str = cfg.get("track_label", "Main Conference")

        raw = await fetch_page(data_url, timeout=60.0, max_retries=4)
        data = json.loads(raw)
        records = data.get("results", []) if isinstance(data, dict) else data
        if not isinstance(records, list):
            return []

        if cfg.get("max_items"):
            records = records[: int(cfg["max_items"])]

        now = datetime.now(timezone.utc)
        items: list[CrawledItem] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            item = self._icml_virtual_record_to_item(
                record,
                venue=venue,
                year=year,
                track_label=track_label,
                now=now,
                cfg=cfg,
            )
            if item:
                items.append(item)
        logger.info(f"[{self.source_id}] fetched {len(items)} ICML virtual records for {year}")
        return items

    @staticmethod
    def _icml_virtual_record_to_item(
        record: dict[str, Any],
        *,
        venue: str,
        year: int,
        track_label: str,
        now: datetime,
        cfg: dict[str, Any],
    ) -> CrawledItem | None:
        title = OpenReviewCrawler._clean_virtual_text(record.get("name"))
        if not title:
            return None

        openreview_url = OpenReviewCrawler._clean_virtual_text(record.get("paper_url")) or None
        openreview_id = OpenReviewCrawler._openreview_id_from_url(openreview_url)
        event_id = OpenReviewCrawler._clean_virtual_text(record.get("id"))
        raw_id = openreview_id or event_id
        paper_id = f"openreview:{openreview_id}" if openreview_id else f"icml_virtual:{year}:{event_id}"

        virtual_path = OpenReviewCrawler._clean_virtual_text(record.get("virtualsite_url"))
        detail_url = urljoin("https://icml.cc", virtual_path) if virtual_path else openreview_url
        pdf_url = OpenReviewCrawler._clean_virtual_text(record.get("paper_pdf_url")) or None
        if pdf_url:
            pdf_url = urljoin("https://icml.cc", pdf_url)

        authors_data = []
        authors = record.get("authors") if isinstance(record.get("authors"), list) else []
        for idx, author in enumerate(authors, start=1):
            if not isinstance(author, dict):
                continue
            name = OpenReviewCrawler._clean_virtual_text(author.get("fullname"))
            if not name:
                continue
            author_url = OpenReviewCrawler._clean_virtual_text(author.get("url")) or None
            if author_url:
                author_url = urljoin("https://icml.cc", author_url)
            authors_data.append(
                {
                    "paper_id": paper_id,
                    "author_order": idx,
                    "name_raw": name,
                    "name_normalized": name,
                    "source_author_id": OpenReviewCrawler._clean_virtual_text(author.get("id")) or None,
                    "author_url": author_url,
                    "affiliation": OpenReviewCrawler._clean_virtual_text(author.get("institution")) or None,
                    "affiliation_country": None,
                    "email": None,
                    "orcid": None,
                    "scraped_at": now.isoformat(),
                    "schema_version": "1.0",
                }
            )

        keywords = record.get("keywords") if isinstance(record.get("keywords"), list) else []
        event_type = (
            OpenReviewCrawler._clean_virtual_text(record.get("event_type"))
            or OpenReviewCrawler._clean_virtual_text(record.get("eventtype"))
            or None
        )
        paper_data = {
            "paper_id": paper_id,
            "source": "icml_virtual",
            "raw_id": raw_id,
            "venue": venue,
            "venue_full": cfg.get("venue_full"),
            "year": year,
            "track": track_label,
            "is_main_track": cfg.get("is_main_track", True),
            "is_workshop": cfg.get("is_workshop", False),
            "title": title,
            "abstract": OpenReviewCrawler._clean_virtual_text(record.get("abstract")) or None,
            "n_authors": len(authors_data),
            "url": detail_url,
            "pdf_url": pdf_url,
            "doi": None,
            "arxiv_id": None,
            "scraped_at": now.isoformat(),
            "schema_version": "1.0",
        }

        return CrawledItem(
            title=title,
            url=detail_url or openreview_url or "",
            published_at=datetime(year, 5, 5, tzinfo=timezone.utc),
            author=authors_data[0]["name_normalized"] if authors_data else None,
            source_id=cfg["id"],
            dimension=cfg.get("dimension", "academic_venues"),
            tags=[venue, str(year), track_label]
            + ([event_type] if event_type else [])
            + [str(item) for item in keywords if str(item).strip()],
            extra={
                "paper": paper_data,
                "authors": authors_data,
                "event_type": event_type,
                "openreview_url": openreview_url,
            },
        )

    @staticmethod
    def _clean_virtual_text(value: Any) -> str:
        return " ".join(unescape(str(value or "")).replace("\x00", " ").split()).strip()

    @staticmethod
    def _openreview_id_from_url(url: str | None) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        if "openreview.net" not in parsed.netloc:
            return None
        note_id = (parse_qs(parsed.query).get("id") or [""])[0].strip()
        return note_id or None

    @staticmethod
    def _note_to_item(
        note: dict, venue: str, year: int, venue_id: str,
        track_label: str, is_main_track: bool, is_workshop: bool,
        api_version: int, now: datetime, cfg: dict,
    ) -> CrawledItem | None:
        """Convert OpenReview note JSON → CrawledItem."""

        def g(field: str):
            """API v2 的字段都包在 {value: X}，v1 直接拿。"""
            c = note.get("content", {})
            if api_version == 2:
                v = c.get(field) or {}
                return v.get("value") if isinstance(v, dict) else v
            return c.get(field)

        forum_id = note.get("forum") or note.get("id")
        title = g("title")
        if not title:
            return None
        title = str(title).strip()

        authors = g("authors") or []
        author_ids = g("authorids") or []
        # 规范化：authors 可能是逗号字符串
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",") if a.strip()]

        abstract = g("abstract") or ""
        keywords = g("keywords") or []
        primary_area = g("primary_area") or None
        pdf_path = g("pdf") or None

        paper_id = f"openreview:{forum_id}"
        detail_url = f"https://openreview.net/forum?id={forum_id}"
        pdf_url = f"https://openreview.net/pdf?id={forum_id}" if pdf_path else None

        authors_data = []
        for idx, (name, aid) in enumerate(zip(authors, author_ids or [None] * len(authors))):
            authors_data.append({
                "paper_id": paper_id,
                "author_order": idx + 1,
                "name_raw": name,
                "name_normalized": name,
                "source_author_id": aid,  # OpenReview profile id 如 ~Zhang_Wei1
                "author_url": f"https://openreview.net/profile?id={aid}" if aid else None,
                "affiliation": None,
                "affiliation_country": None,
                "email": None,
                "orcid": None,
                "scraped_at": now.isoformat(),
                "schema_version": "1.0",
            })

        paper_data = {
            "paper_id": paper_id,
            "source": "openreview",
            "raw_id": forum_id,
            "venue": venue,
            "venue_full": cfg.get("venue_full"),
            "year": year,
            "track": track_label,
            "is_main_track": is_main_track,
            "is_workshop": is_workshop,
            "title": title,
            "abstract": str(abstract).strip() if abstract else None,
            "n_authors": len(authors),
            "url": detail_url,
            "pdf_url": pdf_url,
            "doi": None,
            "arxiv_id": None,
            "scraped_at": now.isoformat(),
            "schema_version": "1.0",
        }

        return CrawledItem(
            title=title,
            url=detail_url,
            published_at=datetime(year, 5, 1, tzinfo=timezone.utc),
            author=authors[0] if authors else None,
            source_id=cfg["id"],
            dimension=cfg.get("dimension", "academic_venues"),
            tags=[venue, str(year), track_label]
                 + (keywords if isinstance(keywords, list) else []),
            extra={
                "paper": paper_data,
                "authors": authors_data,
                "primary_area": primary_area,
                "keywords": keywords,
            },
        )
