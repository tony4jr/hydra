#!/usr/bin/env python3
"""accountchooser 에서 본인 gmail 계정 클릭 — 해상도 무관, 랜덤 오프셋."""
import asyncio, random, sys
sys.path.insert(0, ".")

from playwright.async_api import async_playwright
from hydra.db.session import SessionLocal
from hydra.db.models import Account
from hydra.browser.adspower import AdsPowerClient


async def main(aid: int):
    db = SessionLocal()
    acct = db.get(Account, aid); db.close()
    target_email = acct.gmail.lower()

    adsp = AdsPowerClient()
    info = adsp.start_browser(acct.adspower_profile_id)
    port = info.get("debug_port")
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "accountchooser" in pg.url or "accounts.google.com" in pg.url:
                page = pg; break
        if page is None:
            page = ctx.pages[0]
        print(f"page url = {page.url}")

        box = await page.evaluate(
            """(email) => {
              const cands = Array.from(document.querySelectorAll('[role="link"], [role="button"], li, div'))
                .filter(e => e.offsetParent !== null);
              let best = null, bestArea = 1e12;
              for (const e of cands) {
                const t = (e.innerText||'').toLowerCase();
                if (!t.includes(email)) continue;
                const r = e.getBoundingClientRect();
                if (r.width < 50 || r.height < 30) continue;
                const area = r.width * r.height;
                if (area < bestArea) { best = e; bestArea = area; }
              }
              if (!best) return null;
              const r = best.getBoundingClientRect();
              return {x: r.x, y: r.y, w: r.width, h: r.height,
                      tag: best.tagName, role: best.getAttribute('role')||''};
            }""",
            target_email,
        )
        print(f"account row box: {box}")
        if not box:
            return

        cx = box['x'] + box['w'] * random.uniform(0.25, 0.75)
        cy = box['y'] + box['h'] * random.uniform(0.3, 0.7)
        print(f"mouse click → ({cx:.1f}, {cy:.1f})")
        await page.mouse.move(cx - 15, cy - 8, steps=6)
        await asyncio.sleep(random.uniform(0.2, 0.4))
        await page.mouse.move(cx, cy, steps=4)
        await page.mouse.click(cx, cy, delay=random.randint(40, 90))
        await asyncio.sleep(3)
        print(f"after-click url = {page.url}")
    finally:
        await pw.stop()


if __name__ == "__main__":
    aid = int(sys.argv[1]) if len(sys.argv) > 1 else 31
    asyncio.run(main(aid))
