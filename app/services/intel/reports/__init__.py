"""
AI 分析报告生成模块

提供通用的报告生成框架，支持多维度数据分析和报告生成。
"""

from .base import BaseReportAnalyzer, ReportSection
from .generator import ReportGenerator
from .formatters import MarkdownFormatter

__all__ = [
    "BaseReportAnalyzer",
    "ReportSection",
    "ReportGenerator",
    "MarkdownFormatter",
]
