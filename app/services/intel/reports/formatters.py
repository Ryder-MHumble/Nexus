"""
报告格式化工具

将分析结果格式化为 Markdown 等格式。
"""

from datetime import datetime
from typing import Any, Dict, List

from .base import AnalysisResult, ReportSection


class MarkdownFormatter:
    """Markdown 格式化器"""

    def format(self, result: AnalysisResult) -> str:
        """格式化分析结果为 Markdown"""
        lines = []

        # 标题和元数据
        lines.append(f"# {result.metadata.title}\n")
        lines.append(
            f"> **生成时间**: {result.metadata.generated_at.strftime('%Y-%m-%d %H:%M')}"
        )
        lines.append(f"> **数据范围**: {result.metadata.data_range}")
        lines.append(f"> **数据量**: {result.metadata.total_items} 条\n")
        lines.append("---\n")

        # 各章节
        sorted_sections = sorted(result.sections, key=lambda s: s.order)
        for section in sorted_sections:
            lines.append(self._format_section(section))

        # 页脚
        lines.append("---\n")
        lines.append(
            f"*本报告由 OpenClaw 数据智能平台自动生成 | "
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
        )

        return "\n".join(lines)

    def _format_section(self, section: ReportSection, level: int = 2) -> str:
        """格式化单个章节"""
        lines = []

        # 章节标题
        lines.append(f"{'#' * level} {section.title}\n")

        # 章节内容
        if section.content:
            lines.append(section.content)
            lines.append("")

        # 子章节
        for subsection in section.subsections:
            lines.append(self._format_section(subsection, level + 1))

        return "\n".join(lines)


def format_number(num: int | float) -> str:
    """格式化数字（K/M 简写）"""
    num = int(num) if num else 0
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return str(num)


def get_sentiment_emoji(sentiment: str) -> str:
    """获取情感表情符号"""
    emojis = {"positive": "🟢", "neutral": "🟡", "negative": "🔴"}
    return emojis.get(sentiment, "⚪")


def format_table(headers: List[str], rows: List[List[Any]]) -> str:
    """格式化 Markdown 表格"""
    lines = []

    # 表头
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    # 数据行
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")

    return "\n".join(lines)


def format_list(items: List[str], ordered: bool = False) -> str:
    """格式化列表"""
    if ordered:
        return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))
    else:
        return "\n".join(f"- {item}" for item in items)
