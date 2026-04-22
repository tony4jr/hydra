#!/usr/bin/env python3
"""이미 로그인된 브라우저에서 TOTP authenticator 등록 + DB 저장."""
import asyncio, sys
sys.path.insert(0, ".")

from playwright.async_api import async_playwright
from hydra.db.session import SessionLocal
from hydra.db.models import Account
from hydra.browser.adspower import AdsPowerClient
from hydra.core import crypto
from worker.google_account import register_otp_authenticator


async def main(aid: int):
    db = SessionLocal(); acct = db.get(Account, aid); db.close()
    pwd = crypto.decrypt(acct.password)
    adsp = AdsPowerClient()
    info = adsp.start_browser(acct.adspower_profile_id)
    pw = await async_playwright().start()
    try:
        b = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{info['debug_port']}")
        ctx = b.contexts[0]
        # 작업 가능한 페이지: google/youtube 도메인 우선
        page = next(
            (p for p in ctx.pages if "google.com" in p.url or "youtube.com" in p.url),
            ctx.pages[0] if ctx.pages else None,
        )
        if page is None:
            page = await ctx.new_page()
        print(f"start url = {page.url[:120]}")

        secret, activated = await register_otp_authenticator(page, pwd)
        print(f"secret={secret!r}  activated={activated}")

        if secret:
            db = SessionLocal()
            try:
                row = db.get(Account, aid)
                row.totp_secret = crypto.encrypt(secret)
                db.commit()
                print(f"saved to DB — #{aid} totp_secret set")
            finally:
                db.close()
    finally:
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
