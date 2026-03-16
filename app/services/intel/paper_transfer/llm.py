"""LLM enrichment for paper industry transformation analysis."""
from __future__ import annotations

import logging

from app.services.llm.llm_service import LLMError, call_llm_json

logger = logging.getLogger(__name__)

MODEL = "google/gemini-3-flash-preview"

SYSTEM_PROMPT = """你是一位严格的科研成果产业转化评审专家，服务于中关村人工智能研究院（ZGCAI）。

你的任务是从大量学生论文中，精准筛选出极少数真正值得主动跟进的转化机会。
请记住：**A档应该是稀缺的例外，每100篇论文中通常不超过5-8篇。**
如果你发现自己对很多论文都给了A，说明你的标准太松了，请重新审视。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【第一步：判断成果类型】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- applied（应用型）：有完整、可运行的系统或工具实现。
  具体标志：有可复现的开源代码库、可在线体验的Demo、或经过真实场景实测的原型系统。
  注意：仅提出框架设计、仅做了消融实验、仅构建了benchmark数据集，
  不能算作应用型，应归为mixed。

- theoretical（理论型）：纯数学推导、综述类、收敛性/复杂度分析、
  无实验验证的算法改进、基础科学研究。

- mixed（混合型）：有实验验证的算法改进，但没有完整的端到端系统实现。
  大多数改进型论文都属于此类。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【第二步：判断商业热度梯队】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第一梯队（当前有明确融资和产业需求）：
  大模型应用层（RAG/Agent/AI编程助手/代码生成）、具身智能/人形机器人、
  自动驾驶、AI for Science（药物发现/材料科学/蛋白质设计）、AI安全/对齐

第二梯队（有商业化场景，但市场仍在早期）：
  多模态理解与生成、合成生物学、脑机接口、量子计算应用层、
  卫星遥感/空天信息、数字孪生

第三梯队（技术前沿但商业化路径不清晰）：
  纯基础模型架构研究、纯理论机器学习、传统CV/NLP的增量改进

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【第三步：综合评级（严格执行）】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶ A档（主动跟进）— 门槛极高，必须同时满足以下全部4条：
  ① 成果类型为 applied（有完整系统/代码库/可用Demo）
  ② 研究方向在第一梯队
  ③ 技术解决了当前市场的具体痛点，不需要再做基础研究就能开始工程化
  ④ 自检：假设今天打电话给这个学生，说"我们想基于这项技术做产品"，
     学生明天就能开始工程化工作（而不是还要继续研究半年）

  强制降档至B的情形（符合任意一条即降档）：
  × 核心贡献是提出新算法/改进指标，工程实现只是验证手段
  × 代码只是实验脚本，不是可集成的模块或系统
  × 仅做了benchmark，benchmark本身不是产品
  × 是对已有大型系统（如LLaMA、SAM等）的一个子模块改进
  × 技术成熟度仅在实验室环境验证，真实场景泛化性存疑

▶ B档（保持关注）— 有潜力但暂不达到主动跟进标准：
  - applied + 第二梯队
  - applied + 第一梯队，但存在上述任意一条降档情形
  - mixed + 第一梯队（有工程潜力，方向对）
  - 第一梯队 + theoretical（方向有价值，可等其后续工作）

▶ C档（暂不处理）— 以下情形归C：
  - theoretical + 第三梯队（纯学术推进，无近期转化可能）
  - 综述类论文
  - 改进已有算法指标零点几个百分点，无新应用场景
  - 基础科学研究，离产品至少还有5年以上

  注意：第三梯队论文，即使是applied型，也归C档。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【输出JSON格式（必须严格遵守）】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "grade": "A或B或C",
  "grade_reason": "判断理由（2-3句，明确说出支持该档位的具体证据，
    以及排除更高档位的原因）",
  "content_type": "applied或theoretical或mixed",
  "commercialization_tier": 1或2或3,
  "tech_summary": "用非学术语言描述这个研究解决了什么问题（1句话）",
  "transformation_directions": ["方向A：面向XX的XX产品，客户是XX",
    "方向B：..."],
  "maturity_level": "接近可用或需要工程化或还在早期",
  "negotiation_angle": "建议的接触切入角度（1-2句，具体）",
  "recommendation_reason": "综合推荐理由（2-3句，有说服力）"
}

规则：
- C档的 tech_summary/transformation_directions/maturity_level/
  negotiation_angle/recommendation_reason 必须为 null
- 输出必须是合法JSON，不含任何markdown标记
- transformation_directions 为列表，包含 1-3 个方向
"""


async def enrich_paper(
    title: str,
    abstract: str | None,
    venue: str | None,
    publication_date: str | None,
) -> dict:
    """Run LLM analysis on a single paper.

    Returns a validated enrichment dict with grade + analysis fields.
    Falls back to a safe C-grade default on any failure.
    """
    abstract_text = abstract if abstract else "（摘要未获取，请仅基于标题进行分析）"
    venue_text = venue if venue else "未知"

    user_prompt = (
        f"论文标题：{title}\n"
        f"摘要：{abstract_text}\n"
        f"发表日期：{publication_date or '未知'}\n"
        f"发表场所/期刊/会议：{venue_text}"
    )

    try:
        raw = await call_llm_json(
            prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            model=MODEL,
            temperature=0.1,
            max_tokens=1000,
            stage="paper_transfer",
            article_title=title,
            dimension="paper_transfer",
        )
        if not isinstance(raw, dict):
            logger.warning("LLM returned non-dict response for '%s', using default", title[:50])
            return _default_enrichment()
        return _validate(raw)
    except (LLMError, Exception) as e:
        logger.warning("LLM enrichment failed for '%s': %s", title[:50], e)
        return _default_enrichment()


def _validate(raw: dict) -> dict:
    """Validate and normalize LLM response dict."""
    grade = raw.get("grade", "C")
    if grade not in ("A", "B", "C"):
        grade = "C"

    result: dict = {
        "grade": grade,
        "grade_reason": str(raw.get("grade_reason") or ""),
        "content_type": raw.get("content_type", "mixed"),
        "commercialization_tier": int(raw.get("commercialization_tier") or 3),
        "tech_summary": None,
        "transformation_directions": None,
        "maturity_level": None,
        "negotiation_angle": None,
        "recommendation_reason": None,
    }

    if grade in ("A", "B"):
        result["tech_summary"] = raw.get("tech_summary") or None
        dirs = raw.get("transformation_directions")
        result["transformation_directions"] = dirs if isinstance(dirs, list) else None
        ml = raw.get("maturity_level") or ""
        result["maturity_level"] = (
            ml if ml in ("接近可用", "需要工程化", "还在早期") else None
        )
        result["negotiation_angle"] = raw.get("negotiation_angle") or None
        result["recommendation_reason"] = raw.get("recommendation_reason") or None

    return result


def _default_enrichment() -> dict:
    return {
        "grade": "C",
        "grade_reason": "LLM 分析失败，默认归为 C 档",
        "content_type": "mixed",
        "commercialization_tier": 3,
        "tech_summary": None,
        "transformation_directions": None,
        "maturity_level": None,
        "negotiation_angle": None,
        "recommendation_reason": None,
    }
