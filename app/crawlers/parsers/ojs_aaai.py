"""AAAI 爬虫 — ojs.aaai.org（AAAI Proceedings OJS 平台）

覆盖：AAAI 2018-至今（OJS 平台从 2018 开始）
数据源：https://ojs.aaai.org/index.php/AAAI/issue/view/{issue_id}
特点：每个 issue = 一本会议分卷（volume），一年的 AAAI 分成 20+ issues

两种抓取模式：
  - fetch_affiliations=false (默认)：只用 issue 页（快，无机构）
  - fetch_affiliations=true：并发抓每篇 detail 页取作者机构（慢 40-60×，但有真·机构）

Issue ID 查询：
  访问 https://ojs.aaai.org/index.php/AAAI/issue/archive 获取某年所有 issue。
  （archive 页面一次给出 ~40 年，需翻页，但维护频率低——每年一次）

⚠️ 接入基座：本文件搬到 `app/crawlers/parsers/ojs_aaai.py`
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

BASE = "https://ojs.aaai.org"

# ------------------------------------------------------------------ #
# 模式 1：Issue 页批量抓（无机构）
# ------------------------------------------------------------------ #

_ARTICLE_RE = re.compile(
    r'<h3\s+class="title">\s*'
    r'<a\s+id="article-(?P<aid>\d+)"\s+href="(?P<url>[^"]+)"[^>]*>\s*'
    r'(?P<title>.*?)\s*</a>\s*</h3>\s*'
    r'<div\s+class="meta">\s*'
    r'<div\s+class="authors">\s*(?P<authors>.*?)\s*</div>'
    r'(?:\s*<div\s+class="pages">\s*(?P<pages>[^<]+)\s*</div>)?',
    re.DOTALL,
)

_SECTION_RE = re.compile(
    r'<div\s+class="section"\s+id="([^"]+)">\s*<h2>\s*(.*?)\s*</h2>',
    re.DOTALL,
)

_PDF_LINK_RE = re.compile(
    r'<a\s+class="obj_galley_link pdf"\s+href="([^"]+)"[^>]*aria-labelledby=article-(\d+)',
)

_ARCHIVE_ISSUE_RE = re.compile(
    r'<a[^>]+href="https://ojs\.aaai\.org/index\.php/AAAI/issue/view/(?P<issue_id>\d+)"[^>]*>'
    r'\s*(?P<title>.*?)\s*</a>',
    re.DOTALL,
)


# ------------------------------------------------------------------ #
# 模式 2：Detail 页 <ul class="authors"> 里的 作者 + 机构
# ------------------------------------------------------------------ #

_AUTHORS_UL_RE = re.compile(
    r'<ul\s+class="authors"[^>]*>(.*?)</ul>',
    re.DOTALL,
)
_AUTHOR_LI_RE = re.compile(
    r'<li>\s*'
    r'<span\s+class="name">\s*(?P<name>.*?)\s*</span>\s*'
    r'(?:<span\s+class="affiliation">\s*(?P<aff>.*?)\s*</span>\s*)?'
    r'</li>',
    re.DOTALL,
)


def _parse_authors_with_affiliation(detail_html: str) -> list[dict]:
    """从 AAAI 某论文 detail 页提取 [{name, affiliation}, ...]。"""
    import html as html_mod
    ul_m = _AUTHORS_UL_RE.search(detail_html)
    if not ul_m:
        return []
    out = []
    for m in _AUTHOR_LI_RE.finditer(ul_m.group(1)):
        name = html_mod.unescape(re.sub(r"\s+", " ", m.group("name")).strip())
        aff = m.group("aff")
        aff = html_mod.unescape(re.sub(r"\s+", " ", aff).strip()) if aff else None
        if name:
            out.append({"name": name, "affiliation": aff})
    return out


class AAAICrawler(BaseCrawler):
    """抓 AAAI 某年的所有 issues（一个 volume）。

    YAML 字段：
        id: aaai-2024
        crawler_class: ojs_aaai
        venue: AAAI
        year: 2024
        issue_ids: [576, 577, 578, ..., 596]
        fetch_affiliations: false      # 默认 false，true 时额外抓 detail 页
        detail_concurrency: 3           # detail 抓取并发（OJS 老系统，≤5 为宜）
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
        venue: str = cfg.get("venue", "AAAI")
        year: int = int(cfg["year"])
        issue_ids = await self._resolve_issue_ids(cfg, year)
        fetch_affiliations: bool = cfg.get("fetch_affiliations", False)
        detail_concurrency: int = int(cfg.get("detail_concurrency", 3))
        request_delay: float = float(cfg.get("request_delay", 0.2))

        now = datetime.now(timezone.utc)
        items: list[CrawledItem] = []

        for issue_id in issue_ids:
            url = f"{BASE}/index.php/AAAI/issue/view/{issue_id}"
            logger.info(f"[{self.source_id}] fetching issue {issue_id}")
            try:
                html = await fetch_page(
                    url,
                    timeout=60.0,
                    max_retries=3,
                    request_delay=request_delay,
                )
            except Exception as e:
                logger.error(f"  ❌ issue {issue_id} failed: {e}")
                continue

            sections = self._split_sections(html)
            pdf_map = {m.group(2): m.group(1) for m in _PDF_LINK_RE.finditer(html)}

            issue_paper_count = 0
            for section_text, section_id, section_name in sections:
                for m in _ARTICLE_RE.finditer(section_text):
                    aid = m.group('aid')
                    title = re.sub(r'\s+', ' ', m.group('title')).strip()
                    detail_url = m.group('url').strip()
                    authors_raw = re.sub(r'\s+', ' ', m.group('authors')).strip()
                    pages = (m.group('pages') or '').strip()

                    pdf_url = pdf_map.get(aid)
                    raw_id = f"AAAI-{year}/article/{aid}"
                    paper_id = f"ojs_aaai:{raw_id}"

                    authors_list = [a.strip() for a in authors_raw.split(',') if a.strip()]
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

                    is_main = self._is_main_track(section_name)
                    is_workshop = 'workshop' in section_name.lower()

                    paper_data = {
                        "paper_id": paper_id,
                        "source": "ojs_aaai",
                        "raw_id": raw_id,
                        "venue": venue,
                        "venue_full": "AAAI Conference on Artificial Intelligence",
                        "year": year,
                        "track": section_name,
                        "is_main_track": is_main,
                        "is_workshop": is_workshop,
                        "title": title,
                        "abstract": None,
                        "n_authors": len(authors_list),
                        "url": detail_url,
                        "pdf_url": pdf_url,
                        "doi": None,
                        "arxiv_id": None,
                        "scraped_at": now.isoformat(),
                        "schema_version": "1.0",
                    }

                    items.append(CrawledItem(
                        title=title,
                        url=detail_url,
                        published_at=datetime(year, 2, 1, tzinfo=timezone.utc),
                        author=authors_list[0] if authors_list else None,
                        source_id=self.source_id,
                        dimension=cfg.get("dimension", "academic_venues"),
                        tags=[venue, str(year), section_name],
                        extra={"paper": paper_data, "authors": authors_data, "pages": pages},
                    ))
                    issue_paper_count += 1

            logger.info(f"  issue {issue_id}: {issue_paper_count} papers")
            await asyncio.sleep(1.0)

        if fetch_affiliations and items:
            logger.info(
                f"[{self.source_id}] 开始抓 detail 页补全机构 "
                f"(n={len(items)}, concurrency={detail_concurrency})"
            )
            await self._enrich_affiliations(items, detail_concurrency, request_delay)

        return items

    async def _resolve_issue_ids(self, cfg: dict[str, Any], year: int) -> list[int]:
        raw_issue_ids = cfg.get("issue_ids")
        if isinstance(raw_issue_ids, list) and raw_issue_ids:
            return [int(issue_id) for issue_id in raw_issue_ids]

        archive_pages = int(cfg.get("archive_pages") or self.config.get("archive_pages") or 8)
        issue_ids = await self._discover_issue_ids(year, archive_pages)
        if issue_ids:
            logger.info("[%s] discovered %d AAAI %s issues", self.source_id, len(issue_ids), year)
            return issue_ids

        raise ValueError(
            f"AAAI {year} issue_ids not configured and not found in OJS archive "
            f"(searched {archive_pages} pages)"
        )

    async def _discover_issue_ids(self, year: int, archive_pages: int) -> list[int]:
        cache = getattr(self, "_archive_issue_cache", None)
        if cache is None:
            cache = {}
            self._archive_issue_cache = cache
        if year in cache:
            return cache[year]

        discovered: dict[int, list[int]] = {}
        seen: set[int] = set()
        for page in range(1, archive_pages + 1):
            url = f"{BASE}/index.php/AAAI/issue/archive"
            if page > 1:
                url = f"{url}/{page}"
            html = await fetch_page(url, timeout=60.0, max_retries=3)
            page_matches = list(_ARCHIVE_ISSUE_RE.finditer(html))
            if not page_matches:
                break

            for match in page_matches:
                issue_id = int(match.group("issue_id"))
                title = re.sub(r"<.*?>", " ", match.group("title"))
                title = re.sub(r"\s+", " ", title).strip()
                issue_year = self._issue_title_year(title)
                if issue_year is None:
                    continue
                if issue_id in seen:
                    continue
                seen.add(issue_id)
                discovered.setdefault(issue_year, []).append(issue_id)

        cache.update(discovered)
        return cache.get(year, [])

    async def _enrich_affiliations(
        self,
        items: list[CrawledItem],
        concurrency: int,
        request_delay: float,
    ) -> None:
        """并发抓每篇 detail 页，补 authors[].affiliation。"""
        sem = asyncio.Semaphore(concurrency)
        done = [0]
        total = len(items)

        async def enrich_one(item: CrawledItem):
            async with sem:
                try:
                    html = await fetch_page(
                        item.url,
                        timeout=30.0,
                        max_retries=2,
                        request_delay=request_delay,
                    )
                    affs = _parse_authors_with_affiliation(html)
                    if affs:
                        aff_map = {a["name"]: a["affiliation"] for a in affs}
                        for author in item.extra.get("authors", []):
                            name = author.get("name_normalized")
                            if name in aff_map:
                                author["affiliation"] = aff_map[name]
                except Exception as e:
                    logger.warning(f"  detail 抓取失败 {item.url}: {e}")
                done[0] += 1
                if done[0] % 50 == 0:
                    logger.info(f"  ... {done[0]}/{total}")
                await asyncio.sleep(0.3)

        await asyncio.gather(*(enrich_one(it) for it in items))

    @staticmethod
    def _split_sections(html: str) -> list[tuple[str, str, str]]:
        """按 <h2> 拆分 section。返回 [(section_text, section_id, section_name), ...]。"""
        sections = []
        matches = list(_SECTION_RE.finditer(html))
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
            section_id = m.group(1)
            section_name = re.sub(r'\s+', ' ', m.group(2)).strip()
            sections.append((html[start:end], section_id, section_name))
        return sections

    @staticmethod
    def _issue_title_year(title: str) -> int | None:
        match = re.search(r"\bAAAI[-\s]+(?P<year>\d{2}|\d{4})\b", title, re.IGNORECASE)
        if not match:
            return None
        token = match.group("year")
        if len(token) == 2:
            return 2000 + int(token)
        return int(token)

    @staticmethod
    def _is_main_track(section_name: str) -> bool:
        """判定 section 是否属于主会。"""
        s = section_name.lower()
        if 'technical track' in s:
            return True
        if 'special track' in s:
            return True
        for kw in ['student abstract', 'senior member', 'iaai', 'eaai',
                   'doctoral consortium', 'undergraduate consortium',
                   'workshop', 'bridge', 'tutorial']:
            if kw in s:
                return False
        return 'track' in s
