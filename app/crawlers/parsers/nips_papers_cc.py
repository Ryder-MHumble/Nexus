"""NeurIPS 爬虫 — papers.nips.cc（NeurIPS 官方 Proceedings）

覆盖：NeurIPS 2006-至今（官方从 2006 年开始有在线 proceedings）
数据源：papers.nips.cc/paper_files/paper/{year}
特点：静态 HTML、结构稳定（<li class="conference" data-track="...">）

Track 区分：
- conference            → Main Conference（主会论文）
- datasets_benchmarks   → Datasets & Benchmarks Track（2021+ 新增）

⚠️ 接入基座时：
1. 本文件搬到 `app/crawlers/parsers/nips_papers_cc.py`
2. 修改 import：`from app.crawlers.base import BaseCrawler, CrawledItem`
3. 在 `app/crawlers/registry.py` 的 `_CUSTOM_MAP` 注册
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from app.crawlers.base import BaseCrawler, CrawledItem
    from app.crawlers.utils.http_client import fetch_page
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from base import BaseCrawler, CrawledItem  # type: ignore

    async def fetch_page(url: str, timeout: float = 60.0, max_retries: int = 3) -> str:
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

BASE = "https://papers.nips.cc"

# NeurIPS 列表页每条论文的结构
_PAPER_ROW_RE = re.compile(
    r'<li class="conference"\s+data-track="([^"]+)">\s*'
    r'<div class="paper-content">\s*'
    r'<a[^>]*title="paper title"\s+href="([^"]+)">([^<]+)</a>\s*'
    r'<span class="paper-authors">(.*?)</span>',
    re.DOTALL,
)

# Track 中文/展示名映射
_TRACK_LABEL = {
    "conference":          "Main Conference",
    "datasets_benchmarks": "Datasets & Benchmarks",
}


class NeurIPSCrawler(BaseCrawler):
    """NeurIPS 某一年的全量论文。

    YAML 字段：
        id: neurips-2024
        crawler_class: nips_papers_cc
        venue: NeurIPS
        year: 2024
        # 可选筛选：只要 conference / datasets_benchmarks
        # 不填 = 两 track 都收
        include_tracks: [conference, datasets_benchmarks]
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
        venue: str = cfg.get("venue", "NeurIPS")
        year: int = int(cfg["year"])
        include_tracks = cfg.get("include_tracks") or list(_TRACK_LABEL.keys())

        list_url = f"{BASE}/paper_files/paper/{year}"
        logger.info(f"[{self.source_id}] fetching {list_url}")
        html = await fetch_page(list_url, timeout=60.0, max_retries=3)

        matches = _PAPER_ROW_RE.findall(html)
        logger.info(f"[{self.source_id}] parsed {len(matches)} raw rows")

        now = datetime.now(timezone.utc)
        items: list[CrawledItem] = []

        for track, href, title, authors_raw in matches:
            if track not in include_tracks:
                continue

            # 规范化 href → 完整 URL + 抽 raw_id
            href_full = href if href.startswith("http") else BASE + href
            # paper_files/paper/2024/hash/XXX-Abstract-Conference.html
            m = re.search(r'/hash/([a-f0-9]+)-Abstract', href)
            raw_id = f"{year}/{m.group(1)}" if m else href
            paper_id = f"nips_cc:{raw_id}"

            title_clean = re.sub(r"\s+", " ", title).strip()

            # 作者拆分（逗号分隔）
            authors_list = [a.strip() for a in authors_raw.split(",") if a.strip()]
            authors_data = [
                {
                    "paper_id": paper_id,
                    "author_order": idx + 1,
                    "name_raw": a,
                    "name_normalized": a,  # NeurIPS 已是 "First Last" 格式
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

            track_label = _TRACK_LABEL.get(track, track)
            is_main_track = (track == "conference")

            paper_data = {
                "paper_id": paper_id,
                "source": "nips_cc",
                "raw_id": raw_id,
                "venue": venue,
                "venue_full": "Advances in Neural Information Processing Systems",
                "year": year,
                "track": track_label,
                "is_main_track": is_main_track,
                "is_workshop": False,
                "title": title_clean,
                "abstract": None,  # 列表页不含，要进 detail 才有
                "n_authors": len(authors_list),
                "url": href_full,
                "pdf_url": None,  # detail 页才给出（论文 pdf）
                "doi": None,
                "arxiv_id": None,
                "scraped_at": now.isoformat(),
                "schema_version": "1.0",
            }

            items.append(CrawledItem(
                title=title_clean,
                url=href_full,
                published_at=datetime(year, 12, 1, tzinfo=timezone.utc),  # NeurIPS 一般 12 月
                author=authors_list[0] if authors_list else None,
                source_id=self.source_id,
                dimension=cfg.get("dimension", "academic_venues"),
                tags=[venue, str(year), track_label],
                extra={"paper": paper_data, "authors": authors_data},
            ))

        return items
