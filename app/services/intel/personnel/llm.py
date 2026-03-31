"""LLM enrichment for personnel changes — prompt templates and response parsing.

For each personnel change record, generates:
  relevance, importance, group, note, actionSuggestion, background, signals, aiInsight
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.intel.shared import clamp_value as _clamp
from app.services.intel.shared import str_or_none as _str_or_none
from app.services.llm.llm_service import LLMError, call_llm_json

logger = logging.getLogger(__name__)

CONTENT_TRUNCATE_LEN = 3000

SYSTEM_PROMPT = """\
你是一个通用科技情报平台的人事情报分析专家。你的任务是分析人事变动记录，
评估其与 AI、科研创新和人才发展主题的相关性，并提取结构化字段用于决策支持。

平台关注背景：
- 主要方向：人工智能基础研究、大模型、具身智能、AI+行业应用、人才培养
- 重点关注：教育部/科技部/重点科创部门相关人事变动、高校 AI 领域领导层变化、
  科研机构负责人更替、可能影响产学研合作关系的人员调整

你将收到一批人事变动记录（来自同一篇文章），每条包含 name/action/position/department。
请逐条分析并返回 JSON 数组。

对每条变动，输出：
{
  "name": "原始人名",
  "relevance": 0到100的整数,
  "importance": "紧急|重要|关注|一般",
  "group": "action|watch",
  "note": "为什么这条变动值得关注（1句话，20字以内）",
  "actionSuggestion": "建议平台用户采取的具体行动（1句话，30字以内）",
  "background": "此人或此职位的简要背景（2-3句话，60字以内）",
  "signals": ["关键信号标签1", "关键信号标签2"],
  "aiInsight": "深度分析此变动对相关合作与观察重点的影响（2-3句话，80字以内）"
}

relevance 评分标准：
- 0-20: 与平台关注主题完全无关（如退役军人、残联等）
- 20-40: 间接相关（一般部委人事调整）
- 40-60: 相关领域（教育/科技系统、北京市政府）
- 60-80: 直接相关（高校AI院系、科技主管部门）
- 80-100: 高度相关（教育部科技部核心岗位、重点科创区域、AI研究机构）

group 判断标准：
- action: relevance >= 50，或涉及重点合作单位，需要平台用户采取行动
- watch: relevance < 50，或虽然相关但暂不需行动，持续关注即可

importance 判断标准：
- 紧急: 直接影响现有合作关系或项目
- 重要: 涉及教育部/科技部/重点科创岗位，或高校 AI 领域校长/院长变动
- 关注: 涉及相关领域但影响间接
- 一般: 与平台关注主题关联很弱

请严格以 JSON 数组格式输出，不要包含任何其他文本。"""


def build_user_prompt(
    changes: list[dict[str, Any]],
    article: dict[str, Any],
) -> str:
    """Build user prompt for a batch of changes from one article."""
    title = article.get("title", "无标题")
    source_name = article.get("source_name", "未知来源")
    published_at = article.get("published_at") or "未知日期"
    content = article.get("content") or ""

    if len(content) > CONTENT_TRUNCATE_LEN:
        content = content[:CONTENT_TRUNCATE_LEN] + "...(截断)"

    lines = [
        f"文章标题：{title}",
        f"来源：{source_name}",
        f"发布日期：{published_at}",
        "",
        "人事变动记录：",
    ]

    for i, c in enumerate(changes, 1):
        lines.append(
            f"{i}. {c['action']} {c['name']} → {c['position']}"
            f" ({c.get('department') or '未知部门'})"
        )

    if content.strip():
        lines.append(f"\n原文（供参考）：\n{content}")

    return "\n".join(lines)


VALID_IMPORTANCE = {"紧急", "重要", "关注", "一般"}
VALID_GROUP = {"action", "watch"}


def parse_llm_response(
    raw: list[dict[str, Any]],
    changes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate and normalize LLM output for a batch of changes.

    Returns a list of enrichment dicts, one per change. Falls back to defaults
    for any malformed entries.
    """
    results: list[dict[str, Any]] = []

    # Build lookup by name for matching
    raw_by_name: dict[str, dict[str, Any]] = {}
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name", "")
            raw_by_name[name] = item

    for change in changes:
        name = change.get("name", "")
        llm_item = raw_by_name.get(name, {})

        relevance = _clamp(llm_item.get("relevance"), 0, 100, 10)

        importance = llm_item.get("importance", "一般")
        if importance not in VALID_IMPORTANCE:
            importance = "一般"

        group = llm_item.get("group", "watch")
        if group not in VALID_GROUP:
            group = "action" if relevance >= 50 else "watch"

        signals = llm_item.get("signals")
        if not isinstance(signals, list):
            signals = []
        signals = [str(s) for s in signals if s]

        results.append({
            "relevance": relevance,
            "importance": importance,
            "group": group,
            "note": _str_or_none(llm_item.get("note")),
            "actionSuggestion": _str_or_none(llm_item.get("actionSuggestion")),
            "background": _str_or_none(llm_item.get("background")),
            "signals": signals,
            "aiInsight": _str_or_none(llm_item.get("aiInsight")),
        })

    return results


def default_enrichment() -> dict[str, Any]:
    """Return safe default enrichment when LLM fails for a single change."""
    return {
        "relevance": 10,
        "importance": "一般",
        "group": "watch",
        "note": None,
        "actionSuggestion": None,
        "background": None,
        "signals": [],
        "aiInsight": None,
    }


async def enrich_changes_batch(
    changes: list[dict[str, Any]],
    article: dict[str, Any],
) -> list[dict[str, Any]]:
    """Enrich a batch of changes from one article via LLM.

    Returns a list of enrichment dicts (same length and order as *changes*).
    Falls back to default enrichment if LLM fails.
    """
    if not changes:
        return []

    prompt = build_user_prompt(changes, article)

    try:
        raw = await call_llm_json(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=2000,
            stage="personnel_enrichment",
            article_id=article.get("url_hash"),
            article_title=article.get("title"),
            source_id=article.get("source_id"),
            dimension=article.get("dimension"),
        )
    except LLMError as e:
        logger.warning("LLM failed for article %s: %s", article.get("title", "?")[:40], e)
        return [default_enrichment() for _ in changes]

    if not isinstance(raw, list):
        logger.warning("Expected list from LLM, got %s", type(raw).__name__)
        return [default_enrichment() for _ in changes]

    return parse_llm_response(raw, changes)

