"""SAMR (国家市场监督管理总局) internal JS API crawler."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.content_filter import should_keep_item
from app.crawlers.utils.http_client import fetch_json, fetch_page
from app.crawlers.utils.selector_parser import parse_detail_html

logger = logging.getLogger(__name__)

_API_URL = "https://www.samr.gov.cn/api-gateway/jpaas-publish-server/front/page/build/unit"

# Default params for the 总局要闻 column
_DEFAULT_PARAMS = {
    "parseType": "bulidstatic",
    "webId": "29e9522dc89d4e088a953d8cede72f4c",
    "tplSetId": "5c30fb89ae5e48b9aefe3cdf49853830",
    "pageType": "column",
    "tagId": "内容区域",
    "editType": "null",
    "pageId": "39cd9de1f309431483ef3008309f39ca",
}


class SamrAPICrawler(BaseCrawler):
    """
    Fetch news from samr.gov.cn via its internal JS build API.

    Config fields (all optional, defaults to 总局要闻):
      - api_params: dict of GET params to override _DEFAULT_PARAMS
      - base_url: base URL for resolving relative links (default https://www.samr.gov.cn)
    """

    async def fetch_and_parse(self) -> list[CrawledItem]:
        params = {**_DEFAULT_PARAMS, **self.config.get("api_params", {})}
        base_url = self.config.get("base_url", "https://www.samr.gov.cn")

        data = await fetch_json(
            _API_URL,
            params=params,
            headers={"Referer": self.config.get("url", "https://www.samr.gov.cn/xw/zj/")},
            timeout=30.0,
        )

        if not data.get("success"):
            logger.warning("SAMR API returned failure: %s", data.get("message"))
            return []

        html = data.get("data", {}).get("html", "")
        if not html:
            logger.warning("SAMR API returned empty html")
            return []

        items = self._parse_html(html, base_url)

        # Fetch detail pages if detail_selectors configured
        detail_selectors = self.config.get("detail_selectors")
        if detail_selectors:
            request_delay = self.config.get("request_delay", 0.5)
            for item in items:
                try:
                    detail_html = await fetch_page(item.url, request_delay=request_delay)
                    detail = parse_detail_html(detail_html, detail_selectors, item.url, self.config)
                    item.content = detail.content
                    item.content_hash = detail.content_hash
                    item.content_html = detail.content_html
                    item.images = detail.images
                    if detail.author:
                        item.author = detail.author
                    if detail.pdf_url:
                        item.pdf_url = detail.pdf_url
                except Exception as e:
                    logger.warning("Failed to fetch detail for %s: %s", item.url, e)

        return items

    def _parse_html(self, html: str, base_url: str) -> list[CrawledItem]:
        soup = BeautifulSoup(html, "html.parser")
        items: list[CrawledItem] = []

        # Get filters from config
        keyword_filter = self.config.get("keyword_filter")
        keyword_blacklist = self.config.get("keyword_blacklist")

        # Each article is in: div.Three_zhnlist_02 > ul
        for ul in soup.select("div.Three_zhnlist_02 > ul"):
            a_tag = ul.select_one("li.nav04Left02_content a")
            date_li = ul.select_one("li.nav04Left02_contenttime")
            if not a_tag:
                continue

            title = a_tag.get_text(strip=True)
            href = a_tag.get("href", "")
            if not title or not href:
                continue

            # Apply keyword filtering
            if not should_keep_item(title, keyword_filter, keyword_blacklist):
                continue

            url = href if href.startswith("http") else base_url + href

            published_at = None
            if date_li:
                date_str = date_li.get_text(strip=True)
                date_str = re.sub(r"\s+", "", date_str)
                for fmt in ("%Y-%m-%d", "%Y年%m月%d日"):
                    try:
                        published_at = datetime.strptime(date_str, fmt).replace(
                            tzinfo=timezone.utc
                        )
                        break
                    except ValueError:
                        pass

            items.append(
                CrawledItem(
                    title=title,
                    url=url,
                    published_at=published_at,
                    source_id=self.source_id,
                    dimension=self.config.get("dimension"),
                    tags=self.config.get("tags", []),
                )
            )

        return items
