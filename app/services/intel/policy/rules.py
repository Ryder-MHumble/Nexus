"""Rule-based policy article scoring and field extraction.

Tier 1 of the two-tier enrichment pipeline. Computes matchScore, importance,
isOpportunity, funding, deadline, agency, leader, tags WITHOUT calling LLM.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.intel.shared import (
    clamp_score,
    compute_days_left,
    compute_importance,
    extract_deadline,
    extract_funding,
    extract_leader,
    keyword_score,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Policy-specific keyword tables
# ---------------------------------------------------------------------------

# Tier A: Highly specific to the AI research institute
KEYWORDS_TIER_A: list[tuple[str, int]] = [
    ("人工智能研究院", 30),
    ("新型研发机构", 25),
    ("具身智能", 25),
    ("大模型", 20),
    ("人工智能", 20),
    ("算力", 18),
    ("智能计算", 20),
    ("中关村", 18),
    ("AI", 15),
    ("海淀", 12),
]

# Tier B: Directly related fields
KEYWORDS_TIER_B: list[tuple[str, int]] = [
    ("科技成果转化", 12),
    ("科技人才", 12),
    ("机器人", 12),
    ("卓越工程师", 10),
    ("自然科学基金", 10),
    ("数字经济", 10),
    ("数据要素", 10),
    ("智能制造", 10),
    ("科研经费", 10),
    ("人才引进", 10),
    ("基础研究", 10),
    ("科技", 8),
    ("创新", 8),
    ("人才", 8),
    ("高新技术", 8),
]

# Tier C: Indirectly related
KEYWORDS_TIER_C: list[tuple[str, int]] = [
    ("专项资金", 8),
    ("教育", 5),
    ("高校", 5),
    ("科学", 5),
    ("数字", 5),
    ("信息化", 5),
    ("知识产权", 5),
    ("补贴", 5),
    ("申报", 5),
]

ALL_KEYWORDS = KEYWORDS_TIER_A + KEYWORDS_TIER_B + KEYWORDS_TIER_C

# Source-specific bonus: certain sources are inherently more relevant
SOURCE_SCORE_BONUS: dict[str, int] = {
    "bjkw_policy": 15,
    "zgc_policy": 15,
    "ncsti_policy": 10,
    "most_policy": 10,
    "ndrc_policy": 5,
    "nsfc_news": 8,
}

# ---------------------------------------------------------------------------
# Opportunity detection
# ---------------------------------------------------------------------------

OPPORTUNITY_TITLE_KW = [
    "征集", "申报", "通知", "补贴", "资助", "专项",
    "课题", "评审", "遴选", "招标", "入围",
]

# ---------------------------------------------------------------------------
# Agency mapping
# ---------------------------------------------------------------------------

AGENCY_MAP: dict[str, str] = {
    "gov_cn_zhengce": "国务院",
    "ndrc_policy": "国家发改委",
    "moe_policy": "教育部",
    "most_policy": "科技部",
    "miit_policy": "工信部",
    "nsfc_news": "国家自然科学基金委",
    "beijing_zhengce": "北京市政府",
    "bjkw_policy": "北京市科委/中关村管委会",
    "bjjw_policy": "北京市教委",
    "bjrsj_policy": "北京市人社局",
    "zgc_policy": "中关村管委会",
    "ncsti_policy": "国际科创中心",
    "bjfgw_policy": "北京市发改委",
    "bjhd_policy": "海淀区政府",
    "beijing_ywdt": "首都之窗",
    "bjrd_renshi": "北京市人大常委会",
    "beijing_rsrm": "北京市政府",
    "mohrss_rsrm": "人社部",
    "moe_renshi": "教育部",
    "moe_renshi_si": "教育部人事司",
}


# ===================================================================
# Public API
# ===================================================================


def compute_match_score(article: dict[str, Any]) -> int:
    """Compute keyword-based matchScore for an article (0-100)."""
    title = article.get("title", "")
    content = (article.get("content") or "")[:3000]
    text = f"{title}\n{content}"

    score = keyword_score(text, ALL_KEYWORDS)
    source_id = article.get("source_id", "")
    score += SOURCE_SCORE_BONUS.get(source_id, 0)

    return clamp_score(score)


def detect_opportunity(article: dict[str, Any]) -> bool:
    """Detect if article is a policy opportunity.

    Requires title contains opportunity keyword AND content contains
    funding amount or deadline mention.
    """
    title = article.get("title", "")
    content = article.get("content") or ""

    has_kw = any(kw in title for kw in OPPORTUNITY_TITLE_KW)
    if not has_kw:
        return False

    return bool(extract_funding(content)) or bool(extract_deadline(content))


def extract_tags(article: dict[str, Any]) -> list[str]:
    """Extract keyword-based tags from title + content."""
    title = article.get("title", "")
    text = f"{title}\n{(article.get('content') or '')[:2000]}".lower()
    tags: list[str] = []
    high_kws = [(kw, w) for kw, w in KEYWORDS_TIER_A + KEYWORDS_TIER_B if w >= 10]
    for kw, _ in high_kws:
        if kw.lower() in text and kw not in tags:
            tags.append(kw)
    return tags[:6]


def get_agency(article: dict[str, Any]) -> str:
    """Get agency name from source_id mapping."""
    source_id = article.get("source_id", "")
    return AGENCY_MAP.get(source_id, article.get("source_name", "未知"))


def enrich_by_rules(article: dict[str, Any]) -> dict[str, Any]:
    """Full Tier 1 rule-based enrichment.

    Returns the same 13-field dict shape as LLM enrichment, plus
    ``enrichment_tier`` for debugging.
    """
    title = article.get("title", "")
    content = article.get("content") or ""
    text = f"{title}\n{content}"

    match_score = compute_match_score(article)
    deadline = extract_deadline(text)
    days_left = compute_days_left(deadline)
    importance = compute_importance(match_score, deadline, title)
    is_opportunity = detect_opportunity(article)
    funding = extract_funding(text)
    leader = extract_leader(text)
    agency = get_agency(article)
    tags = extract_tags(article)

    return {
        "summary": title[:80] if title else "无摘要",
        "importance": importance,
        "matchScore": match_score,
        "relevance": match_score,
        "isOpportunity": is_opportunity,
        "funding": funding,
        "deadline": deadline,
        "daysLeft": days_left,
        "agency": agency,
        "signals": [],
        "aiInsight": "",
        "detail": "",
        "leader": leader,
        "tags": tags,
        "enrichment_tier": "rules",
    }
