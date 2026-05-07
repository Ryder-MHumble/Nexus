"""ECVA Papers 爬虫 — ecva.net/papers.php

覆盖：ECCV（European Conference on Computer Vision，双年会议：2018/2020/2022/2024/...）
数据源：ECVA 官方论文汇总页（全部年份在同一个 HTML 里，约 3.6MB）
特点：单页含全年份，用 <button class="accordion">ECCV YYYY Papers</button> 分块；
     页面结构：<dt class="ptitle"><a href=...>TITLE</a></dt><dd>author1, author2...</dd>；
     无机构信息 → affiliation 留空，走后续 OpenAlex enrichment；
     * 作者名末尾的 '*' 表示 corresponding author，我们剥掉只保留名字。

⚠️ 接入基座时：本文件搬到 `app/crawlers/parsers/ecva_papers.py`，
   修改 import：`from app.crawlers.base import BaseCrawler, CrawledItem`

优化：同一 URL 的 HTML 在 class 级缓存，多个 year source 并行跑时只下载一次。

YAML 配置字段（见 sources/academic_venues/ecva.yaml）：
    id: eccv-2024
    venue: ECCV
    year: 2024
    track_label: Main Conference
    is_main_track: true
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

ECVA_BASE = "https://www.ecva.net"
ECVA_PAPERS_URL = f"{ECVA_BASE}/papers.php"

# ECVA 页面结构：
#   <button class="accordion" ...>
#           ECCV 2024 Papers
#   </button>
#   <div class="accordion-content">
#     <div id="content"> <dl>
#       <dt class="ptitle"><br>
#         <a href=papers/eccv_2024/...>Title</a>
#       </dt>
#       <dd>Author A, Author B*, Author C</dd>
#       <dd>[<a href='papers/...00001.pdf'>pdf</a>] ...</dd>
#     ...
# 定位 accordion button 的年份（不试图用正则匹配配对的 </div>，因为内部有多层嵌套）。
# 切块策略：用 _YEAR_BUTTON_START_RE 找到各 button 的位置，
# 每年的内容 = 当前 button 结束 ~ 下一个 button 开始。
_YEAR_BUTTON_START_RE = re.compile(
    r'<button\s+class="accordion"[^>]*>\s*ECCV\s+(?P<year>\d{4})\s+Papers\s*</button>',
    re.IGNORECASE,
)

# 每篇论文：一个 <dt class="ptitle"> 紧跟着一个或多个 <dd>。
# 第 1 个 dd = 作者；第 2 个 dd = pdf/supplementary/DOI 链接。
_PAPER_RE = re.compile(
    r'<dt\s+class="ptitle">.*?'
    r'<a\s+href=(?P<href>[^\s>]+)\s*>\s*(?P<title>.*?)\s*</a>\s*</dt>\s*'
    r'<dd>\s*(?P<authors>.*?)\s*</dd>\s*'
    r'(?P<links><dd>.*?</dd>)?',
    re.DOTALL | re.IGNORECASE,
)

_TAG_RE = re.compile(r'<[^>]+>')
_HREF_RE = re.compile(r"""href=['"]?([^'"\s>]+)""", re.IGNORECASE)


