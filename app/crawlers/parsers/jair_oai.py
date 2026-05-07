"""JAIR OAI-PMH crawler for the paper warehouse."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlencode

from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.utils.http_client import fetch_page

logger = logging.getLogger(__name__)

OAI_URL = "https://www.jair.org/index.php/jair/oai"
_INVALID_XML_CHARS_RE = re.compile(
    r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
)
NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


class JAIROAICrawler(BaseCrawler):
    """Fetch JAIR Dublin Core records via OAI-PMH and filter by publication year."""

    async def fetch_and_parse(self) -> list[CrawledItem]:
        years = self._years()
        if not years:
            return []
        records: list[dict[str, Any]] = []
        token: str | None = None
        pages = 0
        max_pages = int(self.config.get("max_pages") or 20)
        while True:
            pages += 1
            url = self._page_url(token, min(years))
            logger.info("[%s] fetching JAIR OAI page %d", self.source_id, pages)
            xml_text = await fetch_page(
                url,
                timeout=float(self.config.get("request_timeout") or 60),
                max_retries=int(self.config.get("max_retries") or 3),
                request_delay=float(self.config.get("request_delay") or 0.5),
            )
            page_records, token = self._parse_page(xml_text, years)
            records.extend(page_records)
            if not token or pages >= max_pages:
                break

        max_items = int(self.config.get("max_items") or 0)
        if max_items > 0:
            records = records[:max_items]
        return [self._record_to_item(record) for record in records]

    def _years(self) -> set[int]:
        raw = self.config.get("year_configs")
        if isinstance(raw, list) and raw:
            return {
                int(item["year"])
                for item in raw
                if isinstance(item, dict) and item.get("year")
            }
        year = self.config.get("year")
        return {int(year)} if year else set()

    def _page_url(self, token: str | None, from_year: int) -> str:
        base_url = str(self.config.get("oai_url") or OAI_URL)
        if token:
            return f"{base_url}?verb=ListRecords&resumptionToken={quote(token)}"
        params = {
            "verb": "ListRecords",
            "metadataPrefix": "oai_dc",
            "from": f"{from_year}-01-01",
        }
        return f"{base_url}?{urlencode(params)}"

    @staticmethod
    def _parse_page(xml_text: str, years: set[int]) -> tuple[list[dict[str, Any]], str | None]:
        xml_text = _strip_invalid_xml_chars(xml_text)
        root = ET.fromstring(xml_text)
        records: list[dict[str, Any]] = []
        for record in root.findall(".//oai:record", NS):
            parsed = _parse_record(record)
            if parsed is None:
                continue
            if parsed["year"] in years:
                records.append(parsed)
        token = root.findtext(".//oai:resumptionToken", default="", namespaces=NS).strip()
        return records, token or None

    def _record_to_item(self, record: dict[str, Any]) -> CrawledItem:
        now = datetime.now(timezone.utc)
        paper_id = f"jair:{record['raw_id']}"
        authors_data = [
            {
                "paper_id": paper_id,
                "author_order": idx + 1,
                "name_raw": author,
                "name_normalized": author,
                "source_author_id": None,
                "author_url": None,
                "affiliation": None,
                "affiliation_country": None,
                "email": None,
                "orcid": None,
                "scraped_at": now.isoformat(),
                "schema_version": "1.0",
            }
            for idx, author in enumerate(record["authors"])
        ]
        paper_data = {
            "paper_id": paper_id,
            "source": "jair_oai",
            "raw_id": record["raw_id"],
            "venue": self.config.get("venue", "JAIR"),
            "venue_full": self.config.get(
                "venue_full",
                "Journal of Artificial Intelligence Research",
            ),
            "year": record["year"],
            "track": "Journal Article",
            "is_main_track": True,
            "is_workshop": False,
            "title": record["title"],
            "abstract": record.get("abstract"),
            "n_authors": len(record["authors"]),
            "url": record.get("detail_url"),
            "pdf_url": record.get("pdf_url"),
            "doi": record.get("doi"),
            "arxiv_id": None,
            "scraped_at": now.isoformat(),
            "schema_version": "1.0",
        }
        return CrawledItem(
            title=record["title"],
            url=record.get("detail_url") or record.get("doi") or record["raw_id"],
            published_at=_parse_date(record["publication_date"]),
            author=record["authors"][0] if record["authors"] else None,
            content=record.get("abstract"),
            source_id=self.source_id,
            dimension=self.config.get("dimension", "paper"),
            tags=[self.config.get("venue", "JAIR"), str(record["year"]), "journal"],
            extra={"paper": paper_data, "authors": authors_data},
        )


def _parse_record(record: ET.Element) -> dict[str, Any] | None:
    meta = record.find("oai:metadata/oai_dc:dc", NS)
    if meta is None:
        return None
    title = _first(meta, "title")
    publication_date = _first(meta, "date")
    year = _year(publication_date)
    if not title or year is None:
        return None
    identifiers = _all(meta, "identifier")
    relations = _all(meta, "relation")
    raw_identifier = record.findtext("oai:header/oai:identifier", default="", namespaces=NS)
    raw_id = raw_identifier.replace("oai:jair.org:", "").strip() or _raw_id(identifiers)
    return {
        "raw_id": raw_id,
        "title": title,
        "authors": [_normalize_author_name(author) for author in _all(meta, "creator")],
        "publication_date": publication_date,
        "year": year,
        "doi": _doi(identifiers),
        "detail_url": _detail_url(identifiers),
        "pdf_url": relations[0] if relations else None,
        "abstract": _first(meta, "description"),
    }


def _all(meta: ET.Element, name: str) -> list[str]:
    return [
        (item.text or "").strip()
        for item in meta.findall(f"dc:{name}", NS)
        if (item.text or "").strip()
    ]


def _first(meta: ET.Element, name: str) -> str | None:
    values = _all(meta, name)
    return values[0] if values else None


def _year(value: str | None) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", value or "")
    return int(match.group(0)) if match else None


def _parse_date(value: str | None) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        year = _year(text)
        return datetime(year, 1, 1, tzinfo=timezone.utc) if year else None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _doi(values: list[str]) -> str | None:
    for value in values:
        token = value.strip()
        if token.lower().startswith("10."):
            return token
        if "doi.org/" in token.lower():
            return token.rsplit("/", 1)[-1]
    return None


def _detail_url(values: list[str]) -> str | None:
    for value in values:
        if value.startswith("http") and "/article/view/" in value:
            return value
    return None


def _raw_id(values: list[str]) -> str:
    detail_url = _detail_url(values)
    if detail_url:
        article_id = detail_url.rstrip("/").rsplit("/", 1)[-1]
        return f"article/{article_id}"
    return (_doi(values) or "unknown").replace("/", "_")


def _strip_invalid_xml_chars(value: str) -> str:
    return _INVALID_XML_CHARS_RE.sub("", value)


def _normalize_author_name(value: str) -> str:
    if "," not in value:
        return value.strip()
    last, first = value.split(",", 1)
    return f"{first.strip()} {last.strip()}".strip()
