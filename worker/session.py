"""브라우저 세션 관리 — 프로필 열기/닫기/태스크 루프."""
import asyncio
import json
import random
from datetime import datetime, UTC
from hydra.browser.driver import BrowserSession
from hydra.browser.actions import random_delay, scroll_page, click_like_button, watch_video, handle_ad
from worker.youtube_habits import maybe_check_notifications, maybe_visit_own_channel


class WorkerSession:
    """한 계정의 브라우저 세션. 여러 태스크를 자연스럽게 실행."""

    def __init__(self, profile_id: str, account_id: int, device_id: str | None = None):
        self.profile_id = profile_id
        self.account_id = account_id
        self.device_id = device_id
        self.browser: BrowserSession | None = None
        self.tasks_completed = 0
        self.max_tasks_per_session = random.randint(3, 8)
        self.max_session_minutes = random.randint(20, 45)
        self.started_at: datetime | None = None

    async def start(self) -> bool:
        """세션 시작: IP 변경 → 프로필 열기 → YouTube 접속."""
        try:
            # IP 변경
            if self.device_id:
                from hydra.infra.ip import rotate_ip
                await rotate_ip(self.device_id)

            # AdsPower 프로필 열기 + Playwright CDP 연결
            self.browser = BrowserSession(self.profile_id)
            await self.browser.start()

            # YouTube 접속
            await self.browser.goto("https://www.youtube.com")
            await random_delay(2.0, 4.0)

            self.started_at = datetime.now(UTC)
            return True
        except Exception as e:
            print(f"[Session] Failed to start: {e}")
            await self.close()
            return False

    async def should_continue(self) -> bool:
        """세션 계속 여부 판단."""
        if not self.started_at:
            return False
        elapsed = (datetime.now(UTC) - self.started_at).total_seconds() / 60
        if elapsed >= self.max_session_minutes:
            return False
        if self.tasks_completed >= self.max_tasks_per_session:
            return False
        return True

    async def do_natural_browsing(self):
        """태스크 사이에 자연스러운 브라우징."""
        if not self.browser:
            return
        page = self.browser.page

        action = random.choices(
            ["shorts", "watch_recommended", "scroll_home", "nothing"],
            weights=[30, 25, 25, 20],
        )[0]

        if action == "shorts":
            await self._browse_shorts(page)
        elif action == "watch_recommended":
            await self._watch_recommended(page)
        elif action == "scroll_home":
            await self.browser.goto("https://www.youtube.com")
            await scroll_page(page, scrolls=random.randint(2, 5))
        # nothing = 그냥 대기
        await random_delay(2.0, 5.0)

        # 가끔 알림 확인 / 내 채널 방문
        await maybe_check_notifications(page)
        await maybe_visit_own_channel(page)

    async def _browse_shorts(self, page):
        """숏츠 시청 (자연스러운 패턴)."""
        await self.browser.goto("https://www.youtube.com/shorts")
        await random_delay(1.5, 3.0)

        num_shorts = random.randint(2, 15)
        for _ in range(num_shorts):
            behavior = random.choices(
                ["skip", "short_watch", "full_watch", "rewatch"],
                weights=[40, 30, 20, 5],
            )[0]

            if behavior == "skip":
                await random_delay(1.0, 2.0)
            elif behavior == "short_watch":
                await random_delay(3.0, 10.0)
            elif behavior == "full_watch":
                await random_delay(15.0, 60.0)
            elif behavior == "rewatch":
                await random_delay(15.0, 40.0)
                continue  # 다시 보기 — 스와이프 안 함

            # 가끔 좋아요
            if random.random() < 0.1:
                try:
                    await click_like_button(page, target="video")
                except Exception:
                    pass

            # 다음 숏츠로 스와이프
            await page.keyboard.press("ArrowDown")
            await random_delay(0.3, 1.0)

    async def _watch_recommended(self, page):
        """추천 영상 하나 시청."""
        await self.browser.goto("https://www.youtube.com")
        await random_delay(1.5, 3.0)

        thumbnails = page.locator("ytd-rich-item-renderer a#thumbnail")
        count = await thumbnails.count()
        if count > 0:
            idx = random.randint(0, min(count - 1, 9))
            await thumbnails.nth(idx).click()
            await random_delay(2.0, 4.0)
            await handle_ad(page)
            duration = random.randint(10, 180)
            await watch_video(page, duration)

    async def close(self):
        """세션 종료."""
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
            self.browser = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.close()