class ECVACrawler(BaseCrawler):
    """拉取 ECCV 某一届（一年）的全部论文。

    一个 YAML 源 = 一届。多届共享同一份 HTML 抓取（class-level 缓存）。
    """

    # class-level HTML 缓存：同一进程内多个实例共享一次下载
    _html_cache: Optional[str] = None
    _html_fetch_lock: asyncio.Lock = asyncio.Lock()

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
        venue: str = cfg.get("venue", "ECCV")
        year: int = int(cfg["year"])
        track_label: str = cfg.get("track_label", "Main Conference")
        is_main_track: bool = cfg.get("is_main_track", True)
        is_workshop: bool = cfg.get("is_workshop", False)

        html = await self._get_full_html()
        year_body = self._extract_year_block(html, year)
        if year_body is None:
            logger.warning(f"[{self.source_id}] 页面中未找到 ECCV {year} Papers 块；可能该年未召开（ECCV 是双年会）")
            return []

        rows = self._parse_year_block(year_body, year)
        logger.info(f"[{self.source_id}] parsed {len(rows)} papers for ECCV {year}")

        now = datetime.now(timezone.utc)
        items: list[CrawledItem] = []
        for row in rows:
            raw_id = row["raw_id"]
            paper_id = f"ecva:{raw_id}"
            authors = row["authors"]

            item = CrawledItem(
                title=row["title"],
                url=row["detail_url"],
                # ECCV 一般 9-10 月召开；给个合理的默认日期
                published_at=datetime(year, 10, 1, tzinfo=timezone.utc),
                author=authors[0]["name_normalized"] if authors else None,
                source_id=self.source_id,
                dimension=cfg.get("dimension", "academic_venues"),
                tags=[venue, str(year), track_label],
                extra={
                    "paper": {
                        "paper_id": paper_id,
                        "source": "ecva",
                        "raw_id": raw_id,
                        "venue": venue,
                        "venue_full": "European Conference on Computer Vision",
                        "year": year,
                        "track": track_label,
                        "is_main_track": is_main_track,
                        "is_workshop": is_workshop,
                        "title": row["title"],
                        "abstract": None,
                        "n_authors": len(authors),
                        "url": row["detail_url"],
                        "pdf_url": row["pdf_url"],
                        "doi": row["doi"],
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
                            "affiliation": None,   # ECVA 页面不含机构，走 OpenAlex enrichment
                            "affiliation_country": None,
                            "email": None,
                            "orcid": None,
                            "scraped_at": now.isoformat(),
                            "schema_version": "1.0",
                        }
                        for idx, a in enumerate(authors)
                    ],
                    "is_corresponding": [a.get("is_corresponding", False) for a in authors],
                    "supp_url": row["supp_url"],
                },
            )
            items.append(item)

        return items

    # ------------------------------------------------------------------ #
    # 页面缓存（同一进程多 year source 共享一次下载）
    # ------------------------------------------------------------------ #

    @classmethod
    async def _get_full_html(cls) -> str:
        if cls._html_cache is not None:
            return cls._html_cache
        async with cls._html_fetch_lock:
            if cls._html_cache is None:
                logger.info(f"fetching ECVA full HTML: {ECVA_PAPERS_URL}")
                cls._html_cache = await fetch_page(ECVA_PAPERS_URL, timeout=90.0, max_retries=3)
                logger.info(f"ECVA HTML cached: {len(cls._html_cache):,} bytes")
            return cls._html_cache

    # ------------------------------------------------------------------ #
    # HTML 解析
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_year_block(html: str, year: int) -> Optional[str]:
        """按 button 位置切块：年 N 的内容 = button_N.end() ~ button_{N+1}.start()。

        这样不需要考虑 accordion-content 内 </div> 的嵌套配对。
        """
        matches = list(_YEAR_BUTTON_START_RE.finditer(html))
        if not matches:
            return None
        for i, m in enumerate(matches):
            if int(m.group("year")) != year:
                continue
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
            return html[start:end]
        return None

    @classmethod
    def _parse_year_block(cls, body: str, year: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in _PAPER_RE.finditer(body):
            href = m.group("href").strip().strip('"').strip("'")
            title = cls._clean_text(m.group("title"))
            authors_raw = cls._clean_text(m.group("authors"))
            links_html = m.group("links") or ""

            # detail URL 示例：papers/eccv_2024/papers_ECCV/html/4_ECCV_2024_paper.php
            detail_url = cls._absolutize(href)

            # raw_id 从 detail URL 提取数字编号：4_ECCV_2024 → "2024/4"
            rid_match = re.search(r'html/(\d+)_ECCV_(\d{4})_paper\.php', href, re.IGNORECASE)
            if rid_match:
                raw_id = f"{rid_match.group(2)}/{rid_match.group(1)}"
            else:
                raw_id = f"{year}/{href}"  # fallback

            # 从第二个 dd 里抽 PDF / supp / DOI
            pdf_url, supp_url, doi = None, None, None
            for link in _HREF_RE.findall(links_html):
                link_s = link.strip('"').strip("'")
                if '-supp.pdf' in link_s.lower() or 'supplementary' in link_s.lower():
                    supp_url = cls._absolutize(link_s)
                elif link_s.lower().endswith('.pdf'):
                    pdf_url = cls._absolutize(link_s)
                elif 'doi.org' in link_s.lower() or 'link.springer.com' in link_s.lower():
                    doi = link_s

            authors = cls._split_authors(authors_raw)
            out.append({
                "raw_id": raw_id,
                "title": title,
                "authors": authors,
                "detail_url": detail_url,
                "pdf_url": pdf_url,
                "supp_url": supp_url,
                "doi": doi,
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
            return f"{ECVA_BASE}{href}"
        # ECVA 相对路径（如 "papers/eccv_2024/..."）都是相对于 papers.php 的同级目录
        return f"{ECVA_BASE}/{href.lstrip('./')}"

    @staticmethod
    def _split_authors(raw: str) -> list[dict[str, Any]]:
        """ECVA 作者格式：'First Last, First Last*, First Last'，'*' = corresponding。"""
        if not raw:
            return []
        parts = [a.strip() for a in raw.split(",") if a.strip()]
        authors = []
        for p in parts:
            is_corr = p.endswith("*")
            name = p.rstrip("*").strip()
            authors.append({
                "name_raw": p,
                "name_normalized": name,
                "is_corresponding": is_corr,
            })
        return authors
