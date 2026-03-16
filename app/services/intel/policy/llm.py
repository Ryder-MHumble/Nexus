"""LLM enrichment for policy articles — prompt templates and response parsing."""
from __future__ import annotations

import logging
from typing import Any

from app.services.intel.shared import (
    clamp_value as _clamp,
)
from app.services.intel.shared import (
    compute_days_left as _compute_days_left,
)
from app.services.intel.shared import (
    parse_date_str as _parse_date_str,
)
from app.services.llm.llm_service import LLMError, call_llm_json

logger = logging.getLogger(__name__)

CONTENT_TRUNCATE_LEN = 3000

SYSTEM_PROMPT = """\
你是中关村人工智能研究院（ZGCAI）的政策分析专家。你的任务是分析政策/人事文件，\
评估其与研究院的相关性，并提取结构化字段。

研究院背景：
- 全称：中关村人工智能研究院
- 位于北京市海淀区中关村科学城
- 主要方向：人工智能基础研究、大模型、具身智能、AI+行业应用、人才培养
- 关注领域：科技政策、AI 政策、人才引进计划、创新资金/补贴、\
中关村/海淀/北京市政策、高校科研合作、算力基础设施

请严格以 JSON 格式输出以下字段（不要包含任何其他文本）：
{
  "summary": "1-2 句话中文摘要，50字以内",
  "importance": "紧急|重要|关注|一般",
  "matchScore": 0到100的整数,
  "relevance": 0到100的整数,
  "isOpportunity": true或false,
  "funding": "资金额度描述（如'500-1000万'）或null",
  "deadline": "YYYY-MM-DD格式截止日期或null",
  "agency": "发布机构简称（如'科技部'、'北京市科委'）",
  "signals": ["关键信号1", "关键信号2"],
  "aiInsight": "对研究院的具体建议，50字以内",
  "detail": "详细分析，100字以内",
  "leader": "涉及的领导人姓名或null",
  "tags": ["补充标签1", "补充标签2"]
}

matchScore 评分标准：
- 0-20: 与 AI/科技/教育/创新完全无关（如供水、交通法规）
- 20-40: 间接相关（一般经济政策、一般教育政策）
- 40-60: 相关领域（科研经费、科技产业、教育改革、人才政策）
- 60-80: 直接相关（AI 政策、中关村政策、研究院资金、海淀区科技）
- 80-100: 高度匹配（明确提及 AI 研究院/新型研发机构/算力补贴/大模型专项）

importance 判断标准：
- 紧急: 有明确截止日期且距今14天内，或涉及紧急政策变动
- 重要: matchScore >= 70，或标题直接涉及 AI/人工智能/中关村
- 关注: matchScore >= 40，或来自重点部门（科委/发改委/科技部）
- 一般: 其余

isOpportunity 判断：文章是否为可申报的项目/资金/补贴通知（有明确的申报条件、资金额度或截止日期）。\
仅从原文中提取，不要凭空编造。如果文中没有提及资金或截止日期，设为 false。"""

SYSTEM_PROMPT_LITE = """\
你是中关村人工智能研究院（ZGCAI）的政策分析专家。分析以下政策文件，\
生成摘要和建议。系统已通过规则引擎预先计算了 matchScore 和 importance，\
你可以微调这两个值。

研究院背景：北京海淀区中关村科学城，主攻 AI 基础研究、大模型、具身智能。

请严格以 JSON 格式输出以下字段（不要包含任何其他文本）：
{
  "summary": "1-2 句话中文摘要，50字以内",
  "matchScore": 0到100的整数（可微调预设分数）,
  "importance": "紧急|重要|关注|一般（可微调预设等级）",
  "signals": ["关键信号1", "关键信号2"],
  "aiInsight": "对研究院的具体建议，50字以内",
  "detail": "详细分析，100字以内"
}

matchScore 评分标准：
- 0-20: 与 AI/科技/教育/创新完全无关
- 20-40: 间接相关（一般经济政策、一般教育政策）
- 40-60: 相关领域（科研经费、科技产业、教育改革、人才政策）
- 60-80: 直接相关（AI 政策、中关村政策、研究院资金、海淀区科技）
- 80-100: 高度匹配（明确提及 AI 研究院/新型研发机构/算力补贴/大模型专项）"""

VALID_IMPORTANCE = {"紧急", "重要", "关注", "一般"}


def build_user_prompt(article: dict[str, Any]) -> str:
    """Build user prompt for a single article."""
    title = article.get("title", "无标题")
    content = article.get("content") or ""
    source_name = article.get("source_name", "未知来源")
    dimension = article.get("dimension", "")
    published_at = article.get("published_at") or "未知日期"
    tags = ", ".join(article.get("tags", []))

    if len(content) > CONTENT_TRUNCATE_LEN:
        content = content[:CONTENT_TRUNCATE_LEN] + "...(截断)"

    if not content.strip():
        content = "（正文不可用，请仅根据标题和来源分析）"

    return (
        f"标题：{title}\n"
        f"来源：{source_name}\n"
        f"维度：{dimension}\n"
        f"发布日期：{published_at}\n"
        f"标签：{tags}\n"
        f"正文：\n{content}"
    )


