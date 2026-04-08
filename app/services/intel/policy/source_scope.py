from __future__ import annotations

from typing import Any

CORE_POLICY_DIMENSIONS: tuple[str, ...] = (
    "national_policy",
    "beijing_policy",
    "regional_policy",
)

POLICY_PIPELINE_DIMENSIONS: tuple[str, ...] = (
    "national_policy",
    "beijing_policy",
    "regional_policy",
    "talent",
    "universities",
)


def _normalized_tags(article: dict[str, Any]) -> set[str]:
    tags = article.get("tags") or []
    return {str(tag).strip().lower() for tag in tags if str(tag).strip()}


def is_policy_signal_article(article: dict[str, Any]) -> bool:
    dimension = str(article.get("dimension") or "").strip().lower()
    group = str(article.get("group") or "").strip().lower()
    tags = _normalized_tags(article)

    if dimension in CORE_POLICY_DIMENSIONS:
        return group != "news_personnel"
    if dimension == "talent":
        return group == "policy"
    if dimension == "universities":
        return "policy" in tags
    return False


def get_policy_category(
    article: dict[str, Any],
    *,
    is_opportunity: bool = False,
) -> str:
    if is_opportunity:
        return "政策机会"

    dimension = str(article.get("dimension") or "").strip().lower()
    group = str(article.get("group") or "").strip().lower()
    tags = _normalized_tags(article)

    if dimension == "national_policy":
        return "国家政策"
    if dimension == "beijing_policy":
        return "北京政策"
    if dimension == "regional_policy":
        return "区域政策"
    if dimension == "talent" and group == "policy":
        return "人才政策"
    if dimension == "universities" and "policy" in tags:
        return "高校政策"
    return "一般"


def get_policy_agency_type(article: dict[str, Any]) -> str:
    dimension = str(article.get("dimension") or "").strip().lower()
    source_id = str(article.get("source_id") or "").strip().lower()

    if dimension == "beijing_policy":
        return "beijing"
    if dimension == "regional_policy":
        return "regional"
    if dimension == "national_policy":
        if source_id == "gov_cn_zhengce":
            return "national"
        return "ministry"
    if dimension == "talent":
        if source_id.startswith("nsfc") or source_id.startswith("gov_cn"):
            return "national"
        return "ministry"
    if dimension == "universities":
        return "regional"
    return "ministry"
