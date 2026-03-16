"""Faculty crawler — extracts teacher/researcher profiles from university department pages.

Config fields:
  - url: faculty list page URL
  - base_url: for resolving relative links
  - use_playwright: bool (default False) — use Playwright for JS-rendered pages
  - wait_for: CSS selector to wait for (only when use_playwright=True)
  - wait_timeout: milliseconds (default 15000, only when use_playwright=True)
  - faculty_selectors:
      list_item: CSS selector for each faculty entry (required)
      name: selector for name (default "h2"), relative to list_item
      bio: selector for bio/intro text (optional)
      link: selector for profile link (default "a")
      photo: selector for photo img (optional)
      position: selector for position/title (optional, only if separate from name)
      email: selector for email address (optional)
  - detail_selectors: (optional) fetch individual profile pages for richer info
      name: selector for name override
      position: selector for position/title
      bio: selector for bio/intro
      research_areas: selector for research directions text
      email: selector for email address
      photo: selector for photo img src
  - university: university full name (stored in ScholarRecord.university)
  - department: department full name (stored in ScholarRecord.department)
  - request_delay: seconds between detail page requests (default 1.0)

CrawledItem mapping (for pipeline compatibility):
  - title    = ScholarRecord.name
  - url      = ScholarRecord.profile_url  (dedup key)
  - content  = ScholarRecord.bio
  - extra    = ScholarRecord.model_dump() — full structured record

Schema: see app/schemas/scholar.py → ScholarRecord
"""
from __future__ import annotations

import asyncio
import logging
import re as _re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_content_hash, compute_url_hash
from app.crawlers.utils.http_client import fetch_page
from app.schemas.scholar import (
    ScholarRecord,
    compute_scholar_completeness,
    parse_research_areas,
    validate_research_areas,
    validate_scholar_name,
)

# Optional LLM enhancement (only imported if enabled)
try:
    from app.crawlers.utils.scholar_llm_extractor import extract_faculty_fields_with_llm
    LLM_AVAILABLE = True
except ImportError:
    extract_faculty_fields_with_llm = None
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)

# Regex for extracting email addresses from text
_EMAIL_RE = _re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Regex to remove spaces/\xa0 between CJK characters (alignment padding in Chinese names)
_CJK_SPACE_RE = _re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_name(name: str) -> str:
    """Normalize a faculty name: collapse whitespace (incl. \xa0) and remove
    alignment spaces between CJK characters (common in Chinese academic CMS)."""
    # Replace non-breaking spaces and normalize all whitespace to single space
    name = " ".join(name.replace("\xa0", " ").split())
    # Remove spaces between adjacent Chinese characters (visual alignment padding)
    name = _CJK_SPACE_RE.sub("", name)
    return name


def _is_valid_href(href: str) -> bool:
    """Return True if href is a real navigable URL (not javascript:, #, empty)."""
    if not href:
        return False
    href_lower = href.strip().lower()
    if href_lower.startswith("javascript:") or href_lower == "#":
        return False
    return True


def _resolve_url(href: str, base_url: str) -> str:
    """Resolve a potentially relative href against base_url."""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(base_url, href)


def _extract_text(el: BeautifulSoup | None, selector: str | None) -> str:
    """Extract stripped text from a sub-element found by selector."""
    if el is None or not selector:
        return ""
    found = el.select_one(selector)
    return found.get_text(strip=True) if found else ""


def _extract_img_src(el: BeautifulSoup | None, selector: str | None, base_url: str) -> str:
    """Extract and resolve an img src from a sub-element found by selector."""
    if el is None or not selector:
        return ""
    img = el.select_one(selector)
    if img is None:
        return ""
    src = img.get("src", "").strip()
    if not src:
        return ""
    return _resolve_url(src, base_url)


def _extract_email_from_text(text: str) -> str:
    """Find the first email address in text."""
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else ""


