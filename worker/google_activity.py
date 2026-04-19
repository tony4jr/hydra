"""Gmail 확인 + Google 검색 — 자연스러운 쿠키 축적."""
import random

from hydra.browser.actions import random_delay, type_human, scroll_page
from worker.search_pool import pick as pick_query


async def maybe_check_gmail(page, probability=0.3):
    if random.random() > probability:
        return False
    await page.goto("https://mail.google.com")
    await random_delay(3.0, 6.0)
    try:
        await page.wait_for_selector("div[role='main']", timeout=10000)
    except Exception:
        return False
    emails = page.locator("tr.zA")
    count = await emails.count()
    if count > 0:
        clicks = random.randint(1, min(2, count))
        for _ in range(clicks):
            idx = random.randint(0, min(count - 1, 5))
            await emails.nth(idx).click()
            await random_delay(3.0, 8.0)
            await page.go_back()
            await random_delay(1.0, 3.0)
    await random_delay(2.0, 5.0)
    return True


async def maybe_google_search(page, age: int | None = None, *, probability: float = 0.4,
                               occupation: str | None = None):
    """Google 검색. age 가 주어지면 search_pool 의 해당 age bucket 에서 쿼리 픽.
    occupation 은 backward-compat 용 — 무시되지만 시그니처 유지.
    """
    if random.random() > probability:
        return False
    query = pick_query(age if age is not None else 25)
    await page.goto("https://www.google.com")
    await random_delay(1.5, 3.0)
    await type_human(page, "textarea[name='q'], input[name='q']", query)
    await random_delay(0.5, 1.5)
    await page.keyboard.press("Enter")
    await random_delay(2.0, 4.0)
    results = page.locator("div#search a h3")
    count = await results.count()
    if count > 0:
        clicks = random.randint(1, min(2, count))
        for _ in range(clicks):
            idx = random.randint(0, min(count - 1, 4))
            await results.nth(idx).click()
            await random_delay(5.0, 15.0)
            await page.go_back()
            await random_delay(1.0, 3.0)
    return True
