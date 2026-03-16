"""LLM enrichment for Tech Frontier — topic summaries, insights, and opportunity assessment."""
from __future__ import annotations

import logging
from typing import Any

from app.services.llm.llm_service import LLMError, call_llm_json

logger = logging.getLogger(__name__)

CONTENT_TRUNCATE_LEN = 4000

TOPIC_SYSTEM_PROMPT = """\
你是中关村人工智能研究院（ZGCAI）的技术趋势分析专家。你的任务是分析某个技术主题下的最新动态，
为院领导提供战略情报。

研究院背景：
- 全称：中关村人工智能研究院
- 位于北京市海淀区中关村科学城
- 主要方向：人工智能基础研究、大模型、具身智能、AI+行业应用、人才培养
- 关注重点：技术路线、竞争格局、合作机会、人才引进

请严格以 JSON 格式输出以下字段（不要包含任何其他文本）：
{
  "aiSummary": "本周该技术方向的动态概要，100字以内，提及关键事件和趋势",
  "aiInsight": "对我院的战略建议，100字以内，具体可操作",
  "aiRiskAssessment": "风险预警（仅当缺口较大时填写），80字以内，或null",
  "memoSuggestion": "内参选题建议（如有值得撰写的内参），80字以内，或null"
}"""

OPP_SYSTEM_PROMPT = """\
你是中关村人工智能研究院（ZGCAI）的战略合作分析专家。分析以下科技前沿机会，
为院领导提供评估和行动建议。

请严格以 JSON 格式输出以下字段（不要包含任何其他文本）：
{
  "aiAssessment": "对该机会的评估，100字以内，分析价值和风险",
  "actionSuggestion": "具体行动建议，60字以内"
}"""


async def enrich_topic(topic: dict) -> dict[str, Any] | None:
    """Enrich a single topic with LLM-generated summaries and insights.

    Returns dict with aiSummary/aiInsight/aiRiskAssessment/memoSuggestion
    or None on failure.
    """
    # Build context from relatedNews
    news_summaries: list[str] = []
    for news in (topic.get("relatedNews") or [])[:15]:
        news_summaries.append(
            f"- [{news.get('type', '')}] {news.get('title', '')} "
            f"({news.get('source', '')}, {news.get('date', '')})"
        )

    kol_summaries: list[str] = []
    for kol in (topic.get("kolVoices") or [])[:5]:
        kol_summaries.append(
            f"- {kol.get('name', '')}: {kol.get('statement', '')}"
        )

    user_msg = (
        f"技术主题：{topic.get('topic', '')}\n"
        f"描述：{topic.get('description', '')}\n"
        f"热度趋势：{topic.get('heatTrend', '')} ({topic.get('heatLabel', '')})\n"
        f"我院布局：{topic.get('ourStatusLabel', '')}，"
        f"差距级别：{topic.get('gapLevel', '')}\n"
        f"本周信号数：{topic.get('signalsSinceLastWeek', 0)}\n\n"
        f"最新动态：\n" + "\n".join(news_summaries[:15]) + "\n\n"
    )
    if kol_summaries:
        user_msg += "KOL 言论：\n" + "\n".join(kol_summaries) + "\n"

    try:
        result = await call_llm_json(
            system_prompt=TOPIC_SYSTEM_PROMPT,
            prompt=user_msg[:CONTENT_TRUNCATE_LEN],
            stage="tech_frontier_topic",
        )
        return _validate_topic_enrichment(result, topic)
    except LLMError as e:
        logger.warning("LLM enrichment failed for topic %s: %s", topic.get("id"), e)
        return None
    except Exception as e:
        logger.warning(
            "Unexpected error enriching topic %s: %s", topic.get("id"), e
        )
        return None


async def enrich_opportunity(opp: dict) -> dict[str, Any] | None:
    """Enrich a single opportunity with LLM assessment.

    Returns dict with aiAssessment/actionSuggestion or None on failure.
    """
    user_msg = (
        f"机会名称：{opp.get('name', '')}\n"
        f"类型：{opp.get('type', '')}\n"
        f"来源：{opp.get('source', '')}\n"
        f"优先级：{opp.get('priority', '')}\n"
        f"截止日期：{opp.get('deadline', '未知')}\n"
        f"摘要：{opp.get('summary', '')}\n"
    )

    try:
        result = await call_llm_json(
            system_prompt=OPP_SYSTEM_PROMPT,
            prompt=user_msg[:CONTENT_TRUNCATE_LEN],
            stage="tech_frontier_opportunity",
        )
        return _validate_opp_enrichment(result)
    except LLMError as e:
        logger.warning("LLM enrichment failed for opp %s: %s", opp.get("id"), e)
        return None
    except Exception as e:
        logger.warning(
            "Unexpected error enriching opp %s: %s", opp.get("id"), e
        )
        return None


def _validate_topic_enrichment(
    result: dict, topic: dict,
) -> dict[str, Any]:
    """Validate and normalize LLM topic enrichment response."""
    enrichment: dict[str, Any] = {
        "aiSummary": str(result.get("aiSummary") or ""),
        "aiInsight": str(result.get("aiInsight") or ""),
        "aiRiskAssessment": None,
        "memoSuggestion": None,
    }

    # Only include risk assessment for high-gap topics
    if topic.get("gapLevel") == "high":
        risk = result.get("aiRiskAssessment")
        if risk and str(risk).lower() != "null":
            enrichment["aiRiskAssessment"] = str(risk)

    memo = result.get("memoSuggestion")
    if memo and str(memo).lower() != "null":
        enrichment["memoSuggestion"] = str(memo)

    return enrichment


def _validate_opp_enrichment(result: dict) -> dict[str, Any]:
    """Validate and normalize LLM opportunity enrichment response."""
    return {
        "aiAssessment": str(result.get("aiAssessment") or ""),
        "actionSuggestion": str(result.get("actionSuggestion") or ""),
    }