class ScholarCrawler(BaseCrawler):
    """Crawler for university faculty/staff list pages.

    Extracts structured faculty profile data and stores it as a ScholarRecord
    (app.schemas.scholar) in CrawledItem.extra. All missing fields default to
    "" / [] / -1 so the output is always schema-complete and DB-migration-ready.
    """

    async def _fetch_html_static(self, url: str) -> str:
        return await fetch_page(
            url,
            headers=self.config.get("headers"),
            encoding=self.config.get("encoding"),
            request_delay=self.config.get("request_delay"),
            verify=self.config.get("verify_ssl", True),
        )

    async def _fetch_html_playwright(self, url: str) -> str:
        from app.crawlers.utils.playwright_pool import get_page

        wait_for = self.config.get("wait_for", "networkidle")
        wait_timeout = self.config.get("wait_timeout", 15000)

        async with get_page() as page:
            await page.goto(url, wait_until="domcontentloaded", timeout=wait_timeout)
            if wait_for == "networkidle":
                await page.wait_for_load_state("networkidle", timeout=wait_timeout)
            else:
                try:
                    await page.wait_for_selector(wait_for, timeout=wait_timeout)
                except Exception:
                    pass
            return await page.content()

    async def _fetch_detail(self, profile_url: str, detail_selectors: dict) -> dict:
        """Fetch individual profile page and extract detailed faculty info."""
        result: dict = {}
        try:
            html = await fetch_page(
                profile_url,
                headers=self.config.get("headers"),
                encoding=self.config.get("encoding"),
                request_delay=self.config.get("request_delay"),
                verify=self.config.get("verify_ssl", True),
            )
            soup = BeautifulSoup(html, "lxml")

            if name_sel := detail_selectors.get("name"):
                if name_text := _extract_text(soup, name_sel):
                    result["name"] = _clean_name(name_text)

            if pos_sel := detail_selectors.get("position"):
                if pos_text := _extract_text(soup, pos_sel):
                    result["position"] = pos_text

            if bio_sel := detail_selectors.get("bio"):
                if bio_text := _extract_text(soup, bio_sel):
                    result["bio"] = bio_text

            if ra_sel := detail_selectors.get("research_areas"):
                found = soup.select_one(ra_sel)
                if found:
                    # Use newline separator so <li> items are delimited for parse_research_areas
                    ra_text = found.get_text(separator="\n").strip()
                    if ra_text:
                        result["research_areas"] = parse_research_areas(ra_text)

            if email_sel := detail_selectors.get("email"):
                if email_text := _extract_text(soup, email_sel):
                    result["email"] = email_text
            if not result.get("email"):
                full_text = soup.get_text()
                if email := _extract_email_from_text(full_text):
                    result["email"] = email

            if photo_sel := detail_selectors.get("photo"):
                base = self.config.get("base_url", profile_url)
                if photo_url := _extract_img_src(soup, photo_sel, base):
                    result["photo_url"] = photo_url

            # Store full text for optional LLM enrichment
            result["_full_text"] = soup.get_text()

            # heading_sections: {field: "heading text"} — find h2/h3/h4/p/div by text, extract next sibling
            # Useful for pages where sections are identified by heading text (common on Chinese academic sites)
            # heading_text is treated as a regex pattern for robustness (handles "field1|field2|field3" alternations)
            if heading_sections := detail_selectors.get("heading_sections"):
                for field, heading_text in heading_sections.items():
                    # Check heading tags, paragraph tags, and short divs (some sites use div for headings)
                    for tag in soup.find_all(["h2", "h3", "h4", "p", "div"]):
                        if _re.search(heading_text, tag.get_text(strip=True)):
                            # Look for content in next sibling or parent's next sibling
                            sibling = tag.find_next_sibling()
                            if sibling:
                                text = sibling.get_text(strip=True)
                                if text:
                                    if field == "research_areas":
                                        result[field] = parse_research_areas(text)
                                    else:
                                        result[field] = text
                            break

            # label_prefix_sections: {field: "Label："} — find element starting with prefix, extract remainder
            # Searches <p> and <li> tags (handles both paragraph and list-item label+value patterns)
            # Useful for pages where fields are in "Label：Value" format within a single element
            if label_prefix_sections := detail_selectors.get("label_prefix_sections"):
                for field, label_prefix in label_prefix_sections.items():
                    if result.get(field):  # already extracted, skip
                        continue
                    for el in soup.find_all(["p", "li"]):
                        text = el.get_text(strip=True)
                        if text.startswith(label_prefix):
                            value = text[len(label_prefix):].strip()
                            if value:
                                if field == "research_areas":
                                    result[field] = parse_research_areas(value)
                                else:
                                    result[field] = value
                            break

        except Exception as e:
            logger.warning("Failed to fetch faculty detail %s: %s", profile_url, e)
        return result

    async def fetch_and_parse(self) -> list[CrawledItem]:
        url = self.config["url"]
        base_url = self.config.get("base_url", url)
        use_playwright = self.config.get("use_playwright", False)
        faculty_sel = self.config.get("faculty_selectors", {})
        detail_selectors = self.config.get("detail_selectors")
        request_delay = self.config.get("request_delay", 1.0)
        # Pagination: follow "next page" links up to max_pages (default 1 = no pagination)
        # next_page_text is treated as a regex; default r"下一?页" matches "下页" and "下一页" variants
        max_pages = self.config.get("max_pages", 1)
        next_page_text = self.config.get("next_page_text", r"下一?页")

        university = self.config.get("university", "")
        department = self.config.get("department", "")
        source_id = self.source_id
        crawled_at = _now_iso()

        # Extract selectors once (shared across all pages)
        list_item_sel = faculty_sel.get("list_item", "li")
        name_sel = faculty_sel.get("name", "h2")
        bio_sel = faculty_sel.get("bio")
        link_sel = faculty_sel.get("link", "a")
        photo_sel = faculty_sel.get("photo")
        position_sel = faculty_sel.get("position")
        email_sel = faculty_sel.get("email")
        ra_sel = faculty_sel.get("research_areas")  # optional list-page research_areas

        items: list[CrawledItem] = []
        seen_urls: set[str] = set()
        current_url = url
        page_num = 1

        while True:
            # 1. Fetch current page
            if use_playwright:
                html = await self._fetch_html_playwright(current_url)
            else:
                html = await self._fetch_html_static(current_url)

            soup = BeautifulSoup(html, "lxml")

            # 2. Locate faculty entries
            entries = soup.select(list_item_sel)

            if not entries and page_num == 1:
                logger.warning(
                    "ScholarCrawler[%s]: no entries found with selector %r on %s",
                    self.source_id, list_item_sel, current_url,
                )

            # 3. Process entries
            for entry in entries:
                # --- Name ---
                name_text = _extract_text(entry, name_sel)
                # Fallback: when list_item selector directly selects <a> elements (e.g., ul > a without <li>)
                if not name_text and entry.name == "a":
                    name_text = entry.get_text(strip=True)
                name_text = _clean_name(name_text)
                if not name_text:
                    continue
                # Validate name is a real person, not a nav/menu item
                if not validate_scholar_name(name_text):
                    logger.debug(
                        "ScholarCrawler[%s]: skipping non-scholar name %r",
                        self.source_id, name_text,
                    )
                    continue

                # --- Profile URL ---
                profile_url = ""
                # Fallback: when list_item selector directly selects <a> elements, use element's own href
                if entry.name == "a":
                    href = entry.get("href", "").strip()
                    if _is_valid_href(href):
                        profile_url = _resolve_url(href, base_url)
                if not profile_url and link_sel:
                    link_el = entry.select_one(link_sel)
                    if link_el:
                        href = link_el.get("href", "").strip()
                        if _is_valid_href(href):
                            profile_url = _resolve_url(href, base_url)

                # Synthetic URL for faculty without real profile pages
                if not profile_url:
                    name_hash = compute_url_hash(f"{url}#{name_text}")
                    profile_url = f"{url}#{name_hash[:16]}"

                # Skip exact duplicates (same profile URL)
                if profile_url in seen_urls:
                    continue
                seen_urls.add(profile_url)

                # --- Fields from list page ---
                position_text = _extract_text(entry, position_sel) if position_sel else ""
                bio_text = _extract_text(entry, bio_sel) if bio_sel else ""
                photo_url = _extract_img_src(entry, photo_sel, base_url) if photo_sel else ""
                email_text = _extract_text(entry, email_sel) if email_sel else ""
                research_areas: list[str] = []
                if ra_sel:
                    ra_text = _extract_text(entry, ra_sel)
                    if ra_text:
                        research_areas = parse_research_areas(ra_text)

                # --- Optional: fetch detail page ---
                detail_full_text = ""
                if detail_selectors and not profile_url.startswith(f"{url}#"):
                    if request_delay:
                        await asyncio.sleep(request_delay)
                    detail = await self._fetch_detail(profile_url, detail_selectors)
                    detail_full_text = detail.pop("_full_text", "")  # extract for LLM use
                    if detail.get("name"):
                        name_text = detail["name"]
                    if detail.get("bio"):
                        bio_text = detail["bio"]
                    if detail.get("position"):
                        position_text = detail["position"]
                    if detail.get("email"):
                        email_text = detail["email"]
                    if detail.get("photo_url"):
                        photo_url = detail["photo_url"]
                    if detail.get("research_areas"):
                        research_areas = detail["research_areas"]

                # Validate research_areas — clear if it looks like a nav menu
                research_areas = validate_research_areas(research_areas)

                # --- Optional: LLM data cleaning (extract mixed/unstructured fields) ---
                phone_text = ""
                education_records: list[dict] = []
                work_experience_records: list[dict] = []
                award_records: list[dict] = []
                publication_records: list[dict] = []
                academic_titles: list[str] = []
                is_academician = False
                phd_institution = ""
                phd_year = ""

                # LLM extraction: two modes
                # 1. llm_extraction=true + llm_fields: extract specific fields using LLM
                # 2. enable_llm=true: legacy mode, fill missing fields only
                if LLM_AVAILABLE and (self.config.get("llm_extraction") or self.config.get("enable_llm")):
                    llm_fields_to_extract = self.config.get("llm_fields", [])
                    llm_provider = self.config.get("llm_provider", "openrouter")
                    llm_model = self.config.get("llm_model", "deepseek/deepseek-chat")

                    try:
                        llm_result = await extract_faculty_fields_with_llm(
                            raw_name=name_text,
                            raw_bio=bio_text,
                            raw_position=position_text,
                            detail_html_text=detail_full_text,
                            fields_to_extract=llm_fields_to_extract if llm_fields_to_extract else None,
                            llm_provider=llm_provider,
                            llm_model=llm_model,
                        )

                        # Extract phone
                        if "phone" in (llm_fields_to_extract or []):
                            phone_text = llm_result.get("phone", "")

                        # Extract research areas
                        if "research_areas" in (llm_fields_to_extract or []):
                            llm_ra = llm_result.get("research_areas", [])
                            if llm_ra and not research_areas:
                                research_areas = llm_ra if isinstance(llm_ra, list) else parse_research_areas(str(llm_ra))

                        # Extract education
                        if "education" in (llm_fields_to_extract or []):
                            for edu in llm_result.get("education", []):
                                if isinstance(edu, dict):
                                    education_records.append(edu)

                        # Extract work experience
                        if "work_experience" in (llm_fields_to_extract or []):
                            for work in llm_result.get("work_experience", []):
                                if isinstance(work, dict):
                                    work_experience_records.append(work)

                        # Extract awards
                        if "awards" in (llm_fields_to_extract or []):
                            for award in llm_result.get("awards", []):
                                if isinstance(award, dict):
                                    award_records.append(award)

                        # Extract publications
                        if "publications" in (llm_fields_to_extract or []):
                            for pub in llm_result.get("publications", []):
                                if isinstance(pub, dict):
                                    publication_records.append(pub)

                        # Legacy mode: fill missing fields
                        if self.config.get("enable_llm") and not self.config.get("llm_extraction"):
                            if not name_text:
                                name_text = llm_result.get("name", "")
                            if not bio_text:
                                bio_text = llm_result.get("bio", "")
                            if not position_text:
                                position_text = llm_result.get("position", "")
                            if not email_text:
                                email_text = llm_result.get("email", "")
                            academic_titles = llm_result.get("academic_titles", [])
                            is_academician = llm_result.get("is_academician", False)
                            phd_institution = llm_result.get("phd_institution", "")
                            phd_year = llm_result.get("phd_year", "")

                        logger.debug("LLM extraction completed for %s", name_text)
                    except Exception as e:
                        logger.warning("LLM extraction failed for %s: %s", name_text, e)

                # --- Build ScholarRecord ---
                # Convert education records from LLM extraction
                from app.schemas.scholar import EducationRecord, AwardRecord, PublicationRecord
                education_list = []
                for edu in education_records:
                    education_list.append(
                        EducationRecord(
                            degree=edu.get("degree") or "",
                            institution=edu.get("institution") or "",
                            year=edu.get("year") or "",
                            major=edu.get("major") or "",
                        )
                    )

                # Convert award records from LLM extraction
                award_list = []
                for award in award_records:
                    award_list.append(
                        AwardRecord(
                            title=award.get("title") or "",
                            year=award.get("year") or "",
                            level=award.get("level") or "",
                            grantor=award.get("grantor") or "",
                            description=award.get("description") or "",
                            added_by="crawler",
                        )
                    )

                # Convert publication records from LLM extraction
                pub_list = []
                for pub in publication_records:
                    pub_list.append(
                        PublicationRecord(
                            title=pub.get("title") or "",
                            venue=pub.get("venue") or "",
                            year=pub.get("year") or "",
                            authors=pub.get("authors") or "",
                            url=pub.get("url") or "",
                            citation_count=-1,
                            is_corresponding=False,
                            added_by="crawler",
                        )
                    )

                record = ScholarRecord(
                    # 基本信息
                    name=name_text,
                    photo_url=photo_url,
                    # 机构归属
                    university=university,
                    department=department,
                    # 职称
                    position=position_text,
                    # 研究
                    research_areas=research_areas,
                    keywords=[],  # can be extracted from bio/research_areas in future
                    bio=bio_text,
                    academic_titles=academic_titles,
                    is_academician=is_academician,
                    # 教育背景
                    phd_institution=phd_institution,
                    phd_year=phd_year,
                    education=education_list,
                    # 联系方式
                    email=email_text,
                    phone=phone_text,
                    # 代表性论文
                    representative_publications=pub_list,
                    # 奖励
                    awards=award_list,
                    # 主页链接
                    profile_url=profile_url,
                    # 元信息
                    source_id=source_id,
                    source_url=url,
                    crawled_at=crawled_at,
                    last_seen_at=crawled_at,
                    is_active=True,
                )
                record.data_completeness = compute_scholar_completeness(record)

                content_hash = compute_content_hash(bio_text) if bio_text else None

                items.append(
                    CrawledItem(
                        title=name_text,
                        url=profile_url,
                        published_at=None,
                        author=None,
                        content=bio_text or None,
                        content_hash=content_hash,
                        source_id=source_id,
                        dimension=self.config.get("dimension"),
                        tags=self.config.get("tags", []),
                        extra=record.model_dump(),
                    )
                )

            # 4. Pagination: find and follow "next page" link
            if page_num >= max_pages:
                break
            next_link = soup.find("a", string=_re.compile(next_page_text))
            if not next_link:
                break
            next_href = (next_link.get("href") or "").strip()
            if not _is_valid_href(next_href):
                break
            next_url = _resolve_url(next_href, current_url)
            if next_url == current_url:  # guard against infinite loop
                break
            current_url = next_url
            page_num += 1
            if request_delay:
                await asyncio.sleep(request_delay)

        logger.info(
            "ScholarCrawler[%s]: extracted %d faculty from %s (%d page(s))",
            self.source_id, len(items), url, page_num,
        )
        return items
