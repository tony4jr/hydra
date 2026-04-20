"""YouTube 자연스러운 습관 -- 알림 확인, 프로필 방문."""
import random
from hydra.browser.actions import human_click, random_delay


async def maybe_check_notifications(page, probability: float = 0.05):
    """알림 벨 확인 (5% 확률)."""
    if random.random() > probability:
        return False
    try:
        bell = page.locator("button.ytd-notification-topbar-button-renderer, button[aria-label*='알림'], button[aria-label*='Notification']").first
        await human_click(bell)
        await random_delay(2.0, 5.0)
        # 알림 패널 닫기 (다른 곳 클릭)
        await page.keyboard.press("Escape")
        await random_delay(0.5, 1.0)
        return True
    except Exception:
        return False


async def maybe_visit_own_channel(page, probability: float = 0.03):
    """내 채널 방문 (3% 확률)."""
    if random.random() > probability:
        return False
    try:
        # 프로필 아이콘 클릭
        avatar = page.locator("button#avatar-btn").first
        await human_click(avatar)
        await random_delay(1.0, 2.0)
        # "내 채널" 클릭
        my_channel = page.locator("a:has-text('내 채널'), a:has-text('Your channel')").first
        await human_click(my_channel)
        await random_delay(3.0, 6.0)
        # YouTube 홈으로 돌아가기
        await page.goto("https://www.youtube.com")
        await random_delay(1.5, 3.0)
        return True
    except Exception:
        return False
