"""LLM-based faculty field extractor — data cleaner for mixed/unstructured text.

This module provides intelligent extraction of faculty information from raw HTML text
using LLM. It's designed to handle cases where multiple fields are mixed in a single
HTML element (e.g., "电话：62785564" in a <p> tag).

Role: Data Cleaner (not a full crawler)
- Input: raw text from HTML elements
- Output: structured fields mapped to ScholarRecord schema
- Cost: ~$0.01-0.02 per scholar (using Deepseek V3)
"""
from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)


async def extract_faculty_fields_with_llm(
    raw_name: str = "",
    raw_bio: str = "",
    raw_position: str = "",
    detail_html_text: str = "",
    fields_to_extract: list[str] | None = None,
    llm_provider: str = "openrouter",
    llm_model: str = "google/gemini-2.5-flash",
    max_tokens: int = 2000,
) -> dict:
    """Extract faculty fields from raw text using LLM."""
    if fields_to_extract is None:
        fields_to_extract = ["phone", "research_areas", "education", "work_experience"]

    # Get API key
    if llm_provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        api_url = "https://openrouter.ai/api/v1/chat/completions"
    elif llm_provider == "siliconflow":
        api_key = os.getenv("SILICONFLOW_API_KEY")
        api_url = "https://api.siliconflow.cn/v1/chat/completions"
    elif llm_provider == "dashscope":
        api_key = os.getenv("DASHSCOPE_API_KEY")
        api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    else:
        logger.error("Unsupported LLM provider: %s", llm_provider)
        return {}

    if not api_key:
        logger.error("%s_API_KEY not found in environment", llm_provider.upper())
        return {}

    # Build prompt
    prompt = _build_extraction_prompt(
        raw_name=raw_name,
        raw_bio=raw_bio,
        raw_position=raw_position,
        detail_html_text=detail_html_text,
        fields_to_extract=fields_to_extract,
    )

    # Call LLM
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            response = await client.post(
                api_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": llm_model,
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
                            "content": prompt,
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
            logger.debug(
                "LLM extraction: input=%d tokens, output=%d tokens",
                input_tokens,
                output_tokens,
            )

            # Parse JSON response
            resp_content = resp_content.strip()
            if resp_content.startswith("```json"):
                resp_content = resp_content[7:]
            if resp_content.startswith("```"):
                resp_content = resp_content[3:]
            if resp_content.endswith("```"):
                resp_content = resp_content[:-3]
            resp_content = resp_content.strip()

            extracted = json.loads(resp_content)
            logger.debug("LLM extracted fields: %s", list(extracted.keys()))
            return extracted

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse LLM JSON response: %s", e)
        return {}
    except httpx.HTTPError as e:
        logger.warning("LLM API error: %s", e)
        return {}
    except Exception as e:
        logger.warning("Unexpected error in LLM extraction: %s", e)
        return {}


def _build_extraction_prompt(
    raw_name: str,
    raw_bio: str,
    raw_position: str,
    detail_html_text: str,
    fields_to_extract: list[str],
) -> str:
    """Build the LLM prompt for field extraction."""
    context = f"""学者信息：
姓名: {raw_name}
职位: {raw_position}
简介: {raw_bio[:500] if raw_bio else "(无)"}

详情页文本（前 2000 字符）:
{detail_html_text[:2000] if detail_html_text else "(无)"}
"""

    fields_desc = {
        "phone": "电话号码（格式：数字，可能包含 - 或空格）",
        "research_areas": "研究方向/研究领域（数组，每个方向一个字符串）",
        "education": "教育背景（数组，每个元素包含 year, degree, institution, major）",
        "work_experience": "工作经历/学术兼职（数组，每个元素包含 year, position, institution）",
        "awards": "奖励/荣誉（数组，每个元素包含 year, title）",
        "publications": "代表性论文（数组，每个元素包含 title, venue, year）",
    }

    fields_to_extract_desc = "\n".join(
        f"- {field}: {fields_desc.get(field, field)}"
        for field in fields_to_extract
    )

    prompt = f"""{context}

从上述信息中提取以下字段。缺失的字段用空字符串 "" 或空数组 [] 表示。

需要提取的字段：
{fields_to_extract_desc}

返回 JSON 格式（只返回 JSON，不要其他内容）：
{{
  "phone": "...",
  "research_areas": [...],
  "education": [...],
  "work_experience": [...],
  "awards": [...],
  "publications": [...]
}}

注意：
1. 对于数组字段，如果没有找到，返回空数组 []
2. 对于字符串字段，如果没有找到，返回空字符串 ""
3. 只提取明确的信息，不要推测或编造
4. 日期格式统一为 "YYYY" 或 "YYYY-YYYY"
5. research_areas 只放研究方向关键词，不要放导航链接、版权信息、联系方式或工作经历
6. 不要将工作经历（含年份范围如"2018年—今"）放入 research_areas
7. 不要将页脚信息（含地址、邮编、CopyRight等）放入任何字段
"""
    return prompt
