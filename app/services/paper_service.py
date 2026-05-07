from __future__ import annotations

import asyncio
import hashlib
import json
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import asyncpg

from app.schemas.paper import (
    PaperAffiliationMapping,
    PaperIngestPayload,
    PaperIngestRunRecord,
    PaperRecord,
    PaperSourceRef,
)

_SCHEMA_READY = False
_SCHEMA_LOCK = asyncio.Lock()

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_YEAR_SPECIFIC_SOURCE_ID_RE = re.compile(r"(^|_)(19|20)\d{2}($|_)")

SOURCE_PRIORITY = {
    "raw_official": 3,
    "official_api": 2,
    "third_party_api": 1,
}


@dataclass(slots=True)
class PaperIngestSummary:
    run_id: str
    source_id: str
    status: str
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    filtered_chinese_count: int = 0
    paper_ids: list[str] = field(default_factory=list)
    error_message: str | None = None


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


@asynccontextmanager
async def _acquire_conn(pool: asyncpg.Pool):
    if hasattr(pool, "acquire"):
        async with pool.acquire() as conn:  # type: ignore[union-attr]
            yield conn
        return
    resolver = getattr(pool, "_resolve_pool", None)
    if resolver is None:
        raise TypeError("Pool object does not support connection acquisition")
    resolved_pool = await resolver()
    async with resolved_pool.acquire() as conn:
        yield conn


def _normalize_doi(value: Any) -> str | None:
    raw = _clean_text(value).lower()
    if not raw:
        return None
    raw = raw.replace("https://doi.org/", "").replace("http://doi.org/", "")
    raw = raw.replace("doi:", "").strip()
    return raw or None


def _normalize_title(value: Any) -> str:
    return " ".join(_clean_text(value).lower().split())


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = _clean_text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _to_iso(value: Any) -> str | None:
    dt = _to_datetime(value)
    return dt.isoformat() if dt else None


def title_contains_cjk(title: str) -> bool:
    return bool(_CJK_RE.search(title or ""))


def _normalize_authors(value: Any) -> list[str]:
    if isinstance(value, str):
        token = _clean_text(value)
        if not token:
            return []
        try:
            value = json.loads(token)
        except json.JSONDecodeError:
            return [token]
    if not isinstance(value, list):
        return []
    return [_clean_text(item) for item in value if _clean_text(item)]


def _normalize_affiliations(value: Any) -> list[PaperAffiliationMapping]:
    if isinstance(value, str):
        token = _clean_text(value)
        if not token:
            return []
        try:
            value = json.loads(token)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    mappings: list[PaperAffiliationMapping] = []
    for item in value:
        try:
            mapping = (
                item
                if isinstance(item, PaperAffiliationMapping)
                else PaperAffiliationMapping.model_validate(item)
            )
        except Exception:
            continue
        if not _clean_text(mapping.author_name) or not _clean_text(mapping.affiliation):
            continue
        mappings.append(mapping)
    return mappings


def build_canonical_uid(
    *,
    doi: Any = None,
    source_id: Any = None,
    raw_id: Any = None,
    title: Any = None,
    publication_date: Any = None,
) -> str:
    doi_norm = _normalize_doi(doi)
    if doi_norm:
        return f"doi:{doi_norm}"
    source_token = _clean_text(source_id)
    raw_token = _clean_text(raw_id)
    if source_token and raw_token:
        return f"source:{source_token}:{raw_token}"
    title_token = _normalize_title(title)
    date_token = (_to_iso(publication_date) or "").split("T", 1)[0]
    digest = hashlib.sha1(f"{title_token}|{date_token}".encode("utf-8")).hexdigest()[:24]
    return f"fingerprint:{digest}"


def _source_score(source: PaperSourceRef) -> tuple[int, int]:
    completeness = sum(
        1
        for token in (
            source.name,
            source.source_id,
            source.raw_id,
            source.detail_url,
            source.pdf_url,
            source.venue,
            source.venue_year,
            source.track,
        )
        if token not in ("", None)
    )
    return SOURCE_PRIORITY.get(source.type, 0), completeness


def _choose_better_source(current: PaperSourceRef, candidate: PaperSourceRef) -> PaperSourceRef:
    current_id = _clean_text(current.source_id)
    candidate_id = _clean_text(candidate.source_id)
    if current_id and candidate_id:
        current_is_year_specific = bool(_YEAR_SPECIFIC_SOURCE_ID_RE.search(current_id))
        candidate_is_year_specific = bool(_YEAR_SPECIFIC_SOURCE_ID_RE.search(candidate_id))
        if current_is_year_specific and not candidate_is_year_specific:
            return candidate
    return candidate if _source_score(candidate) > _source_score(current) else current


