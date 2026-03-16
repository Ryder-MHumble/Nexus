"""Faculty Crawler for Tsinghua CS Department

清华大学计算机系师资爬虫
基于 CSS 选择器的精确爬取

网页结构：
  people01
    └─ dl (学部)
       └─ dd
          └─ ul
             └─ li (学者)
                └─ a href="./info/xxxx/xxxx.htm"
"""
from __future__ import annotations

import asyncio
import logging
import re as _re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.http_client import fetch_page
from app.schemas.scholar import (
    AwardRecord,
    EducationRecord,
    PublicationRecord,
    ScholarRecord,
    compute_scholar_completeness,
    parse_research_areas,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.cs.tsinghua.edu.cn"
_LIST_URL = "https://www.cs.tsinghua.edu.cn/szzk/jzgml.htm"


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
    return urljoin(base_url, href)


class TsinghuaCsFacultyCrawler(BaseCrawler):
    """清华大学计算机系师资爬虫"""

    async def _get_scholar_list(self) -> list[dict]:
        """获取所有学者列表"""
        try:
            html = await fetch_page(_LIST_URL)
            soup = BeautifulSoup(html, "lxml")

            scholar_links = []

            # 遍历所有 dl（研究所/部门）
            for dl in soup.find_all("dl"):
                # 找到 dd（学者列表容器）
                dd = dl.find("dd")
                if not dd:
                    continue

                # 找到 ul（学者列表）
                ul = dd.find("ul")
                if not ul:
                    continue

                # 遍历所有 li（学者）
                for li in ul.find_all("li"):
                    # 找到学者名字链接（在 h2 > a 中）
                    h2 = li.find("h2")
                    if not h2:
                        continue

                    a = h2.find("a", href=True)
                    if not a:
                        continue

                    href = a.get("href", "")
                    text = a.get_text(strip=True)

                    if text and href:
                        full_url = _normalize_url(_BASE_URL, href)
                        scholar_links.append({
                            "name": text,
                            "url": full_url,
                        })

            logger.info("TsinghuaCsFacultyCrawler: found %d scholars", len(scholar_links))
            return scholar_links

        except Exception as e:
            logger.error("TsinghuaCsFacultyCrawler: failed to get scholar list: %s", e)
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

            # 提取标题
            title = soup.find("title")
            if title:
                title_text = title.get_text()
                details["name"] = title_text.split("-")[0].strip() if "-" in title_text else title_text.strip()

            # 找到主要内容区域
            main_content = soup.find("div", class_="v_news_content")
            if not main_content:
                main_content = soup.find("div", class_="content")
            if not main_content:
                main_content = soup.find("div", class_="main")

            if main_content:
                # 提取完整文本作为 bio
                full_text = main_content.get_text(separator="\n", strip=True)
                details["bio"] = _re.sub(r"\n\s*\n", "\n", full_text)

                # 提取邮箱
                email = _extract_email_from_text(full_text)
                if email:
                    details["email"] = email

                # 提取职位（从 "职称：" 后面）
                position_match = _re.search(r"职称[：:]\s*([^\n]+)", full_text)
                if position_match:
                    details["position"] = position_match.group(1).strip()

                # 提取研究方向（从 "研究领域：" 后面）
                research_match = _re.search(r"研究领域[：:]\s*([^\n]+)", full_text)
                if research_match:
                    details["research_areas"] = research_match.group(1).strip()

                # 按 h4 标题分段提取信息
                for h4 in main_content.find_all("h4"):
                    # 获取该 h4 后面的所有 p 标签，直到下一个 h4
                    paragraphs = []
                    current = h4.find_next_sibling()
                    while current and current.name != "h4":
                        if current.name == "p":
                            para_text = current.get_text(strip=True)
                            if para_text:
                                paragraphs.append(para_text)
                        current = current.find_next_sibling()

                    # 第一个段落通常是标题，用它来确定分类
                    if not paragraphs:
                        continue
                    section_title = paragraphs[0]
                    data_paragraphs = paragraphs[1:]  # 跳过标题段落

                    # 根据标题类型处理
                    if "教育" in section_title:
                        for para in data_paragraphs:
                            # 匹配 "学位 (专业), 学校, 国家, 年份" 的模式
                            match = _re.match(r"([^,，]+)\s*\(([^)）]*)\)\s*,\s*([^,，]+)\s*,\s*([^,，]+)\s*,\s*(\d{4})", para)
                            if match:
                                details["education"].append({
                                    "year": match.group(5),
                                    "degree": match.group(1).strip(),
                                    "institution": match.group(3).strip(),
                                    "major": match.group(2).strip(),
                                })

                    elif "奖励" in section_title or "荣誉" in section_title:
                        for para in data_paragraphs:
                            # 匹配 "奖项名称 (年份)" 或 "奖项名称 (年份)"
                            year_match = _re.search(r"\((\d{4})\)", para)
                            year = year_match.group(1) if year_match else ""
                            details["honors"].append({
                                "year": year,
                                "content": para,
                            })

                    elif "学术成果" in section_title or "论文" in section_title:
                        for para in data_paragraphs:
                            if para.startswith("["):
                                # 匹配 "[1] 论文标题..."
                                match = _re.match(r"\[(\d+)\]\s*(.+)", para)
                                if match:
                                    details["publications"].append({
                                        "number": match.group(1),
                                        "content": match.group(2),
                                    })

            return details

        except Exception as e:
            logger.warning("TsinghuaCsFacultyCrawler: failed to extract details from %s: %s", url, e)
            return {
                "url": url,
                "name": name_hint,
                "error": str(e),
            }

    async def fetch_and_parse(self) -> list[CrawledItem]:
        university = self.config.get("university", "清华大学")
        department = self.config.get("department", "计算机科学与技术系")
        source_id = self.source_id
        source_url = self.config.get("url", _LIST_URL)
        crawled_at = _now_iso()

        # Get scholar list
        scholars = await self._get_scholar_list()
        if not scholars:
            logger.warning("TsinghuaCsFacultyCrawler: no scholars found")
            return []

        items: list[CrawledItem] = []
        request_delay = self.config.get("request_delay", 0.5)

        for i, scholar in enumerate(scholars):
            if i > 0 and request_delay:
                await asyncio.sleep(request_delay)

            details = await self._extract_scholar_details(scholar["url"], scholar["name"])

            if "error" in details:
                logger.warning("TsinghuaCsFacultyCrawler: skipping %s due to error", scholar["name"])
                continue

            # Parse education records
            education_records = []
            for edu in details.get("education", []):
                education_records.append(
                    EducationRecord(
                        degree=edu.get("degree", ""),
                        institution=edu.get("institution", ""),
                        year=edu.get("year", ""),
                        major=edu.get("major", ""),
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
                        title=pub.get("content", "")[:200],
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
            research_areas = parse_research_areas(research_areas_str) if research_areas_str else []

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
                source_id=source_id,
                source_url=source_url,
                crawled_at=crawled_at,
                first_seen_at=crawled_at,
                last_seen_at=crawled_at,
                is_active=True,
                data_completeness=0,
            )

            record.data_completeness = compute_scholar_completeness(record)

            # Convert ScholarRecord to dict for JSON serialization
            record_dict = {
                "name": record.name,
                "name_en": record.name_en,
                "gender": record.gender,
                "photo_url": record.photo_url,
                "university": record.university,
                "department": record.department,
                "secondary_departments": record.secondary_departments,
                "position": record.position,
                "academic_titles": record.academic_titles,
                "is_academician": record.is_academician,
                "research_areas": record.research_areas,
                "keywords": record.keywords,
                "bio": record.bio,
                "bio_en": record.bio_en,
                "email": record.email,
                "phone": record.phone,
                "office": record.office,
                "profile_url": record.profile_url,
                "lab_url": record.lab_url,
                "google_scholar_url": record.google_scholar_url,
                "dblp_url": record.dblp_url,
                "orcid": record.orcid,
                "phd_institution": record.phd_institution,
                "phd_year": record.phd_year,
                "education": [edu.__dict__ for edu in record.education],
                "publications_count": record.publications_count,
                "h_index": record.h_index,
                "citations_count": record.citations_count,
                "metrics_updated_at": record.metrics_updated_at,
                "representative_publications": [pub.__dict__ for pub in record.representative_publications],
                "patents": record.patents,
                "awards": [award.__dict__ for award in record.awards],
                "is_advisor_committee": record.is_advisor_committee,
                "is_adjunct_supervisor": record.is_adjunct_supervisor,
                "supervised_students": record.supervised_students,
                "joint_research_projects": record.joint_research_projects,
                "joint_management_roles": record.joint_management_roles,
                "academic_exchange_records": record.academic_exchange_records,
                "is_potential_recruit": record.is_potential_recruit,
                "institute_relation_notes": record.institute_relation_notes,
                "relation_updated_by": record.relation_updated_by,
                "relation_updated_at": record.relation_updated_at,
                "recent_updates": record.recent_updates,
                "source_id": record.source_id,
                "source_url": record.source_url,
                "crawled_at": record.crawled_at,
                "first_seen_at": record.first_seen_at,
                "last_seen_at": record.last_seen_at,
                "is_active": record.is_active,
                "data_completeness": record.data_completeness,
            }

            items.append(
                CrawledItem(
                    title=record.name,
                    url=record.profile_url,
                    published_at=None,
                    author=None,
                    content=record.bio[:500] if record.bio else None,
                    content_hash=None,
                    source_id=source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []),
                    extra=record_dict,
                )
            )

        logger.info(
            "TsinghuaCsFacultyCrawler: extracted %d scholars with avg completeness %.1f%%",
            len(items),
            sum(item.extra["data_completeness"] for item in items) / len(items) if items else 0,
        )
        return items
