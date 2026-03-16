"""Rule-based paper pre-classification using title/abstract keyword signals."""
from __future__ import annotations

# Positive signals: engineering / applied work
APPLIED_KEYWORDS = [
    "system",
    "framework",
    "tool",
    "platform",
    "prototype",
    "demo",
    "benchmark",
    "dataset",
    "open-source",
    "pipeline",
    "engine",
    "toolkit",
    "library",
    "interface",
    "application",
    "deployment",
    "系统",
    "框架",
    "工具",
    "平台",
    "数据集",
    "基准",
]

# Negative signals: pure academic / theoretical work
THEORETICAL_KEYWORDS = [
    "theoretical",
    "theory",
    "proof",
    "survey",
    "review",
    "bound",
    "convergence",
    "complexity",
    "approximation",
    "综述",
    "理论",
    "证明",
    "分析",
]

# Tier 1: clear commercial demand right now
TIER1_KEYWORDS = [
    "llm",
    "large language model",
    "rag",
    "retrieval-augmented",
    "agent",
    "embodied",
    "robot",
    "autonomous driving",
    "self-driving",
    "drug discovery",
    "protein",
    "alignment",
    "ai safety",
    "code generation",
    "coding assistant",
    "大模型",
    "智能体",
    "具身",
    "机器人",
    "自动驾驶",
]

# Tier 2: early-stage commercial potential
TIER2_KEYWORDS = [
    "multimodal",
    "multi-modal",
    "synthetic biology",
    "brain-computer",
    "bci",
    "quantum",
    "remote sensing",
    "satellite",
    "digital twin",
    "多模态",
    "合成生物",
    "脑机",
    "量子",
    "遥感",
    "数字孪生",
]


def classify_paper_by_rules(title: str, abstract: str | None) -> dict:
    """Classify a paper by keyword signals in its title and abstract.

    Returns a dict with:
        content_type: "applied" | "theoretical" | "mixed"
        commercialization_tier: 1 | 2 | 3
        matched_signals: list[str] — all matched keywords
    """
    text = (title + " " + (abstract or "")).lower()

    applied_hits = [kw for kw in APPLIED_KEYWORDS if kw in text]
    theory_hits = [kw for kw in THEORETICAL_KEYWORDS if kw in text]

    if applied_hits and len(applied_hits) >= len(theory_hits):
        content_type = "applied"
    elif len(theory_hits) > len(applied_hits):
        content_type = "theoretical"
    else:
        content_type = "mixed"

    tier1_hits = [kw for kw in TIER1_KEYWORDS if kw in text]
    tier2_hits = [kw for kw in TIER2_KEYWORDS if kw in text]

    if tier1_hits:
        tier = 1
    elif tier2_hits:
        tier = 2
    else:
        tier = 3

    matched_signals = list(set(applied_hits + theory_hits + tier1_hits + tier2_hits))

    return {
        "content_type": content_type,
        "commercialization_tier": tier,
        "matched_signals": matched_signals,
    }
