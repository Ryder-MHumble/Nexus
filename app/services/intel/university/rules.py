"""Rules engine for university ecosystem — keyword-based article categorization.

Classifies raw university articles into research types (论文/专利/获奖)
and computes influence level based on keyword scoring.
"""
from __future__ import annotations

import re

from app.services.intel.shared import clamp_score, keyword_score

# ---------------------------------------------------------------------------
# Research type keywords  (keyword, weight)
# ---------------------------------------------------------------------------

KEYWORDS_PAPER: list[tuple[str, int]] = [
    ("论文", 30), ("paper", 25), ("发表", 20), ("录用", 25),
    ("期刊", 20), ("journal", 20), ("会议论文", 30),
    ("science", 30), ("nature", 30), ("cell", 20),
    ("icra", 20), ("cvpr", 20), ("neurips", 20), ("nips", 15),
    ("aaai", 20), ("iclr", 20), ("icml", 20), ("acl", 15),
    ("emnlp", 15), ("sigir", 15), ("kdd", 15), ("www", 10),
    ("ieee", 15), ("acm", 15), ("arxiv", 15),
    ("usenix", 15), ("security", 10),
    ("研究成果", 20), ("学术", 15), ("学报", 15),
    ("top会议", 20), ("顶会", 20), ("顶刊", 20),
    ("一作", 15), ("通讯作者", 15),
]

KEYWORDS_PATENT: list[tuple[str, int]] = [
    ("专利", 40), ("patent", 35), ("发明", 25), ("授权", 20),
    ("实用新型", 30), ("知识产权", 25), ("技术转让", 20),
    ("成果转化", 20), ("产业化", 15), ("技术突破", 15),
]

KEYWORDS_AWARD: list[tuple[str, int]] = [
    ("获奖", 35), ("荣获", 35), ("奖项", 30), ("颁奖", 25),
    ("一等奖", 30), ("二等奖", 25), ("三等奖", 20),
    ("特等奖", 35), ("金奖", 30), ("银奖", 20),
    ("杰出", 20), ("表彰", 20), ("院士", 15),
    ("国家奖", 30), ("自然科学奖", 30), ("技术发明奖", 30),
    ("科技进步奖", 30), ("科学技术奖", 25),
    ("最佳论文", 25), ("best paper", 25),
    ("长江学者", 20), ("杰青", 20), ("优青", 15),
    ("人才计划", 15), ("挑战赛", 15),
]

# Influence level keywords
KEYWORDS_HIGH_INFLUENCE: list[tuple[str, int]] = [
    ("science", 40), ("nature", 40), ("cell", 35),
    ("院士", 20), ("国家级", 30), ("国家奖", 30),
    ("重大突破", 30), ("世界首次", 30), ("全球首个", 30),
    ("特等奖", 30), ("一等奖", 25),
    ("neurips", 20), ("icml", 20), ("cvpr", 20),
    ("长江学者", 20), ("杰青", 20),
]

KEYWORDS_MED_INFLUENCE: list[tuple[str, int]] = [
    ("aaai", 15), ("iclr", 15), ("acl", 15), ("icra", 15),
    ("ieee", 10), ("acm", 10),
    ("省级", 10), ("教育部", 10), ("科技部", 10),
    ("二等奖", 10), ("金奖", 10),
    ("优青", 10), ("人才计划", 10),
]

