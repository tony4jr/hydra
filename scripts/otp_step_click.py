#!/usr/bin/env python3
"""현재 페이지에서 지정 텍스트 (부분일치) 포함한 클릭 가능 요소를 랜덤 마우스 클릭."""
import asyncio, random, sys
sys.path.insert(0, ".")

from playwright.async_api import async_playwright
from hydra.db.session import SessionLocal
from hydra.db.models import Account
from hydra.browser.adspower import AdsPowerClient


async def main(aid: int, needle: str):
    db = SessionLocal(); a = db.get(Account, aid); db.close()
    adsp = AdsPowerClient(); info = adsp.start_browser(a.adspower_profile_id)
    pw = await async_playwright().start()
    try:
        b = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{info['debug_port']}")
        ctx = b.contexts[0]
        page = next((p for p in ctx.pages if "google.com" in p.url), ctx.pages[0])
        print(f"start url = {page.url[:120]}")
        try: await page.wait_for_load_state("networkidle", timeout=5000)
        except: pass

        box = await page.evaluate("""(needle) => {
          const lo = needle.toLowerCase();
          const els = Array.from(document.querySelectorAll(
            'button, a, [role="button"], [role="link"]'
          )).filter(e => e.offsetParent !== null);
          let best = null, bestArea = 1e12;
          for (const e of els) {
            const t = (e.innerText||e.textContent||'').trim().toLowerCase();
            if (!t.includes(lo)) continue;
            const r = e.getBoundingClientRect();
            if (r.width < 20 || r.height < 15) continue;
            const area = r.width * r.height;
            if (area < bestArea) { best = e; bestArea = area; }
          }
          if (!best) return null;
          const r = best.getBoundingClientRect();
          return {x: r.x, y: r.y, w: r.width, h: r.height,
                  text: (best.innerText||'').trim().slice(0,80)};
        }""", needle)
        print(f"match: {box}")
        if not box: return

        cx = box['x'] + box['w'] * random.uniform(0.3, 0.7)
        cy = box['y'] + box['h'] * random.uniform(0.35, 0.65)
        await page.mouse.move(cx - 14, cy - 8, steps=6)
        await asyncio.sleep(random.uniform(0.2, 0.4))
        await page.mouse.move(cx, cy, steps=4)
        await page.mouse.click(cx, cy, delay=random.randint(40, 90))
        await asyncio.sleep(3)
        print(f"after url = {page.url[:120]}")
    finally:
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), sys.argv[2]))
