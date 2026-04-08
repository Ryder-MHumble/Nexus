from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import asyncpg

SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(slots=True)
class PostgresBootstrapSettings:
    host: str
    port: int
    user: str
    password: str
    database: str
    admin_database: str = "postgres"


def _quote_ident(name: str) -> str:
    if not SAFE_IDENTIFIER_RE.fullmatch(name):
        raise ValueError(f"Unsafe PostgreSQL identifier: {name!r}")
    return f'"{name}"'


CORE_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS articles (
      url_hash VARCHAR(64) PRIMARY KEY,
      source_id VARCHAR(128) NOT NULL,
      dimension VARCHAR(64) NOT NULL,
      group_name VARCHAR(128),
      url TEXT NOT NULL,
      title TEXT NOT NULL,
      author TEXT,
      published_at TIMESTAMPTZ,
      content TEXT,
      content_html TEXT,
      content_hash VARCHAR(64),
      tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
      extra JSONB NOT NULL DEFAULT '{}'::jsonb,
      custom_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
      is_read BOOLEAN NOT NULL DEFAULT FALSE,
      importance VARCHAR(32),
      crawled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      is_new BOOLEAN NOT NULL DEFAULT TRUE
    )
    """.strip(),
    'CREATE INDEX IF NOT EXISTS idx_articles_dimension ON articles ("dimension")',
    'CREATE INDEX IF NOT EXISTS idx_articles_source_id ON articles ("source_id")',
    'CREATE INDEX IF NOT EXISTS idx_articles_group_name ON articles ("group_name")',
    'CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles ("published_at" DESC)',
    'CREATE INDEX IF NOT EXISTS idx_articles_crawled_at ON articles ("crawled_at" DESC)',
    'CREATE INDEX IF NOT EXISTS idx_articles_tags_gin ON articles USING GIN ("tags")',
    """
    CREATE TABLE IF NOT EXISTS source_states (
      source_id VARCHAR(128) PRIMARY KEY,
      last_crawl_at TIMESTAMPTZ,
      last_success_at TIMESTAMPTZ,
      consecutive_failures SMALLINT NOT NULL DEFAULT 0,
      is_enabled_override BOOLEAN,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """.strip(),
    """
    CREATE TABLE IF NOT EXISTS crawl_logs (
      id BIGSERIAL PRIMARY KEY,
      source_id VARCHAR(128) NOT NULL,
      status VARCHAR(32) NOT NULL,
      items_total INT NOT NULL DEFAULT 0,
      items_new INT NOT NULL DEFAULT 0,
      error_message TEXT,
      started_at TIMESTAMPTZ,
      finished_at TIMESTAMPTZ,
      duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0
    )
    """.strip(),
    (
        'CREATE INDEX IF NOT EXISTS idx_crawl_logs_source_started '
        'ON crawl_logs ("source_id", "started_at" DESC)'
    ),
    'CREATE INDEX IF NOT EXISTS idx_crawl_logs_started_at ON crawl_logs ("started_at" DESC)',
    """
    CREATE TABLE IF NOT EXISTS snapshots (
      source_id VARCHAR(128) PRIMARY KEY,
      data JSONB NOT NULL DEFAULT '{}'::jsonb,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """.strip(),
)


def build_core_schema_statements() -> tuple[str, ...]:
    return CORE_SCHEMA_STATEMENTS


async def ensure_database_exists(settings: PostgresBootstrapSettings) -> bool:
    conn = await asyncpg.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        database=settings.admin_database,
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            settings.database,
        )
        if exists:
            return False
        quoted_db = _quote_ident(settings.database)
        await conn.execute(f"CREATE DATABASE {quoted_db}")
        return True
    finally:
        await conn.close()


async def ensure_core_schema(settings: PostgresBootstrapSettings) -> None:
    conn = await asyncpg.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        database=settings.database,
    )
    try:
        for statement in CORE_SCHEMA_STATEMENTS:
            await conn.execute(statement)
    finally:
        await conn.close()


async def bootstrap_postgres(settings: PostgresBootstrapSettings) -> dict[str, object]:
    database_created = await ensure_database_exists(settings)
    await ensure_core_schema(settings)
    return {
        "database_created": database_created,
        "schema_statements": len(CORE_SCHEMA_STATEMENTS),
        "database": settings.database,
    }


def bootstrap_postgres_sync(settings: PostgresBootstrapSettings) -> dict[str, object]:
    return asyncio.run(bootstrap_postgres(settings))
