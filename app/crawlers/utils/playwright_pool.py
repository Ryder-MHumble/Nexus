from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from playwright.async_api import Browser, Page, Playwright, async_playwright

from app.config import settings

logger = logging.getLogger(__name__)

_pw: Playwright | None = None
_browser: Browser | None = None
_lock = asyncio.Lock()
_context_semaphore = asyncio.Semaphore(settings.PLAYWRIGHT_MAX_CONTEXTS)


async def _get_browser() -> Browser:
    """Get or create a singleton browser instance."""
    global _browser, _pw
    if _browser is None or not _browser.is_connected():
        async with _lock:
            if _browser is None or not _browser.is_connected():
                _pw = await async_playwright().start()
                _browser = await _pw.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process',
                    ]
                )
                logger.info("Playwright browser launched")
    return _browser


@asynccontextmanager
async def get_page(*, apply_webdriver_patch: bool = True) -> AsyncGenerator[Page, None]:
    """Acquire a browser page from the pool, yield it, then close.

    Limits concurrent contexts to PLAYWRIGHT_MAX_CONTEXTS to avoid resource exhaustion.
    """
    async with _context_semaphore:
        browser = await _get_browser()
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        if apply_webdriver_patch:
            # Some sites detect automation through navigator.webdriver.
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
        page = await context.new_page()
        try:
            yield page
        finally:
            await page.close()
            await context.close()


async def close_browser() -> None:
    """Shut down the browser and Playwright subprocess (called during app shutdown)."""
    global _browser, _pw
    if _browser and _browser.is_connected():
        await _browser.close()
        _browser = None
        logger.info("Playwright browser closed")
    if _pw:
        await _pw.stop()
        _pw = None
        logger.info("Playwright subprocess stopped")
