"""Global Supabase async client for the main database."""
from __future__ import annotations

from supabase import AsyncClient, create_async_client

_client: AsyncClient | None = None


async def init_client(url: str, key: str) -> None:
    """Initialize the global Supabase client. Call once at app startup."""
    global _client
    if _client is not None:
        return
    _client = await create_async_client(url, key)


async def close_client() -> None:
    """Close the client. Call at app shutdown."""
    global _client
    _client = None


def get_client() -> AsyncClient:
    """Return the active client. Raises RuntimeError if not initialized."""
    if _client is None:
        raise RuntimeError("Supabase client not initialized. Call init_client() first.")
    return _client
