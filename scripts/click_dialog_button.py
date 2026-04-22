#!/usr/bin/env python3
"""현재 열린 브라우저의 다이얼로그에서 지정 텍스트 버튼 클릭 — 마우스 랜덤.

usage: python scripts/click_dialog_button.py <account_id> <dialog_text> <button_text>
ex:    python scripts/click_dialog_button.py 50 "본인 인증" "다음"
"""
import asyncio, random, sys
sys.path.insert(0, ".")

from playwright.async_api import async_playwright
from hydra.db.session import SessionLocal
from hydra.db.models import Account
from hydra.browser.adspower import AdsPowerClient


async def main(aid: int, dialog_text: str, button_text: str):
    db = SessionLocal(); acct = db.get(Account, aid); db.close()
    adsp = AdsPowerClient()
    info = adsp.start_browser(acct.adspower_profile_id)
    pw = await async_playwright().start()
    try:
        b = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{info['debug_port']}")
        ctx = b.contexts[0]
        page = next((p for p in ctx.pages if "studio.youtube.com" in p.url), None)
        if page is None:
            page = next((p for p in ctx.pages if "youtube.com" in p.url), ctx.pages[0])
        print(f"page url = {page.url[:120]}")
        # 네비게이션 안정화 대기 — 반복 리다이렉트에서 evaluate 컨텍스트 터지는 것 회피
        for _ in range(5):
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5_000)
                await asyncio.sleep(2)
                await page.wait_for_load_state("networkidle", timeout=5_000)
                break
            except Exception:
                await asyncio.sleep(1)

        box = await page.evaluate(
            """(args) => {
              const {dt, bt} = args;
              const dlgs = Array.from(document.querySelectorAll(
                'tp-yt-paper-dialog, ytcp-dialog, [role="dialog"], [role="alertdialog"]'
              )).filter(d => d.offsetParent !== null);
              for (const d of dlgs) {
                if (!(d.innerText||'').includes(dt)) continue;
                const btns = Array.from(d.querySelectorAll('button, [role="button"]'))
                  .filter(e => e.offsetParent !== null);
                const hit = btns.find(b => (b.innerText||'').trim() === bt);
                if (!hit) continue;
                const r = hit.getBoundingClientRect();
                return {x: r.x, y: r.y, w: r.width, h: r.height, aria: hit.getAttribute('aria-label')||''};
              }
              return null;
            }""",
            {"dt": dialog_text, "bt": button_text},
        )
        print(f"button box: {box}")
        if not box:
            print("button not found")
            return

        cx = box['x'] + box['w'] * random.uniform(0.3, 0.7)
        cy = box['y'] + box['h'] * random.uniform(0.35, 0.65)
        print(f"click → ({cx:.1f}, {cy:.1f})")
        await page.mouse.move(cx - 14, cy - 8, steps=6)
        await asyncio.sleep(random.uniform(0.15, 0.35))
        await page.mouse.move(cx, cy, steps=4)
        await page.mouse.click(cx, cy, delay=random.randint(40, 90))
        await asyncio.sleep(3)
        print(f"after url = {page.url[:120]}")
    finally:
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), sys.argv[2], sys.argv[3]))