# Institution short-name extraction
INSTITUTION_PATTERNS: list[tuple[str, str]] = [
    ("清华", "清华大学"),
    ("北大", "北京大学"),
    ("北京大学", "北京大学"),
    ("复旦", "复旦大学"),
    ("交大", "上海交通大学"),
    ("上海交通", "上海交通大学"),
    ("浙大", "浙江大学"),
    ("浙江大学", "浙江大学"),
    ("中科大", "中国科学技术大学"),
    ("中国科学技术大学", "中国科学技术大学"),
    ("南大", "南京大学"),
    ("南京大学", "南京大学"),
    ("哈工大", "哈尔滨工业大学"),
    ("武大", "武汉大学"),
    ("武汉大学", "武汉大学"),
    ("山东大学", "山东大学"),
    ("中山大学", "中山大学"),
    ("华科", "华中科技大学"),
    ("华中科技", "华中科技大学"),
    ("同济", "同济大学"),
    ("天大", "天津大学"),
    ("天津大学", "天津大学"),
    ("西交", "西安交通大学"),
    ("西安交通", "西安交通大学"),
    ("北航", "北京航空航天大学"),
    ("北理", "北京理工大学"),
    ("人大", "中国人民大学"),
    ("AIR", "清华AIR"),
    ("智源", "智源研究院"),
    ("中科院", "中国科学院"),
    ("深圳", "深圳"),
    ("上海AI", "上海AI实验室"),
    ("商汤", "商汤科技"),
]

# Field extraction from tags
TAG_TO_FIELD: dict[str, str] = {
    "ai": "人工智能",
    "ml": "机器学习",
    "nlp": "自然语言处理",
    "cv": "计算机视觉",
    "robotics": "机器人",
    "security": "网络安全",
    "quantum": "量子计算",
    "biology": "生物医学",
    "education": "教育",
    "policy": "政策",
    "institute": "研究机构",
    "university": "高校",
}

# Negative title patterns — articles matching these are NOT research
NEGATIVE_TITLE_PATTERNS: list[str] = [
    "看望慰问", "走访慰问", "走访调研", "调研座谈",
    "带队走访", "带队调研",
    "工作务虚会", "工作会议", "部署会", "推进会", "座谈会", "动员会",
    "新春", "春节", "团拜会", "联欢会", "拜年", "团圆饭",
    "对话", "访谈", "专访", "采访",
    "签订合作", "合作协议", "框架协议", "座谈交流",
    "开学典礼", "毕业典礼", "开幕式", "闭幕式",
    "就业", "招生", "招聘", "录取",
    "寒假工作", "暑假工作",
    "习近平", "重点任务",
]

# Min score to qualify as a research article
MIN_RESEARCH_SCORE = 30


# ---------------------------------------------------------------------------
# Core classification logic
# ---------------------------------------------------------------------------

def classify_article(article: dict) -> dict | None:
    """Classify a university article into a research output.

    Returns enrichment dict with type/influence/field/detail, or None if
    the article does not match any research category.
    """
    title = article.get("title", "")

    # Guard: reject very short titles (pagination artifacts)
    if len(title.strip()) < 4:
        return None

    # Guard: reject non-research articles by title pattern
    for neg in NEGATIVE_TITLE_PATTERNS:
        if neg in title:
            return None

    content = (article.get("content") or "")[:3000]
    text = f"{title}\n{content}"

    # Score each type
    paper_score = keyword_score(text, KEYWORDS_PAPER)
    patent_score = keyword_score(text, KEYWORDS_PATENT)
    award_score = keyword_score(text, KEYWORDS_AWARD)

    scores = sorted([paper_score, patent_score, award_score], reverse=True)
    best_score = scores[0]
    runner_up = scores[1]

    # Must meet minimum threshold
    if best_score < MIN_RESEARCH_SCORE:
        return None

    # If scores are too close and low, classification is ambiguous — reject
    if best_score < 40 and (best_score - runner_up) < 10:
        return None

    # Determine type
    if paper_score >= patent_score and paper_score >= award_score:
        rtype = "论文"
    elif patent_score >= award_score:
        rtype = "专利"
    else:
        rtype = "获奖"

    # Determine influence
    high_score = keyword_score(text, KEYWORDS_HIGH_INFLUENCE)
    med_score = keyword_score(text, KEYWORDS_MED_INFLUENCE)

    if high_score >= 25:
        influence = "高"
    elif high_score >= 10 or med_score >= 20:
        influence = "中"
    else:
        influence = "低"

    # Extract institution
    institution = _extract_institution(article)

    # Extract field
    field = _extract_field(article)

    # Extract authors
    authors = _extract_authors(article)

    # Build detail snippet
    detail = _build_detail(article)

    # Build brief analysis
    ai_analysis = _build_analysis(rtype, influence, institution, title)

    return {
        "type": rtype,
        "influence": influence,
        "institution": institution,
        "field": field,
        "authors": authors,
        "detail": detail,
        "aiAnalysis": ai_analysis,
        "matchScore": clamp_score(best_score),
    }


