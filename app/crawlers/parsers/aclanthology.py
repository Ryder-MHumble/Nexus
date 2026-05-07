"""ACL Anthology 爬虫 — aclanthology.org

覆盖：ACL / EMNLP / NAACL / COLING / EACL（NLP 会议大集合）
数据源：官方 BibTeX 批量导出 `/volumes/{year}.{venue}-{track}.bib`
特点：结构化、开放、无限流、零 JS 渲染依赖

⚠️ 接入基座时：本文件搬到 `app/crawlers/parsers/aclanthology.py`，
   修改 import：`from app.crawlers.base import BaseCrawler, CrawledItem`

YAML 配置字段（见 sources/academic_venues/acl-*.yaml）：
    id: acl-2024-long
    venue: ACL
    year: 2024
    track: acl-long              # bib 卷 ID（去年份）
    track_label: Long Paper
    is_main_track: true
    is_workshop: false
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# 导入路径兼容本地 / 基座
try:
    from app.crawlers.base import BaseCrawler, CrawledItem
    from app.crawlers.utils.http_client import fetch_page
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from base import BaseCrawler, CrawledItem  # type: ignore

    async def fetch_page(url: str, timeout: float = 30.0, max_retries: int = 2) -> str:
        """本地 fallback：简单的 httpx 实现，接入基座后用基座的 fetch_page。"""
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

ANTHOLOGY_BASE = "https://aclanthology.org"


class ACLAnthologyCrawler(BaseCrawler):
    """拉取 ACL Anthology 某一卷（venue × year × track）的全部论文。

    一个 YAML 源 = 一卷。比如：
      - acl-2024-long   → 2024 ACL Long Papers
      - acl-2024-short  → 2024 ACL Short Papers
      - emnlp-2024-main → 2024 EMNLP Main

    原因：ACL 的卷之间差异大，拆开配置可灵活启停（比如禁用 Findings）。
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
        track: str = cfg["track"]                         # bib 卷 ID 后缀，如 "acl-long"
        track_label: str = cfg.get("track_label", track)  # 展示用，如 "Long Paper"
        is_main_track: bool = cfg.get("is_main_track", True)
        is_workshop: bool = cfg.get("is_workshop", False)

        bib_url = f"{ANTHOLOGY_BASE}/volumes/{year}.{track}.bib"
        logger.info(f"[{self.source_id}] fetching {bib_url}")
        bib_text = await fetch_page(bib_url, timeout=45.0, max_retries=3)

        entries = self._parse_bib(bib_text)
        logger.info(f"[{self.source_id}] parsed {len(entries)} entries")

        now = datetime.now(timezone.utc)
        items: list[CrawledItem] = []
        for e in entries:
            anthology_id = e["anthology_id"]
            if not anthology_id:
                continue  # 跳过无法识别的 proceedings 头条目

            paper_id = f"aclanthology:{anthology_id}"
            authors = e["authors"]

            # 构造 CrawledItem。
            # 核心论文字段填进 extra['paper']（对齐基座 schema）
            # 作者列表填进 extra['authors']（入库时由 service 拆表）
            item = CrawledItem(
                title=e["title"],
                url=e["url"],
                published_at=self._infer_published_at(year, e.get("month")),
                author=authors[0]["name_normalized"] if authors else None,
                source_id=self.source_id,
                dimension=cfg.get("dimension", "academic_venues"),
                tags=[venue, str(year), track_label],
                extra={
                    "paper": {
                        "paper_id": paper_id,
                        "source": "aclanthology",
                        "raw_id": anthology_id,
                        "venue": venue,
                        "venue_full": e.get("booktitle"),
                        "year": year,
                        "track": track_label,
                        "is_main_track": is_main_track,
                        "is_workshop": is_workshop,
                        "title": e["title"],
                        "abstract": None,  # Anthology 的 bib 不含 abstract
                        "n_authors": len(authors),
                        "url": e["url"],
                        "pdf_url": self._guess_pdf_url(anthology_id),
                        "doi": e.get("doi"),
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
                            "source_author_id": None,  # Anthology bib 不含作者 ID，detail HTML 有
                            "author_url": None,
                            "affiliation": None,
                            "affiliation_country": None,
                            "email": None,
                            "orcid": None,
                            "scraped_at": now.isoformat(),
                            "schema_version": "1.0",
                        }
                        for idx, a in enumerate(authors)
                    ],
                    "doi": e.get("doi"),
                    "pages": e.get("pages"),
                },
            )
            items.append(item)

        return items

    # ------------------------------------------------------------------ #
    # BibTeX 解析
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_bib(bib_text: str) -> list[dict[str, Any]]:
        """轻量 BibTeX 解析，足以处理 Anthology 的规范格式。

        返回每条 inproceedings entry 的字段字典。
        """
        entries = re.split(r'\n(?=@\w+\{)', bib_text)
        out: list[dict[str, Any]] = []

        def grab(field: str, text: str) -> str:
            m = re.search(rf'{field}\s*=\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
            return m.group(1).strip() if m else ""

        for entry in entries:
            if not entry.lstrip().startswith('@inproceedings'):
                continue
            title = grab('title', entry).replace('\n', ' ').strip()
            author_raw = grab('author', entry)
            url = grab('url', entry)
            doi = grab('doi', entry)
            pages = grab('pages', entry)
            booktitle = grab('booktitle', entry).replace('\n', ' ').strip()
            month = grab('month', entry)

            # 作者拆分：bib 格式 "Last, First and Last, First"
            author_strs = [a.strip() for a in re.split(r'\s+and\s+', author_raw) if a.strip()]
            authors = []
            for a in author_strs:
                if ',' in a:
                    last, first = a.split(',', 1)
                    name_norm = f"{first.strip()} {last.strip()}"
                else:
                    name_norm = a
                authors.append({"name_raw": a, "name_normalized": name_norm})

            # 提取 anthology_id: https://aclanthology.org/2024.acl-long.2/
            anthology_id = ""
            m = re.search(r'/(\d{4}\.[\w-]+\.\d+)/?$', url)
            if m:
                anthology_id = m.group(1)

            out.append({
                "anthology_id": anthology_id,
                "title": title,
                "authors": authors,
                "url": url,
                "doi": doi,
                "pages": pages,
                "booktitle": booktitle,
                "month": month,
            })
        return out

    @staticmethod
    def _guess_pdf_url(anthology_id: str) -> Optional[str]:
        """Anthology 约定：详情页 URL 后加 .pdf 即是 PDF 直链。"""
        if not anthology_id:
            return None
        return f"{ANTHOLOGY_BASE}/{anthology_id}.pdf"

    @staticmethod
    def _infer_published_at(year: int, month: str) -> Optional[datetime]:
        """从 bib 的 month 字段（如 "aug"）推断日期，失败返回年份首日。"""
        month_map = {
            'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
            'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12,
        }
        m = month_map.get((month or '').lower()[:3], 1)
        try:
            return datetime(year, m, 1, tzinfo=timezone.utc)
        except Exception:
            return datetime(year, 1, 1, tzinfo=timezone.utc)
