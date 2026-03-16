"""
报告生成引擎

协调数据获取、分析和格式化的完整流程。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import AnalysisResult, BaseReportAnalyzer
from .formatters import MarkdownFormatter

logger = logging.getLogger(__name__)


class ReportGenerator:
    """通用报告生成器"""

    def __init__(self, analyzer: BaseReportAnalyzer):
        self.analyzer = analyzer
        self.formatter = MarkdownFormatter()

    async def generate(
        self,
        data: List[Dict[str, Any]],
        date_range: Optional[tuple[datetime, datetime]] = None,
        output_format: str = "markdown",
        **kwargs,
    ) -> str:
        """
        生成完整报告

        Args:
            data: 原始数据
            date_range: 日期范围
            output_format: 输出格式 (markdown/json/html)
            **kwargs: 传递给分析器的额外参数

        Returns:
            str: 格式化后的报告内容
        """
        logger.info(
            f"Generating {self.analyzer.dimension} report for {len(data)} items"
        )

        # 1. 数据分析
        analysis_result = await self.analyzer.analyze(data, date_range, **kwargs)

        # 2. 格式化输出
        if output_format == "markdown":
            return self.formatter.format(analysis_result)
        elif output_format == "json":
            return self._format_json(analysis_result)
        elif output_format == "html":
            return self._format_html(analysis_result)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

    def _format_json(self, result: AnalysisResult) -> str:
        """格式化为 JSON"""
        import json

        return json.dumps(
            {
                "metadata": {
                    "title": result.metadata.title,
                    "generated_at": result.metadata.generated_at.isoformat(),
                    "data_range": result.metadata.data_range,
                    "dimension": result.metadata.dimension,
                    "total_items": result.metadata.total_items,
                    **result.metadata.additional_info,
                },
                "sections": [
                    {
                        "title": section.title,
                        "content": section.content,
                        "order": section.order,
                    }
                    for section in result.sections
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    def _format_html(self, result: AnalysisResult) -> str:
        """格式化为 HTML"""
        # 简单实现：将 Markdown 转换为 HTML
        import markdown

        md_content = self.formatter.format(result)
        return markdown.markdown(md_content, extensions=["tables", "fenced_code"])
