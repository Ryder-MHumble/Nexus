from __future__ import annotations

import asyncio
import logging
import random
import ssl
from collections import defaultdict
from collections.abc import Callable
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# User-Agent rotation pool
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
]

# Per-domain semaphores to enforce rate limiting
_domain_semaphores: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(1))
_domain_last_request: dict[str, float] = {}


def _get_random_ua() -> str:
    return random.choice(_USER_AGENTS)


async def _wait_for_domain(domain: str, delay: float) -> None:
    """Enforce minimum delay between requests to the same domain."""
    loop = asyncio.get_event_loop()
    now = loop.time()
    last = _domain_last_request.get(domain, 0.0)
    wait = max(0.0, delay - (now - last))
    if wait > 0:
        await asyncio.sleep(wait)
    _domain_last_request[domain] = loop.time()


async def _request_with_retry(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    request_delay: float | None = None,
    verify: bool = True,
    extract: Callable[[httpx.Response], object],
) -> object:
    """Core retry logic shared by fetch_page and fetch_json."""
    domain = urlparse(url).netloc
    delay = request_delay or settings.DEFAULT_REQUEST_DELAY

    # Build complete browser-like headers
    merged_headers = {
        "User-Agent": _get_random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    if headers:
        merged_headers.update(headers)

    async with _domain_semaphores[domain]:
        await _wait_for_domain(domain, delay)

        last_exc: Exception | None = None
        # When verify=False, use a legacy SSL context that allows old cipher suites
        # (needed for servers with SSLv3 alert handshake failures)
        if not verify:
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            ssl_ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
            ssl_param: bool | ssl.SSLContext = ssl_ctx
        else:
            ssl_param = True
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, verify=ssl_param
        ) as client:
            for attempt in range(max_retries):
                try:
                    response = await client.get(
                        url, headers=merged_headers, params=params,
                    )
                    response.raise_for_status()
                    return extract(response)
                except (httpx.HTTPStatusError, httpx.RequestError) as e:
                    last_exc = e
                    wait_time = 2**attempt + random.uniform(0, 1)
                    logger.warning(
                        "Request failed (attempt %d/%d) for %s: %s. Retrying in %.1fs",
                        attempt + 1, max_retries, url, e, wait_time,
                    )
                    await asyncio.sleep(wait_time)

        raise last_exc  # type: ignore[misc]


async def fetch_page(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    encoding: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    request_delay: float | None = None,
    verify: bool = True,
) -> str:
    """Fetch a URL with retry, rate limiting, and UA rotation. Returns response text."""

    def _extract(response: httpx.Response) -> str:
        if encoding:
            response.encoding = encoding
        return response.text

    return await _request_with_retry(  # type: ignore[return-value]
        url,
        headers=headers,
        timeout=timeout,
        max_retries=max_retries,
        request_delay=request_delay,
        verify=verify,
        extract=_extract,
    )


async def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float = 30.0,
    max_retries: int = 3,
    request_delay: float | None = None,
) -> dict:
    """Fetch a JSON API endpoint with retry and rate limiting."""
    return await _request_with_retry(  # type: ignore[return-value]
        url,
        headers=headers,
        params=params,
        timeout=timeout,
        max_retries=max_retries,
        request_delay=request_delay,
        extract=lambda r: r.json(),
    )
