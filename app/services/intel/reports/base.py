"""
报告生成基础类

定义报告生成器的抽象接口和通用数据结构。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ReportSection:
    """报告章节"""

    title: str
    content: str
    order: int = 0
    subsections: List["ReportSection"] = field(default_factory=list)


@dataclass
class ReportMetadata:
    """报告元数据"""

    title: str
    generated_at: datetime
    data_range: str
    dimension: str
    total_items: int
    additional_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """分析结果"""

    metadata: ReportMetadata
    sections: List[ReportSection]
    raw_data: Dict[str, Any] = field(default_factory=dict)


class BaseReportAnalyzer(ABC):
    """报告分析器基类"""

    def __init__(self, dimension: str):
        self.dimension = dimension

    @abstractmethod
    async def analyze(
        self,
        data: List[Dict[str, Any]],
        date_range: Optional[tuple[datetime, datetime]] = None,
        **kwargs,
    ) -> AnalysisResult:
        """
        分析数据并生成报告结构

        Args:
            data: 原始数据列表
            date_range: 日期范围 (start, end)
            **kwargs: 额外参数

        Returns:
            AnalysisResult: 分析结果
        """
        pass

    @abstractmethod
    def get_overview_metrics(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """获取概览指标"""
        pass

    @abstractmethod
    def identify_key_insights(self, data: List[Dict[str, Any]]) -> List[str]:
        """识别关键洞察"""
        pass

    @abstractmethod
    def generate_recommendations(self, data: List[Dict[str, Any]]) -> List[str]:
        """生成行动建议"""
        pass
