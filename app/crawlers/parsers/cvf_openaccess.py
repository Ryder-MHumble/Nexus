"""CVF Open Access 爬虫 — openaccess.thecvf.com

覆盖：CVPR / ICCV / WACV
数据源：https://openaccess.thecvf.com/{venue}{year}?day=all
特点：静态 HTML、结构稳定（<dt class="ptitle"> + <dd>authors</dd>）

⚠️ 不在 CVF Open Access 的会议：
- ECCV（在 ecva.net，独立 parser）
- CVPR Workshop 入口独立（/CVPR2024W），需单独 source

⚠️ Track 区分：
- CVF 列表页不区分 Oral/Highlight/Poster（要从 Session 页才有，成本高）
- 当前 parser 统一标为 "Main Conference"，track 精细化留给后续增强

⚠️ 接入基座：本文件搬到 `app/crawlers/parsers/cvf_openaccess.py`
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

try:
    from app.crawlers.base import BaseCrawler, CrawledItem
    from app.crawlers.utils.http_client import fetch_page
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from base import BaseCrawler, CrawledItem  # type: ignore

    async def fetch_page(url: str, timeout: float = 90.0, max_retries: int = 3) -> str:
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
                    await asyncio.sleep(3 ** attempt)
        raise last_err


logger = logging.getLogger(__name__)

BASE = "https://openaccess.thecvf.com"


_ARXIV_RE = re.compile(r'arxiv\.org/abs/(\d{4}\.\d{4,5})', re.I)


class CVFCrawler(BaseCrawler):
    """CVF Open Access 任意年 × 任意会议（CVPR/ICCV/WACV）。

    YAML 字段：
        id: cvpr-2024
        crawler_class: cvf_openaccess
        venue: CVPR
        year: 2024
        is_workshop: false   # True 时 URL 后缀加 W
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
        venue: str = cfg["venue"]
        year: int = int(cfg["year"])
        is_workshop: bool = cfg.get("is_workshop", False)

        # URL 模式
        workshop_suffix = "W" if is_workshop else ""
        list_url = str(cfg.get("url") or f"{BASE}/{venue}{year}{workshop_suffix}?day=all")

        logger.info(f"[{self.source_id}] fetching {list_url}")
        html = await fetch_page(list_url, timeout=90.0, max_retries=3)

        rows = self._parse_rows(html)
        logger.info(f"[{self.source_id}] parsed {len(rows)} papers")

        now = datetime.now(timezone.utc)
        items: list[CrawledItem] = []

        for row in rows:
            href = row["href"]
            title = row["title"]
            authors_list = row["authors"]
            link_hrefs = row["link_hrefs"]

            # 完整 URL
            detail_url = href if href.startswith('http') else f"{BASE}/{href}"

            # raw_id：从 href 抽 paper hash
            # content/CVPR2024/html/Author_Title_CVPR_2024_paper.html
            raw_id_m = re.search(r'/html/([^/]+)_paper\.html', href)
            raw_id = f"{venue}{year}/{raw_id_m.group(1)}" if raw_id_m else href
            paper_id = f"cvf:{raw_id}"

            # PDF
            pdf_url = next(
                (self._absolutize(link) for link in link_hrefs if link.lower().endswith(".pdf") and "supplemental/" not in link.lower()),
                None,
            )
            # arXiv
            arxiv_id = next(
                (m.group(1) for link in link_hrefs if (m := _ARXIV_RE.search(link))),
                None,
            )
            authors_data = [
                {
                    "paper_id": paper_id,
                    "author_order": idx + 1,
                    "name_raw": a,
                    "name_normalized": a,
                    "source_author_id": None,
                    "author_url": None,
                    "affiliation": None,
                    "affiliation_country": None,
                    "email": None,
                    "orcid": None,
                    "scraped_at": now.isoformat(),
                    "schema_version": "1.0",
                }
                for idx, a in enumerate(authors_list)
            ]

            # Track 标注
            if is_workshop:
                track_label = "Workshop"
                is_main_track = False
            else:
                track_label = "Main Conference"
                is_main_track = True

            paper_data = {
                "paper_id": paper_id,
                "source": "cvf",
                "raw_id": raw_id,
                "venue": venue,
                "venue_full": _VENUE_FULL.get(venue, venue),
                "year": year,
                "track": track_label,
                "is_main_track": is_main_track,
                "is_workshop": is_workshop,
                "title": title,
                "abstract": None,
                "n_authors": len(authors_list),
                "url": detail_url,
                "pdf_url": pdf_url,
                "doi": None,
                "arxiv_id": arxiv_id,
                "scraped_at": now.isoformat(),
                "schema_version": "1.0",
            }

            items.append(CrawledItem(
                title=title,
                url=detail_url,
                published_at=datetime(year, 6, 1, tzinfo=timezone.utc),  # CVPR 6月，ICCV 10月，WACV 1月
                author=authors_list[0] if authors_list else None,
                source_id=self.source_id,
                dimension=cfg.get("dimension", "academic_venues"),
                tags=[venue, str(year), track_label],
                extra={"paper": paper_data, "authors": authors_data},
            ))

        return items

    @staticmethod
    def _absolutize(href: str) -> str:
        if href.startswith("http"):
            return href
        return f"{BASE}/{href.lstrip('/')}"

    @classmethod
    def _parse_rows(cls, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        rows: list[dict[str, Any]] = []
        for dt in soup.select("dt.ptitle"):
            if not isinstance(dt, Tag):
                continue
            link = dt.find("a", href=True)
            if link is None:
                continue
            href = str(link.get("href") or "").strip()
            title = link.get_text(" ", strip=True)
            if not href or not title:
                continue

            authors_dd = dt.find_next_sibling("dd")
            links_dd = authors_dd.find_next_sibling("dd") if isinstance(authors_dd, Tag) else None
            author_links = authors_dd.select("a") if isinstance(authors_dd, Tag) else []
            if author_links:
                authors = [a.get_text(" ", strip=True) for a in author_links if a.get_text(" ", strip=True)]
            else:
                author_text = authors_dd.get_text(", ", strip=True) if isinstance(authors_dd, Tag) else ""
                authors = [token.strip() for token in author_text.split(",") if token.strip()]

            link_hrefs = []
            if isinstance(links_dd, Tag):
                for anchor in links_dd.select("a[href]"):
                    href_value = str(anchor.get("href") or "").strip()
                    if href_value:
                        link_hrefs.append(href_value)

            rows.append(
                {
                    "href": href.lstrip("/"),
                    "title": title,
                    "authors": authors,
                    "link_hrefs": link_hrefs,
                }
            )
        return rows


_VENUE_FULL = {
    "CVPR": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
    "ICCV": "IEEE/CVF International Conference on Computer Vision",
    "WACV": "IEEE/CVF Winter Conference on Applications of Computer Vision",
}
