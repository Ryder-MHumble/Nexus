"""Rule-based personnel article scoring and change extraction.

Extracts structured appointment/dismissal data from government personnel
notices (e.g. "国务院任免国家工作人员").  Pure regex, no LLM needed.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any

from app.services.intel.shared import (
    clamp_score,
    compute_importance,
    keyword_score,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Personnel-specific keyword tables
# ---------------------------------------------------------------------------

KEYWORDS_PERSONNEL: list[tuple[str, int]] = [
    # Tier A: Directly relevant departments
    ("教育部", 20),
    ("科技部", 20),
    ("中关村", 20),
    ("海淀", 18),
    ("科学技术", 15),
    ("人工智能", 25),
    # Tier B: Related departments/roles
    ("发改委", 10),
    ("工信部", 10),
    ("基金委", 10),
    ("高校", 10),
    ("校长", 10),
    ("副校长", 10),
    ("院长", 8),
    ("研究院", 12),
    # Tier C: General government
    ("国务院", 5),
    ("北京市", 5),
    ("部长", 5),
    ("副部长", 5),
]

# Title keywords that trigger "重要" for personnel
HIGH_IMPORTANCE_KW = ["教育部", "科技部", "人工智能", "中关村", "校长"]

# ---------------------------------------------------------------------------
# Appointment / Dismissal regex
# ---------------------------------------------------------------------------

# "任命黄如（女）为国家发展和改革委员会副主任"
APPOINTMENT_RE = re.compile(
    r"任命\s*([\u4e00-\u9fa5]{2,4})(?:（[^）]*）)?\s*为\s*(.+?)(?=[；。\n])",
)

# "免去孙其信的中国农业大学校长职务"
DISMISSAL_RE = re.compile(
    r"免去\s*([\u4e00-\u9fa5]{2,4})(?:（[^）]*）)?\s*的\s*(.+?)职务",
)

# ---------------------------------------------------------------------------
# Department inference from position text
# ---------------------------------------------------------------------------

DEPARTMENT_MAP: list[tuple[str, str]] = [
    ("教育部", "教育部"),
    ("科技部", "科技部"),
    ("国家发展和改革委员会", "国家发改委"),
    ("发展改革委", "国家发改委"),
    ("工业和信息化部", "工信部"),
    ("工信部", "工信部"),
    ("人力资源和社会保障部", "人社部"),
    ("住房和城乡建设部", "住建部"),
    ("退役军人事务部", "退役军人事务部"),
    ("商务部", "商务部"),
    ("自然科学基金委", "国家自然科学基金委"),
    ("中央广播电视总台", "中央广播电视总台"),
    ("国家行政学院", "国家行政学院"),
    ("中国残疾人联合会", "中国残联"),
    ("北京市", "北京市政府"),
    ("海淀", "海淀区"),
    ("中关村", "中关村"),
]

# University patterns
UNIVERSITY_RE = re.compile(r"([\u4e00-\u9fa5]{2,8}(?:大学|学院|研究院))")


def _infer_department(position: str) -> str | None:
    """Infer department from position text."""
    for keyword, dept in DEPARTMENT_MAP:
        if keyword in position:
            return dept
    m = UNIVERSITY_RE.search(position)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_changes(article: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract all personnel changes from an article.

    Returns list of dicts with keys:
        name, action, position, department, date, source_article_id
    """
    content = article.get("content") or ""
    title = article.get("title") or ""
    text = f"{title}\n{content}"
    url_hash = article.get("url_hash", "")

    # Extract date from article
    pub = article.get("published_at")
    art_date = ""
    if pub:
        try:
            art_date = datetime.fromisoformat(pub).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    changes: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()  # (name, action, position) dedup

    for m in APPOINTMENT_RE.finditer(text):
        name = m.group(1).strip()
        position = m.group(2).strip()
        # Clean up stray whitespace/newlines in position
        position = re.sub(r"\s+", "", position)
        key = (name, "任命", position)
        if key not in seen:
            seen.add(key)
            changes.append({
                "name": name,
                "action": "任命",
                "position": position,
                "department": _infer_department(position),
                "date": art_date,
                "source_article_id": url_hash,
            })

    for m in DISMISSAL_RE.finditer(text):
        name = m.group(1).strip()
        position = m.group(2).strip()
        position = re.sub(r"\s+", "", position)
        key = (name, "免去", position)
        if key not in seen:
            seen.add(key)
            changes.append({
                "name": name,
                "action": "免去",
                "position": position,
                "department": _infer_department(position),
                "date": art_date,
                "source_article_id": url_hash,
            })

    return changes


def compute_match_score(article: dict[str, Any]) -> int:
    """Compute matchScore for a personnel article (0-100)."""
    title = article.get("title", "")
    content = (article.get("content") or "")[:3000]
    text = f"{title}\n{content}"
    score = keyword_score(text, KEYWORDS_PERSONNEL)
    return clamp_score(score)


def enrich_by_rules(article: dict[str, Any]) -> dict[str, Any]:
    """Tier 1 enrichment for personnel articles.

    Returns dict with matchScore, importance, changes, and metadata.
    """
    title = article.get("title", "")
    changes = extract_changes(article)
    match_score = compute_match_score(article)
    importance = compute_importance(
        match_score, None, title, high_keywords=HIGH_IMPORTANCE_KW,
    )

    return {
        "matchScore": match_score,
        "importance": importance,
        "changes": changes,
        "change_count": len(changes),
        "enrichment_tier": "rules",
    }


def change_id(change: dict[str, Any]) -> str:
    """Generate a stable ID for a single change record."""
    key = f"{change.get('name', '')}-{change.get('action', '')}-{change.get('position', '')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
