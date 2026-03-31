"""LLM narrative generation for AI Daily Briefing.

Contains prompt templates, LLM interaction, response validation,
and fallback generation for when LLM is unavailable.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.services.llm.llm_service import LLMError, call_llm_json

logger = logging.getLogger(__name__)

# Allowed moduleId values for validation
VALID_MODULE_IDS = frozenset({
    "policy-intel",
    "tech-frontier",
    "talent-radar",
    "university-eco",
    "smart-schedule",
})

SYSTEM_PROMPT = """\
你是一个通用科技情报平台的 AI 助理。你的任务是根据今日爬取的信息数据，
生成一份详细的「AI 日报」，供平台使用者全面了解当日各维度的重要信息动态。

## 输出格式要求

你必须输出严格的 JSON，格式如下：
{
  "paragraphs": [
    [
      "今日有N件事项值得优先关注。",
      {"text": "某某政策标题", "moduleId": "policy-intel",
       "articleId": "#a1b2c3d4", "action": "查看政策"},
      "（某某说明文字），",
      {"text": "另一条重要信息", "moduleId": "tech-frontier",
       "articleId": "#e5f6g7h8"},
      "。"
    ]
  ],
  "summary": "纯文本摘要（80字以内，不含链接标记）"
}

## 段落结构规则

