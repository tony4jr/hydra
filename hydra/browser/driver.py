"""Playwright browser driver — connects to AdsPower CDP endpoint.

One BrowserSession per account. Handles:
- Connect to AdsPower-launched Chrome via CDP
- Page lifecycle (new tab, navigate, close)
- Auto-cleanup on exit
"""

import asyncio
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from hydra.core.config import settings
from hydra.core.logger import get_logger


def _get_browser_client():
    """Return the configured browser backend client (adspower or gologin)."""
    backend = settings.browser_backend.lower()
    if backend == "gologin":
        from hydra.browser.gologin import gologin
        return gologin
    from hydra.browser.adspower import adspower
    return adspower


# Backward-compat alias used throughout codebase
adspower = _get_browser_client()

log = get_logger("browser")

PLAYWRIGHT_CLOSE_TIMEOUT_SEC = 8.0
ADSPOWER_STOP_TIMEOUT_SEC = 15.0


class BrowserSession:
    """Wraps a single AdsPower profile's browser session."""

    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._playwright = None
        self._adspower_started = False
        self._adspower_debug_port: str | int | None = None
        self._adspower_process_ids: set[int] = set()

    async def start(self) -> "BrowserSession":
        """Start AdsPower browser and connect Playwright via CDP."""
        try:
            # Launch via AdsPower
            info = adspower.start_browser(self.profile_id)
            self._adspower_started = True
            self._adspower_debug_port = info.get("debug_port")
            self._adspower_process_ids = {
                int(pid) for pid in info.get("process_ids", []) if pid
            }
            ws_endpoint = info["ws_endpoint"]

            if not ws_endpoint:
                raise RuntimeError(f"No WebSocket endpoint for profile {self.profile_id}")

            # Connect Playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(ws_endpoint)
            self._context = self._browser.contexts[0]

            # AdsPower 프로필이 여러 복원 탭(start.adspower.net + 과거 myaccount 탭 등)을
            # 띄울 수 있음. 여분 탭 전부 닫고 하나만 유지.
            pages = list(self._context.pages)
            if pages:
                self._page = pages[0]
                for extra in pages[1:]:
                    try:
                        await extra.close()
                    except Exception as e:
                        log.warning(f"failed to close extra tab: {e}")
                if len(pages) > 1:
                    log.info(f"closed {len(pages)-1} extra startup tab(s)")
            else:
                self._page = await self._context.new_page()

            # Phase 1.5.5 — opt-in CloakBrowser human/ patch_page wiring.
            # When HYDRA_HUMAN_PATCH=true on worker, all existing + future pages
            # in this context get bezier mouse, NEARBY_KEYS typing, wheel-burst
            # scroll, and CDP isolated DOM reads. Failure is non-fatal.
            self._apply_human_patch_if_enabled()

            log.info(f"Connected to profile {self.profile_id}")
            return self
        except Exception:
            await self.close(force_process_cleanup=True)
            raise

    def _apply_human_patch_if_enabled(self) -> None:
        """Apply hydra.browser.human.patch_context_async if env opt-in.

        Lazy import + try/except so a patch failure never blocks task execution
        (caller can disable via HYDRA_HUMAN_PATCH=false to immediately roll back).
        """
        import os
        if os.getenv("HYDRA_HUMAN_PATCH", "").strip().lower() not in ("1", "true", "yes"):
            return
        try:
            from hydra.browser.human import patch_context_async, resolve_config
            preset = os.getenv("HYDRA_HUMAN_PRESET", "careful").strip().lower()
            cfg = resolve_config(preset)
            patch_context_async(self._context, cfg)
            log.info(f"human patch applied (preset={preset})")
        except Exception as e:
            log.warning(f"human patch skipped — {type(e).__name__}: {e}")

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

    async def close(self, *, force_process_cleanup: bool = False):
        """Disconnect Playwright and stop AdsPower browser."""
        try:
            if self._browser:
                await asyncio.wait_for(
                    self._browser.close(),
                    timeout=PLAYWRIGHT_CLOSE_TIMEOUT_SEC,
                )
        except asyncio.TimeoutError:
            log.warning(f"Browser close timeout for profile {self.profile_id}")
        except Exception as e:
            log.warning(f"Browser close error: {e}")

        try:
            if self._playwright:
                await asyncio.wait_for(
                    self._playwright.stop(),
                    timeout=PLAYWRIGHT_CLOSE_TIMEOUT_SEC,
                )
        except asyncio.TimeoutError:
            log.warning(f"Playwright stop timeout for profile {self.profile_id}")
        except Exception:
            pass

        should_stop = self._adspower_started or force_process_cleanup
        if should_stop:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(adspower.stop_browser, self.profile_id),
                    timeout=ADSPOWER_STOP_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                log.warning(f"AdsPower stop timeout for profile {self.profile_id}")
            except Exception as e:
                log.warning(f"AdsPower stop error: {e}")

            try:
                from hydra.browser.adspower_cleanup import cleanup_adspower_processes
                result = await asyncio.to_thread(
                    cleanup_adspower_processes,
                    profile_id=self.profile_id,
                    known_pids=self._adspower_process_ids,
                    debug_port=self._adspower_debug_port,
                    reason="browser_session_close",
                )
                if result.get("matched_pids"):
                    log.warning(
                        f"AdsPower process fallback for profile {self.profile_id}: {result}"
                    )
            except Exception as e:
                log.warning(f"AdsPower process cleanup error: {e}")

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
