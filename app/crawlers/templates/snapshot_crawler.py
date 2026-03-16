from __future__ import annotations

import difflib
import hashlib
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem, CrawlResult, CrawlStatus
from app.crawlers.utils.http_client import fetch_page
from app.services.stores.snapshot_store import get_last_snapshot, save_snapshot

logger = logging.getLogger(__name__)


class SnapshotDiffCrawler(BaseCrawler):
    """
    Crawler for pages without news lists (leadership rosters, faculty directories).
    Compares page content hash with last stored snapshot to detect changes.

    Config fields:
      - url: target page URL
      - selectors:
          content_area: CSS selector for meaningful content area
      - ignore_patterns: regex patterns to strip before hashing (timestamps, counters)
      - headers, encoding, request_delay: same as StaticHTMLCrawler
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        raise NotImplementedError("Use run() directly; fetch_and_parse not used for snapshots")

    async def run(self) -> CrawlResult:
        """Override run() to handle snapshot comparison."""
        result = CrawlResult(source_id=self.source_id)
        result.started_at = datetime.now(timezone.utc)

        try:
            url = self.config["url"]
            selectors = self.config.get("selectors", {})
            ignore_patterns = self.config.get("ignore_patterns", [])

            html = await fetch_page(
                url,
                headers=self.config.get("headers"),
                encoding=self.config.get("encoding"),
                request_delay=self.config.get("request_delay"),
            )

            # Extract content area
            soup = BeautifulSoup(html, "lxml")
            content_area_sel = selectors.get("content_area")
            if content_area_sel:
                el = soup.select_one(content_area_sel)
                text = el.get_text(separator="\n").strip() if el else ""
            else:
                text = soup.get_text(separator="\n").strip()

            # Apply ignore patterns
            for pattern in ignore_patterns:
                text = re.sub(pattern, "", text)

            # Compute hash
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

            # Get last snapshot from local JSON
            last = await get_last_snapshot(self.source_id)

            if last and last.get("content_hash") == content_hash:
                # No change
                result.status = CrawlStatus.NO_NEW_CONTENT
                result.items_total = 0
                result.items_new = 0
            else:
                # Content changed (or first snapshot)
                diff_text = None
                if last and last.get("content_text"):
                    diff_lines = difflib.unified_diff(
                        last["content_text"].splitlines(),
                        text.splitlines(),
                        lineterm="",
                    )
                    diff_text = "\n".join(diff_lines)

                # Store new snapshot
                await save_snapshot(self.source_id, content_hash, text, diff_text)

                # Create a CrawledItem for the change
                title = f"[变更检测] {self.config.get('name', self.source_id)}"
                item_url = f"{url}#snapshot-{content_hash[:12]}"
                item = CrawledItem(
                    title=title,
                    url=item_url,
                    content=diff_text or f"初次快照: {text[:500]}",
                    content_hash=content_hash,
                    source_id=self.source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []) + ["snapshot_diff"],
                    extra={"is_first_snapshot": last is None},
                )
                result.items = [item]
                result.items_total = 1
                result.items_new = 1
                result.status = CrawlStatus.SUCCESS

        except Exception as e:
            logger.exception("Snapshot crawl failed for %s", self.source_id)
            result.status = CrawlStatus.FAILED
            result.error_message = str(e)
        finally:
            result.finished_at = datetime.now(timezone.utc)
            result.duration_seconds = (result.finished_at - result.started_at).total_seconds()

        return result