1. 每段是一个 JSON 数组，包含字符串和链接对象交替排列
2. 字符串 = 叙事连接文字（如"政策方面，"、"技术前沿，"、"此外，"）
3. 链接对象 = {"text": "高亮信息", "moduleId": "模块ID",
     "articleId": "#ID", "action": "操作文字"}
   - text: 必须引用真实的文章标题或关键事实（不要编造）
   - moduleId: 必须是以下之一:
     policy-intel | tech-frontier | talent-radar | university-eco | smart-schedule
   - articleId: 必须是文章列表中的 [#xxxxxxxx] 标识（如 "#a1b2c3d4"），用于关联原文
   - action: 可选操作按钮文字（如 "查看政策"、"查看前沿"、"查看详情"）
4. 每段 3-10 个 segment，确保叙事流畅自然
5. 总共 5-8 段

## 分段策略（必须按维度组织，每个有内容的维度至少一段）

- 第1段：总览开头，概述当日信息全貌，点出最重要的1-2条跨维度亮点
- 第2段：政策情报（policy-intel）— 国家+北京政策，高匹配度政策优先，提及资金/截止日
- 第3段：科技前沿（tech-frontier）— 技术突破、AI进展、产业动态，按主题归纳
- 第4段：高校动态（university-eco）— 高校科研成果、重要合作、学术进展
- 第5段：人事动态（talent-radar）— 重要人事任免、人才政策变化
- 第6段：活动会议（smart-schedule）— 近期重要会议、活动、峰会
- 可省略无内容的维度，但有内容的维度必须覆盖
- 若某维度内容特别丰富，可拆分为两段

## 内容聚合要求（重要！）

- 每个维度段落中，不要只列一条新闻，要尽量覆盖该维度的多条重要信息（3-5条）
- 同类信息要归纳聚合，如"中科院发布多项人事任免"而非逐一罗列
- 用"此外"、"同时"、"另外"、"值得关注的是"等连接词串联同一维度的多条信息
- 提炼趋势和主题，如"AI领域本日多条消息聚焦大模型应用落地"
- 每条引用必须基于输入数据中的真实文章，绝不编造标题或事实

## 叙事风格

- 像智能情报助理向平台使用者做每日信息汇报
- 优先报告：紧急截止日、高匹配度政策、重大技术突破、重要人事变动
- 提及具体数字（如"匹配度98%"、"资金500万"、"仅剩3天"）
- 充分利用「正文摘要」中的信息：人事任免必须提及具体职位，政策必须提及核心内容
- 高校动态要提及具体学校和成果，技术新闻要提及关键技术细节
- 中文输出，专业简洁，信息密度高

## moduleId 含义
- policy-intel: 国家政策 + 北京政策
- tech-frontier: 技术动态 + 产业动态 + Twitter/KOL
- talent-radar: 人才政策 + 人事变动
- university-eco: 高校动态
- smart-schedule: 活动会议日程"""


# ---------------------------------------------------------------------------
# LLM narrative generation
# ---------------------------------------------------------------------------


async def generate_briefing_narrative(
    llm_input: str,
    metric_summary: str,
    article_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call LLM to generate the narrative briefing.

    Args:
        llm_input: Structured article list (from rules.prepare_llm_input).
        metric_summary: Short statistics summary for context.
        article_index: Mapping from short ID to article metadata for
            post-processing (injecting url/contentSnippet).

    Returns:
        Parsed JSON with 'paragraphs' and 'summary' keys.

    Raises:
        LLMError: If the API call fails after retries.
    """
    user_prompt = (
        f"## 今日数据统计\n{metric_summary}\n\n"
        f"## 今日文章列表（按维度分组）\n{llm_input}\n\n"
        "请根据以上数据生成 AI 日报，确保每个有数据的维度都有覆盖，"
        "每个维度段落中引用该维度最重要的3-5条文章。"
    )

    briefing_model = settings.BRIEFING_LLM_MODEL
    logger.info("Using model %s for daily briefing generation", briefing_model)

    raw = await call_llm_json(
        prompt=user_prompt,
        system_prompt=SYSTEM_PROMPT,
        model=briefing_model,
        temperature=0.3,
        max_tokens=8000,
        stage="daily_briefing_generation",
    )

    if not isinstance(raw, dict):
        raise LLMError(f"Expected dict from LLM, got {type(raw).__name__}")

    return _validate_and_normalize(raw, article_index=article_index or {})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_and_normalize(
    raw: dict[str, Any],
    article_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate and normalize LLM output.

    Ensures:
    - paragraphs is a list of lists
    - Each segment is either a string or a dict with valid moduleId
    - Invalid moduleIds are corrected or stripped to plain text
    - Article metadata (url, contentSnippet, sourceName) is injected
      from article_index using articleId
    """
    idx = article_index or {}

    paragraphs = raw.get("paragraphs")
    if not isinstance(paragraphs, list):
        logger.warning("LLM output missing 'paragraphs' key, using summary fallback")
        summary = raw.get("summary", "今日暂无重要信息更新。")
        return {
            "paragraphs": [[summary]],
            "summary": summary,
        }

    cleaned_paragraphs: list[list[str | dict[str, str]]] = []
    for paragraph in paragraphs:
        if not isinstance(paragraph, list):
            if isinstance(paragraph, str):
                cleaned_paragraphs.append([paragraph])
            continue

        cleaned_segments: list[str | dict[str, str]] = []
        for segment in paragraph:
            if isinstance(segment, str):
                cleaned_segments.append(segment)
            elif isinstance(segment, dict):
                text = segment.get("text", "")
                module_id = segment.get("moduleId", "")
                if not text:
                    continue
                if module_id not in VALID_MODULE_IDS:
                    logger.warning(
                        "Invalid moduleId '%s', stripping to plain text", module_id
                    )
                    cleaned_segments.append(text)
                else:
                    link: dict[str, str] = {
                        "text": text,
                        "moduleId": module_id,
                    }
                    action = segment.get("action")
                    if action:
                        link["action"] = action

                    # Inject article metadata from index
                    article_id = segment.get("articleId", "")
                    # Normalize: strip leading '#' if present
                    short_id = article_id.lstrip("#") if article_id else ""
                    if short_id and short_id in idx:
                        meta = idx[short_id]
                        if meta.get("url"):
                            link["url"] = meta["url"]
                        if meta.get("contentSnippet"):
                            link["contentSnippet"] = meta["contentSnippet"]
                        if meta.get("sourceName"):
                            link["sourceName"] = meta["sourceName"]

                    cleaned_segments.append(link)

        if cleaned_segments:
            cleaned_paragraphs.append(cleaned_segments)

    if not cleaned_paragraphs:
        summary = raw.get("summary", "今日暂无重要信息更新。")
        return {"paragraphs": [[summary]], "summary": summary}

    return {
        "paragraphs": cleaned_paragraphs,
        "summary": raw.get("summary"),
    }


# ---------------------------------------------------------------------------
# Fallback (no LLM)
# ---------------------------------------------------------------------------


def _make_link(article: dict[str, Any], module_id: str,
               action: str | None = None, max_title: int = 60) -> dict[str, str]:
    """Build a link segment dict with article metadata."""
    link: dict[str, str] = {
        "text": (article.get("title") or "")[:max_title],
        "moduleId": module_id,
    }
    if action:
        link["action"] = action
    url = article.get("url", "")
    if url:
        link["url"] = url
    content = (article.get("content") or "").strip()
    if content:
        link["contentSnippet"] = content[:200]
    source_name = article.get("source_name", "")
    if source_name:
        link["sourceName"] = source_name
    return link


def build_fallback_briefing(
    articles_by_dim: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Generate a rule-based briefing without LLM.

    Produces per-dimension paragraphs referencing top articles from each group.
    """
    paragraphs: list[list[str | dict[str, str]]] = []
    total = sum(len(v) for v in articles_by_dim.values())
    dim_count = len([d for d, v in articles_by_dim.items() if v])

    # Opening paragraph
    opening: list[str | dict[str, str]] = [
        f"今日共监测到{total}条信息更新，覆盖{dim_count}个维度。",
    ]
    # Add the single most important highlight across all dimensions
    policy_articles = (
        articles_by_dim.get("national_policy", [])
        + articles_by_dim.get("beijing_policy", [])
    )
    if policy_articles:
        opening.append("最新政策方面，")
        opening.append(_make_link(policy_articles[0], "policy-intel", action="查看政策"))
        opening.append("值得优先关注。")
    else:
        opening.append("以下是各维度重要信息汇总。")
    paragraphs.append(opening)

    # Policy paragraph (if more than the one mentioned in opening)
    if len(policy_articles) > 1:
        policy_para: list[str | dict[str, str]] = ["政策情报方面，除上述政策外，"]
        for i, art in enumerate(policy_articles[1:3]):
            if i > 0:
                policy_para.append("同时，")
            policy_para.append(_make_link(art, "policy-intel", action="查看政策"))
            policy_para.append("，")
        policy_para.append(f"共{len(policy_articles)}条政策信息。")
        paragraphs.append(policy_para)

    # Tech paragraph
    tech_articles = (
        articles_by_dim.get("technology", [])
        + articles_by_dim.get("industry", [])
    )
    if tech_articles:
        tech_para: list[str | dict[str, str]] = [
            f"科技前沿方面，今日共{len(tech_articles)}条动态。",
        ]
        for i, art in enumerate(tech_articles[:3]):
            if i > 0:
                tech_para.append("此外，")
            tech_para.append(_make_link(art, "tech-frontier", action="查看前沿"))
            tech_para.append("。")
        paragraphs.append(tech_para)

    # University paragraph
    uni_articles = articles_by_dim.get("universities", [])
    if uni_articles:
        uni_para: list[str | dict[str, str]] = [
            f"高校动态方面，今日共{len(uni_articles)}条更新。",
        ]
        for i, art in enumerate(uni_articles[:3]):
            if i > 0:
                uni_para.append("另外，")
            uni_para.append(_make_link(art, "university-eco"))
            uni_para.append("。")
        paragraphs.append(uni_para)

    # Personnel paragraph
    personnel_articles = articles_by_dim.get("personnel", [])
    talent_articles = articles_by_dim.get("talent", [])
    if personnel_articles or talent_articles:
        hr_para: list[str | dict[str, str]] = ["人事动态方面，"]
        combined = personnel_articles[:2] + talent_articles[:2]
        for i, art in enumerate(combined[:3]):
            module = "talent-radar"
            if i > 0:
                hr_para.append("同时，")
            hr_para.append(_make_link(art, module))
            hr_para.append("。")
        paragraphs.append(hr_para)

    # Events paragraph
    events_articles = articles_by_dim.get("events", [])
    if events_articles:
        events_para: list[str | dict[str, str]] = [
            f"活动会议方面，今日共{len(events_articles)}条信息。",
        ]
        for i, art in enumerate(events_articles[:2]):
            if i > 0:
                events_para.append("此外，")
            events_para.append(_make_link(art, "smart-schedule"))
            events_para.append("。")
        paragraphs.append(events_para)

    summary_parts = []
    if policy_articles:
        summary_parts.append(f"{len(policy_articles)}条政策")
    if tech_articles:
        summary_parts.append(f"{len(tech_articles)}条科技动态")
    if uni_articles:
        summary_parts.append(f"{len(uni_articles)}条高校动态")
    summary = f"今日共{total}条信息：{'、'.join(summary_parts)}等。"

    return {
        "paragraphs": paragraphs,
        "summary": summary,
    }
