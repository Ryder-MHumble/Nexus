from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from app.config import BASE_DIR
from app.crawlers.base import BaseCrawler, CrawledItem
from app.crawlers.parsers._talent_scout_common import (
    build_blocked_item,
    build_crawled_item,
    build_review_item,
    build_talent_signal,
    extract_records,
    fetch_options,
    get_track,
    is_obvious_non_person_candidate_name,
)
from app.crawlers.utils.http_client import fetch_json, fetch_page


class PaperAuthorSourceCrawler(BaseCrawler):
    async def fetch_and_parse(self) -> list[CrawledItem]:
        adapter_key = str(self.config.get("adapter_key") or "")
        if adapter_key == "semantic_scholar":
            return await self._fetch_semantic_scholar()
        if adapter_key == "dblp_json":
            return await self._fetch_dblp()
        if adapter_key == "arxiv_atom":
            return await self._fetch_arxiv()
        if adapter_key == "openreview_notes":
            return await self._fetch_openreview()
        if adapter_key == "author_aggregate_json":
            return await self._fetch_author_aggregate()
        if adapter_key == "acl_anthology_events":
            return await self._fetch_acl_anthology_events()
        if adapter_key == "cvf_openaccess":
            return await self._fetch_cvf_openaccess()
        if adapter_key == "talent_signal_json":
            return await self._fetch_talent_signal_json()

        try:
            payload = await fetch_json(self._source_url(), **fetch_options(self.config))
        except Exception as exc:
            if self.config.get("fallback_mode") == "evidence_only":
                return [
                    build_blocked_item(
                        self.config,
                        notes=str(exc),
                        signal_type="paper_author",
                    )
                ]
            raise

        items = [self._record_to_item(record) for record in extract_records(payload)]
        items = [item for item in items if item is not None]
        if items:
            return items
        if self.config.get("fallback_mode") == "evidence_only":
            return [
                build_review_item(
                    self.config,
                    notes="no structured paper author records",
                    signal_type="paper_author",
                )
            ]
        return []

    async def _fetch_semantic_scholar(self) -> list[CrawledItem]:
        try:
            payload = await fetch_json(
                self._source_url(),
                params={
                    "query": str(self.config.get("search_query") or "artificial intelligence"),
                    "limit": str(int(self.config.get("max_results", 10))),
                    "fields": "title,authors,year,url,citationCount,venue",
                },
                **fetch_options(self.config),
            )
        except Exception as exc:
            return [build_blocked_item(self.config, notes=str(exc), signal_type="paper_author")]

        records: list[dict[str, Any]] = []
        for paper in payload.get("data", []):
            if not isinstance(paper, dict):
                continue
            authors = paper.get("authors") if isinstance(paper.get("authors"), list) else []
            for index, author in enumerate(authors[:3], start=1):
                if not isinstance(author, dict):
                    continue
                records.append(
                    {
                        "candidate_name": author.get("name"),
                        "paper_title": paper.get("title"),
                        "venue": paper.get("venue"),
                        "venue_year": paper.get("year"),
                        "author_order": index,
                        "citation_count": paper.get("citationCount"),
                        "evidence_url": paper.get("url"),
                        "confidence": 0.75,
                    }
                )
        return self._records_or_review(records)

    async def _fetch_dblp(self) -> list[CrawledItem]:
        try:
            payload = await fetch_json(
                self._source_url(),
                params={
                    "q": str(self.config.get("search_query") or "machine learning"),
                    "format": "json",
                    "h": str(int(self.config.get("max_results", 10))),
                },
                **fetch_options(self.config),
            )
        except Exception as exc:
            return [build_blocked_item(self.config, notes=str(exc), signal_type="paper_author")]

        hits = (
            payload.get("result", {})
            .get("hits", {})
            .get("hit", [])
        )
        records: list[dict[str, Any]] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            info = hit.get("info") if isinstance(hit.get("info"), dict) else {}
            authors = info.get("authors", {}).get("author", [])
            if isinstance(authors, dict):
                authors = [authors]
            for index, author in enumerate(authors[:3], start=1):
                name = author.get("text") if isinstance(author, dict) else str(author)
                records.append(
                    {
                        "candidate_name": name,
                        "paper_title": info.get("title"),
                        "venue": info.get("venue"),
                        "venue_year": info.get("year"),
                        "author_order": index,
                        "dblp_pid": author.get("@pid") if isinstance(author, dict) else "",
                        "evidence_url": info.get("url"),
                        "confidence": 0.8,
                    }
                )
        return self._records_or_review(records)

    async def _fetch_arxiv(self) -> list[CrawledItem]:
        query = urlencode(
            {
                "search_query": str(self.config.get("search_query") or "cat:cs.AI"),
                "start": "0",
                "max_results": str(int(self.config.get("max_results", 10))),
            }
        )
        url = f"{self._source_url()}?{query}"
        try:
            raw = await fetch_page(url, **fetch_options(self.config))
        except Exception as exc:
            return [build_blocked_item(self.config, notes=str(exc), signal_type="paper_author")]

        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        root = ElementTree.fromstring(raw)
        records: list[dict[str, Any]] = []
        for entry in root.findall("atom:entry", namespace):
            title = self._node_text(entry, "atom:title", namespace)
            year = self._node_text(entry, "atom:published", namespace)[:4]
            evidence_url = self._node_text(entry, "atom:id", namespace)
            for index, author in enumerate(entry.findall("atom:author", namespace)[:3], start=1):
                records.append(
                    {
                        "candidate_name": self._node_text(author, "atom:name", namespace),
                        "paper_title": title,
                        "venue": "arXiv",
                        "venue_year": year,
                        "author_order": index,
                        "evidence_url": evidence_url,
                        "confidence": 0.7,
                    }
                )
        return self._records_or_review(records)

    async def _fetch_openreview(self) -> list[CrawledItem]:
        try:
            payload = await fetch_json(
                self._openreview_api_url(),
                params=self._openreview_params(),
                **fetch_options(self.config),
            )
        except Exception as exc:
            return [build_blocked_item(self.config, notes=str(exc), signal_type="paper_author")]

        return self._records_or_review(self._openreview_notes_to_records(payload))

    async def _fetch_author_aggregate(self) -> list[CrawledItem]:
        raw_path = self.config.get("local_results_path")
        if raw_path not in ("", None):
            data_path = self._resolve_local_results_path(raw_path)
            if data_path is None:
                return [
                    build_blocked_item(
                        self.config,
                        notes="local_results_path is required for author_aggregate_json",
                        signal_type="paper_author",
                    )
                ]
            try:
                payload = json.loads(data_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                return [
                    build_blocked_item(
                        self.config,
                        notes=str(exc),
                        signal_type="paper_author",
                    )
                ]
            return self._records_or_review(self._author_aggregate_to_records(payload))

        try:
            payload = await fetch_json(self._source_url(), **fetch_options(self.config))
        except Exception as exc:
            return [build_blocked_item(self.config, notes=str(exc), signal_type="paper_author")]

        return self._records_or_review(self._author_aggregate_to_records(payload))

    async def _fetch_acl_anthology_events(self) -> list[CrawledItem]:
        records: list[dict[str, Any]] = []
        last_exc: Exception | None = None
        for source_ref in self._source_refs():
            source_url = str(source_ref["url"])
            try:
                html = await fetch_page(source_url, **fetch_options(self.config))
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
            records.extend(
                self._acl_anthology_html_to_records(
                    html,
                    source_url=source_url,
                    source_ref=source_ref,
                )
            )
        if records:
            return self._records_or_review(records)
        if last_exc is not None:
            return [
                build_blocked_item(
                    self.config,
                    notes=str(last_exc),
                    signal_type="paper_author",
                )
            ]
        return self._records_or_review([])

    async def _fetch_cvf_openaccess(self) -> list[CrawledItem]:
        records: list[dict[str, Any]] = []
        last_exc: Exception | None = None
        for source_ref in self._source_refs():
            source_url = str(source_ref["url"])
            try:
                html = await fetch_page(source_url, **fetch_options(self.config))
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
            records.extend(
                self._cvf_openaccess_html_to_records(
                    html,
                    source_url=source_url,
                    source_ref=source_ref,
                )
            )
        if records:
            return self._records_or_review(records)
        if last_exc is not None:
            return [
                build_blocked_item(
                    self.config,
                    notes=str(last_exc),
                    signal_type="paper_author",
                )
            ]
        return self._records_or_review([])

    async def _fetch_talent_signal_json(self) -> list[CrawledItem]:
        raw_path = self.config.get("local_results_path")
        data_path = self._resolve_local_results_path(raw_path)
        if data_path is None:
            return [
                build_blocked_item(
                    self.config,
                    notes="local_results_path is required for talent_signal_json",
                    signal_type="paper_author",
                )
            ]

        try:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return [
                build_blocked_item(
                    self.config,
                    notes=str(exc),
                    signal_type="paper_author",
                )
            ]

        records = [
            self._talent_signal_row_to_paper_record(row)
            for row in extract_records(payload)
            if self._local_source_filter_matches(row)
        ]
        records = [record for record in records if record is not None]
        return self._records_or_review(records)

    def _records_or_review(self, records: list[dict[str, Any]]) -> list[CrawledItem]:
        items = [self._record_to_item(record) for record in records]
        items = [item for item in items if item is not None]
        if items:
            return items
        return [
            build_review_item(
                self.config,
                notes="no paper author records",
                signal_type="paper_author",
            )
        ]

    def _record_to_item(self, record: dict[str, Any]) -> CrawledItem | None:
        candidate_name = self._clean(record.get("candidate_name"))
        evidence_url = self._clean(record.get("evidence_url")) or self._source_url()
        if (
            not candidate_name
            or not evidence_url
            or is_obvious_non_person_candidate_name(candidate_name)
        ):
            return None

        university = self._clean(record.get("university"))
        department = self._clean(record.get("department"))
        email = self._clean(record.get("email"))
        paper_title = self._clean(record.get("paper_title"))
        venue = self._clean(record.get("venue"))
        notes = self._clean(record.get("notes"))
        affiliations = self._clean_list(record.get("affiliations"))
        papers = self._dict_list(record.get("papers"))

        talent_signal = build_talent_signal(
            signal_type="paper_author",
            record_status="structured",
            evidence_url=evidence_url,
            candidate_name=candidate_name,
            university=university,
            department=department,
            email=email,
            track=get_track(self.config),
            confidence=float(record.get("confidence", 0.95)),
            identity_hints={
                key: value
                for key, value in {
                    "dblp_pid": self._clean(record.get("dblp_pid")),
                    "openreview_author_id": self._clean(record.get("openreview_author_id")),
                    "author_order": record.get("author_order"),
                }.items()
                if value not in ("", None)
            },
            source_metrics={
                key: value
                for key, value in {
                    "paper_count_in_scope": record.get("paper_count_in_scope"),
                    "citation_count": record.get("citation_count"),
                    "h_index": record.get("h_index"),
                }.items()
                if value is not None
            },
            evidence_title=(
                self._clean(record.get("evidence_title"))
                or paper_title
                or venue
                or self.config.get("name")
                or self.source_id
            ),
            notes=notes,
        )

        return build_crawled_item(
            self.config,
            title=candidate_name,
            url=evidence_url,
            talent_signal=talent_signal,
            extra={
                "paper_title": paper_title,
                "venue": venue,
                "venue_year": record.get("venue_year"),
                "author_order": record.get("author_order"),
                "paper_count_in_scope": record.get("paper_count_in_scope"),
                "citation_count": record.get("citation_count"),
                "h_index": record.get("h_index"),
                "dblp_pid": self._clean(record.get("dblp_pid")),
                "openreview_note_id": self._clean(record.get("openreview_note_id")),
                "openreview_forum_id": self._clean(record.get("openreview_forum_id")),
                "affiliations": affiliations,
                "papers": papers,
                "notes": notes,
                "original_record_status": self._clean(record.get("original_record_status")),
            },
        )

    def _talent_signal_row_to_paper_record(
        self,
        row: dict[str, Any],
    ) -> dict[str, Any] | None:
        candidate_name = self._clean(row.get("candidate_name"))
        evidence_url = self._clean(row.get("evidence_url"))
        if (
            not candidate_name
            or not evidence_url
            or is_obvious_non_person_candidate_name(candidate_name)
        ):
            return None
        return {
            "candidate_name": candidate_name,
            "university": row.get("university"),
            "department": row.get("department"),
            "email": row.get("email"),
            "paper_title": row.get("paper_title") or row.get("evidence_title"),
            "venue": row.get("venue") or row.get("source_name"),
            "venue_year": row.get("venue_year") or self._extract_year(row.get("time_info")),
            "author_order": row.get("author_order"),
            "citation_count": row.get("citation_count"),
            "dblp_pid": row.get("dblp_pid"),
            "evidence_title": row.get("evidence_title"),
            "evidence_url": evidence_url,
            "confidence": row.get("confidence", 0.7),
            "notes": row.get("notes"),
            "original_record_status": row.get("record_status"),
        }

    def _author_aggregate_to_records(self, payload: Any) -> list[dict[str, Any]]:
        authors: list[Any] = []
        source_name = ""
        if isinstance(payload, dict):
            source_name = self._clean(payload.get("source"))
            if isinstance(payload.get("authors"), list):
                authors = payload.get("authors", [])
            elif isinstance(payload.get("results"), dict):
                nested_authors = payload["results"].get("authors")
                if isinstance(nested_authors, list):
                    authors = nested_authors
        elif isinstance(payload, list):
            authors = payload

        records: list[dict[str, Any]] = []
        for author in authors:
            if not isinstance(author, dict):
                continue
            papers = self._dict_list(author.get("papers"))
            first_paper = papers[0] if papers else {}
            affiliations = self._clean_list(author.get("affiliations"))
            paper_count_in_scope = author.get("total_papers")
            if paper_count_in_scope is None:
                paper_count_in_scope = len(papers)
            records.append(
                {
                    "candidate_name": author.get("candidate_name") or author.get("name"),
                    "university": self._clean(author.get("university")) or (
                        affiliations[0] if affiliations else ""
                    ),
                    "paper_title": first_paper.get("title") or author.get("paper_title"),
                    "venue": first_paper.get("venue") or author.get("venue"),
                    "venue_year": first_paper.get("year") or author.get("venue_year"),
                    "paper_count_in_scope": paper_count_in_scope,
                    "citation_count": author.get("total_citations") or author.get("citation_count"),
                    "h_index": author.get("h_index"),
                    "affiliations": affiliations,
                    "papers": papers,
                    "evidence_url": self._clean(author.get("evidence_url")) or self._source_url(),
                    "confidence": 0.8,
                    "notes": (
                        f"aggregated author profile from {source_name}" if source_name else ""
                    ),
                }
            )
        return records

    def _openreview_notes_to_records(self, payload: Any) -> list[dict[str, Any]]:
        notes = payload.get("notes") if isinstance(payload, dict) else []
        if not isinstance(notes, list):
            return []

        records: list[dict[str, Any]] = []
        for note in notes:
            if not isinstance(note, dict):
                continue
            content = note.get("content") if isinstance(note.get("content"), dict) else {}
            authors = self._clean_list(self._openreview_value(content.get("authors")))
            authorids = self._clean_list(self._openreview_value(content.get("authorids")))
            title = self._clean(self._openreview_value(content.get("title")))
            venue = self._clean(self._openreview_value(content.get("venue"))) or self._clean(
                note.get("domain")
            )
            venue_year = self._extract_year(
                venue,
                self._clean(note.get("domain")),
                self._clean(note.get("invitation")),
            )
            forum_id = self._clean(note.get("forum") or note.get("id"))
            evidence_url = (
                f"https://openreview.net/forum?id={forum_id}" if forum_id else self._source_url()
            )
            for index, author in enumerate(authors[:3], start=1):
                records.append(
                    {
                        "candidate_name": author,
                        "paper_title": title,
                        "venue": venue,
                        "venue_year": venue_year,
                        "author_order": index,
                        "evidence_url": evidence_url,
                        "openreview_author_id": (
                            authorids[index - 1] if len(authorids) >= index else ""
                        ),
                        "openreview_note_id": self._clean(note.get("id")),
                        "openreview_forum_id": self._clean(note.get("forum")),
                        "confidence": 0.78,
                    }
                )
        return records

    def _acl_anthology_html_to_records(
        self,
        html: str,
        *,
        source_url: str,
        source_ref: dict[str, Any],
    ) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        records: list[dict[str, Any]] = []
        max_papers = int(source_ref.get("max_papers") or self.config.get("max_papers", 30))
        max_authors = int(
            source_ref.get("max_authors_per_paper")
            or self.config.get("max_authors_per_paper", 3)
        )
        venue = self._clean(source_ref.get("venue")) or self._clean(self.config.get("venue"))
        venue_year = source_ref.get("year") or self._extract_year(source_url)

        seen_papers: set[str] = set()
        for container in soup.select("p, li, div"):
            title_link = self._find_acl_paper_link(container)
            if title_link is None:
                continue
            paper_href = self._clean(title_link.get("href"))
            evidence_url = urljoin(source_url, paper_href)
            if evidence_url in seen_papers:
                continue
            seen_papers.add(evidence_url)

            title = title_link.get_text(" ", strip=True)
            if not title:
                continue
            author_links = [
                link
                for link in container.select("a[href]")
                if "/people/" in self._clean(link.get("href"))
            ]
            authors = [link.get_text(" ", strip=True) for link in author_links]
            authors = [author for author in authors if author][:max_authors]
            for index, author in enumerate(authors, start=1):
                records.append(
                    {
                        "candidate_name": author,
                        "paper_title": title,
                        "venue": venue or self._infer_venue_from_url(source_url),
                        "venue_year": venue_year,
                        "author_order": index,
                        "evidence_url": evidence_url,
                        "confidence": 0.72,
                        "notes": "parsed from ACL Anthology event page",
                    }
                )
            if len(seen_papers) >= max_papers:
                break
        return records

    def _cvf_openaccess_html_to_records(
        self,
        html: str,
        *,
        source_url: str,
        source_ref: dict[str, Any],
    ) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "lxml")
        records: list[dict[str, Any]] = []
        max_papers = int(source_ref.get("max_papers") or self.config.get("max_papers", 30))
        max_authors = int(
            source_ref.get("max_authors_per_paper")
            or self.config.get("max_authors_per_paper", 3)
        )
        venue = self._clean(source_ref.get("venue")) or self._infer_venue_from_url(source_url)
        venue_year = source_ref.get("year") or self._extract_year(source_url)

        for paper_index, title_node in enumerate(soup.select("dt.ptitle"), start=1):
            if paper_index > max_papers:
                break
            link = title_node.select_one("a[href]")
            if link is None:
                continue
            title = link.get_text(" ", strip=True)
            evidence_url = urljoin(source_url, self._clean(link.get("href")))
            author_node = title_node.find_next_sibling("dd")
            authors = self._split_author_text(
                author_node.get_text(" ", strip=True) if author_node is not None else ""
            )[:max_authors]
            for index, author in enumerate(authors, start=1):
                records.append(
                    {
                        "candidate_name": author,
                        "paper_title": title,
                        "venue": venue,
                        "venue_year": venue_year,
                        "author_order": index,
                        "evidence_url": evidence_url,
                        "confidence": 0.72,
                        "notes": "parsed from CVF OpenAccess paper index",
                    }
                )
        return records

    def _openreview_api_url(self) -> str:
        source_url = self._source_url()
        parsed = urlparse(source_url)
        if parsed.netloc in {"api.openreview.net", "api2.openreview.net"} and parsed.path:
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return str(self.config.get("api_url") or "https://api2.openreview.net/notes")

    def _openreview_params(self) -> dict[str, str]:
        source_url = self._source_url()
        parsed = urlparse(source_url)
        query = parse_qs(parsed.query)

        invitation = self._clean(
            self.config.get("openreview_invitation")
            or self.config.get("invitation")
            or self._query_value(query, "invitation")
        )
        if not invitation:
            group_id = self._clean(
                self.config.get("openreview_group_id")
                or self.config.get("group_id")
                or self._query_value(query, "id")
            )
            if group_id:
                suffix = self._clean(self.config.get("invitation_suffix")) or "-/Submission"
                invitation = f"{group_id.rstrip('/')}/{suffix.lstrip('/')}"

        max_results = self.config.get("max_results", self._query_value(query, "limit") or 10)
        params: dict[str, str] = {"limit": str(int(max_results))}
        if invitation:
            params["invitation"] = invitation

        content_venue = self._clean(
            self.config.get("content_venue") or self._query_value(query, "content.venue")
        )
        if content_venue:
            params["content.venue"] = content_venue

        forum_id = self._clean(self.config.get("forum") or self._query_value(query, "forum"))
        if forum_id:
            params["forum"] = forum_id

        return params

    @staticmethod
    def _node_text(node: ElementTree.Element, path: str, namespace: dict[str, str]) -> str:
        found = node.find(path, namespace)
        if found is None or found.text is None:
            return ""
        return found.text.strip()

    def _source_url(self) -> str:
        refs = self._source_refs()
        if refs:
            return str(refs[0]["url"])
        return str(self.config.get("url") or "")

    def _source_refs(self) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for value in self.config.get("seed_urls") or []:
            if isinstance(value, str) and value.strip():
                refs.append({"url": value.strip()})
            elif isinstance(value, dict):
                url = self._clean(value.get("url"))
                if url:
                    ref = dict(value)
                    ref["url"] = url
                    refs.append(ref)
        if not refs:
            url = self._clean(self.config.get("url"))
            if url:
                refs.append({"url": url})
        return refs

    def _local_source_filter_matches(self, row: dict[str, Any]) -> bool:
        row_source_id = self._clean(row.get("source_id"))
        if not row_source_id:
            return False
        source_ids = self._configured_local_source_ids()
        if source_ids and row_source_id in source_ids:
            return True
        prefixes = self._configured_local_source_prefixes()
        if prefixes and any(row_source_id.startswith(prefix) for prefix in prefixes):
            return True
        return not source_ids and not prefixes and row_source_id == self.source_id

    def _configured_local_source_ids(self) -> set[str]:
        raw_value = self.config.get("local_source_ids")
        values: list[str] = []
        if isinstance(raw_value, str):
            values = [raw_value]
        elif isinstance(raw_value, list):
            values = [value for value in raw_value if isinstance(value, str)]
        return {value.strip() for value in values if value.strip()}

    def _configured_local_source_prefixes(self) -> list[str]:
        raw_value = self.config.get("local_source_id_prefixes")
        values: list[str] = []
        if isinstance(raw_value, str):
            values = [raw_value]
        elif isinstance(raw_value, list):
            values = [value for value in raw_value if isinstance(value, str)]
        return [value.strip() for value in values if value.strip()]

    @staticmethod
    def _dict_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _clean_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [cleaned for item in value if (cleaned := str(item).strip())]

    @staticmethod
    def _openreview_value(value: Any) -> Any:
        if isinstance(value, dict) and "value" in value:
            return value.get("value")
        return value

    @staticmethod
    def _extract_year(*values: Any) -> int | None:
        for value in values:
            if not value:
                continue
            match = re.search(r"(19|20)\d{2}", str(value))
            if match:
                return int(match.group(0))
        return None

    @staticmethod
    def _query_value(query: dict[str, list[str]], key: str) -> str:
        values = query.get(key) or []
        return values[0] if values else ""

    @staticmethod
    def _find_acl_paper_link(container: Any) -> Any | None:
        for link in container.select("a[href]"):
            href = str(link.get("href") or "")
            if re.search(r"/20\d{2}\.[^/]+/$", href):
                return link
        return None

    @staticmethod
    def _split_author_text(value: str) -> list[str]:
        value = re.sub(r"\s+", " ", value or "").strip()
        if not value:
            return []
        value = value.replace(" and ", ", ")
        return [piece.strip() for piece in value.split(",") if piece.strip()]

    @staticmethod
    def _infer_venue_from_url(value: str) -> str:
        upper_value = value.upper()
        for venue in ("CVPR", "ICCV", "ECCV", "ACL", "EMNLP", "NAACL"):
            if venue in upper_value:
                return venue
        return ""

    @staticmethod
    def _resolve_local_results_path(raw_path: Any) -> Path | None:
        if raw_path in ("", None):
            return None
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = BASE_DIR / path
        return path if path.exists() else None

    @staticmethod
    def _clean(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()