def _extract_institution(article: dict) -> str:
    """Extract institution name from source_name or content."""
    source_name = article.get("source_name", "")
    title = article.get("title", "")
    text = f"{source_name} {title}"

    for pattern, name in INSTITUTION_PATTERNS:
        if pattern in text:
            return name
    return source_name.split("-")[0].split("(")[0].strip() or "未知机构"


def _extract_field(article: dict) -> str:
    """Infer research field from tags and content."""
    tags = article.get("tags", [])
    for tag in tags:
        tag_lower = tag.lower()
        for key, field_name in TAG_TO_FIELD.items():
            if key in tag_lower:
                return field_name

    # Fall back to content keyword scanning
    title = article.get("title", "")
    content = (article.get("content") or "")[:500]
    text = f"{title} {content}".lower()

    field_keywords = [
        ("大模型", "大模型"), ("llm", "大模型"), ("gpt", "大模型"),
        ("具身智能", "具身智能"), ("embodied", "具身智能"),
        ("机器人", "机器人"), ("robot", "机器人"),
        ("量子", "量子计算"), ("quantum", "量子计算"),
        ("安全", "网络安全"), ("security", "网络安全"),
        ("医学", "AI医学"), ("医疗", "AI医学"), ("drug", "AI制药"),
        ("自动驾驶", "自动驾驶"), ("autonomous", "自动驾驶"),
        ("视觉", "计算机视觉"), ("vision", "计算机视觉"),
        ("自然语言", "自然语言处理"), ("nlp", "自然语言处理"),
        ("教育", "AI教育"),
        ("人工智能", "人工智能"), ("ai", "人工智能"),
    ]
    for kw, field_name in field_keywords:
        if kw in text:
            return field_name

    return "综合"


_AUTHOR_RE = re.compile(
    r"(?:作者|团队|课题组|实验室|教授|研究员|博士)[：:\s]*"
    r"([\u4e00-\u9fa5A-Za-z\s、,，]+?)(?=[。；\n]|$)"
)


def _extract_authors(article: dict) -> str:
    """Try to extract author/team info from content."""
    author = article.get("author")
    if author and author.strip():
        return author.strip()

    content = article.get("content") or ""
    m = _AUTHOR_RE.search(content[:1000])
    if m:
        return m.group(1).strip()[:100]

    source_name = article.get("source_name", "")
    return f"{source_name}研究团队"


def _build_detail(article: dict) -> str:
    """Build a detail snippet from article content."""
    content = article.get("content") or ""
    if content:
        # Take first meaningful paragraph
        paragraphs = [p.strip() for p in content.split("\n") if len(p.strip()) > 20]
        if paragraphs:
            snippet = paragraphs[0][:300]
            if len(paragraphs[0]) > 300:
                snippet += "…"
            return snippet
    return article.get("title", "")


def _build_analysis(
    rtype: str, influence: str, institution: str, title: str,
) -> str:
    """Generate a brief analysis sentence."""
    influence_label = {"高": "高影响力", "中": "中等影响力", "低": "常规"}[influence]
    type_label = {"论文": "学术论文", "专利": "专利成果", "获奖": "获奖荣誉"}[rtype]
    return (
        f"{institution}发布{influence_label}{type_label}。"
        f"「{title[:40]}」值得关注，建议持续追踪该机构在相关领域的动态。"
    )
