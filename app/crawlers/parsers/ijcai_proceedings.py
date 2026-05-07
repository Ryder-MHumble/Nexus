"""IJCAI Proceedings 爬虫 — ijcai.org/proceedings/{year}/

覆盖：IJCAI（International Joint Conference on Artificial Intelligence）
数据源：IJCAI 官方 proceedings HTML（每年一页，内嵌全量论文列表）
特点：HTML 结构干净，单页含全部 track（Main / Survey / Journal / Demo / ...）；
     无机构信息 → affiliation 留空，走后续 OpenAlex enrichment。

⚠️ 接入基座时：本文件搬到 `app/crawlers/parsers/ijcai_proceedings.py`，
   修改 import：`from app.crawlers.base import BaseCrawler, CrawledItem`

YAML 配置字段（见 sources/academic_venues/ijcai.yaml）：
    id: ijcai-2024-main
    venue: IJCAI
    year: 2024
    track_filter: ["Main Track"]        # 留空=全部 track；严格口径默认只要 Main Track
    track_label: Main Track             # 入库时用作 track 字段
    is_main_track: true
    is_workshop: false
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Optional

try:
    from app.crawlers.base import BaseCrawler, CrawledItem
    from app.crawlers.utils.http_client import fetch_page
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from base import BaseCrawler, CrawledItem  # type: ignore

    async def fetch_page(url: str, timeout: float = 30.0, max_retries: int = 2) -> str:
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
                    await asyncio.sleep(2 ** attempt)
        raise last_err


logger = logging.getLogger(__name__)

IJCAI_BASE = "https://www.ijcai.org"

# 页面片段正则（IJCAI 页面 DOM 极规整，一次性扫全部块）
# 每个 section 形如：
#   <div class="section" id="sectionN">
#     <div class="section_title"><h3>Main Track</h3></div>
#     <div class="subsection" ...>                        # 领域分组（无关）
#       <div id="paperK" class="paper_wrapper">
#         <div class="title">...</div>
#         <div class="authors">A, B, C</div>
#         <div class="details">(<a href="0001.pdf">PDF</a> | <a href="/proceedings/2024/1">Details</a>)</div>
#       </div>
#       ...
# 策略：按 section div 切块，每块内部用 paper 正则扫。
_SECTION_RE = re.compile(
    r'<div\s+class="section"\s+id="section\d+">'
    r'\s*<div\s+class="section_title">\s*<h3>(?P<track>.*?)</h3>\s*</div>'
    r'(?P<body>.*?)'
    r'(?=<div\s+class="section"\s+id="section\d+">|</section>|\Z)',
    re.DOTALL | re.IGNORECASE,
)

_PAPER_RE = re.compile(
    r'<div\s+id="paper(?P<pid>\d+)"\s+class="paper_wrapper">\s*'
    r'<div\s+class="title">(?P<title>.*?)</div>\s*'
    r'<div\s+class="authors">(?P<authors>.*?)</div>\s*'
    r'<div\s+class="details">(?P<details>.*?)</div>\s*</div>',
    re.DOTALL | re.IGNORECASE,
)

_TAG_RE = re.compile(r'<[^>]+>')
_DETAILS_HREF_RE = re.compile(r'href="([^"]+)"')


class IJCAIProceedingsCrawler(BaseCrawler):
    """拉取 IJCAI 某年 proceedings 页面的全部论文。

    一个 YAML 源 = 一届（一年）。Track 通过 track_filter 在后处理过滤。
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
        venue: str = cfg.get("venue", "IJCAI")
        year: int = int(cfg["year"])
        track_filter: list[str] = cfg.get("track_filter") or []
        track_label: str = cfg.get("track_label", "Main Track")
        is_main_track: bool = cfg.get("is_main_track", True)
        is_workshop: bool = cfg.get("is_workshop", False)

        url = f"{IJCAI_BASE}/proceedings/{year}/"
        logger.info(f"[{self.source_id}] fetching {url}")
        html = await fetch_page(url, timeout=60.0, max_retries=3)

        parsed = self._parse_page(html, track_filter, year)
        logger.info(f"[{self.source_id}] parsed {len(parsed)} papers across filtered tracks")

        now = datetime.now(timezone.utc)
        items: list[CrawledItem] = []
        for row in parsed:
            pid = row["pid"]
            raw_id = f"{year}/{pid}"
            paper_id = f"ijcai:{raw_id}"
            authors = row["authors"]
            details_url = row["details_url"]
            pdf_url = row["pdf_url"]

            # 默认所有通过 filter 的论文打 track_label；
            # 若 YAML 未指定 track_filter，则用页面里的原始 section title 做 track。
            effective_track = track_label if track_filter else row["section"]

            item = CrawledItem(
                title=row["title"],
                url=details_url or f"{IJCAI_BASE}/proceedings/{year}/",
                published_at=datetime(year, 8, 1, tzinfo=timezone.utc),  # IJCAI 固定 8 月
                author=authors[0]["name_normalized"] if authors else None,
                source_id=self.source_id,
                dimension=cfg.get("dimension", "academic_venues"),
                tags=[venue, str(year), effective_track],
                extra={
                    "paper": {
                        "paper_id": paper_id,
                        "source": "ijcai",
                        "raw_id": raw_id,
                        "venue": venue,
                        "venue_full": "International Joint Conference on Artificial Intelligence",
                        "year": year,
                        "track": effective_track,
                        "is_main_track": is_main_track,
                        "is_workshop": is_workshop,
                        "title": row["title"],
                        "abstract": None,
                        "n_authors": len(authors),
                        "url": details_url,
                        "pdf_url": pdf_url,
                        "doi": None,
                        "arxiv_id": None,
                        "scraped_at": now.isoformat(),
                        "schema_version": "1.0",
                    },
                    "authors": [
                        {
                            "paper_id": paper_id,
                            "author_order": idx + 1,
                            "name_raw": a["name_raw"],
                            "name_normalized": a["name_normalized"],
                            "source_author_id": None,
                            "author_url": None,
                            "affiliation": None,       # IJCAI 页面不含机构，走 OpenAlex enrichment
                            "affiliation_country": None,
                            "email": None,
                            "orcid": None,
                            "scraped_at": now.isoformat(),
                            "schema_version": "1.0",
                        }
                        for idx, a in enumerate(authors)
                    ],
                    "section_title": row["section"],
                },
            )
            items.append(item)

        return items

    # ------------------------------------------------------------------ #
    # HTML 解析
    # ------------------------------------------------------------------ #

    @classmethod
    def _parse_page(cls, html: str, track_filter: list[str], year: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for sec in _SECTION_RE.finditer(html):
            section = cls._strip_html(sec.group("track")).strip()
            if track_filter and not any(tf.lower() in section.lower() for tf in track_filter):
                continue
            body = sec.group("body")
            for m in _PAPER_RE.finditer(body):
                pid = m.group("pid")
                title = cls._clean_text(m.group("title"))
                authors_raw = cls._clean_text(m.group("authors"))
                details_html = m.group("details")

                # details 里找两个链接：PDF + Details 页
                hrefs = _DETAILS_HREF_RE.findall(details_html)
                pdf_url = None
                details_url = None
                for h in hrefs:
                    if h.lower().endswith(".pdf"):
                        pdf_url = cls._absolutize_pdf(h, year)
                    elif "/proceedings/" in h:
                        details_url = cls._absolutize(h)

                authors = cls._split_authors(authors_raw)
                out.append({
                    "pid": pid,
                    "section": section,
                    "title": title,
                    "authors": authors,
                    "pdf_url": pdf_url,
                    "details_url": details_url,
                })
        return out

    # ------------------------------------------------------------------ #

    @staticmethod
    def _strip_html(s: str) -> str:
        return _TAG_RE.sub("", s)

    @classmethod
    def _clean_text(cls, s: str) -> str:
        s = cls._strip_html(s)
        s = unescape(s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    @staticmethod
    def _absolutize(href: str) -> str:
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return f"{IJCAI_BASE}{href}"
        return href

    @staticmethod
    def _absolutize_pdf(href: str, year: int) -> str:
        """PDF 链接形如 '0001.pdf'（相对当前 proceedings 目录）→ 补完整 URL。"""
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return f"{IJCAI_BASE}{href}"
        return f"{IJCAI_BASE}/proceedings/{year}/{href}"

    @staticmethod
    def _split_authors(raw: str) -> list[dict[str, str]]:
        """IJCAI 作者是 'First Last, First Last, First Last' 格式（逗号分隔）。"""
        if not raw:
            return []
        parts = [a.strip() for a in raw.split(",") if a.strip()]
        authors = []
        for p in parts:
            # 去末尾的 '*'（corresponding author 标记）
            name = p.rstrip("*").strip()
            authors.append({"name_raw": p, "name_normalized": name})
        return authors
