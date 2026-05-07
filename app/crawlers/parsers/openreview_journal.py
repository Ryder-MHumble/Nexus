"""OpenReview journal crawler for rolling venues such as TMLR."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.http_client import fetch_page

logger = logging.getLogger(__name__)

API_HOST = "https://api2.openreview.net"


class OpenReviewJournalCrawler(BaseCrawler):
    """Fetch accepted OpenReview journal notes and filter them by publication year."""

    async def fetch_and_parse(self) -> list[CrawledItem]:
        years = self._years()
        if not years:
            return []
        min_year = min(years)
        page_size = int(self.config.get("page_size") or 1000)
        max_pages = int(self.config.get("max_pages") or 20)
        offset = 0
        notes: list[dict[str, Any]] = []
        for page in range(max_pages):
            url = self._notes_url(limit=page_size, offset=offset)
            logger.info("[%s] fetching OpenReview journal offset=%d", self.source_id, offset)
            raw = await fetch_page(
                url,
                timeout=float(self.config.get("request_timeout") or 30),
                max_retries=int(self.config.get("max_retries") or 4),
                request_delay=float(self.config.get("request_delay") or 0.6),
            )
            batch = json.loads(raw).get("notes") or []
            if not batch:
                break
            notes.extend(note for note in batch if self._note_year(note) in years)
            if any((self._note_year(note) or 9999) < min_year for note in batch):
                break
            if len(batch) < page_size:
                break
            offset += page_size
        max_items = int(self.config.get("max_items") or 0)
        if max_items > 0:
            notes = notes[:max_items]
        items: list[CrawledItem] = []
        for note in notes:
            item = self._note_to_item(note)
            if item is not None:
                items.append(item)
        return items

    def _years(self) -> set[int]:
        raw = self.config.get("year_configs")
        if isinstance(raw, list) and raw:
            return {
                int(item["year"])
                for item in raw
                if isinstance(item, dict) and item.get("year")
            }
        year = self.config.get("year")
        return {int(year)} if year else set()

    def _notes_url(self, *, limit: int, offset: int) -> str:
        params = {
            "content.venueid": str(self.config["venue_id"]),
            "limit": str(limit),
            "offset": str(offset),
            "sort": "pdate:desc",
        }
        return f"{API_HOST}/notes?{urlencode(params)}"

    @staticmethod
    def _note_year(note: dict[str, Any]) -> int | None:
        timestamp = note.get("pdate") or note.get("odate") or note.get("cdate")
        if not isinstance(timestamp, int):
            return None
        return datetime.fromtimestamp(timestamp / 1000, timezone.utc).year

    def _note_to_item(self, note: dict[str, Any]) -> CrawledItem | None:
        content = note.get("content") if isinstance(note.get("content"), dict) else {}

        def field(name: str) -> Any:
            value = content.get(name)
            if isinstance(value, dict):
                return value.get("value")
            return value

        title = str(field("title") or "").strip()
        if not title:
            return None
        forum_id = str(note.get("forum") or note.get("id") or "").strip()
        if not forum_id:
            return None
        authors = field("authors") or []
        if isinstance(authors, str):
            authors = [item.strip() for item in authors.split(",") if item.strip()]
        author_ids = field("authorids") or []
        if not isinstance(author_ids, list):
            author_ids = []
        year = self._note_year(note)
        if year is None:
            return None
        published_at = datetime.fromtimestamp(
            (note.get("pdate") or note.get("odate") or note.get("cdate")) / 1000,
            timezone.utc,
        )
        detail_url = f"https://openreview.net/forum?id={forum_id}"
        pdf_url = f"https://openreview.net/pdf?id={forum_id}" if field("pdf") else None
        paper_id = f"openreview:{self.config.get('venue', 'journal').lower()}:{forum_id}"
        now = datetime.now(timezone.utc)
        authors_data = [
            {
                "paper_id": paper_id,
                "author_order": idx + 1,
                "name_raw": author,
                "name_normalized": author,
                "source_author_id": author_ids[idx] if idx < len(author_ids) else None,
                "author_url": (
                    f"https://openreview.net/profile?id={author_ids[idx]}"
                    if idx < len(author_ids) and author_ids[idx]
                    else None
                ),
                "affiliation": None,
                "affiliation_country": None,
                "email": None,
                "orcid": None,
                "scraped_at": now.isoformat(),
                "schema_version": "1.0",
            }
            for idx, author in enumerate(authors)
        ]
        paper_data = {
            "paper_id": paper_id,
            "source": "openreview",
            "raw_id": forum_id,
            "venue": self.config.get("venue"),
            "venue_full": self.config.get("venue_full"),
            "year": year,
            "track": "Journal Article",
            "is_main_track": True,
            "is_workshop": False,
            "title": title,
            "abstract": str(field("abstract") or "").strip() or None,
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
            published_at=published_at,
            author=authors[0] if authors else None,
            content=paper_data["abstract"],
            source_id=self.source_id,
            dimension=self.config.get("dimension", "paper"),
            tags=[str(self.config.get("venue") or ""), str(year), "journal"],
            extra={"paper": paper_data, "authors": authors_data},
        )
