"""워밍업 모드 — 2~3일 점진적 활동 증가."""
import random
import json
from datetime import datetime, UTC
from hydra.browser.actions import (
    random_delay, scroll_page, click_like_button,
    post_comment, watch_video, handle_ad, scroll_to_comments,
)
from worker.session import WorkerSession
from worker.google_activity import maybe_check_gmail, maybe_google_search
from worker.login import ensure_logged_in

class WarmupExecutor:
    """워밍업 세션 실행기."""

    def __init__(self, session: WorkerSession, day: int = 1, persona: dict | None = None):
        self.session = session
        self.day = day
        self.persona = persona or {}
        self.occupation = self.persona.get("occupation", "default")

    async def run(self) -> dict:
        """워밍업 세션 실행. 결과 요약 반환."""
        page = self.session.browser.page
        result = {"day": self.day, "actions": []}

        # Google 활동 (Day 2+)
        if self.day >= 2:
            if await maybe_check_gmail(page, probability=0.3):
                result["actions"].append("gmail_check")
            if await maybe_google_search(page, self.occupation, probability=0.4):
                result["actions"].append("google_search")
            # YouTube로 복귀
            await self.session.browser.goto("https://www.youtube.com")
            await random_delay(2.0, 4.0)

        # 숏츠 시청
        await self.session._browse_shorts(page)
        result["actions"].append("shorts")

        # 영상 시청
        videos_to_watch = self._pick_video_count()
        for _ in range(videos_to_watch):
            await self.session._watch_recommended(page)
            result["actions"].append("watch_video")

            if random.random() < self._like_probability():
                try:
                    await click_like_button(page, target="video")
                    result["actions"].append("like_video")
                except Exception:
                    pass

        # 댓글 (Day 2+)
        if self.day >= 2:
            comments_to_post = self._pick_comment_count()
            for _ in range(comments_to_post):
                await self.session._watch_recommended(page)
                await scroll_to_comments(page)
                await random_delay(3.0, 8.0)
                comment_text = self._generate_casual_comment()
                try:
                    comment_id = await post_comment(page, comment_text)
                    if comment_id:
                        result["actions"].append(f"comment:{comment_id}")
                except Exception:
                    pass

        # 구독 (Day 2+, 30%)
        if self.day >= 2 and random.random() < 0.3:
            subscribe_btn = page.locator("ytd-subscribe-button-renderer button")
            try:
                if await subscribe_btn.count() > 0:
                    await subscribe_btn.first.click()
                    result["actions"].append("subscribe")
            except Exception:
                pass

        return result

    def _pick_video_count(self) -> int:
        if self.day == 1:
            return random.randint(1, 2)
        elif self.day == 2:
            return random.randint(2, 3)
        return random.randint(2, 3)

    def _pick_comment_count(self) -> int:
        if self.day == 1:
            return 0
        elif self.day == 2:
            return random.randint(1, 2)
        return random.randint(3, 5)

    def _like_probability(self) -> float:
        if self.day == 1:
            return 0.3
        return 0.5

    def _generate_casual_comment(self) -> str:
        comments = [
            "좋은 영상이네요~",
            "오 이런 정보 처음 알았어요",
            "유익합니다 감사해요",
            "저도 한번 해봐야겠다",
            "와 진짜 좋은 내용이네요",
            "구독했어요!",
            "잘 봤습니다~",
            "영상 잘 만드시네요",
            "이거 궁금했는데 감사합니다",
            "오늘도 유익한 영상 감사해요",
            "대박 정보 감사합니다ㅋㅋ",
            "ㅋㅋㅋ 재밌다",
            "요즘 이게 핫하더라",
        ]
        return random.choice(comments)
