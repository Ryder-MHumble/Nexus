"""Tech Frontier rules engine — topic classification, heat calculation, signal extraction.

Pure functions (no I/O). The processor calls these to transform raw articles
into structured topic objects aligned with the frontend TechTopic type.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.intel.shared import (
    article_date,
    article_datetime,
    extract_deadline,
    keyword_score,
)

# ---------------------------------------------------------------------------
# Topic configuration (8 topics)
# ---------------------------------------------------------------------------

TOPIC_MATCH_THRESHOLD = 15  # minimum score to classify an article into a topic

TOPICS_CONFIG: list[dict[str, Any]] = [
    {
        "id": "embodied_ai",
        "topic": "具身智能",
        "description": "将AI与物理世界交互的关键技术方向，涵盖机器人控制、运动规划、导航等",
        "tags": ["机器人", "运动控制", "仿真", "感知"],
        "ourStatus": "none",
        "ourStatusLabel": "未布局",
        "gapLevel": "high",
        "keywords": [
            ("具身智能", 20), ("embodied intelligence", 18), ("embodied ai", 18),
            ("humanoid robot", 15), ("人形机器人", 15), ("机器人控制", 12),
            ("运动规划", 10), ("motion planning", 10), ("robotics", 8),
            ("manipulation", 8), ("locomotion", 8), ("navigation", 6),
            ("sim-to-real", 10), ("仿真到现实", 10), ("触觉感知", 8),
        ],
    },
    {
        "id": "multimodal",
        "topic": "多模态大模型",
        "description": "整合视觉、语音、文本等多种模态的大模型技术，是大模型发展的重要方向",
        "tags": ["大模型", "视觉", "视频生成", "长上下文"],
        "ourStatus": "deployed",
        "ourStatusLabel": "已布局",
        "gapLevel": "low",
        "keywords": [
            ("多模态", 18), ("multimodal", 18), ("视觉语言", 15),
            ("vision-language", 15), ("视频生成", 15), ("video generation", 15),
            ("图像生成", 12), ("image generation", 12), ("CLIP", 10),
            ("Sora", 12), ("DALL-E", 10), ("Stable Diffusion", 8),
            ("文生图", 12), ("文生视频", 12), ("text-to-image", 10),
            ("text-to-video", 10), ("长上下文", 8), ("long context", 8),
        ],
    },
    {
        "id": "ai_agent",
        "topic": "AI Agent",
        "description": "自主完成复杂任务的智能代理系统，涵盖工具调用、多Agent协作、自主编程等",
        "tags": ["AI编程", "Agent框架", "工具调用", "自主任务"],
        "ourStatus": "weak",
        "ourStatusLabel": "基础薄弱",
        "gapLevel": "medium",
        "keywords": [
            ("AI Agent", 20), ("智能体", 15), ("agent", 10),
            ("tool use", 12), ("工具调用", 12), ("function calling", 10),
            ("多Agent", 15), ("multi-agent", 15), ("自主编程", 12),
            ("agentic", 12), ("AutoGPT", 10), ("Claude Code", 10),
            ("Copilot", 8), ("自主任务", 10), ("任务规划", 8),
            ("ReAct", 10), ("chain of thought", 8), ("思维链", 8),
        ],
    },
    {
        "id": "ai_for_science",
        "topic": "AI for Science",
        "description": "利用AI加速科学发现的新范式，涵盖药物发现、蛋白质结构预测、分子模拟等",
        "tags": ["科学计算", "药物发现", "蛋白质", "开源模型"],
        "ourStatus": "deployed",
        "ourStatusLabel": "已布局",
        "gapLevel": "low",
        "keywords": [
            ("AI for Science", 20), ("ai4science", 18), ("科学计算", 15),
            ("药物发现", 15), ("drug discovery", 15), ("蛋白质", 12),
            ("protein", 10), ("AlphaFold", 15), ("分子模拟", 12),
            ("molecular dynamics", 12), ("材料设计", 10), ("materials", 8),
            ("气候模型", 8), ("genomics", 8), ("基因组", 8),
        ],
    },
    {
        "id": "edge_ai",
        "topic": "端侧AI推理",
        "description": "将AI推理从云端迁移到边缘设备，涉及模型压缩、专用芯片、高效推理等技术",
        "tags": ["边缘计算", "模型压缩", "AI芯片", "推理优化"],
        "ourStatus": "none",
        "ourStatusLabel": "未布局",
        "gapLevel": "high",
        "keywords": [
            ("端侧", 18), ("edge ai", 18), ("on-device", 15),
            ("模型压缩", 15), ("model compression", 15), ("量化", 12),
            ("quantization", 12), ("知识蒸馏", 12), ("distillation", 10),
            ("NPU", 12), ("AI芯片", 15), ("ai chip", 15),
            ("推理优化", 12), ("inference optimization", 12),
            ("pruning", 8), ("剪枝", 8), ("TinyML", 10),
        ],
    },
    {
        "id": "llm_foundation",
        "topic": "大语言模型",
        "description": "基础语言模型的预训练、微调、推理等核心技术，包括Scaling Law、架构创新等",
        "tags": ["预训练", "微调", "Scaling Law", "架构创新"],
        "ourStatus": "deployed",
        "ourStatusLabel": "已布局",
        "gapLevel": "medium",
        "keywords": [
            ("大语言模型", 15), ("大模型", 10), ("LLM", 15),
            ("GPT", 10), ("Claude", 10), ("Gemini", 10),
            ("DeepSeek", 12), ("预训练", 12), ("pre-training", 12),
            ("Scaling Law", 15), ("微调", 10), ("fine-tuning", 10),
            ("RLHF", 12), ("instruction tuning", 10), ("指令微调", 10),
            ("Transformer", 8), ("Mamba", 10), ("SSM", 8),
            ("Llama", 10), ("Qwen", 10), ("foundation model", 12),
            ("基础模型", 12), ("开源模型", 8),
        ],
    },
    {
        "id": "ai_safety",
        "topic": "AI安全与治理",
        "description": "AI系统的安全性、可控性与社会治理，涵盖对齐、可解释性、监管政策等",
        "tags": ["对齐", "可解释性", "监管", "红队测试"],
        "ourStatus": "weak",
        "ourStatusLabel": "基础薄弱",
        "gapLevel": "medium",
        "keywords": [
            ("AI安全", 20), ("AI safety", 20), ("alignment", 15),
            ("对齐", 15), ("治理", 12), ("governance", 12),
            ("监管", 10), ("regulation", 10), ("可解释性", 12),
            ("explainability", 12), ("interpretability", 10),
            ("红队", 12), ("red team", 12), ("jailbreak", 10),
            ("幻觉", 10), ("hallucination", 10), ("偏见", 8),
            ("bias", 8), ("responsible AI", 10), ("负责任AI", 10),
        ],
    },
    {
        "id": "genai_apps",
        "topic": "生成式AI应用",
        "description": "基于生成式AI的应用落地，包括内容生成、AI编程、设计工具、教育等场景",
        "tags": ["AIGC", "AI编程", "内容创作", "应用落地"],
        "ourStatus": "weak",
        "ourStatusLabel": "基础薄弱",
        "gapLevel": "medium",
        "keywords": [
            ("生成式AI", 18), ("generative AI", 18), ("AIGC", 15),
            ("AI绘画", 12), ("AI编程", 12), ("AI coding", 12),
            ("Cursor", 10), ("内容生成", 10), ("content generation", 10),
            ("AI助手", 10), ("AI assistant", 10), ("ChatGPT", 8),
            ("AI教育", 10), ("AI设计", 10), ("AI写作", 10),
            ("AI应用", 8), ("AI产品", 8), ("商业化", 6),
        ],
    },
]

# Pre-build id→config lookup
_TOPICS_BY_ID: dict[str, dict] = {t["id"]: t for t in TOPICS_CONFIG}

# ---------------------------------------------------------------------------
# Source → platform mapping
# ---------------------------------------------------------------------------

_PLATFORM_MAP: dict[str, str] = {
    "arxiv_cs_ai": "ArXiv",
    "arxiv_cs_lg": "ArXiv",
    "arxiv_cs_cl": "ArXiv",
    "github_trending": "GitHub",
    "hacker_news": "GitHub",  # close enough for HN
    "twitter_ai_kol_international": "X",
    "twitter_ai_kol_chinese": "X",
    "twitter_ai_breakthrough": "X",
    "twitter_ai_papers": "X",
    "twitter_ai_industry": "X",
    "twitter_ai_talent": "X",
    "twitter_zgci_sentiment": "X",
}

_KOL_SOURCE_IDS = {"twitter_ai_kol_international", "twitter_ai_kol_chinese"}

# ---------------------------------------------------------------------------
# News type detection
# ---------------------------------------------------------------------------

_NEWS_TYPE_KEYWORDS: list[tuple[str, list[tuple[str, int]]]] = [
    ("投融资", [
        ("融资", 15), ("估值", 12), ("投资", 10), ("风投", 10),
        ("A轮", 12), ("B轮", 12), ("C轮", 12), ("IPO", 12),
        ("funding", 12), ("valuation", 10), ("Series", 8),
    ]),
    ("收购", [
        ("收购", 20), ("并购", 18), ("合并", 15), ("被收购", 18),
        ("acquisition", 18), ("acquire", 15), ("merger", 12),
    ]),
    ("政策", [
        ("政策", 15), ("意见", 10), ("通知", 8), ("指南", 10),
        ("规划", 10), ("监管", 12), ("法规", 10), ("regulation", 10),
        ("policy", 8), ("国务院", 12), ("工信部", 10),
    ]),
    ("合作", [
        ("合作", 12), ("联合", 10), ("共建", 12), ("战略合作", 15),
        ("签约", 10), ("partnership", 10), ("collaboration", 10),
        ("联合实验室", 15), ("产学研", 12),
    ]),
    ("新产品", [
        ("发布", 10), ("推出", 10), ("发布会", 12), ("新品", 10),
        ("上线", 8), ("开源", 10), ("开放", 6), ("launch", 10),
        ("release", 10), ("announce", 8), ("open source", 10),
    ]),
]

# ---------------------------------------------------------------------------
# Opportunity detection
# ---------------------------------------------------------------------------

_OPP_TYPE_KEYWORDS: list[tuple[str, list[tuple[str, int]]]] = [
    ("会议", [
        ("会议", 12), ("峰会", 15), ("论坛", 12), ("大会", 12),
        ("邀请", 12), ("conference", 12), ("summit", 12),
        ("workshop", 10), ("symposium", 10),
    ]),
    ("合作", [
        ("合作", 10), ("共建", 12), ("联合实验室", 18),
        ("产学研", 15), ("申报", 12), ("基金", 12),
        ("专项", 15), ("资助", 12), ("招标", 12),
    ]),
    ("内参", [
        ("内参", 18), ("征稿", 12), ("政策解读", 12),
        ("白皮书", 12), ("报告", 8), ("指南", 8),
    ]),
]

OPP_MATCH_THRESHOLD = 20  # minimum score to flag as opportunity


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def classify_article(article: dict) -> list[dict]:
    """Classify an article into matching topics.

    Returns list of ``{"topic_id": str, "match_score": int}`` for each match.
    """
    title = article.get("title") or ""
    content = article.get("content") or ""
    text = f"{title} {content}"

    matches: list[dict] = []
    for topic in TOPICS_CONFIG:
        score = keyword_score(text, topic["keywords"])
        if score >= TOPIC_MATCH_THRESHOLD:
            matches.append({"topic_id": topic["id"], "match_score": score})
    return matches


def detect_news_type(article: dict) -> str:
    """Detect the news type of an article: 投融资 / 收购 / 政策 / 合作 / 新产品."""
    title = article.get("title") or ""
    content = (article.get("content") or "")[:500]
    text = f"{title} {content}"

    best_type = "新产品"  # default
    best_score = 0
    for news_type, keywords in _NEWS_TYPE_KEYWORDS:
        score = keyword_score(text, keywords)
        if score > best_score:
            best_score = score
            best_type = news_type
    return best_type


def assess_impact(match_score: int) -> str:
    """Assess impact level based on match score."""
    if match_score >= 60:
        return "重大"
    if match_score >= 30:
        return "较大"
    return "一般"


def detect_opportunity(article: dict) -> dict | None:
    """Detect whether an article represents an opportunity.

    Returns opportunity dict or None.
    """
    title = article.get("title") or ""
    content = (article.get("content") or "")[:800]
    text = f"{title} {content}"

    best_type = ""
    best_score = 0
    for opp_type, keywords in _OPP_TYPE_KEYWORDS:
        score = keyword_score(text, keywords)
        if score > best_score:
            best_score = score
            best_type = opp_type

    if best_score < OPP_MATCH_THRESHOLD:
        return None

    deadline = extract_deadline(text)
    priority = _compute_priority(best_score, deadline)

    return {
        "id": f"opp_{article.get('url_hash', '')[:16]}",
        "name": title[:60],
        "type": best_type,
        "source": article.get("source_name") or article.get("source_id", ""),
        "priority": priority,
        "deadline": deadline or "",
        "summary": (content or title)[:300],
        "aiAssessment": "",
        "actionSuggestion": "",
    }


def map_platform(source_id: str) -> str:
    """Map source_id to display platform name."""
    if source_id in _PLATFORM_MAP:
        return _PLATFORM_MAP[source_id]
    if source_id.endswith("_rss"):
        return "博客"
    if source_id.endswith("_blog"):
        return "博客"
    return "博客"


def is_kol_source(source_id: str) -> bool:
    """Check if source_id is a KOL twitter source."""
    return source_id in _KOL_SOURCE_IDS


def build_kol_voice(article: dict) -> dict:
    """Build a KOLVoice dict from a KOL twitter article."""
    return {
        "id": article.get("url_hash", ""),
        "name": article.get("author") or article.get("source_name", ""),
        "affiliation": "",
        "influence": "高",
        "statement": (article.get("title") or "")[:200],
        "platform": "X",
        "sourceUrl": article.get("url", ""),
        "source_id": article.get("source_id", ""),
        "source_name": article.get("source_name", ""),
        "date": _article_date(article),
    }


def build_topic_news(article: dict, match_score: int) -> dict:
    """Build a TopicNews dict from a classified article."""
    content = article.get("content") or ""
    return {
        "id": article.get("url_hash", ""),
        "title": article.get("title", ""),
        "source": article.get("source_name") or article.get("source_id", ""),
        "source_id": article.get("source_id", ""),
        "source_name": article.get("source_name", ""),
        "sourceUrl": article.get("url", ""),
        "type": detect_news_type(article),
        "date": _article_date(article),
        "impact": assess_impact(match_score),
        "summary": content[:200] if content else (article.get("title") or ""),
        "aiAnalysis": "",
        "relevance": "",
    }


def build_trending_post(article: dict) -> dict:
    """Build a TrendingPost dict from an article."""
    content = article.get("content") or ""
    source_id = article.get("source_id", "")
    return {
        "id": article.get("url_hash", ""),
        "title": article.get("title", ""),
        "platform": map_platform(source_id),
        "author": article.get("author") or article.get("source_name", ""),
        "date": _article_date(article),
        "sourceUrl": article.get("url", ""),
        "summary": content[:200] if content else (article.get("title") or ""),
        "engagement": None,
    }


def compute_heat(
    current_count: int,
    previous_count: int,
) -> tuple[str, str]:
    """Compute heat trend and label from article counts.

    Returns (heatTrend, heatLabel).
    """
    if previous_count == 0:
        if current_count > 0:
            return ("surging", f"+{current_count * 100}%")
        return ("stable", "+0%")

    pct_change = ((current_count - previous_count) / previous_count) * 100

    if pct_change > 100:
        trend = "surging"
    elif pct_change > 20:
        trend = "rising"
    elif pct_change >= -20:
        trend = "stable"
    else:
        trend = "declining"

    sign = "+" if pct_change >= 0 else ""
    label = f"{sign}{int(pct_change)}%"
    return (trend, label)


# ---------------------------------------------------------------------------
# University-dimension source filter
# ---------------------------------------------------------------------------

# Only include these university sources (AI research institutes)
UNI_AI_INSTITUTE_SOURCES: set[str] = {
    "baai_news", "tsinghua_air", "shlab_news", "pcl_news",
    "ia_cas_news", "ict_cas_news", "sii_news", "slai_news",
    "cesi_news", "iie_cas_news",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_article_date = article_date
_article_datetime = article_datetime


def _compute_priority(opp_score: int, deadline: str | None) -> str:
    """Compute opportunity priority from score and deadline proximity."""
    days_left: int | None = None
    if deadline:
        try:
            dl = datetime.strptime(deadline, "%Y-%m-%d").date()
            days_left = (dl - datetime.now(timezone.utc).date()).days
        except ValueError:
            pass

    if days_left is not None and 0 < days_left <= 7:
        return "紧急"
    if opp_score >= 40 or (days_left is not None and 0 < days_left <= 14):
        return "高"
    if opp_score >= 25:
        return "中"
    return "低"


def split_by_period(
    articles: list[dict],
    days: int = 7,
) -> tuple[list[dict], list[dict]]:
    """Split articles into current period and previous period.

    Returns (current_period, previous_period) where current is last ``days``
    and previous is the ``days`` before that.
    """
    now = datetime.now(timezone.utc)
    cutoff_current = now - timedelta(days=days)
    cutoff_previous = now - timedelta(days=days * 2)

    current: list[dict] = []
    previous: list[dict] = []

    for a in articles:
        dt = _article_datetime(a)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= cutoff_current:
            current.append(a)
        elif dt >= cutoff_previous:
            previous.append(a)

    return current, previous