def _choose_better_text(current: str | None, candidate: str | None) -> str | None:
    current_text = _clean_text(current)
    candidate_text = _clean_text(candidate)
    if not current_text:
        return candidate_text or None
    if len(candidate_text) > len(current_text):
        return candidate_text
    return current_text


def _affiliation_score(value: list[PaperAffiliationMapping]) -> tuple[int, int]:
    non_empty = sum(1 for item in value if _clean_text(item.affiliation))
    return non_empty, len(value)


def _choose_better_authors(current: list[str], candidate: list[str]) -> list[str]:
    return candidate if len(candidate) > len(current) else current


def _choose_better_affiliations(
    current: list[PaperAffiliationMapping],
    candidate: list[PaperAffiliationMapping],
) -> list[PaperAffiliationMapping]:
    return candidate if _affiliation_score(candidate) > _affiliation_score(current) else current


def normalize_payload(payload: PaperIngestPayload | dict[str, Any]) -> PaperIngestPayload:
    if isinstance(payload, PaperIngestPayload):
        model = payload
    else:
        model = PaperIngestPayload.model_validate(payload)
    model.doi = _normalize_doi(model.doi)
    model.title = _clean_text(model.title)
    model.abstract = _clean_text(model.abstract) or None
    model.authors = _normalize_authors(model.authors)
    model.affiliations = _normalize_affiliations(model.affiliations)
    model.raw_id = _clean_text(model.raw_id) or None
    model.detail_url = _clean_text(model.detail_url) or None
    model.pdf_url = _clean_text(model.pdf_url) or None
    model.venue = _clean_text(model.venue) or None
    model.track = _clean_text(model.track) or None
    model.source.type = _clean_text(model.source.type)
    model.source.name = _clean_text(model.source.name)
    model.source.source_id = _clean_text(model.source.source_id)
    model.source.raw_id = _clean_text(model.source.raw_id) or None
    model.source.detail_url = _clean_text(model.source.detail_url) or None
    model.source.pdf_url = _clean_text(model.source.pdf_url) or None
    model.source.venue = _clean_text(model.source.venue) or None
    model.source.track = _clean_text(model.source.track) or None
    if model.publication_date:
        model.publication_date = _to_iso(model.publication_date)
    return model


