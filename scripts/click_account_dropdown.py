#!/usr/bin/env python3
"""현재 열린 #31 브라우저에 재연결해서 계정 드롭다운 클릭."""
import asyncio, sys
sys.path.insert(0, ".")

from playwright.async_api import async_playwright
from hydra.db.session import SessionLocal
from hydra.db.models import Account
from hydra.browser.adspower import AdsPowerClient


async def main(aid: int):
    db = SessionLocal()
    acct = db.get(Account, aid)
    db.close()
    assert acct

    adsp = AdsPowerClient()
    # 이미 열려 있으면 기존 debug_port 반환
    info = adsp.start_browser(acct.adspower_profile_id)
    port = info.get("debug_port")
    print(f"debug_port={port}")

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "accounts.google.com" in pg.url or "ipp" in pg.url:
                page = pg; break
        if page is None:
            page = ctx.pages[0]
        print(f"page url = {page.url}")

        # 계정 chip bounding box 찾기 (해상도 무관 — 요소의 실제 좌표/크기 사용)
        box = await page.evaluate("""() => {
          // chip 은 role=link 이고 aria-label 에 '항목이 선택' 같은 combobox 표현 포함,
          // 그리고 작은 크기 (보통 width < 350)
          const cands = Array.from(document.querySelectorAll('[role="link"], [role="combobox"], [role="button"]'))
            .filter(e => e.offsetParent !== null);
          let best = null, bestW = 9999;
          for (const e of cands) {
            const t = (e.innerText||'').trim();
            const a = (e.getAttribute('aria-label')||'');
            if (!/@gmail\\.com/.test(t+' '+a)) continue;
            const r = e.getBoundingClientRect();
            if (r.width < 10 || r.height < 10) continue;
            if (r.width < bestW) { best = e; bestW = r.width; }
          }
          if (!best) return null;
          const r = best.getBoundingClientRect();
          return {x: r.x, y: r.y, w: r.width, h: r.height,
                  tag: best.tagName, role: best.getAttribute('role')||'',
                  aria: best.getAttribute('aria-label')||''};
        }""")
        print(f"chip box: {box}")
        if not box:
            return
        # 랜덤 오프셋 — 중심 고정 금지 (anti-detection)
        import random
        cx = box['x'] + box['w'] * random.uniform(0.2, 0.8)
        cy = box['y'] + box['h'] * random.uniform(0.3, 0.7)
        print(f"mouse click → ({cx:.1f}, {cy:.1f})")
        await page.mouse.move(cx - 10, cy - 5, steps=6)
        await asyncio.sleep(random.uniform(0.15, 0.35))
        await page.mouse.move(cx, cy, steps=4)
        await page.mouse.click(cx, cy, delay=random.randint(40, 90))
        await asyncio.sleep(2)
        print(f"after-click url = {page.url}")

        # 새로 생긴 메뉴 항목 캡처
        menu = await page.evaluate("""() => {
          const items = Array.from(document.querySelectorAll('[role="menuitem"], [role="link"], a, button'))
            .filter(e => e.offsetParent !== null);
          return items.slice(0, 20).map(e => ({
            tag: e.tagName,
            role: e.getAttribute('role')||'',
            aria: e.getAttribute('aria-label')||'',
            text: (e.innerText||e.textContent||'').trim().slice(0, 80),
          })).filter(i => i.text);
        }""")
        print("\n--- visible menu/links after click ---")
        for m in menu:
            print(f"  [{m['tag']}|{m['role']}] {m['aria'][:40]:<40} | {m['text']}")

    finally:
        await pw.stop()


if __name__ == "__main__":
    aid = int(sys.argv[1]) if len(sys.argv) > 1 else 31
    asyncio.run(main(aid))
