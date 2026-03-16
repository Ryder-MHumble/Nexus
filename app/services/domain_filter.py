"""
领域过滤服务

提供灵活的领域关键词过滤功能，支持：
- 多级领域分类（一级领域 → 二级子领域）
- 领域组合（预设常用组合）
- 自定义关键词
- 命令行参数覆盖
"""

import yaml
from pathlib import Path
from typing import List, Set, Optional
import logging

logger = logging.getLogger(__name__)


class DomainFilter:
    """领域过滤器"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化领域过滤器

        Args:
            config_path: 领域配置文件路径，默认为 config/domains.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "domains.yaml"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self.domains = {}
        self.domain_groups = {}
        self._load_config()

    def _load_config(self):
        """加载领域配置文件"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                self.domains = config.get("domains", {})
                self.domain_groups = config.get("domain_groups", {})
                logger.info(f"Loaded domain config from {self.config_path}")
        except FileNotFoundError:
            logger.warning(f"Domain config file not found: {self.config_path}")
            self.domains = {}
            self.domain_groups = {}
        except Exception as e:
            logger.error(f"Failed to load domain config: {e}")
            self.domains = {}
            self.domain_groups = {}

    def get_keywords(self, domain_spec: str) -> List[str]:
        """
        获取指定领域的关键词列表

        Args:
            domain_spec: 领域标识，支持以下格式：
                - "all": 全领域，返回空列表（不过滤）
                - "technology": 一级领域，返回所有子领域关键词
                - "technology.ai": 二级子领域，返回该子领域关键词
                - "technology.ai,economy.finance": 多个子领域，逗号分隔

        Returns:
            关键词列表，空列表表示不过滤
        """
        if not domain_spec or domain_spec == "all":
            return []

        keywords_set: Set[str] = set()

        # 分割多个领域
        domain_parts = [d.strip() for d in domain_spec.split(",")]

        for part in domain_parts:
            if "." in part:
                # 二级子领域：technology.ai
                parent, child = part.split(".", 1)
                if parent in self.domains:
                    subdomains = self.domains[parent].get("subdomains", {})
                    if child in subdomains:
                        kws = subdomains[child].get("keywords", [])
                        keywords_set.update(kws)
                    else:
                        logger.warning(f"Subdomain not found: {part}")
                else:
                    logger.warning(f"Parent domain not found: {parent}")
            else:
                # 一级领域：technology（返回所有子领域关键词）
                if part in self.domains:
                    subdomains = self.domains[part].get("subdomains", {})
                    for subdomain in subdomains.values():
                        kws = subdomain.get("keywords", [])
                        keywords_set.update(kws)
                else:
                    logger.warning(f"Domain not found: {part}")

        return list(keywords_set)

    def get_keywords_from_group(self, group_name: str) -> List[str]:
        """
        获取领域组合的关键词列表

        Args:
            group_name: 领域组合名称，如 "tech_all"

        Returns:
            关键词列表
        """
        if group_name not in self.domain_groups:
            logger.warning(f"Domain group not found: {group_name}")
            return []

        group = self.domain_groups[group_name]
        domains = group.get("domains", [])

        keywords_set: Set[str] = set()
        for domain_spec in domains:
            kws = self.get_keywords(domain_spec)
            keywords_set.update(kws)

        return list(keywords_set)

    def resolve_keywords(
        self,
        domain: Optional[str] = None,
        domain_group: Optional[str] = None,
        custom_keywords: Optional[List[str]] = None,
    ) -> List[str]:
        """
        解析最终使用的关键词列表

        优先级：custom_keywords > domain > domain_group

        Args:
            domain: 领域标识
            domain_group: 领域组合名称
            custom_keywords: 自定义关键词列表

        Returns:
            关键词列表
        """
        # 优先使用自定义关键词
        if custom_keywords:
            return custom_keywords

        # 其次使用 domain
        if domain:
            return self.get_keywords(domain)

        # 最后使用 domain_group
        if domain_group:
            return self.get_keywords_from_group(domain_group)

        # 默认不过滤
        return []

    def filter_text(self, text: str, keywords: List[str]) -> bool:
        """
        判断文本是否匹配关键词

        Args:
            text: 待检查的文本
            keywords: 关键词列表，空列表表示不过滤（返回 True）

        Returns:
            True 表示匹配（保留），False 表示不匹配（过滤掉）
        """
        if not keywords:
            # 空关键词列表表示不过滤
            return True

        if not text:
            return False

        # 任意关键词匹配即可（OR 逻辑）
        for keyword in keywords:
            if keyword.lower() in text.lower():
                return True

        return False

    def list_domains(self) -> dict:
        """
        列出所有可用的领域

        Returns:
            领域字典
        """
        return self.domains

    def list_domain_groups(self) -> dict:
        """
        列出所有可用的领域组合

        Returns:
            领域组合字典
        """
        return self.domain_groups


# 全局单例
_domain_filter_instance: Optional[DomainFilter] = None


def get_domain_filter() -> DomainFilter:
    """获取全局领域过滤器单例"""
    global _domain_filter_instance
    if _domain_filter_instance is None:
        _domain_filter_instance = DomainFilter()
    return _domain_filter_instance
