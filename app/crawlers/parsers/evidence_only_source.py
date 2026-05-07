from __future__ import annotations

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.parsers._talent_scout_common import build_blocked_item


class EvidenceOnlySourceCrawler(BaseCrawler):
    async def fetch_and_parse(self) -> list[CrawledItem]:
        notes = []
        if self.config.get("requires_auth"):
            notes.append("auth required")
        notes.append("evidence-only source")
        return [build_blocked_item(self.config, notes="; ".join(notes))]
