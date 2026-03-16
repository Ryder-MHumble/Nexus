"""Global asyncpg connection pool for Supabase."""
from __future__ import annotations

import asyncpg

_pool: asyncpg.Pool | None = None


async def init_pool(
    dsn: str | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
    **kwargs,
) -> None:
    """Initialize the global connection pool. Call once at app startup.

    Two modes:
    - Keyword params (recommended): init_pool(host=..., port=..., user=..., password=..., database=...)
      No URL encoding needed — safe for passwords with special characters.
    - DSN string: init_pool(dsn="postgresql+asyncpg://user:pass@host:port/db")
      Passwords with '@' or ']' must be URL-encoded (%40, %5D).
    """
    global _pool
    if _pool is not None:
        return

    if host:
        # Keyword-param mode: pass directly to asyncpg (no URL parsing)
        connect_kwargs: dict = {
            "host": host,
            "port": port or 6543,
            "user": user or "postgres",
            "password": password or "",
            "database": database or "postgres",
            "min_size": 2,
            "max_size": 10,
            **kwargs,
        }
    else:
        if not dsn:
            raise ValueError("Either dsn or host must be provided")
        # DSN mode: strip ORM prefix, parse manually (handles @ in passwords)
        from urllib.parse import unquote  # noqa: PLC0415

        clean_dsn = dsn.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgresql+psycopg2://", "postgresql://"
        )
        scheme_end = clean_dsn.index("://") + 3
        rest = clean_dsn[scheme_end:]

        last_at = rest.rfind("@")
        credentials = rest[:last_at]
        host_part = rest[last_at + 1:]

        first_colon = credentials.index(":")
        _user = unquote(credentials[:first_colon])
        _password = unquote(credentials[first_colon + 1:])

        host_db, _, _database = host_part.partition("/")
        _host, _, port_str = host_db.partition(":")
        _port = int(port_str) if port_str else 5432

        connect_kwargs = {
            "host": _host,
            "port": _port,
            "user": _user,
            "password": _password,
            "database": _database or "postgres",
            "min_size": 2,
            "max_size": 10,
            **kwargs,
        }

    _pool = await asyncpg.create_pool(**connect_kwargs)


async def close_pool() -> None:
    """Close the connection pool. Call at app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Get the active pool. Raises RuntimeError if not initialized."""
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_pool() first.")
    return _pool


async def execute(query: str, *args) -> str:
    """Execute a query (INSERT/UPDATE/DELETE) and return status."""
    return await get_pool().execute(query, *args)


async def fetch(query: str, *args) -> list[asyncpg.Record]:
    """Fetch multiple rows."""
    return await get_pool().fetch(query, *args)


async def fetchrow(query: str, *args) -> asyncpg.Record | None:
    """Fetch a single row."""
    return await get_pool().fetchrow(query, *args)


async def fetchval(query: str, *args):
    """Fetch a single value."""
    return await get_pool().fetchval(query, *args)