def parse_llm_response(raw: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize LLM output, merging with article metadata."""
    importance = raw.get("importance", "一般")
    if importance not in VALID_IMPORTANCE:
        importance = "一般"

    match_score = _clamp(raw.get("matchScore"), 0, 100, 0)
    relevance = _clamp(raw.get("relevance"), 0, 100, match_score)
    deadline = _parse_date_str(raw.get("deadline"))
    days_left = _compute_days_left(deadline)
    funding = raw.get("funding")
    if funding and not isinstance(funding, str):
        funding = str(funding)

    signals = raw.get("signals")
    if not isinstance(signals, list):
        signals = []
    signals = [str(s) for s in signals if s]

    llm_tags = raw.get("tags")
    if not isinstance(llm_tags, list):
        llm_tags = []
    llm_tags = [str(t) for t in llm_tags if t]

    leader = raw.get("leader")
    if leader and not isinstance(leader, str):
        leader = str(leader)

    return {
        "summary": str(raw.get("summary", article.get("title", "")[:80])),
        "importance": importance,
        "matchScore": match_score,
        "relevance": relevance,
        "isOpportunity": bool(raw.get("isOpportunity", False)),
        "funding": funding if funding and funding.lower() != "null" else None,
        "deadline": deadline,
        "daysLeft": days_left,
        "agency": str(raw.get("agency", article.get("source_name", "未知"))),
        "signals": signals,
        "aiInsight": str(raw.get("aiInsight", "")),
        "detail": str(raw.get("detail", "")),
        "leader": leader if leader and leader.lower() != "null" else None,
        "tags": llm_tags,
    }


def default_enrichment(article: dict[str, Any]) -> dict[str, Any]:
    """Return safe default enrichment when LLM fails."""
    title = article.get("title", "")
    return {
        "summary": title[:80] if title else "无摘要",
        "importance": "一般",
        "matchScore": 0,
        "relevance": 0,
        "isOpportunity": False,
        "funding": None,
        "deadline": None,
        "daysLeft": None,
        "agency": article.get("source_name", "未知"),
        "signals": [],
        "aiInsight": "",
        "detail": "",
        "leader": None,
        "tags": [],
    }


async def enrich_article(article: dict[str, Any]) -> dict[str, Any]:
    """Enrich a single article via LLM (full prompt). Returns merged enrichment dict.

    Raises LLMError if all retries fail (caller should use default_enrichment).
    """
    prompt = build_user_prompt(article)

    raw = await call_llm_json(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        temperature=0.1,
        max_tokens=1500,
        stage="policy_tier1",
        article_id=article.get("url_hash"),
        article_title=article.get("title"),
        source_id=article.get("source_id"),
        dimension=article.get("dimension"),
    )

    if not isinstance(raw, dict):
        raise LLMError(f"Expected dict from LLM, got {type(raw).__name__}")

    return parse_llm_response(raw, article)


async def enrich_article_lite(
    article: dict[str, Any],
    tier1_result: dict[str, Any],
) -> dict[str, Any]:
    """Lightweight LLM enrichment for Tier 2.

    Takes Tier 1 rule-based results and asks LLM only for summary, signals,
    aiInsight, detail, and optionally refined matchScore/importance.
    Returns a merged dict with all 13 fields.

    Raises LLMError if all retries fail.
    """
    prompt = build_user_prompt(article)
    prompt += (
        f"\n\n预设分数参考：matchScore={tier1_result['matchScore']}, "
        f"importance={tier1_result['importance']}"
    )

    raw = await call_llm_json(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT_LITE,
        temperature=0.1,
        max_tokens=800,
        stage="policy_tier2",
        article_id=article.get("url_hash"),
        article_title=article.get("title"),
        source_id=article.get("source_id"),
        dimension=article.get("dimension"),
    )

    if not isinstance(raw, dict):
        raise LLMError(f"Expected dict from LLM, got {type(raw).__name__}")

    # Start from Tier 1 result, then overlay LLM fields
    result = dict(tier1_result)
    result["summary"] = str(raw.get("summary", tier1_result.get("summary", "")))
    result["enrichment_tier"] = "llm"

    signals = raw.get("signals")
    if isinstance(signals, list):
        result["signals"] = [str(s) for s in signals if s]

    ai_insight = raw.get("aiInsight")
    if ai_insight:
        result["aiInsight"] = str(ai_insight)

    detail = raw.get("detail")
    if detail:
        result["detail"] = str(detail)

    # Let LLM adjust matchScore within ±30 of Tier 1 value
    llm_score = _clamp(raw.get("matchScore"), 0, 100, tier1_result["matchScore"])
    if abs(llm_score - tier1_result["matchScore"]) <= 30:
        result["matchScore"] = llm_score
        result["relevance"] = llm_score

    llm_importance = raw.get("importance", "")
    if llm_importance in VALID_IMPORTANCE:
        result["importance"] = llm_importance

    return result
