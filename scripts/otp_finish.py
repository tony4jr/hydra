#!/usr/bin/env python3
"""Authenticator 설정 페이지에서 시크릿 추출 → Next → 코드 입력 → DB 저장."""
import asyncio, random, re, sys
import pyotp
sys.path.insert(0, ".")

from playwright.async_api import async_playwright
from hydra.db.session import SessionLocal
from hydra.db.models import Account
from hydra.browser.adspower import AdsPowerClient
from hydra.core import crypto


async def _click_by_text(page, needle: str, *, exact=False):
    box = await page.evaluate("""(args) => {
      const {needle, exact} = args;
      const lo = needle.toLowerCase();
      const els = Array.from(document.querySelectorAll(
        'button, a, [role="button"], [role="link"]'
      )).filter(e => e.offsetParent !== null);
      let best = null, bestArea = 1e12;
      for (const e of els) {
        const t = (e.innerText||e.textContent||'').trim().toLowerCase();
        const hit = exact ? (t === lo) : t.includes(lo);
        if (!hit) continue;
        const r = e.getBoundingClientRect();
        if (r.width < 15 || r.height < 15) continue;
        const area = r.width * r.height;
        if (area < bestArea) { best = e; bestArea = area; }
      }
      if (!best) return null;
      const r = best.getBoundingClientRect();
      return {x: r.x, y: r.y, w: r.width, h: r.height};
    }""", {"needle": needle, "exact": exact})
    if not box:
        return False
    cx = box['x'] + box['w'] * random.uniform(0.3, 0.7)
    cy = box['y'] + box['h'] * random.uniform(0.35, 0.65)
    await page.mouse.move(cx - 14, cy - 8, steps=6)
    await asyncio.sleep(random.uniform(0.2, 0.4))
    await page.mouse.move(cx, cy, steps=4)
    await page.mouse.click(cx, cy, delay=random.randint(40, 90))
    return True


async def main(aid: int):
    db = SessionLocal(); a = db.get(Account, aid); db.close()
    adsp = AdsPowerClient(); info = adsp.start_browser(a.adspower_profile_id)
    pw = await async_playwright().start()
    try:
        b = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{info['debug_port']}")
        ctx = b.contexts[0]
        page = next(p for p in ctx.pages if "authenticator" in p.url)

        # 1) 시크릿 추출 (dialog 본문 텍스트에서 base32 블록)
        dlg_text = await page.evaluate(
            "() => { const d = document.querySelector('[role=\"dialog\"]'); return d ? d.innerText : ''; }"
        )
        m = re.search(r'([a-z2-7]{4}(?:[ -]?[a-z2-7]{4}){3,})', dlg_text, re.I)
        if not m:
            print("NO secret found")
            print(dlg_text); return
        secret = re.sub(r'[^a-z2-7]', '', m.group(1), flags=re.I).upper()
        print(f"secret = {secret}  (len={len(secret)})")

        # 2) Next 클릭 → 코드 입력 페이지
        await asyncio.sleep(random.uniform(0.8, 1.5))
        if not await _click_by_text(page, "Next", exact=True):
            print("Next button not found"); return
        await asyncio.sleep(3)
        print(f"after Next: {page.url[:120]}")

        # 3) 6자리 코드 입력
        code = pyotp.TOTP(secret).now()
        print(f"generated code: {code}")
        inp = page.locator("input[type='text'], input[type='tel'], input[name='pin']").first
        await inp.wait_for(timeout=10_000)
        await inp.click()
        await asyncio.sleep(random.uniform(0.3, 0.6))
        await page.keyboard.type(code, delay=random.randint(70, 150))
        await asyncio.sleep(random.uniform(0.5, 1.0))

        # 4) Verify/Next 클릭
        for btn in ("Verify", "Next", "Done", "Save"):
            if await _click_by_text(page, btn, exact=True):
                print(f"clicked '{btn}'"); break
        await asyncio.sleep(4)
        print(f"final url: {page.url[:140]}")

        # 5) DB 저장
        db = SessionLocal()
        try:
            row = db.get(Account, aid)
            row.totp_secret = crypto.encrypt(secret)
            db.commit()
            print(f"saved totp_secret for #{aid}")
        finally:
            db.close()
    finally:
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
