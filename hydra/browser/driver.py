"""Playwright browser driver — connects to AdsPower CDP endpoint.

One BrowserSession per account. Handles:
- Connect to AdsPower-launched Chrome via CDP
- Page lifecycle (new tab, navigate, close)
- Auto-cleanup on exit
"""

import asyncio
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from hydra.browser.adspower import adspower
from hydra.core.logger import get_logger

log = get_logger("browser")


class BrowserSession:
    """Wraps a single AdsPower profile's browser session."""

    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._playwright = None

    async def start(self) -> "BrowserSession":
        """Start AdsPower browser and connect Playwright via CDP."""
        # Launch via AdsPower
        info = adspower.start_browser(self.profile_id)
        ws_endpoint = info["ws_endpoint"]

        if not ws_endpoint:
            raise RuntimeError(f"No WebSocket endpoint for profile {self.profile_id}")

        # Connect Playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(ws_endpoint)
        self._context = self._browser.contexts[0]

        # Use existing page or create new
        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

        log.info(f"Connected to profile {self.profile_id}")
        return self

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser session not started")
        return self._page

    async def new_tab(self, url: str | None = None) -> Page:
        """Open a new tab, optionally navigating to url."""
        page = await self._context.new_page()
        if url:
            await page.goto(url, wait_until="domcontentloaded")
        return page

    async def goto(self, url: str, timeout: int = 30000):
        """Navigate current page."""
        await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)

    async def close(self):
        """Disconnect Playwright and stop AdsPower browser."""
        try:
            if self._browser:
                await self._browser.close()
        except Exception as e:
            log.warning(f"Browser close error: {e}")

        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass

        try:
            adspower.stop_browser(self.profile_id)
        except Exception as e:
            log.warning(f"AdsPower stop error: {e}")

        log.info(f"Closed session for profile {self.profile_id}")

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *exc):
        await self.close()


@asynccontextmanager
async def open_browser(profile_id: str):
    """Context manager for a browser session.

    Usage:
        async with open_browser("profile_abc") as session:
            await session.goto("https://youtube.com")
            page = session.page
    """
    session = BrowserSession(profile_id)
    try:
        await session.start()
        yield session
    finally:
        await session.close()
