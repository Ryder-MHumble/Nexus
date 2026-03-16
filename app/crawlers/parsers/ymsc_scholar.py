"""YMSC Faculty Parser — 清华大学丘成桐数学科学中心学者信息爬取器

深度爬取所有学者的完整详细信息，包括：
- 基本信息：姓名、职位、照片、联系方式
- 研究方向
- 教育背景（学位、院校、年份）
- 工作经历
- 荣誉与奖励
- 发表论文
- 完整个人简介文本

数据来源：https://ymsc.tsinghua.edu.cn/sxxr/zxjs.htm
"""
from __future__ import annotations

import asyncio
import logging
import re as _re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.dedup import compute_url_hash
from app.crawlers.utils.http_client import fetch_page
from app.schemas.scholar import (
    AwardRecord,
    EducationRecord,
    PublicationRecord,
    ScholarRecord,
    compute_scholar_completeness,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://ymsc.tsinghua.edu.cn"
_LIST_URL = "https://ymsc.tsinghua.edu.cn/sxxr/zxjs.htm"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_email_from_text(text: str) -> str:
    """Find the first email address in text."""
    m = _re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return m.group(0) if m else ""


def _normalize_url(base_url: str, href: str) -> str:
    """Normalize relative URLs to absolute URLs."""
    if href.startswith("http"):
        return href
    elif href.startswith("../info/"):
        full_url = base_url + href.replace("..", "")
    else:
        full_url = base_url + "/" + href.lstrip("../").lstrip("./")

    # Fix double slashes
    full_url = full_url.replace("//", "/").replace("http:/", "http://").replace("https:/", "https://")
    return full_url


class YMSCFacultyCrawler(BaseCrawler):
    """清华大学丘成桐数学科学中心学者信息爬取器"""

    async def _get_scholar_list(self) -> list[dict]:
        """获取所有学者列表"""
        try:
            html = await fetch_page(_LIST_URL)
            soup = BeautifulSoup(html, "lxml")

            scholar_links = []
            all_links = soup.find_all("a", href=True)

            for link in all_links:
                href = link.get("href", "")
                text = link.get_text(strip=True)

                # Filter for faculty profile links
                if "info" in href.lower() and "/sxxr/" not in href:
                    full_url = _normalize_url(_BASE_URL, href)

                    if text and len(text) > 1:
                        scholar_links.append({
                            "name": text,
                            "url": full_url,
                        })

            # Deduplicate by URL
            seen_urls: set[str] = set()
            unique_scholars = []
            for scholar in scholar_links:
                if scholar["url"] not in seen_urls:
                    seen_urls.add(scholar["url"])
                    unique_scholars.append(scholar)

            logger.info("YMSCFacultyCrawler: found %d scholars", len(unique_scholars))
            return unique_scholars

        except Exception as e:
            logger.error("YMSCFacultyCrawler: failed to get scholar list: %s", e)
            return []

    async def _extract_scholar_details(self, url: str, name_hint: str) -> dict:
        """提取单个学者的详细信息"""
        try:
            html = await fetch_page(url)
            soup = BeautifulSoup(html, "lxml")

            details = {
                "url": url,
                "name": name_hint,
                "name_en": "",
                "position": "",
                "photo_url": "",
                "office": "",
                "phone": "",
                "email": "",
                "homepage": "",
                "research_areas": "",
                "education": [],
                "work_experience": [],
                "honors": [],
                "publications": [],
                "bio": "",
            }

            # Extract title
            title = soup.find("title")
            if title:
                title_text = title.get_text()
                details["name"] = title_text.split("-")[0].strip() if "-" in title_text else title_text.strip()

            # Find main content area
            main_content = soup.find("div", class_="v_news_content")
            if not main_content:
                main_content = soup.find("div", class_="kec_content_main")
            if not main_content:
                main_content = soup.find("div", class_="gltd_content_left")

            # Extract basic info box
            info_box = soup.find("div", class_="item_center")
            if info_box:
                # Name and position
                item_box = info_box.find("div", class_="item_box")
                if item_box:
                    h2 = item_box.find("h2")
                    if h2:
                        details["name"] = h2.get_text(strip=True)
                    span = item_box.find("span")
                    if span:
                        details["position"] = span.get_text(strip=True)

                # Contact info
                item_item = info_box.find("div", class_="item_item")
                if item_item:
                    text = item_item.get_text()

                    # Phone
                    phone_match = _re.search(r"电话[：:]\s*([^\n办公室]+)", text)
                    if phone_match:
                        details["phone"] = phone_match.group(1).strip()

                    # Office
                    office_match = _re.search(r"办公室[：:]\s*([^\n邮箱]+)", text)
                    if office_match:
                        details["office"] = office_match.group(1).strip()

                    # Email
                    email = _extract_email_from_text(text)
                    if email:
                        details["email"] = email

                    # Homepage
                    homepage_match = _re.search(r"个人主页[：:]\s*([^\n]+)", text)
                    if homepage_match:
                        details["homepage"] = homepage_match.group(1).strip()

                # Photo
                img = info_box.find("img")
                if img and img.get("src"):
                    src = img.get("src")
                    if not src.startswith("http"):
                        src = _normalize_url(_BASE_URL, src)
                    details["photo_url"] = src

            if main_content:
                # Full text bio
                full_text = main_content.get_text(separator="\n", strip=True)
                details["bio"] = _re.sub(r"\n\s*\n", "\n", full_text)

                # Research areas
                research_h3 = main_content.find("h3", string=_re.compile("研究领域"))
                if research_h3:
                    research_p = research_h3.find_next_sibling("p")
                    if research_p:
                        details["research_areas"] = research_p.get_text(strip=True)
                    else:
                        next_text = research_h3.next_sibling
                        if next_text and isinstance(next_text, str):
                            details["research_areas"] = next_text.strip()

                # Education background
                edu_h3 = main_content.find("h3", string=_re.compile("教育背景|教育经历"))
                if edu_h3:
                    edu_section = edu_h3.find_next_sibling()
                    if edu_section:
                        edu_text = edu_section.get_text()
                        # Match patterns like "2013-2016 博士 耶鲁大学"
                        edu_entries = _re.findall(r"(\d{4}[-~至]\d{4}|以来|\d{4})\s+([^\n]+)", edu_text)
                        for year, content in edu_entries:
                            details["education"].append({
                                "year": year.strip(),
                                "content": content.strip(),
                            })

                # Work experience
                work_h3 = main_content.find("h3", string=_re.compile("工作经历|科研经历"))
                if work_h3:
                    work_section = work_h3.find_next_sibling()
                    if work_section:
                        work_text = work_section.get_text()
                        work_entries = _re.findall(r"(\d{4}[-~至]\d{4}|至今|\d{4})\s+([^\n]+)", work_text)
                        for year, content in work_entries:
                            details["work_experience"].append({
                                "year": year.strip(),
                                "content": content.strip(),
                            })

                # Honors and awards
                honor_h3 = main_content.find("h3", string=_re.compile("荣誉"))
                if honor_h3:
                    honor_section = honor_h3.find_next_sibling()
                    if honor_section:
                        honor_text = honor_section.get_text()
                        honor_entries = _re.findall(r"(\d{4})\s+([^\n]+)", honor_text)
                        for year, content in honor_entries:
                            details["honors"].append({
                                "year": year.strip(),
                                "content": content.strip(),
                            })

                # Publications
                pub_h3 = main_content.find("h3", string=_re.compile("发表论文|代表性论文"))
                if pub_h3:
                    pub_section = pub_h3.find_next_sibling()
                    if pub_section:
                        pub_text = pub_section.get_text()
                        pub_entries = _re.findall(r"\[(\d+)\]\s*([^\[]+)", pub_text)
                        for num, content in pub_entries:
                            details["publications"].append({
                                "number": num,
                                "content": content.strip(),
                            })

            return details

        except Exception as e:
            logger.warning("YMSCFacultyCrawler: failed to extract details from %s: %s", url, e)
            return {
                "url": url,
                "name": name_hint,
                "error": str(e),
            }

    async def fetch_and_parse(self) -> list[CrawledItem]:
        university = self.config.get("university", "清华大学")
        department = self.config.get("department", "丘成桐数学科学中心")
        source_id = self.source_id
        source_url = self.config.get("url", _LIST_URL)
        crawled_at = _now_iso()

        # Get scholar list
        scholars = await self._get_scholar_list()
        if not scholars:
            logger.warning("YMSCFacultyCrawler: no scholars found")
            return []

        items: list[CrawledItem] = []
        request_delay = self.config.get("request_delay", 0.5)

        for i, scholar in enumerate(scholars):
            if i > 0 and request_delay:
                await asyncio.sleep(request_delay)

            details = await self._extract_scholar_details(scholar["url"], scholar["name"])

            if "error" in details:
                logger.warning("YMSCFacultyCrawler: skipping %s due to error", scholar["name"])
                continue

            # Parse education records
            education_records = []
            for edu in details.get("education", []):
                year_str = edu.get("year", "")
                content = edu.get("content", "")

                # Try to parse degree and institution from content
                degree = ""
                institution = ""
                major = ""

                # Common patterns: "博士 耶鲁大学", "学士 清华大学", "硕士 北京大学"
                degree_match = _re.search(r"(博士|硕士|学士|博士后)", content)
                if degree_match:
                    degree = degree_match.group(1)
                    # Extract institution after degree
                    inst_match = _re.search(r"(博士|硕士|学士|博士后)\s+([^\n，,]+)", content)
                    if inst_match:
                        institution = inst_match.group(2).strip()
                else:
                    # If no degree keyword, treat entire content as institution
                    institution = content

                education_records.append(
                    EducationRecord(
                        degree=degree,
                        institution=institution,
                        year=year_str,
                        major=major,
                    )
                )

            # Parse awards
            award_records = []
            for honor in details.get("honors", []):
                award_records.append(
                    AwardRecord(
                        title=honor.get("content", ""),
                        year=honor.get("year", ""),
                        level="",
                        grantor="",
                        description="",
                        added_by="crawler",
                    )
                )

            # Parse publications
            pub_records = []
            for pub in details.get("publications", []):
                pub_records.append(
                    PublicationRecord(
                        title=pub.get("content", "")[:200],  # Truncate long titles
                        venue="",
                        year="",
                        authors="",
                        url="",
                        citation_count=-1,
                        is_corresponding=False,
                        added_by="crawler",
                    )
                )

            # Parse research areas
            research_areas_str = details.get("research_areas", "")
            research_areas = []
            if research_areas_str:
                # Split by common delimiters
                areas = _re.split(r"[，,、；;]+", research_areas_str)
                research_areas = [a.strip() for a in areas if a.strip()]

            # Build ScholarRecord
            record = ScholarRecord(
                name=details.get("name", scholar["name"]),
                name_en="",
                gender="",
                photo_url=details.get("photo_url", ""),
                university=university,
                department=department,
                secondary_departments=[],
                position=details.get("position", ""),
                academic_titles=[],
                is_academician=False,
                research_areas=research_areas,
                keywords=[],
                bio=details.get("bio", ""),
                bio_en="",
                email=details.get("email", ""),
                phone=details.get("phone", ""),
                office=details.get("office", ""),
                profile_url=details.get("url", scholar["url"]),
                lab_url="",
                google_scholar_url="",
                dblp_url="",
                orcid="",
                phd_institution="",
                phd_year="",
                education=education_records,
                publications_count=-1,
                h_index=-1,
                citations_count=-1,
                metrics_updated_at="",
                representative_publications=pub_records,
                patents=[],
                awards=award_records,
                # User-maintained fields (never overwritten by crawler)
                is_advisor_committee=False,
                is_adjunct_supervisor=False,
                supervised_students=[],
                joint_research_projects=[],
                joint_management_roles=[],
                academic_exchange_records=[],
                is_potential_recruit=False,
                institute_relation_notes="",
                relation_updated_by="",
                relation_updated_at="",
                recent_updates=[],
                # Metadata
                source_id=source_id,
                source_url=source_url,
                crawled_at=crawled_at,
                first_seen_at=crawled_at,
                last_seen_at=crawled_at,
                is_active=True,
                data_completeness=0,
            )

            # Compute completeness score
            record.data_completeness = compute_scholar_completeness(record)

            # Create CrawledItem
            items.append(
                CrawledItem(
                    title=record.name,
                    url=record.profile_url,
                    published_at=None,
                    author=None,
                    content=record.bio[:500] if record.bio else None,  # Preview
                    content_hash=None,
                    source_id=source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []),
                    extra=record.model_dump(),
                )
            )

        logger.info(
            "YMSCFacultyCrawler: extracted %d scholars with avg completeness %.1f%%",
            len(items),
            sum(item.extra["data_completeness"] for item in items) / len(items) if items else 0,
        )
        return items
