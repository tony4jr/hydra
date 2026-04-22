#!/usr/bin/env python3
"""현재 pwd 페이지에 비번 입력 + Enter → 이후 FSM 로 이어받기."""
import asyncio, sys
sys.path.insert(0, ".")

from playwright.async_api import async_playwright
from hydra.db.session import SessionLocal
from hydra.db.models import Account
from hydra.browser.adspower import AdsPowerClient
from hydra.browser.actions import type_human, random_delay
from hydra.core import crypto
from onboarding.login_fsm import run_login_fsm


async def main(aid: int):
    db = SessionLocal()
    acct = db.get(Account, aid); db.close()

    adsp = AdsPowerClient()
    info = adsp.start_browser(acct.adspower_profile_id)
    port = info.get("debug_port")
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0]
        page = next((p for p in ctx.pages if "accounts.google.com" in p.url), ctx.pages[0])
        print(f"start url = {page.url}")

        # 비번 입력 (현재 pwd 페이지 가정)
        pwd = crypto.decrypt(acct.password)
        await page.locator("input[type='password']").first.wait_for(timeout=10_000)
        await type_human(page, "input[type='password'][name='Passwd']", pwd, typing_style="typist")
        await random_delay(0.5, 1.2)
        await page.keyboard.press("Enter")
        print("password submitted, waiting for URL change…")

        # 남은 FSM 이어받기 (selection/ipe/done 등)
        # run_login_fsm 은 signin 으로 goto 하므로 여기선 사용하지 않고 직접 관찰만
        for i in range(30):
            await asyncio.sleep(2)
            print(f"  [{i*2:>3}s] {page.url[:110]}")
            if "myaccount.google.com" in page.url or "youtube.com" in page.url:
                print("=> LOGGED IN")
                break
    finally:
        await pw.stop()


if __name__ == "__main__":
    aid = int(sys.argv[1]) if len(sys.argv) > 1 else 31
    asyncio.run(main(aid))