async def ensure_paper_tables(pool: asyncpg.Pool) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    async with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        async with _acquire_conn(pool) as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    canonical_uid TEXT NOT NULL UNIQUE,
                    doi TEXT,
                    title TEXT NOT NULL,
                    abstract TEXT,
                    publication_date TIMESTAMPTZ,
                    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
                    affiliations JSONB NOT NULL DEFAULT '[]'::jsonb,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    raw_id TEXT,
                    detail_url TEXT,
                    pdf_url TEXT,
                    venue TEXT,
                    venue_year INTEGER,
                    track TEXT,
                    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS paper_id TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS paper_uid TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS canonical_uid TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS dedup_key TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS normalized_title TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS title_fingerprint TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS source_type TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS source_name TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS source_id TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS source TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS target_key TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS raw_id TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS detail_url TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS pdf_url TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS venue TEXT")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS venue_year INTEGER")
            await conn.execute("ALTER TABLE papers ADD COLUMN IF NOT EXISTS track TEXT")
            await conn.execute(
                "ALTER TABLE papers ADD COLUMN IF NOT EXISTS "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
            )
            await conn.execute(
                "ALTER TABLE papers ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMPTZ"
            )
            await conn.execute("DROP INDEX IF EXISTS idx_papers_canonical_uid")
            await conn.execute("DROP INDEX IF EXISTS idx_papers_paper_id")
            await conn.execute(
                """
                UPDATE papers
                SET
                    source_type = COALESCE(NULLIF(source_type, ''), 'third_party_api'),
                    source_name = COALESCE(NULLIF(source_name, ''), NULLIF(source, ''), 'legacy'),
                    source_id = COALESCE(NULLIF(source_id, ''), NULLIF(source, ''), 'legacy'),
                    paper_id = COALESCE(
                        NULLIF(paper_id, ''),
                        NULLIF(paper_uid, ''),
                        NULLIF(canonical_uid, ''),
                        NULLIF(dedup_key, ''),
                        'legacy:' || md5(COALESCE(title, '') || '|' || COALESCE(doi, ''))
                    ),
                    paper_uid = COALESCE(NULLIF(paper_uid, ''), paper_id),
                    canonical_uid = COALESCE(
                        NULLIF(canonical_uid, ''),
                        CASE
                            WHEN COALESCE(doi, '') <> '' THEN
                                'doi:' || lower(
                                    replace(
                                        replace(
                                            replace(doi, 'https://doi.org/', ''),
                                            'http://doi.org/',
                                            ''
                                        ),
                                        'doi:',
                                        ''
                                    )
                                )
                            WHEN COALESCE(source_id, '') <> '' AND COALESCE(raw_id, '') <> '' THEN
                                'source:' || source_id || ':' || raw_id
                            ELSE
                                'legacy:' || md5(
                                    lower(regexp_replace(COALESCE(title, ''), '\\s+', ' ', 'g'))
                                    || '|'
                                    || COALESCE(publication_date::text, '')
                                )
                        END
                    ),
                    authors = COALESCE(authors, '[]'::jsonb),
                    affiliations = COALESCE(affiliations, '[]'::jsonb),
                    ingested_at = COALESCE(ingested_at, created_at, now())
                WHERE paper_id IS NULL
                   OR paper_id = ''
                   OR paper_uid IS NULL
                   OR paper_uid = ''
                   OR canonical_uid IS NULL
                   OR canonical_uid = ''
                   OR source_type IS NULL
                   OR source_name IS NULL
                   OR source_id IS NULL
                   OR ingested_at IS NULL
                """
            )
            await conn.execute(
                """
                DELETE FROM papers
                WHERE ctid IN (
                    SELECT ctid
                    FROM (
                        SELECT
                            ctid,
                            row_number() OVER (
                                PARTITION BY paper_id
                                ORDER BY
                                    updated_at DESC NULLS LAST,
                                    created_at DESC NULLS LAST,
                                    ctid DESC
                            ) AS rn
                        FROM papers
                        WHERE COALESCE(paper_id, '') <> ''
                    ) ranked
                    WHERE rn > 1
                )
                """
            )
            await conn.execute(
                """
                DELETE FROM papers
                WHERE ctid IN (
                    SELECT ctid
                    FROM (
                        SELECT
                            ctid,
                            row_number() OVER (
                                PARTITION BY canonical_uid
                                ORDER BY
                                    updated_at DESC NULLS LAST,
                                    created_at DESC NULLS LAST,
                                    ctid DESC
                            ) AS rn
                        FROM papers
                        WHERE COALESCE(canonical_uid, '') <> ''
                    ) ranked
                    WHERE rn > 1
                )
                """
            )
            await conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_canonical_uid
                ON papers(canonical_uid)
                WHERE COALESCE(canonical_uid, '') <> ''
                """
            )
            await conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_paper_id
                ON papers(paper_id)
                WHERE COALESCE(paper_id, '') <> ''
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_papers_publication_date "
                "ON papers(publication_date DESC)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_papers_source_id ON papers(source_id)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_papers_venue_year ON papers(venue, venue_year DESC)"
            )
            await conn.execute("DROP TABLE IF EXISTS paper_authorships")
            await conn.execute("DROP TABLE IF EXISTS paper_sources")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_ingest_runs (
                    run_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    inserted_count INTEGER NOT NULL DEFAULT 0,
                    updated_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    filtered_chinese_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    finished_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            await conn.execute(
                "ALTER TABLE paper_ingest_runs ADD COLUMN IF NOT EXISTS "
                "inserted_count INTEGER NOT NULL DEFAULT 0"
            )
            await conn.execute(
                "ALTER TABLE paper_ingest_runs ADD COLUMN IF NOT EXISTS "
                "updated_count INTEGER NOT NULL DEFAULT 0"
            )
            await conn.execute(
                "ALTER TABLE paper_ingest_runs ADD COLUMN IF NOT EXISTS "
                "skipped_count INTEGER NOT NULL DEFAULT 0"
            )
            await conn.execute(
                "ALTER TABLE paper_ingest_runs ADD COLUMN IF NOT EXISTS "
                "filtered_chinese_count INTEGER NOT NULL DEFAULT 0"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_paper_ingest_runs_source_id "
                "ON paper_ingest_runs(source_id, started_at DESC)"
            )
        _SCHEMA_READY = True


async def _upsert_paper(
    conn: asyncpg.Connection,
    *,
    payload: PaperIngestPayload,
) -> tuple[str, bool]:
    canonical_uid = build_canonical_uid(
        doi=payload.doi,
        source_id=payload.source.source_id,
        raw_id=payload.raw_id,
        title=payload.title,
        publication_date=payload.publication_date,
    )
    paper_id = payload.paper_id or f"paper_{uuid4().hex}"
    existing = await conn.fetchrow(
        "SELECT * FROM papers WHERE canonical_uid = $1 LIMIT 1",
        canonical_uid,
    )
    if existing is None and payload.paper_id:
        existing = await conn.fetchrow(
            "SELECT * FROM papers WHERE paper_id = $1 LIMIT 1",
            payload.paper_id,
        )
    if existing is None:
        row = await conn.fetchrow(
            """
            INSERT INTO papers (
                paper_id,
                paper_uid,
                canonical_uid,
                doi,
                title,
                abstract,
                publication_date,
                authors,
                affiliations,
                source,
                source_type,
                source_name,
                source_id,
                raw_id,
                detail_url,
                pdf_url,
                venue,
                venue_year,
                track,
                target_key
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11,
                $12, $13, $14, $15, $16, $17, $18, $19, $20
            )
            RETURNING paper_id
            """,
            paper_id,
            paper_id,
            canonical_uid,
            payload.doi,
            payload.title,
            payload.abstract,
            _to_datetime(payload.publication_date),
            json.dumps(payload.authors),
            json.dumps([item.model_dump() for item in payload.affiliations]),
            payload.source.name,
            payload.source.type,
            payload.source.name,
            payload.source.source_id,
            payload.raw_id,
            payload.detail_url,
            payload.pdf_url,
            payload.venue,
            payload.venue_year,
            payload.track,
            payload.source.source_id,
        )
        assert row is not None
        return str(row["paper_id"]), True
    assert existing is not None
    existing_source = PaperSourceRef(
        type=_clean_text(existing["source_type"]),
        name=_clean_text(existing["source_name"]),
        source_id=_clean_text(existing["source_id"]),
        raw_id=_clean_text(existing["raw_id"]) or None,
        detail_url=_clean_text(existing["detail_url"]) or None,
        pdf_url=_clean_text(existing["pdf_url"]) or None,
        venue=_clean_text(existing["venue"]) or None,
        venue_year=existing["venue_year"],
        track=_clean_text(existing["track"]) or None,
    )
    source = _choose_better_source(existing_source, payload.source)
    authors = _choose_better_authors(_normalize_authors(existing["authors"]), payload.authors)
    affiliations = _choose_better_affiliations(
        _normalize_affiliations(existing["affiliations"]),
        payload.affiliations,
    )
    await conn.execute(
        """
        UPDATE papers
        SET
            canonical_uid = $2,
            doi = COALESCE(papers.doi, $3),
            title = CASE WHEN papers.title = '' THEN $4 ELSE papers.title END,
            abstract = $5,
            publication_date = COALESCE(papers.publication_date, $6),
            authors = $7::jsonb,
            affiliations = $8::jsonb,
            source = COALESCE(papers.source, $9),
            source_type = $10,
            source_name = $11,
            source_id = $12,
            raw_id = COALESCE(papers.raw_id, $13),
            detail_url = COALESCE(papers.detail_url, $14),
            pdf_url = COALESCE(papers.pdf_url, $15),
            venue = COALESCE(papers.venue, $16),
            venue_year = COALESCE(papers.venue_year, $17),
            track = COALESCE(papers.track, $18),
            target_key = COALESCE(papers.target_key, $19),
            updated_at = now()
        WHERE paper_id = $1
        """,
        str(existing["paper_id"]),
        canonical_uid,
        payload.doi,
        payload.title,
        _choose_better_text(existing["abstract"], payload.abstract),
        _to_datetime(payload.publication_date),
        json.dumps(authors),
        json.dumps([item.model_dump() for item in affiliations]),
        source.name,
        source.type,
        source.name,
        source.source_id,
        payload.raw_id,
        payload.detail_url,
        payload.pdf_url,
        payload.venue,
        payload.venue_year,
        payload.track,
        source.source_id,
    )
    return str(existing["paper_id"]), False


async def _create_run(conn: asyncpg.Connection, source_id: str) -> str:
    run_id = f"paper_run_{uuid4().hex}"
    await conn.execute(
        """
        INSERT INTO paper_ingest_runs (run_id, source_id, status)
        VALUES ($1, $2, 'running')
        """,
        run_id,
        source_id,
    )
    return run_id


async def _finish_run(conn: asyncpg.Connection, summary: PaperIngestSummary) -> None:
    await conn.execute(
        """
        UPDATE paper_ingest_runs
        SET
            status = $2,
            inserted_count = $3,
            updated_count = $4,
            skipped_count = $5,
            filtered_chinese_count = $6,
            error_message = $7,
            finished_at = now(),
            updated_at = now()
        WHERE run_id = $1
        """,
        summary.run_id,
        summary.status,
        summary.inserted_count,
        summary.updated_count,
        summary.skipped_count,
        summary.filtered_chinese_count,
        summary.error_message,
    )


async def ingest_papers(
    pool: asyncpg.Pool,
    *,
    source_id: str,
    payloads: list[PaperIngestPayload | dict[str, Any]],
    dry_run: bool = False,
) -> PaperIngestSummary:
    await ensure_paper_tables(pool)
    normalized = [normalize_payload(item) for item in payloads]
    if dry_run:
        summary = PaperIngestSummary(
            run_id=f"paper_run_dry_{uuid4().hex}",
            source_id=source_id,
            status="dry_run",
        )
        for payload in normalized:
            if title_contains_cjk(payload.title):
                summary.filtered_chinese_count += 1
            else:
                summary.inserted_count += 1
        return summary

    async with _acquire_conn(pool) as conn:
        run_id = await _create_run(conn, source_id)
    summary = PaperIngestSummary(run_id=run_id, source_id=source_id, status="success")

    try:
        async with _acquire_conn(pool) as conn:
            async with conn.transaction():
                for payload in normalized:
                    if title_contains_cjk(payload.title):
                        summary.filtered_chinese_count += 1
                        continue
                    paper_id, inserted = await _upsert_paper(conn, payload=payload)
                    summary.paper_ids.append(paper_id)
                    if inserted:
                        summary.inserted_count += 1
                    else:
                        summary.updated_count += 1
    except Exception as exc:  # noqa: BLE001
        summary.status = "failed"
        summary.error_message = str(exc)
        async with _acquire_conn(pool) as conn:
            await _finish_run(conn, summary)
        raise

    async with _acquire_conn(pool) as conn:
        await _finish_run(conn, summary)
    return summary


def payload_from_crawled_item(
    item: Any,
    source_config: dict[str, Any],
) -> PaperIngestPayload | None:
    extra = getattr(item, "extra", None) or {}
    paper = extra.get("paper")
    if not isinstance(paper, dict):
        return None
    affiliations = []
    authors_payload = []
    for author in extra.get("authors") or []:
        if not isinstance(author, dict):
            continue
        author_name = _clean_text(author.get("name_normalized") or author.get("name_raw"))
        if author_name:
            authors_payload.append(author_name)
        affiliation = _clean_text(author.get("affiliation"))
        if author_name and affiliation:
            affiliations.append(
                PaperAffiliationMapping(
                    author_order=int(author.get("author_order") or (len(authors_payload) or 1)),
                    author_name=author_name,
                    affiliation=affiliation,
                )
            )
    source = PaperSourceRef(
        type=_clean_text(
            source_config.get("source_type") or paper.get("source_type") or "raw_official"
        ),
        name=_clean_text(
            source_config.get("name") or paper.get("venue_full") or paper.get("source")
        ),
        source_id=_clean_text(source_config.get("id")),
        raw_id=_clean_text(paper.get("raw_id")) or None,
        detail_url=_clean_text(paper.get("url")) or None,
        pdf_url=_clean_text(paper.get("pdf_url")) or None,
        venue=_clean_text(paper.get("venue")) or None,
        venue_year=paper.get("year"),
        track=_clean_text(paper.get("track")) or None,
    )
    return PaperIngestPayload(
        paper_id=_clean_text(paper.get("paper_id")) or f"paper_{uuid4().hex}",
        title=_clean_text(paper.get("title")),
        doi=paper.get("doi"),
        abstract=_clean_text(paper.get("abstract")) or None,
        publication_date=_to_iso(getattr(item, "published_at", None)),
        authors=authors_payload,
        affiliations=affiliations,
        source=source,
        raw_id=_clean_text(paper.get("raw_id")) or None,
        detail_url=_clean_text(paper.get("url")) or None,
        pdf_url=_clean_text(paper.get("pdf_url")) or None,
        venue=_clean_text(paper.get("venue")) or None,
        venue_year=paper.get("year"),
        track=_clean_text(paper.get("track")) or None,
    )


async def ingest_crawl_result(
    pool: asyncpg.Pool,
    result: Any,
    source_config: dict[str, Any],
    *,
    dry_run: bool = False,
) -> PaperIngestSummary:
    payloads = []
    all_items = getattr(result, "items_all", None) or getattr(result, "items", [])
    for item in all_items:
        payload = payload_from_crawled_item(item, source_config)
        if payload is not None:
            payloads.append(payload)
    return await ingest_papers(
        pool,
        source_id=_clean_text(source_config.get("id")) or "unknown",
        payloads=payloads,
        dry_run=dry_run,
    )


def _row_to_paper_record(row: asyncpg.Record | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    source = {
        "type": _clean_text(payload.get("source_type")),
        "name": _clean_text(payload.get("source_name")),
        "source_id": _clean_text(payload.get("source_id")),
    }
    return PaperRecord(
        paper_id=_clean_text(payload.get("paper_id") or payload.get("paper_uid")),
        canonical_uid=_clean_text(payload.get("canonical_uid")),
        doi=_clean_text(payload.get("doi")) or None,
        title=_clean_text(payload.get("title")),
        abstract=_clean_text(payload.get("abstract")) or None,
        publication_date=_to_iso(payload.get("publication_date")),
        authors=_normalize_authors(payload.get("authors")),
        affiliations=_normalize_affiliations(payload.get("affiliations")),
        source=PaperSourceRef.model_validate(source),
        detail_url=_clean_text(payload.get("detail_url")) or None,
        pdf_url=_clean_text(payload.get("pdf_url")) or None,
        venue=_clean_text(payload.get("venue")) or None,
        venue_year=payload.get("venue_year"),
        track=_clean_text(payload.get("track")) or None,
        ingested_at=_to_iso(payload.get("ingested_at")),
        updated_at=_to_iso(payload.get("updated_at")),
    ).model_dump(mode="json")


async def list_papers(
    pool: asyncpg.Pool,
    *,
    q: str | None = None,
    doi: str | None = None,
    source_type: str | None = None,
    source_name: str | None = None,
    source_id: str | None = None,
    venue: str | None = None,
    venue_year: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    has_abstract: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "publication_date",
    order: str = "desc",
) -> dict[str, Any]:
    await ensure_paper_tables(pool)
    clauses: list[str] = []
    params: list[Any] = []

    def add_clause(sql: str, value: Any) -> None:
        params.append(value)
        clauses.append(sql.format(len(params)))

    if q:
        params.append(f"%{_clean_text(q)}%")
        token = f"${len(params)}"
        clauses.append(f"(p.title ILIKE {token} OR COALESCE(p.abstract, '') ILIKE {token})")
    if doi:
        add_clause("LOWER(COALESCE(p.doi, '')) = LOWER(${})", _normalize_doi(doi))
    if source_type:
        add_clause("p.source_type = ${}", _clean_text(source_type))
    if source_name:
        add_clause("p.source_name = ${}", _clean_text(source_name))
    if source_id:
        add_clause("p.source_id = ${}", _clean_text(source_id))
    if venue:
        add_clause("p.venue = ${}", _clean_text(venue))
    if venue_year is not None:
        add_clause("p.venue_year = ${}", venue_year)
    if date_from:
        add_clause("p.publication_date >= ${}::timestamptz", _to_datetime(date_from))
    if date_to:
        add_clause("p.publication_date <= ${}::timestamptz", _to_datetime(date_to))
    if has_abstract is True:
        clauses.append("COALESCE(p.abstract, '') <> ''")
    elif has_abstract is False:
        clauses.append("COALESCE(p.abstract, '') = ''")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sort_map = {
        "publication_date": "publication_date",
        "updated_at": "updated_at",
        "ingested_at": "ingested_at",
        "title": "title",
    }
    sort_column = sort_map.get(_clean_text(sort_by), "publication_date")
    sort_order = "ASC" if _clean_text(order) == "asc" else "DESC"
    offset = max(page - 1, 0) * page_size

    total = await pool.fetchval(
        f"SELECT COUNT(*)::int FROM papers p {where_sql}",
        *params,
    )
    rows = await pool.fetch(
        f"""
        SELECT p.*
        FROM papers p
        {where_sql}
        ORDER BY p.{sort_column} {sort_order} NULLS LAST, p.updated_at DESC, p.paper_id ASC
        LIMIT ${len(params) + 1}
        OFFSET ${len(params) + 2}
        """,
        *params,
        page_size,
        offset,
    )
    return {
        "items": [_row_to_paper_record(row) for row in rows],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


async def get_paper(pool: asyncpg.Pool, paper_id: str) -> dict[str, Any] | None:
    await ensure_paper_tables(pool)
    row = await pool.fetchrow("SELECT * FROM papers WHERE paper_id = $1", _clean_text(paper_id))
    if row is None:
        return None
    return _row_to_paper_record(row)


async def list_import_runs(
    pool: asyncpg.Pool,
    *,
    source_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    await ensure_paper_tables(pool)
    clauses: list[str] = []
    params: list[Any] = []
    if source_id:
        params.append(_clean_text(source_id))
        clauses.append(f"source_id = ${len(params)}")
    if status:
        params.append(_clean_text(status))
        clauses.append(f"status = ${len(params)}")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = await pool.fetchval(
        f"SELECT COUNT(*)::int FROM paper_ingest_runs {where_sql}",
        *params,
    )
    offset = max(page - 1, 0) * page_size
    rows = await pool.fetch(
        f"""
        SELECT *
        FROM paper_ingest_runs
        {where_sql}
        ORDER BY started_at DESC, run_id DESC
        LIMIT ${len(params) + 1}
        OFFSET ${len(params) + 2}
        """,
        *params,
        page_size,
        offset,
    )
    items = [
        PaperIngestRunRecord(
            run_id=_clean_text(row["run_id"]),
            source_id=_clean_text(row["source_id"]),
            status=_clean_text(row["status"]),
            inserted_count=int(row["inserted_count"] or 0),
            updated_count=int(row["updated_count"] or 0),
            skipped_count=int(row["skipped_count"] or 0),
            filtered_chinese_count=int(row["filtered_chinese_count"] or 0),
            error_message=_clean_text(row["error_message"]) or None,
            started_at=_to_iso(row["started_at"]),
            finished_at=_to_iso(row["finished_at"]),
            created_at=_to_iso(row["created_at"]),
            updated_at=_to_iso(row["updated_at"]),
        ).model_dump(mode="json")
        for row in rows
    ]
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


async def list_source_stats(pool: asyncpg.Pool) -> dict[str, dict[str, Any]]:
    await ensure_paper_tables(pool)
    rows = await pool.fetch(
        """
        SELECT
          p.source_id,
          MAX(p.source_name) AS source_name,
          MAX(p.source_type) AS source_type,
          COUNT(*)::int AS paper_count
        FROM papers p
        WHERE COALESCE(p.source_id, '') <> ''
        GROUP BY p.source_id
        """
    )
    stats = {
        _clean_text(row["source_id"]): {
            "paper_count": int(row["paper_count"] or 0),
            "source_name": _clean_text(row["source_name"]) or None,
            "source_type": _clean_text(row["source_type"]) or None,
        }
        for row in rows
    }
    latest_runs = await pool.fetch(
        """
        SELECT DISTINCT ON (source_id)
          source_id, run_id, status, inserted_count, updated_count, skipped_count,
          filtered_chinese_count, error_message, started_at, finished_at
        FROM paper_ingest_runs
        ORDER BY source_id, started_at DESC, run_id DESC
        """
    )
    for row in latest_runs:
        source_id = _clean_text(row["source_id"])
        current = stats.setdefault(source_id, {"paper_count": 0})
        current["latest_run"] = {
            "run_id": _clean_text(row["run_id"]),
            "status": _clean_text(row["status"]),
            "inserted_count": int(row["inserted_count"] or 0),
            "updated_count": int(row["updated_count"] or 0),
            "skipped_count": int(row["skipped_count"] or 0),
            "filtered_chinese_count": int(row["filtered_chinese_count"] or 0),
            "error_message": _clean_text(row["error_message"]) or None,
            "started_at": _to_iso(row["started_at"]),
            "finished_at": _to_iso(row["finished_at"]),
        }
    return stats
