from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import asyncpg


_SCHEMA_READY = False
_SCHEMA_LOCK = asyncio.Lock()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_owner_type(value: Any) -> str:
    owner_type = _clean_text(value).lower()
    if owner_type not in {"student", "scholar"}:
        raise ValueError(f"Unsupported owner_type: {value}")
    return owner_type


def _normalize_source_type(value: Any, *, default: str = "manual_upload") -> str:
    source_type = _clean_text(value).lower() or default
    mapping = {
        "manual": "manual_upload",
        "manual_upload": "manual_upload",
        "bulk": "bulk_import",
        "bulk_import": "bulk_import",
        "monitor": "monitor_api",
        "monitor_api": "monitor_api",
        "legacy": "legacy_migrated",
        "legacy_migrated": "legacy_migrated",
    }
    resolved = mapping.get(source_type, source_type)
    if resolved not in {"manual_upload", "bulk_import", "monitor_api", "legacy_migrated"}:
        raise ValueError(f"Unsupported source_type: {value}")
    return resolved


def _normalize_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        token = _clean_text(value)
        if not token:
            return []
        try:
            parsed = json.loads(token)
        except json.JSONDecodeError:
            return [token]
        value = parsed
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    return []


def _normalize_json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        token = _clean_text(value)
        if not token:
            return {}
        try:
            parsed = json.loads(token)
        except json.JSONDecodeError:
            return {}
        value = parsed
    if isinstance(value, dict):
        return value
    return {}


