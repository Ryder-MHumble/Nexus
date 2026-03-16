"""LLM-Driven Faculty Crawler — 基于 LLM 的自适应学者信息爬取器

核心思路：
1. 使用 httpx 直接获取 HTML，通过正则清洗无用内容（script/style/nav等）
2. 使用 LLM 从清洗后的 HTML 提取结构化数据
3. 严格控制输入输出 token 数量，降低成本
4. 无需手写 CSS 选择器，自动适配不同网站结构

配置示例（YAML）：
  crawler_class: llm_faculty
  llm_provider: openrouter    # openrouter | siliconflow | dashscope
  llm_model: google/gemini-2.5-flash  # 推荐 gemini-2.5-flash（快速且便宜）
  max_list_tokens: 4000       # 列表页最大 token 数
  max_detail_tokens: 8000     # 详情页最大 token 数
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.schemas.scholar import (
    AwardRecord,
    EducationRecord,
    PublicationRecord,
    ScholarRecord,
    compute_scholar_completeness,
    parse_research_areas,
    validate_research_areas,
    validate_scholar_name,
)

logger = logging.getLogger(__name__)

# Regex to extract position/title from bio text
_POSITION_RE = re.compile(
    r"(教授|副教授|助理教授|讲师|研究员|副研究员|"
    r"助理研究员|博士生导师|硕士生导师|"
    r"正高级工程师|高级工程师|工程师)"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_position_from_text(text: str) -> str:
    """Try to extract position/title from the first 100 chars of bio text."""
    if not text:
        return ""
    head = text[:100]
    match = _POSITION_RE.search(head)
    return match.group(1) if match else ""


def _clean_html(html: str, max_length: int = 50000) -> str:
    """清洗 HTML，移除无用标签，保留主要内容

    清洗策略：
    1. 移除 script, style, nav, footer, header 等无用标签
    2. 移除 class/id 名含 footer/copyright 的 div
    3. 移除注释
    4. 压缩空白字符
    5. 移除常见页脚文本模式
    6. 截断过长内容
    """
    soup = BeautifulSoup(html, "lxml")

    # 移除无用标签
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()

    # 移除 class/id 名含 footer/copyright 等的 div
    # Note: decompose() clears __dict__ on child tags, so we must
    # skip tags that were already decomposed as children of a prior match.
    for tag in list(soup.find_all(["div", "section", "span"])):
        if getattr(tag, "decomposed", False) or tag.attrs is None:
            continue
        classes = " ".join(tag.get("class") or [])
        tag_id = tag.get("id") or ""
        combined = f"{classes} {tag_id}".lower()
        if any(kw in combined for kw in ("footer", "copyright", "bottom-bar", "site-info")):
            tag.decompose()

    # 移除注释
    for comment in soup.find_all(
        string=lambda text: isinstance(text, str) and text.strip().startswith("<!--")
    ):
        comment.extract()

    # 获取文本内容
    text = soup.get_text(separator="\n", strip=True)

    # 压缩多余空白
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r" +", " ", text)

    # 移除常见页脚文本模式
    text = re.sub(
        r"(?:CopyRight|Copyright|版权所有).*?(?:All Rights Reserved|保留所有权利)[。.]*",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 截断过长内容
    if len(text) > max_length:
        text = text[:max_length] + "\n...(内容过长，已截断)"

    return text


def _repair_json(text: str) -> str:
    """Attempt to repair common LLM JSON output issues.

    Handles: trailing commas, truncated arrays/objects (unclosed brackets).
    """
    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # If truncated (unclosed brackets), try to close them
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    if open_braces > 0 or open_brackets > 0:
        # Find last complete JSON object/array item
        # Try to truncate at the last complete item
        last_brace = text.rfind("}")
        last_bracket = text.rfind("]")
        last_complete = max(last_brace, last_bracket)
        if last_complete > 0:
            text = text[:last_complete + 1]
            # Re-count and close
            open_braces = text.count("{") - text.count("}")
            open_brackets = text.count("[") - text.count("]")
        # Remove trailing commas again after truncation
        text = re.sub(r",\s*$", "", text)
        text += "]" * open_brackets + "}" * open_braces

    return text


class LLMFacultyCrawler(BaseCrawler):
    """基于 LLM 的自适应学者信息爬取器"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.llm_provider = config.get("llm_provider", "openrouter")
        self.llm_model = config.get("llm_model", "google/gemini-2.5-flash")
        self.max_list_tokens = config.get("max_list_tokens", 4000)
        self.max_detail_tokens = config.get("max_detail_tokens", 8000)

        # Cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.api_calls = 0

        # API key 根据 provider 选择
        if self.llm_provider == "openrouter":
            self.llm_api_key = os.getenv("OPENROUTER_API_KEY")
            self.llm_api_url = "https://openrouter.ai/api/v1/chat/completions"
        elif self.llm_provider == "siliconflow":
            self.llm_api_key = os.getenv("SILICONFLOW_API_KEY")
            self.llm_api_url = "https://api.siliconflow.cn/v1/chat/completions"
        elif self.llm_provider == "dashscope":
            self.llm_api_key = os.getenv("DASHSCOPE_API_KEY")
            self.llm_api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        else:
            raise ValueError(f"Unsupported llm_provider: {self.llm_provider}")

        if not self.llm_api_key:
            raise ValueError(f"{self.llm_provider.upper()}_API_KEY not found in environment")

    async def _fetch_and_clean(self, url: str, max_length: int = 50000) -> str:
        """获取页面并清洗 HTML"""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                        " AppleWebKit/537.36"
                    ),
                },
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                # 自动检测编码
                response.encoding = response.encoding or "utf-8"
                html = response.text

                # 清洗 HTML
                cleaned = _clean_html(html, max_length)
                logger.debug(
                    "LLMFacultyCrawler: cleaned %d chars from %s",
                    len(cleaned), url,
                )
                return cleaned
        except httpx.TimeoutException as e:
            logger.error("LLMFacultyCrawler: timeout fetching %s: %s", url, e)
            raise
        except httpx.HTTPError as e:
            logger.error("LLMFacultyCrawler: HTTP error fetching %s: %s", url, e)
            raise

    async def _llm_extract(
        self, prompt: str, content: str,
        max_tokens: int = 2000, retry_count: int = 3,
    ) -> dict:
        """使用 LLM 从清洗后的内容中提取结构化数据，带重试机制"""
        for attempt in range(retry_count):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                    response = await client.post(
                        self.llm_api_url,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {self.llm_api_key}",
                        },
                        json={
                            "model": self.llm_model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": (
                                        "你是一个数据提取助手。"
                                        "从学术网页中提取结构化信息，"
                                        "只返回有效的 JSON，不要包含任何解释或 markdown 格式。"
                                    ),
                                },
                                {
                                    "role": "user",
                                    "content": f"{prompt}\n\n---\n\n{content}",
                                },
                            ],
                            "temperature": 0,
                            "max_tokens": max_tokens,
                        },
                    )
                    response.raise_for_status()
                    result = response.json()
                    resp_content = result["choices"][0]["message"]["content"]

                    # Track token usage
                    usage = result.get("usage", {})
                    input_tokens = usage.get("prompt_tokens", 0)
                    output_tokens = usage.get("completion_tokens", 0)
                    self.total_input_tokens += input_tokens
                    self.total_output_tokens += output_tokens
                    self.api_calls += 1
                    logger.debug(
                        "LLMFacultyCrawler: API call #%d - input: %d, output: %d tokens",
                        self.api_calls, input_tokens, output_tokens
                    )

                    # 清理可能的 markdown 代码块
                    resp_content = resp_content.strip()
                    if resp_content.startswith("```json"):
                        resp_content = resp_content[7:]
                    if resp_content.startswith("```"):
                        resp_content = resp_content[3:]
                    if resp_content.endswith("```"):
                        resp_content = resp_content[:-3]
                    resp_content = resp_content.strip()

                    return json.loads(_repair_json(resp_content))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(
                    "LLMFacultyCrawler: JSON parse error attempt %d/%d: %s",
                    attempt + 1, retry_count, e,
                )
                if attempt == retry_count - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            except httpx.TimeoutException as e:
                logger.warning(
                    "LLMFacultyCrawler: timeout attempt %d/%d: %s",
                    attempt + 1, retry_count, e,
                )
                if attempt == retry_count - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
            except httpx.HTTPError as e:
                logger.warning(
                    "LLMFacultyCrawler: HTTP error attempt %d/%d: %s",
                    attempt + 1, retry_count, e,
                )
                if attempt == retry_count - 1:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def _extract_scholar_list(self, list_url: str) -> list[dict]:
        """从列表页提取学者信息"""
        logger.info("LLMFacultyCrawler: fetching list page %s", list_url)
        try:
            content = await self._fetch_and_clean(list_url, max_length=30000)
        except Exception as e:
            logger.error(
                "LLMFacultyCrawler: failed to fetch list page: %s", e, exc_info=True,
            )
            return []

        prompt = """从这个页面提取所有教师/学者信息。

返回 JSON 数组，每个元素包含：
- name: 学者姓名（中文或英文）
- profile_url: 个人主页链接（完整 URL，如 https://xxx.edu.cn/info/1234.htm）
- position: 职称（如"教授"、"副教授"、"助理教授"），如果页面上有的话
- email: 邮箱地址，如果页面上有的话
- research_areas: 研究方向，如果页面上有的话（字符串形式）

示例输出：
[
  {
    "name": "张三",
    "profile_url": "https://example.edu.cn/info/1234.htm",
    "position": "教授",
    "email": "zhangsan@example.edu.cn",
    "research_areas": "机器学习、计算机视觉"
  }
]

重要规则：
1. 只包含有有效个人主页链接的真实学者/教师，不要包含导航链接、网站栏目名称
2. profile_url 必须是完整的 URL，不能是相对路径
3. 如果没找到学者，返回空数组 []"""

        try:
            scholars = await self._llm_extract(prompt, content, max_tokens=self.max_list_tokens)
            if not isinstance(scholars, list):
                logger.error("LLMFacultyCrawler: expected list, got %s", type(scholars).__name__)
                return []
            logger.info("LLMFacultyCrawler: extracted %d scholars from list page", len(scholars))
            return scholars
        except Exception as e:
            logger.error("LLMFacultyCrawler: failed to extract scholar list: %s", e)
            return []

    async def _extract_scholar_details(self, profile_url: str, name_hint: str) -> dict:
        """从详情页提取学者详细信息"""
        try:
            content = await self._fetch_and_clean(profile_url, max_length=40000)

            prompt = f"""从这个页面提取学者 "{name_hint}" 的详细信息。

返回 JSON 对象，包含以下字段（缺失的字段用空字符串 "" 或空数组 []）：

{{
  "name": "学者姓名",
  "name_en": "英文姓名（如果有）",
  "position": "职称（教授/副教授/研究员/讲师等），必须提取",
  "email": "邮箱地址",
  "phone": "电话号码",
  "office": "办公室地址",
  "homepage": "个人主页 URL",
  "photo_url": "照片 URL（如果有）",
  "research_areas": "研究方向关键词，逗号分隔，不含页脚/导航",
  "bio": "学术简介叙述文字，不含教育/工作经历列表",
  "education": [
    {{"year": "2010-2014", "degree": "博士", "institution": "清华大学", "major": "计算机科学"}}
  ],
  "work_experience": [
    {{"year": "2020-至今", "position": "教授", "institution": "清华大学"}}
  ],
  "awards": [
    {{"year": "2020", "title": "国家自然科学奖二等奖"}}
  ],
  "publications": [
    {{"title": "论文标题", "venue": "会议/期刊", "year": "2023", "authors": "作者列表（如有）"}}
  ]
}}

重要规则：
1. position（职称）必须填写，从页面中提取（教授、副教授、研究员、讲师等）
2. bio 只放叙述性简介文字，不要放结构化数据（教育/工作经历请用对应字段）
3. research_areas 只放研究领域关键词，不要放导航链接、版权信息或联系方式
4. 不要把页面底部的版权声明、地址、电话等页脚信息放入任何字段
5. education 和 work_experience 要分开提取，不要混入 bio
6. publications 尽可能提取代表性论文（标题、期刊/会议、年份）
7. awards 提取所有能找到的奖项/荣誉"""

            details = await self._llm_extract(prompt, content, max_tokens=self.max_detail_tokens)
            return details

        except Exception as e:
            logger.warning(
                "LLMFacultyCrawler: failed to extract details from %s: %s",
                profile_url, e,
            )
            return {"name": name_hint, "error": str(e)}

    async def fetch_and_parse(self) -> list[CrawledItem]:
        university = self.config.get("university", "")
        department = self.config.get("department", "")
        source_id = self.source_id
        source_url = self.config.get("url")
        crawled_at = _now_iso()

        # Step 1: Extract scholar list from list page
        try:
            scholars = await self._extract_scholar_list(source_url)
        except Exception as e:
            logger.error("LLMFacultyCrawler: failed to extract scholar list: %s", e)
            return []

        if not scholars:
            logger.warning("LLMFacultyCrawler: no scholars found")
            return []

        logger.info(
            "LLMFacultyCrawler: found %d scholars, starting detail extraction",
            len(scholars),
        )

        # Step 2: Extract details for each scholar
        items: list[CrawledItem] = []
        request_delay = self.config.get("request_delay", 2.0)  # Higher delay for API rate limits

        for i, scholar in enumerate(scholars):
            if i > 0 and request_delay:
                await asyncio.sleep(request_delay)

            profile_url = scholar.get("profile_url", "")
            name = scholar.get("name", "")

            if not profile_url or not name:
                logger.debug("LLMFacultyCrawler: skipping scholar with missing url or name")
                continue

            # Validate name is a real person, not a nav/menu item
            if not validate_scholar_name(name):
                logger.debug("LLMFacultyCrawler: skipping non-scholar name %r", name)
                continue

            logger.info("LLMFacultyCrawler: [%d/%d] processing %s", i + 1, len(scholars), name)

            try:
                # Fetch details
                details = await self._extract_scholar_details(profile_url, name)

                if "error" in details:
                    logger.warning(
                        "LLMFacultyCrawler: skipping %s due to error: %s",
                        name, details.get("error"),
                    )
                    continue
            except Exception as e:
                logger.error("LLMFacultyCrawler: exception processing %s: %s", name, e)
                continue

            # Merge list page data with detail page data
            merged = {**scholar, **details}

            # Parse education records
            education_records = []
            for edu in merged.get("education", []):
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
            for award in merged.get("awards", []):
                award_records.append(
                    AwardRecord(
                        title=award.get("title", ""),
                        year=award.get("year", ""),
                        level="",
                        grantor="",
                        description="",
                        added_by="crawler",
                    )
                )

            # Parse publications
            pub_records = []
            for pub in merged.get("publications", []):
                pub_records.append(
                    PublicationRecord(
                        title=pub.get("title", ""),
                        venue=pub.get("venue", ""),
                        year=pub.get("year", ""),
                        authors=pub.get("authors", ""),
                        url="",
                        citation_count=-1,
                        is_corresponding=False,
                        added_by="crawler",
                    )
                )

            # Parse research areas + validate
            # LLM may return a string or a list
            ra_raw = merged.get("research_areas", "")
            if isinstance(ra_raw, list):
                research_areas = [str(x).strip() for x in ra_raw if x]
            elif ra_raw:
                research_areas = parse_research_areas(ra_raw)
            else:
                research_areas = []
            research_areas = validate_research_areas(research_areas)

            # Post-process: extract position from bio if LLM left it empty
            position = merged.get("position", "")
            if not position:
                position = _extract_position_from_text(merged.get("bio", ""))

            # Build ScholarRecord — bio is clean narrative only, no work_experience appended
            record = ScholarRecord(
                name=merged.get("name", name),
                name_en=merged.get("name_en", ""),
                gender="",
                photo_url=merged.get("photo_url", ""),
                university=university,
                department=department,
                secondary_departments=[],
                position=position,
                academic_titles=[],
                is_academician=False,
                research_areas=research_areas,
                keywords=[],
                bio=merged.get("bio", "").strip(),
                bio_en="",
                email=merged.get("email", ""),
                phone=merged.get("phone", ""),
                office=merged.get("office", ""),
                profile_url=profile_url,
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
                    extra=record.model_dump(),
                )
            )

        # Calculate cost estimate
        cost_per_m_input = 0.27 if "deepseek" in self.llm_model.lower() else 1.25
        cost_per_m_output = 1.10 if "deepseek" in self.llm_model.lower() else 5.0
        estimated_cost = (
            self.total_input_tokens / 1_000_000 * cost_per_m_input
            + self.total_output_tokens / 1_000_000 * cost_per_m_output
        )

        logger.info(
            "LLMFacultyCrawler: extracted %d scholars with avg completeness %.1f%%",
            len(items),
            sum(item.extra["data_completeness"] for item in items) / len(items) if items else 0,
        )
        logger.info(
            "LLMFacultyCrawler: API stats - calls: %d, "
            "input: %d, output: %d tokens, cost: $%.4f",
            self.api_calls, self.total_input_tokens,
            self.total_output_tokens, estimated_cost,
        )
        return items
