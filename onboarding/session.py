"""브라우저 세션 설정 — IP 로테 + AdsPower + CDP + 탭/다이얼로그 정리."""
import asyncio
import subprocess
import time
from dataclasses import dataclass

from playwright.async_api import async_playwright

from hydra.browser.adspower import AdsPowerClient
from hydra.core.logger import get_logger

log = get_logger("onboarding.session")


def rotate_ip() -> str:
    """ADB 모바일 데이터 토글 후 새 외부 IP 반환 (실패 시 빈 문자열)."""
    try:
        subprocess.run(["adb", "shell", "svc", "data", "disable"], check=True, timeout=10)
        time.sleep(3)
        subprocess.run(["adb", "shell", "svc", "data", "enable"], check=True, timeout=10)
        time.sleep(8)
        ip = subprocess.check_output(
            ["curl", "-s", "--max-time", "10", "https://api.ipify.org"], timeout=12
        ).decode().strip()
        return ip
    except Exception as e:
        log.warning(f"rotate_ip error: {e}")
        return ""


@dataclass
class Session:
    profile_id: str
    page: object           # playwright Page
    context: object        # playwright BrowserContext
    _pw: object            # async_playwright instance (for cleanup)
    _browser: object       # CDP-connected browser
    _adsp: AdsPowerClient

    async def close(self):
        try:
            await self._browser.close()
        except Exception:
            pass
        try:
            await self._pw.stop()
        except Exception:
            pass
        try:
            self._adsp.stop_browser(self.profile_id)
        except Exception:
            pass


async def open_session(acct, *, rotate: bool = True) -> Session:
    """IP 로테 → AdsPower start → Playwright CDP connect → 작업 탭 1개만 유지."""
    if rotate:
        ip = rotate_ip()
        log.info(f"IP → {ip or 'FAILED'}")
        if not ip:
            raise RuntimeError("IP rotation failed")

    adsp = AdsPowerClient()
    info = adsp.start_browser(acct.adspower_profile_id)
    debug_port = info.get("debug_port")
    if not debug_port:
        raise RuntimeError("AdsPower start: no debug_port")
    cdp = f"http://127.0.0.1:{debug_port}"
    log.info(f"AdsPower opened profile={acct.adspower_profile_id} port={debug_port}")
    await asyncio.sleep(3)  # tabs settle

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(cdp)
        ctx = browser.contexts[0] if browser.contexts else None
        if ctx is None:
            raise RuntimeError("no browser context")

        # 작업 탭 선택 (youtube.com / google.com 우선, 없으면 첫 탭 or new_page)
        work = None
        for pg in ctx.pages:
            if "youtube.com" in pg.url or "google.com" in pg.url:
                work = pg
                break
        if work is None:
            work = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # 나머지 탭 close (start.adspower 등)
        for pg in list(ctx.pages):
            if pg is not work:
                try:
                    await pg.close()
                except Exception:
                    pass

        # dialog 자동 accept
        work.on("dialog", lambda d: asyncio.create_task(d.accept()))

        # 주의: ctx.on("page") 로 잉여 탭 auto-close 하던 로직 의도적 제거.
        # 이유: 911panel 2FA 탭을 우리가 의도적으로 열면 auto-close 가 0.5초 후
        # 닫아서 fetch_2fa_code 의 page.goto 가 ERR_ABORTED. 초기 탭 정리만 하고
        # 이후 탭은 호출자가 명시적으로 관리.

        return Session(
            profile_id=acct.adspower_profile_id,
            page=work,
            context=ctx,
            _pw=pw,
            _browser=browser,
            _adsp=adsp,
        )
    except Exception:
        try:
            await pw.stop()
        except Exception:
            pass
        try:
            adsp.stop_browser(acct.adspower_profile_id)
        except Exception:
            pass
        raise
