"""Gmail 확인 + Google 검색 — 자연스러운 쿠키 축적."""
import random

from hydra.browser.actions import random_delay, type_human, scroll_page

SEARCH_QUERIES = {
    "대학생": ["과제 마감일", "대학생 할인", "아르바이트 추천", "시험 공부법"],
    "회사원": ["퇴근 후 운동", "점심 맛집", "연차 사용법", "이직 준비"],
    "자영업": ["소상공인 대출", "매출 관리", "가게 인테리어", "배달 앱 수수료"],
    "주부": ["아이 간식 레시피", "육아 꿀팁", "주부 재테크", "집안일 꿀팁"],
    "프리랜서": ["프리랜서 세금", "재택근무 환경", "포트폴리오", "작업 카페"],
    "default": ["오늘 날씨", "맛집 추천", "영화 추천", "뉴스", "운동법"],
}


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


async def maybe_google_search(page, occupation="default", probability=0.4):
    if random.random() > probability:
        return False
    queries = SEARCH_QUERIES.get(occupation, SEARCH_QUERIES["default"])
    query = random.choice(queries)
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
