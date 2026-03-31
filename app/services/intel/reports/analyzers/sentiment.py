"""
舆情分析器

基于社交媒体数据生成舆情监测报告。
"""

import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..base import AnalysisResult, BaseReportAnalyzer, ReportMetadata, ReportSection
from ..formatters import format_number, format_table, get_sentiment_emoji

logger = logging.getLogger(__name__)


class SentimentReportAnalyzer(BaseReportAnalyzer):
    """舆情报告分析器"""

    def __init__(self):
        super().__init__(dimension="sentiment")

        # 风险关键词
        self.risk_keywords = {
            "high": ["投诉", "举报", "骗局", "欺骗", "违规", "虚假", "诈骗"],
            "medium": ["问题", "担心", "失望", "不满", "质疑", "疑虑"],
        }

        # 正面关键词
        self.positive_keywords = [
            "优秀",
            "很好",
            "专业",
            "领先",
            "创新",
            "推荐",
            "满意",
        ]

    async def analyze(
        self,
        data: List[Dict[str, Any]],
        date_range: Optional[tuple[datetime, datetime]] = None,
        **kwargs,
    ) -> AnalysisResult:
        """分析舆情数据"""

        if not data:
            return self._empty_result(date_range)

        # 数据预处理
        processed_data = self._preprocess_data(data)

        # 生成各章节
        sections = [
            self._generate_overview_section(processed_data),
            self._generate_sentiment_section(processed_data),
            self._generate_platform_section(processed_data),
            self._generate_risk_section(processed_data),
            self._generate_opportunity_section(processed_data),
            self._generate_action_section(processed_data),
        ]

        # 元数据
        metadata = ReportMetadata(
            title="舆情监测报告",
            generated_at=datetime.now(),
            data_range=self._format_date_range(date_range),
            dimension=self.dimension,
            total_items=len(processed_data),
            additional_info={
                "platforms": list(
                    set(item.get("platform", "unknown") for item in processed_data)
                ),
            },
        )

        return AnalysisResult(metadata=metadata, sections=sections, raw_data=data)

    def _preprocess_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """数据预处理：统一字段、计算情感等"""
        processed = []

        for item in data:
            # 统一字段名
            processed_item = {
                "id": item.get("id"),
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "platform": item.get("platform", "unknown"),
                "author": item.get("author", {}).get("name", "未知用户"),
                "url": item.get("url", ""),
                "published_at": item.get("published_at"),
                "engagement": {
                    "likes": item.get("liked_count", 0),
                    "comments": item.get("comment_count", 0),
                    "shares": item.get("share_count", 0),
                    "collects": item.get("collected_count", 0),
                },
            }

            # 计算情感
            processed_item["sentiment"] = self._analyze_sentiment(
                processed_item["title"] + " " + processed_item["content"]
            )

            # 检测风险
            processed_item["risk_level"] = self._detect_risk(
                processed_item["title"] + " " + processed_item["content"]
            )

            processed.append(processed_item)

        return processed

    def _analyze_sentiment(self, text: str) -> str:
        """简单的情感分析"""
        # 检查负面关键词
        for keyword in self.risk_keywords["high"] + self.risk_keywords["medium"]:
            if keyword in text:
                return "negative"

        # 检查正面关键词
        for keyword in self.positive_keywords:
            if keyword in text:
                return "positive"

        return "neutral"

    def _detect_risk(self, text: str) -> Optional[str]:
        """检测风险等级"""
        for keyword in self.risk_keywords["high"]:
            if keyword in text:
                return "high"

        for keyword in self.risk_keywords["medium"]:
            if keyword in text:
                return "medium"

        return None

    def _generate_overview_section(
        self, data: List[Dict[str, Any]]
    ) -> ReportSection:
        """生成概览章节"""
        metrics = self.get_overview_metrics(data)

        # 构建表格
        rows = [
            ["总内容数", f"{metrics['total_items']} 条"],
            ["总互动量", format_number(metrics["total_engagement"])],
            [
                "情感分布",
                f"🟢 {metrics['sentiment_pct']['positive']}% 正面 / "
                f"🟡 {metrics['sentiment_pct']['neutral']}% 中性 / "
                f"🔴 {metrics['sentiment_pct']['negative']}% 负面",
            ],
        ]

        # 平台分布
        if metrics.get("platform_dist"):
            platform_str = " / ".join(
                f"{p} {c}条" for p, c in metrics["platform_dist"].items()
            )
            rows.append(["平台分布", platform_str])

        content = format_table(["维度", "数据"], rows)

        return ReportSection(title="数据概览", content=content, order=1)

    def _generate_sentiment_section(
        self, data: List[Dict[str, Any]]
    ) -> ReportSection:
        """生成情感分析章节"""
        sentiment_counts = Counter(item["sentiment"] for item in data)
        total = len(data)

        rows = []
        for sentiment in ["positive", "neutral", "negative"]:
            count = sentiment_counts.get(sentiment, 0)
            pct = round(count / total * 100) if total > 0 else 0
            emoji = get_sentiment_emoji(sentiment)
            label = {"positive": "正面", "neutral": "中性", "negative": "负面"}[
                sentiment
            ]
            rows.append([f"{emoji} {label}", count, f"{pct}%"])

        content = format_table(["情感", "数量", "占比"], rows)

        return ReportSection(title="情感分析", content=content, order=2)

    def _generate_platform_section(
        self, data: List[Dict[str, Any]]
    ) -> ReportSection:
        """生成平台分析章节"""
        platform_data = defaultdict(
            lambda: {"count": 0, "engagement": 0, "sentiment": Counter()}
        )

        for item in data:
            platform = item["platform"]
            platform_data[platform]["count"] += 1
            platform_data[platform]["engagement"] += sum(
                item["engagement"].values()
            )
            platform_data[platform]["sentiment"][item["sentiment"]] += 1

        rows = []
        for platform, stats in sorted(
            platform_data.items(), key=lambda x: x[1]["count"], reverse=True
        ):
            avg_eng = (
                stats["engagement"] // stats["count"] if stats["count"] > 0 else 0
            )
            sentiment_dist = " / ".join(
                f"{get_sentiment_emoji(s)}{c}"
                for s, c in stats["sentiment"].most_common()
            )
            rows.append(
                [
                    platform,
                    stats["count"],
                    format_number(stats["engagement"]),
                    format_number(avg_eng),
                    sentiment_dist,
                ]
            )

        content = format_table(
            ["平台", "内容数", "总互动", "平均互动", "情感分布"], rows
        )

        return ReportSection(title="平台分析", content=content, order=3)

    def _generate_risk_section(self, data: List[Dict[str, Any]]) -> ReportSection:
        """生成风险预警章节"""
        risks = [item for item in data if item.get("risk_level")]

        if not risks:
            content = "✅ **当前无风险预警**，所有监测内容未发现需要关注的风险项。\n"
            return ReportSection(title="风险预警", content=content, order=4)

        # 按风险等级分组
        high_risks = [r for r in risks if r["risk_level"] == "high"]
        medium_risks = [r for r in risks if r["risk_level"] == "medium"]

        content_lines = []

        if high_risks:
            content_lines.append("### 🔴 高优先级（48小时内处理）\n")
            for i, risk in enumerate(high_risks[:3], 1):
                content_lines.append(self._format_risk_item(risk, i))

        if medium_risks:
            content_lines.append("### 🟡 中优先级（本周内关注）\n")
            for i, risk in enumerate(medium_risks[:2], 1):
                content_lines.append(self._format_risk_item(risk, i))

        return ReportSection(
            title="风险预警", content="\n".join(content_lines), order=4
        )

    def _format_risk_item(self, item: Dict[str, Any], index: int) -> str:
        """格式化单个风险项"""
        title = item["title"][:60] if item["title"] else item["content"][:60]
        eng = sum(item["engagement"].values())
        platform = item["platform"]
        author = item["author"]

        lines = [
            f"**{index}. 《{title}》**\n",
            f"- 📱 平台：{platform} | 👤 作者：{author} | 📊 互动：{format_number(eng)}",
        ]

        if item.get("url"):
            lines.append(f"- 🔗 [查看原文]({item['url']})")

        lines.append("\n**建议行动**：")
        if item["risk_level"] == "high":
            lines.append("- 48小时内评估内容真实性，准备官方回应")
            lines.append("- 若情况属实：直接联系作者说明改进计划")
            lines.append("- 若情况不实：发布简洁声明，附事实证据")
        else:
            lines.append("- 本周内在内容下方留下官方回复")
            lines.append("- 正面回应具体疑虑，避免沉默")

        lines.append("")
        return "\n".join(lines)

    def _generate_opportunity_section(
        self, data: List[Dict[str, Any]]
    ) -> ReportSection:
        """生成正向机会章节"""
        positive_items = [item for item in data if item["sentiment"] == "positive"]

        if not positive_items:
            content = "当前暂无高互动正面内容可借势。\n"
            return ReportSection(title="正向机会", content=content, order=5)

        # 按互动量排序
        positive_items.sort(
            key=lambda x: sum(x["engagement"].values()), reverse=True
        )

        content_lines = ["以下高互动正面内容可转发/借势放大：\n"]

        for i, item in enumerate(positive_items[:5], 1):
            eng = sum(item["engagement"].values())
            title = item["title"][:60] if item["title"] else item["content"][:60]
            platform = item["platform"]
            author = item["author"]

            content_lines.append(f"{i}. **《{title}》** — {format_number(eng)} 互动")
            content_lines.append(f"   - 来源：{platform} @{author}")
            if item.get("url"):
                content_lines.append(f"   - [🔗 查看并转发]({item['url']})")

            if eng > 1000:
                content_lines.append(
                    "   - 💡 互动量高，建议官方账号直接转发或引用\n"
                )
            else:
                content_lines.append(
                    "   - 💡 可在下次推文中引用此内容作为用户真实评价\n"
                )

        return ReportSection(
            title="正向机会", content="\n".join(content_lines), order=5
        )

    def _generate_action_section(self, data: List[Dict[str, Any]]) -> ReportSection:
        """生成行动清单章节"""
        actions = self.generate_recommendations(data)

        content = "\n".join(f"- [ ] {action}" for action in actions)

        return ReportSection(title="立即执行清单", content=content, order=6)

    def get_overview_metrics(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """获取概览指标"""
        sentiment_counts = Counter(item["sentiment"] for item in data)
        total = len(data)

        return {
            "total_items": total,
            "total_engagement": sum(
                sum(item["engagement"].values()) for item in data
            ),
            "sentiment_pct": {
                "positive": round(sentiment_counts.get("positive", 0) / total * 100)
                if total > 0
                else 0,
                "neutral": round(sentiment_counts.get("neutral", 0) / total * 100)
                if total > 0
                else 0,
                "negative": round(sentiment_counts.get("negative", 0) / total * 100)
                if total > 0
                else 0,
            },
            "platform_dist": Counter(item["platform"] for item in data),
        }

    def identify_key_insights(self, data: List[Dict[str, Any]]) -> List[str]:
        """识别关键洞察"""
        insights = []

        # 情感分布洞察
        sentiment_counts = Counter(item["sentiment"] for item in data)
        if sentiment_counts.get("negative", 0) > len(data) * 0.2:
            insights.append("⚠️ 负面情感占比超过20%，需要重点关注")

        # 风险洞察
        high_risks = [item for item in data if item.get("risk_level") == "high"]
        if high_risks:
            insights.append(f"🔴 发现 {len(high_risks)} 条高风险内容，需立即处理")

        # 平台洞察
        platform_counts = Counter(item["platform"] for item in data)
        if platform_counts:
            top_platform = platform_counts.most_common(1)[0]
            insights.append(
                f"📱 {top_platform[0]} 是声量最高的平台（{top_platform[1]} 条）"
            )

        return insights

    def generate_recommendations(self, data: List[Dict[str, Any]]) -> List[str]:
        """生成行动建议"""
        actions = []

        # 处理高风险内容
        high_risks = [item for item in data if item.get("risk_level") == "high"]
        for risk in high_risks[:2]:
            title = risk["title"][:25] if risk["title"] else risk["content"][:25]
            url_part = f" → [查看]({risk['url']})" if risk.get("url") else ""
            actions.append(f"**【48h内】** 回应高风险内容《{title}...》{url_part}")

        # 处理中风险内容
        medium_risks = [item for item in data if item.get("risk_level") == "medium"]
        if medium_risks and len(actions) < 5:
            risk = medium_risks[0]
            title = risk["title"][:25] if risk["title"] else risk["content"][:25]
            url_part = f" → [查看]({risk['url']})" if risk.get("url") else ""
            actions.append(f"**【本周内】** 官方回复中风险帖子《{title}...》{url_part}")

        # 借势正面内容
        positive_items = sorted(
            [i for i in data if i["sentiment"] == "positive"],
            key=lambda x: sum(x["engagement"].values()),
            reverse=True,
        )
        if positive_items and len(actions) < 5:
            top = positive_items[0]
            eng = sum(top["engagement"].values())
            title = top["title"][:25] if top["title"] else top["content"][:25]
            url_part = f" → [查看]({top['url']})" if top.get("url") else ""
            actions.append(
                f"**【本周内】** 转发高互动正面内容《{title}...》"
                f"（{format_number(eng)} 互动）{url_part}"
            )

        # 无风险时的主动策略
        if not high_risks and not medium_risks and len(actions) < 5:
            platform_counts = Counter(item["platform"] for item in data)
            if platform_counts:
                top_platform = platform_counts.most_common(1)[0]
                actions.append(
                    f"**【本周内】** 在声量最高的 {top_platform[0]}"
                    f"（{top_platform[1]} 条提及）发布主动内容"
                )

        if not actions:
            actions.append("**【本周内】** 当前无紧急事项，建议安排内容选题会")

        return actions[:5]

    def _empty_result(
        self, date_range: Optional[tuple[datetime, datetime]]
    ) -> AnalysisResult:
        """空数据结果"""
        metadata = ReportMetadata(
            title="舆情监测报告",
            generated_at=datetime.now(),
            data_range=self._format_date_range(date_range),
            dimension=self.dimension,
            total_items=0,
        )

        sections = [
            ReportSection(
                title="数据概览", content="暂无数据", order=1
            )
        ]

        return AnalysisResult(metadata=metadata, sections=sections)

    def _format_date_range(
        self, date_range: Optional[tuple[datetime, datetime]]
    ) -> str:
        """格式化日期范围"""
        if not date_range:
            return "全量数据"

        start, end = date_range
        return f"{start.strftime('%Y-%m-%d')} 至 {end.strftime('%Y-%m-%d')}"