def _to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = _clean_text(value)
    return text or None


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = _to_iso(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _build_canonical_uid(
    *,
    doi: Any = None,
    arxiv_id: Any = None,
    title: Any = None,
    publication_date: Any = None,
) -> str:
    doi_token = _clean_text(doi).lower()
    if doi_token:
        return f"doi:{doi_token}"
    arxiv_token = _clean_text(arxiv_id).lower()
    if arxiv_token:
        return f"arxiv:{arxiv_token}"
    title_token = " ".join(_clean_text(title).lower().split())
    date_token = (_to_iso(publication_date) or "").split("T", 1)[0]
    digest = hashlib.sha1(f"{title_token}|{date_token}".encode("utf-8")).hexdigest()[:24]
    return f"fingerprint:{digest}"


def _merge_compliance_details(
    base: dict[str, Any] | None,
    *,
    affiliation_status: str | None = None,
    compliance_reason: str | None = None,
    matched_tokens: list[str] | None = None,
    checked_affiliations: list[str] | None = None,
    assessed_at: str | None = None,
) -> dict[str, Any]:
    payload = dict(base or {})
    if affiliation_status is not None:
        payload["affiliation_status"] = affiliation_status
    if compliance_reason is not None:
        payload["compliance_reason"] = compliance_reason
    if matched_tokens is not None:
        payload["matched_tokens"] = matched_tokens
    if checked_affiliations is not None:
        payload["checked_affiliations"] = checked_affiliations
    if assessed_at is not None:
        payload["assessed_at"] = assessed_at
    return payload


async def ensure_publication_tables(pool: asyncpg.Pool) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    async with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS publications (
                    publication_id TEXT PRIMARY KEY,
                    canonical_uid TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    doi TEXT,
                    arxiv_id TEXT,
                    abstract TEXT,
                    publication_date TIMESTAMPTZ,
                    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
                    affiliations JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_publications_publication_date ON publications(publication_date DESC)"
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS publication_owners (
                    owner_link_id TEXT PRIMARY KEY,
                    publication_id TEXT NOT NULL REFERENCES publications(publication_id) ON DELETE CASCADE,
                    owner_type TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    project_group_name TEXT,
                    source_type TEXT NOT NULL DEFAULT 'manual_upload',
                    source_details JSONB NOT NULL DEFAULT '{}'::jsonb,
                    compliance_details JSONB NOT NULL DEFAULT '{}'::jsonb,
                    confirmed_by TEXT,
                    confirmed_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (publication_id, owner_type, owner_id)
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_publication_owners_owner ON publication_owners(owner_type, owner_id)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_publication_owners_publication_id ON publication_owners(publication_id)"
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS publication_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    owner_type TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    target_key TEXT,
                    canonical_uid TEXT NOT NULL,
                    paper_uid TEXT,
                    title TEXT NOT NULL,
                    doi TEXT,
                    arxiv_id TEXT,
                    abstract TEXT,
                    publication_date TIMESTAMPTZ,
                    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
                    affiliations JSONB NOT NULL DEFAULT '[]'::jsonb,
                    source TEXT,
                    source_type TEXT NOT NULL DEFAULT 'monitor_api',
                    source_details JSONB NOT NULL DEFAULT '{}'::jsonb,
                    project_group_name TEXT,
                    compliance_details JSONB NOT NULL DEFAULT '{}'::jsonb,
                    review_status TEXT NOT NULL DEFAULT 'pending_review',
                    review_decision JSONB NOT NULL DEFAULT '{}'::jsonb,
                    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    promoted_publication_id TEXT,
                    promoted_owner_link_id TEXT,
                    affiliation_status TEXT,
                    compliance_reason TEXT,
                    matched_tokens JSONB NOT NULL DEFAULT '[]'::jsonb,
                    checked_affiliations JSONB NOT NULL DEFAULT '[]'::jsonb,
                    assessed_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (owner_type, owner_id, canonical_uid)
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_publication_candidates_owner_status ON publication_candidates(owner_type, owner_id, review_status)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_publication_candidates_target_uid ON publication_candidates(target_key, canonical_uid)"
            )
        _SCHEMA_READY = True


async def _upsert_publication(
    conn: asyncpg.Connection,
    *,
    title: str,
    doi: str | None,
    arxiv_id: str | None,
    abstract: str | None,
    publication_date: str | None,
    authors: list[str],
    affiliations: list[str],
) -> tuple[str, str]:
    canonical_uid = _build_canonical_uid(
        doi=doi,
        arxiv_id=arxiv_id,
        title=title,
        publication_date=publication_date,
    )
    publication_id = f"pub_{uuid4().hex}"
    row = await conn.fetchrow(
        """
        INSERT INTO publications (
            publication_id,
            canonical_uid,
            title,
            doi,
            arxiv_id,
            abstract,
            publication_date,
            authors,
            affiliations
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb
        )
        ON CONFLICT (canonical_uid) DO UPDATE
        SET
            title = CASE
                WHEN publications.title = '' AND EXCLUDED.title <> '' THEN EXCLUDED.title
                ELSE publications.title
            END,
            doi = COALESCE(publications.doi, EXCLUDED.doi),
            arxiv_id = COALESCE(publications.arxiv_id, EXCLUDED.arxiv_id),
            abstract = COALESCE(publications.abstract, EXCLUDED.abstract),
            publication_date = COALESCE(publications.publication_date, EXCLUDED.publication_date),
            authors = CASE
                WHEN publications.authors = '[]'::jsonb AND EXCLUDED.authors <> '[]'::jsonb THEN EXCLUDED.authors
                ELSE publications.authors
            END,
            affiliations = CASE
                WHEN publications.affiliations = '[]'::jsonb AND EXCLUDED.affiliations <> '[]'::jsonb THEN EXCLUDED.affiliations
                ELSE publications.affiliations
            END,
            updated_at = now()
        RETURNING publication_id, canonical_uid
        """,
        publication_id,
        canonical_uid,
        title,
        doi,
        arxiv_id,
        abstract,
        _to_datetime(publication_date),
        json.dumps(authors),
        json.dumps(affiliations),
    )
    assert row is not None
    return str(row["publication_id"]), str(row["canonical_uid"])


async def _upsert_owner_link(
    conn: asyncpg.Connection,
    *,
    publication_id: str,
    owner_type: str,
    owner_id: str,
    project_group_name: str | None,
    source_type: str,
    source_details: dict[str, Any],
    compliance_details: dict[str, Any],
    confirmed_by: str | None,
) -> str:
    owner_link_id = f"owner_{uuid4().hex}"
    row = await conn.fetchrow(
        """
        INSERT INTO publication_owners (
            owner_link_id,
            publication_id,
            owner_type,
            owner_id,
            project_group_name,
            source_type,
            source_details,
            compliance_details,
            confirmed_by,
            confirmed_at
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, now()
        )
        ON CONFLICT (publication_id, owner_type, owner_id) DO UPDATE
        SET
            project_group_name = COALESCE(EXCLUDED.project_group_name, publication_owners.project_group_name),
            source_type = EXCLUDED.source_type,
            source_details = publication_owners.source_details || EXCLUDED.source_details,
            compliance_details = publication_owners.compliance_details || EXCLUDED.compliance_details,
            confirmed_by = COALESCE(EXCLUDED.confirmed_by, publication_owners.confirmed_by),
            confirmed_at = COALESCE(publication_owners.confirmed_at, now()),
            updated_at = now()
        RETURNING owner_link_id
        """,
        owner_link_id,
        publication_id,
        owner_type,
        owner_id,
        project_group_name,
        source_type,
        json.dumps(source_details),
        json.dumps(compliance_details),
        confirmed_by,
    )
    assert row is not None
    return str(row["owner_link_id"])


def _row_to_publication_item(row: asyncpg.Record | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    compliance_details = _normalize_json_dict(payload.get("compliance_details"))
    return {
        "paper_uid": _clean_text(payload.get("owner_link_id")),
        "owner_link_id": _clean_text(payload.get("owner_link_id")),
        "publication_id": _clean_text(payload.get("publication_id")),
        "owner_type": _clean_text(payload.get("owner_type")),
        "owner_id": _clean_text(payload.get("owner_id")),
        "canonical_uid": _clean_text(payload.get("canonical_uid")),
        "title": _clean_text(payload.get("title")),
        "doi": _clean_text(payload.get("doi")) or None,
        "arxiv_id": _clean_text(payload.get("arxiv_id")) or None,
        "abstract": _clean_text(payload.get("abstract")) or None,
        "publication_date": _to_iso(payload.get("publication_date")),
        "authors": _normalize_json_list(payload.get("authors")),
        "affiliations": _normalize_json_list(payload.get("affiliations")),
        "project_group_name": _clean_text(payload.get("project_group_name")) or None,
        "source": _clean_text(payload.get("source_type")) or None,
        "source_details": _normalize_json_dict(payload.get("source_details")),
        "compliance_details": compliance_details,
        "affiliation_status": _clean_text(compliance_details.get("affiliation_status")) or None,
        "compliance_reason": _clean_text(compliance_details.get("compliance_reason")) or None,
        "matched_tokens": _normalize_json_list(compliance_details.get("matched_tokens")),
        "checked_affiliations": _normalize_json_list(compliance_details.get("checked_affiliations")),
        "assessed_at": _to_iso(compliance_details.get("assessed_at")),
        "confirmed_by": _clean_text(payload.get("confirmed_by")) or None,
        "confirmed_at": _to_iso(payload.get("confirmed_at")),
        "created_at": _to_iso(payload.get("created_at")),
        "updated_at": _to_iso(payload.get("updated_at")),
    }


def _row_to_candidate_item(row: asyncpg.Record | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    return {
        "candidate_id": _clean_text(payload.get("candidate_id")),
        "owner_type": _clean_text(payload.get("owner_type")),
        "owner_id": _clean_text(payload.get("owner_id")),
        "target_key": _clean_text(payload.get("target_key")) or None,
        "canonical_uid": _clean_text(payload.get("canonical_uid")),
        "title": _clean_text(payload.get("title")),
        "doi": _clean_text(payload.get("doi")) or None,
        "arxiv_id": _clean_text(payload.get("arxiv_id")) or None,
        "abstract": _clean_text(payload.get("abstract")) or None,
        "publication_date": _to_iso(payload.get("publication_date")),
        "authors": _normalize_json_list(payload.get("authors")),
        "affiliations": _normalize_json_list(payload.get("affiliations")),
        "source_type": _clean_text(payload.get("source_type")) or "monitor_api",
        "source_details": _normalize_json_dict(payload.get("source_details")),
        "project_group_name": _clean_text(payload.get("project_group_name")) or None,
        "compliance_details": _normalize_json_dict(payload.get("compliance_details")),
        "review_status": _clean_text(payload.get("review_status")),
        "review_decision": _normalize_json_dict(payload.get("review_decision")),
        "promoted_publication_id": _clean_text(payload.get("promoted_publication_id")) or None,
        "promoted_owner_link_id": _clean_text(payload.get("promoted_owner_link_id")) or None,
        "created_at": _to_iso(payload.get("created_at")),
        "updated_at": _to_iso(payload.get("updated_at")),
    }


async def create_formal_publication(
    pool: asyncpg.Pool,
    *,
    owner_type: str,
    owner_id: str,
    title: str,
    doi: str | None = None,
    arxiv_id: str | None = None,
    abstract: str | None = None,
    publication_date: str | None = None,
    authors: list[str] | None = None,
    affiliations: list[str] | None = None,
    project_group_name: str | None = None,
    source_type: str = "manual_upload",
    source_details: dict[str, Any] | None = None,
    compliance_details: dict[str, Any] | None = None,
    confirmed_by: str | None = None,
) -> dict[str, str]:
    await ensure_publication_tables(pool)
    normalized_owner_type = _normalize_owner_type(owner_type)
    normalized_source_type = _normalize_source_type(source_type)
    async with pool.acquire() as conn:
        async with conn.transaction():
            publication_id, _ = await _upsert_publication(
                conn,
                title=_clean_text(title),
                doi=_clean_text(doi) or None,
                arxiv_id=_clean_text(arxiv_id) or None,
                abstract=_clean_text(abstract) or None,
                publication_date=_to_iso(publication_date),
                authors=_normalize_json_list(authors),
                affiliations=_normalize_json_list(affiliations),
            )
            owner_link_id = await _upsert_owner_link(
                conn,
                publication_id=publication_id,
                owner_type=normalized_owner_type,
                owner_id=_clean_text(owner_id),
                project_group_name=_clean_text(project_group_name) or None,
                source_type=normalized_source_type,
                source_details=_normalize_json_dict(source_details),
                compliance_details=_normalize_json_dict(compliance_details),
                confirmed_by=_clean_text(confirmed_by) or None,
            )
    return {
        "status": "created",
        "publication_id": publication_id,
        "owner_link_id": owner_link_id,
    }


async def list_publications(
    pool: asyncpg.Pool,
    *,
    owner_type: str,
    owner_id: str,
) -> list[dict[str, Any]]:
    await ensure_publication_tables(pool)
    rows = await pool.fetch(
        """
        SELECT
            o.owner_link_id,
            o.publication_id,
            o.owner_type,
            o.owner_id,
            o.project_group_name,
            o.source_type,
            o.source_details,
            o.compliance_details,
            o.confirmed_by,
            o.confirmed_at,
            o.created_at,
            o.updated_at,
            p.canonical_uid,
            p.title,
            p.doi,
            p.arxiv_id,
            p.abstract,
            p.publication_date,
            p.authors,
            p.affiliations
        FROM publication_owners o
        JOIN publications p ON p.publication_id = o.publication_id
        WHERE o.owner_type = $1 AND o.owner_id = $2
        ORDER BY p.publication_date DESC NULLS LAST, o.created_at DESC, o.owner_link_id ASC
        """,
        _normalize_owner_type(owner_type),
        _clean_text(owner_id),
    )
    return [_row_to_publication_item(row) for row in rows]


async def update_owner_publication(
    pool: asyncpg.Pool,
    *,
    owner_link_id: str,
    title: str | None = None,
    doi: str | None = None,
    arxiv_id: str | None = None,
    abstract: str | None = None,
    publication_date: str | None = None,
    authors: list[str] | None = None,
    affiliations: list[str] | None = None,
    project_group_name: str | None = None,
    source_type: str | None = None,
    source_details: dict[str, Any] | None = None,
    compliance_details: dict[str, Any] | None = None,
    confirmed_by: str | None = None,
) -> dict[str, str] | None:
    await ensure_publication_tables(pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                """
                SELECT
                    o.owner_link_id,
                    o.publication_id,
                    o.project_group_name,
                    o.source_type,
                    o.source_details,
                    o.compliance_details,
                    p.title,
                    p.doi,
                    p.arxiv_id,
                    p.abstract,
                    p.publication_date,
                    p.authors,
                    p.affiliations
                FROM publication_owners o
                JOIN publications p ON p.publication_id = o.publication_id
                WHERE o.owner_link_id = $1
                """,
                _clean_text(owner_link_id),
            )
            if existing is None:
                return None

            next_title = _clean_text(title) or _clean_text(existing["title"])
            next_doi = _clean_text(doi) or (_clean_text(existing["doi"]) or None)
            next_arxiv_id = _clean_text(arxiv_id) or (_clean_text(existing["arxiv_id"]) or None)
            next_abstract = _clean_text(abstract) or (_clean_text(existing["abstract"]) or None)
            next_publication_date = _to_iso(publication_date) or _to_iso(existing["publication_date"])
            next_authors = _normalize_json_list(authors) if authors is not None else _normalize_json_list(existing["authors"])
            next_affiliations = _normalize_json_list(affiliations) if affiliations is not None else _normalize_json_list(existing["affiliations"])
            next_canonical_uid = _build_canonical_uid(
                doi=next_doi,
                arxiv_id=next_arxiv_id,
                title=next_title,
                publication_date=next_publication_date,
            )

            await conn.execute(
                """
                UPDATE publications
                SET
                    canonical_uid = $2,
                    title = $3,
                    doi = $4,
                    arxiv_id = $5,
                    abstract = $6,
                    publication_date = $7,
                    authors = $8::jsonb,
                    affiliations = $9::jsonb,
                    updated_at = now()
                WHERE publication_id = $1
                """,
                str(existing["publication_id"]),
                next_canonical_uid,
                next_title,
                next_doi,
                next_arxiv_id,
                next_abstract,
                _to_datetime(next_publication_date),
                json.dumps(next_authors),
                json.dumps(next_affiliations),
            )

            merged_source_details = _normalize_json_dict(existing["source_details"])
            if source_details is not None:
                merged_source_details.update(_normalize_json_dict(source_details))
            merged_compliance_details = _normalize_json_dict(existing["compliance_details"])
            if compliance_details is not None:
                merged_compliance_details.update(_normalize_json_dict(compliance_details))

            await conn.execute(
                """
                UPDATE publication_owners
                SET
                    project_group_name = COALESCE($2, project_group_name),
                    source_type = COALESCE($3, source_type),
                    source_details = $4::jsonb,
                    compliance_details = $5::jsonb,
                    confirmed_by = COALESCE($6, confirmed_by),
                    confirmed_at = CASE WHEN $6 IS NOT NULL THEN now() ELSE confirmed_at END,
                    updated_at = now()
                WHERE owner_link_id = $1
                """,
                _clean_text(owner_link_id),
                _clean_text(project_group_name) or None,
                _normalize_source_type(source_type, default=_clean_text(existing["source_type"]) or "manual_upload")
                if source_type is not None
                else None,
                json.dumps(merged_source_details),
                json.dumps(merged_compliance_details),
                _clean_text(confirmed_by) or None,
            )
    return {
        "status": "updated",
        "publication_id": str(existing["publication_id"]),
        "owner_link_id": _clean_text(owner_link_id),
    }


async def delete_owner_publication(pool: asyncpg.Pool, *, owner_link_id: str) -> bool:
    await ensure_publication_tables(pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            publication_id = await conn.fetchval(
                "SELECT publication_id FROM publication_owners WHERE owner_link_id = $1",
                _clean_text(owner_link_id),
            )
            if publication_id is None:
                return False
            result = await conn.execute(
                "DELETE FROM publication_owners WHERE owner_link_id = $1",
                _clean_text(owner_link_id),
            )
            remaining = await conn.fetchval(
                "SELECT COUNT(*)::int FROM publication_owners WHERE publication_id = $1",
                str(publication_id),
            )
            if int(remaining or 0) == 0:
                await conn.execute(
                    "DELETE FROM publications WHERE publication_id = $1",
                    str(publication_id),
                )
    return not result.endswith("0")


async def list_candidates(
    pool: asyncpg.Pool,
    *,
    owner_type: str,
    owner_id: str,
    review_status: str | None = None,
) -> list[dict[str, Any]]:
    await ensure_publication_tables(pool)
    args: list[Any] = [_normalize_owner_type(owner_type), _clean_text(owner_id)]
    where = ["owner_type = $1", "owner_id = $2"]
    if _clean_text(review_status):
        args.append(_clean_text(review_status))
        where.append(f"review_status = ${len(args)}")
    rows = await pool.fetch(
        f"""
        SELECT *
        FROM publication_candidates
        WHERE {' AND '.join(where)}
        ORDER BY last_seen_at DESC, created_at DESC, candidate_id ASC
        """,
        *args,
    )
    return [_row_to_candidate_item(row) for row in rows]


async def confirm_candidate(
    pool: asyncpg.Pool,
    *,
    candidate_id: str,
    confirmed_by: str | None = None,
) -> dict[str, str] | None:
    await ensure_publication_tables(pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            candidate = await conn.fetchrow(
                "SELECT * FROM publication_candidates WHERE candidate_id = $1",
                _clean_text(candidate_id),
            )
            if candidate is None:
                return None
            compliance_details = _normalize_json_dict(candidate["compliance_details"])
            compliance_details = _merge_compliance_details(
                compliance_details,
                affiliation_status=_clean_text(candidate["affiliation_status"]) or None,
                compliance_reason=_clean_text(candidate["compliance_reason"]) or None,
                matched_tokens=_normalize_json_list(candidate["matched_tokens"]),
                checked_affiliations=_normalize_json_list(candidate["checked_affiliations"]),
                assessed_at=_to_iso(candidate["assessed_at"]),
            )
            publication_id, _ = await _upsert_publication(
                conn,
                title=_clean_text(candidate["title"]),
                doi=_clean_text(candidate["doi"]) or None,
                arxiv_id=_clean_text(candidate["arxiv_id"]) or None,
                abstract=_clean_text(candidate["abstract"]) or None,
                publication_date=_to_iso(candidate["publication_date"]),
                authors=_normalize_json_list(candidate["authors"]),
                affiliations=_normalize_json_list(candidate["affiliations"]),
            )
            source_details = _normalize_json_dict(candidate["source_details"])
            source_details.setdefault("candidate_id", _clean_text(candidate_id))
            owner_link_id = await _upsert_owner_link(
                conn,
                publication_id=publication_id,
                owner_type=_clean_text(candidate["owner_type"]),
                owner_id=_clean_text(candidate["owner_id"]),
                project_group_name=_clean_text(candidate["project_group_name"]) or None,
                source_type=_normalize_source_type(candidate["source_type"], default="monitor_api"),
                source_details=source_details,
                compliance_details=compliance_details,
                confirmed_by=_clean_text(confirmed_by) or None,
            )
            review_decision = _normalize_json_dict(candidate["review_decision"])
            review_decision.update(
                {
                    "decision": "confirmed",
                    "confirmed_by": _clean_text(confirmed_by) or None,
                    "confirmed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            await conn.execute(
                """
                UPDATE publication_candidates
                SET
                    review_status = 'confirmed',
                    review_decision = $2::jsonb,
                    promoted_publication_id = $3,
                    promoted_owner_link_id = $4,
                    updated_at = now()
                WHERE candidate_id = $1
                """,
                _clean_text(candidate_id),
                json.dumps(review_decision),
                publication_id,
                owner_link_id,
            )
    return {
        "status": "confirmed",
        "candidate_id": _clean_text(candidate_id),
        "publication_id": publication_id,
        "owner_link_id": owner_link_id,
    }


async def reject_candidate(
    pool: asyncpg.Pool,
    *,
    candidate_id: str,
    rejected_by: str | None = None,
    note: str | None = None,
) -> bool:
    await ensure_publication_tables(pool)
    current = await pool.fetchrow(
        "SELECT review_decision FROM publication_candidates WHERE candidate_id = $1",
        _clean_text(candidate_id),
    )
    if current is None:
        return False
    review_decision = _normalize_json_dict(current["review_decision"])
    review_decision.update(
        {
            "decision": "rejected",
            "rejected_by": _clean_text(rejected_by) or None,
            "note": _clean_text(note) or None,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    result = await pool.execute(
        """
        UPDATE publication_candidates
        SET
            review_status = 'rejected',
            review_decision = $2::jsonb,
            updated_at = now()
        WHERE candidate_id = $1
        """,
        _clean_text(candidate_id),
        json.dumps(review_decision),
    )
    return not result.endswith("0")
