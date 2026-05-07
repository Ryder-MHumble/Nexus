"""JMLR paper crawler for the paper warehouse."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.http_client import fetch_page

logger = logging.getLogger(__name__)

BASE = "https://www.jmlr.org"


class JMLRPapersCrawler(BaseCrawler):
    """Fetch JMLR index pages and map rows to paper warehouse items."""

    async def fetch_and_parse(self) -> list[CrawledItem]:
        items: list[CrawledItem] = []
        max_items = int(self.config.get("max_items") or 0)
        for cfg in self._iter_year_configs():
            remaining = max_items - len(items) if max_items > 0 else None
            if remaining is not None and remaining <= 0:
                break
            items.extend(await self._fetch_single_year(cfg, remaining=remaining))
        return items[:max_items] if max_items > 0 else items

    def _iter_year_configs(self) -> list[dict[str, Any]]:
        raw = self.config.get("year_configs")
        if isinstance(raw, list) and raw:
            return [{**self.config, **item} for item in raw if isinstance(item, dict)]
        return [self.config]

    async def _fetch_single_year(
        self,
        cfg: dict[str, Any],
        *,
        remaining: int | None = None,
    ) -> list[CrawledItem]:
        year = int(cfg["year"])
        volume = int(cfg.get("volume") or year - 1999)
        list_url = str(cfg.get("url") or f"{BASE}/papers/v{volume}/")
        logger.info("[%s] fetching %s", self.source_id, list_url)
        html = await fetch_page(
            list_url,
            timeout=float(cfg.get("request_timeout") or 45),
            max_retries=int(cfg.get("max_retries") or 3),
            request_delay=float(cfg.get("request_delay") or 0.2),
        )
        rows = self._parse_rows(html, volume=volume)
        if remaining is not None:
            rows = rows[:remaining]
        logger.info("[%s] parsed %d JMLR rows for %s", self.source_id, len(rows), year)

        items: list[CrawledItem] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            detail = {}
            if cfg.get("fetch_abstracts", True) and row.get("detail_url"):
                detail = await self._fetch_detail(row["detail_url"], cfg)

            title = str(detail.get("title") or row["title"]).strip()
            authors = detail.get("authors") or row["authors"]
            abstract = str(detail.get("abstract") or "").strip() or None
            pdf_url = str(detail.get("pdf_url") or row.get("pdf_url") or "").strip() or None
            published_at = self._published_at(detail.get("publication_date"), year)
            raw_id = row["raw_id"]
            paper_id = f"jmlr:{raw_id}"
            authors_data = [
                {
                    "paper_id": paper_id,
                    "author_order": idx + 1,
                    "name_raw": author,
                    "name_normalized": author,
                    "source_author_id": None,
                    "author_url": None,
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
                "source": "jmlr",
                "raw_id": raw_id,
                "venue": cfg.get("venue", "JMLR"),
                "venue_full": cfg.get("venue_full", "Journal of Machine Learning Research"),
                "year": year,
                "track": cfg.get("track_label", "Journal Article"),
                "is_main_track": True,
                "is_workshop": False,
                "title": title,
                "abstract": abstract,
                "n_authors": len(authors),
                "url": row["detail_url"],
                "pdf_url": pdf_url,
                "doi": None,
                "arxiv_id": None,
                "scraped_at": now.isoformat(),
                "schema_version": "1.0",
            }
            items.append(
                CrawledItem(
                    title=title,
                    url=row["detail_url"],
                    published_at=published_at,
                    author=authors[0] if authors else None,
                    content=abstract,
                    source_id=self.source_id,
                    dimension=cfg.get("dimension", "paper"),
                    tags=[cfg.get("venue", "JMLR"), str(year), "journal"],
                    extra={"paper": paper_data, "authors": authors_data},
                )
            )
        return items

    async def _fetch_detail(self, detail_url: str, cfg: dict[str, Any]) -> dict[str, Any]:
        try:
            html = await fetch_page(
                detail_url,
                timeout=float(cfg.get("request_timeout") or 45),
                max_retries=int(cfg.get("max_retries") or 2),
                request_delay=float(cfg.get("request_delay") or 0.2),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] failed JMLR detail %s: %s", self.source_id, detail_url, exc)
            return {}
        soup = BeautifulSoup(html, "lxml")
        meta = _citation_meta(soup)
        abstract_el = soup.select_one("p.abstract, .abstract")
        return {
            "title": _first(meta, "citation_title"),
            "authors": meta.get("citation_author") or [],
            "publication_date": _first(meta, "citation_publication_date"),
            "pdf_url": _first(meta, "citation_pdf_url"),
            "abstract": abstract_el.get_text(" ", strip=True) if abstract_el else None,
        }

    @staticmethod
    def _parse_rows(html: str, *, volume: int) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        rows: list[dict[str, Any]] = []
        for dt in soup.select("dt"):
            if not isinstance(dt, Tag):
                continue
            title = dt.get_text(" ", strip=True)
            dd = dt.find_next_sibling("dd")
            if not title or not isinstance(dd, Tag):
                continue
            links = {
                a.get_text(" ", strip=True).lower(): urljoin(BASE, str(a.get("href") or ""))
                for a in dd.select("a[href]")
            }
            detail_url = links.get("abs")
            if not detail_url:
                continue
            raw_match = re.search(r"/papers/v\d+/([^/.]+)\.html$", detail_url)
            raw_token = (
                raw_match.group(1)
                if raw_match
                else detail_url.rstrip("/").rsplit("/", 1)[-1]
            )
            rows.append(
                {
                    "title": title,
                    "authors": _parse_authors(dd),
                    "detail_url": detail_url,
                    "pdf_url": links.get("pdf"),
                    "raw_id": f"v{volume}/{raw_token}",
                }
            )
        return rows

    @staticmethod
    def _published_at(value: Any, fallback_year: int) -> datetime:
        text = str(value or "").strip()
        year_match = re.search(r"\b(19|20)\d{2}\b", text)
        year = int(year_match.group(0)) if year_match else fallback_year
        return datetime(year, 1, 1, tzinfo=timezone.utc)


def _parse_authors(dd: Tag) -> list[str]:
    author_el = dd.select_one("b i")
    author_text = author_el.get_text(" ", strip=True) if author_el else dd.get_text(" ", strip=True)
    author_text = author_text.split(";", 1)[0]
    return [item.strip() for item in author_text.split(",") if item.strip()]


def _citation_meta(soup: BeautifulSoup) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for meta in soup.select("meta[name][content]"):
        name = str(meta.get("name") or "").strip()
        content = str(meta.get("content") or "").strip()
        if name and content:
            values.setdefault(name, []).append(content)
    return values


def _first(values: dict[str, list[str]], key: str) -> str | None:
    items = values.get(key) or []
    return items[0] if items else None
