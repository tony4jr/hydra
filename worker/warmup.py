"""워밍업 모드 — 2~3일 점진적 활동 증가."""
import random
import json
from datetime import datetime, UTC
from hydra.browser.actions import (
    human_click,
    random_delay, scroll_page, click_like_button,
    post_comment, watch_video, handle_ad, scroll_to_comments,
    check_ghost,
)
from worker.session import WorkerSession
from worker.google_activity import maybe_check_gmail, maybe_google_search
from worker.language_setup import ensure_korean_language
from worker.login import ensure_logged_in
from worker.subscription_hygiene import (
    maybe_subscribe_if_korean, maybe_unsubscribe_non_korean,
)

class WarmupExecutor:
    """워밍업 세션 실행기."""

    def __init__(self, session: WorkerSession, day: int = 1, persona: dict | None = None, session_context: dict | None = None):
        self.session = session
        self.day = day
        self.persona = persona or {}
        self.session_context = session_context or {}
        self.occupation = self.persona.get("occupation", "default")

    async def run(self) -> dict:
        """워밍업 세션 실행. 결과 요약 반환."""
        page = self.session.browser.page
        result = {"day": self.day, "actions": []}

        # Day 1 최초: UI 언어를 한국어로 정렬 (idempotent)
        # Gmail 이 다른 로캘 (예: 베트남어) 로 생성돼 IP/지문은 KR 인데 UI 만
        # 다른 언어로 나오는 불일치를 워밍업 시작점에서 해소한다.
        if self.day == 1:
            try:
                ok = await ensure_korean_language(page)
                if ok:
                    result["actions"].append("language_setup_ko")
                else:
                    result["actions"].append("language_setup_failed")
            except Exception as e:
                result["actions"].append(f"language_setup_error:{e}")
            # 언어 설정 끝나면 YouTube 로 복귀
            await self.session.browser.goto("https://www.youtube.com")
            await random_delay(2.0, 4.0)

        # 채널 이름/아바타/설명은 온보딩 세션에서 이미 완료됨 — 여기선 처리하지 않음.
        # (worker/onboard_session.py 의 마지막 단계 참조)

        # Google 활동 (Day 2+)
        if self.day >= 2:
            if await maybe_check_gmail(page, probability=0.3):
                result["actions"].append("gmail_check")
            age = int(self.persona.get("age", 25))
            if await maybe_google_search(page, age=age, probability=0.4):
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

        # 구독 (Day 2+, 30% 확률 + 한국어 컨텍스트에서만)
        if self.day >= 2:
            try:
                if await maybe_subscribe_if_korean(page, probability=0.3):
                    result["actions"].append("subscribe_kr")
            except Exception:
                pass

        # 구독 관리 — 한국 외 채널 1~2개 조용히 해지 (Day 2+, 30% 확률)
        if self.day >= 2:
            try:
                removed = await maybe_unsubscribe_non_korean(
                    page, max_actions=2, probability=0.3,
                )
                if removed:
                    result["actions"].append(f"unsubscribe_non_kr:{removed}")
            except Exception:
                pass

        # 고스트 체크 (Day 3 — Day 2에서 남긴 댓글 확인)
        if self.day >= 3:
            await self._check_previous_comments(page, result)

        return result

    async def _check_previous_comments(self, page, result: dict):
        """이전에 남긴 댓글 생존 확인."""
        previous_comments = self.session_context.get("previous_comments", [])

        for comment_info in previous_comments[:2]:  # 최대 2개만 체크
            video_id = comment_info.get("video_id", "")
            comment_id = comment_info.get("youtube_comment_id", "")
            if not video_id or not comment_id:
                continue

            try:
                await page.goto(f"https://www.youtube.com/watch?v={video_id}")
                await random_delay(2.0, 4.0)

                await scroll_to_comments(page)

                # 최신순 전환
                sort_btn = page.locator("#sort-menu tp-yt-paper-button, #sort-menu button").first
                await human_click(sort_btn)
                await random_delay(0.5, 1.0)
                newest = page.locator("tp-yt-paper-listbox a, div[role='option']").nth(1)
                await human_click(newest)
                await random_delay(2.0, 4.0)

                ghost_result = await check_ghost(page, comment_id)
                result["actions"].append(f"ghost_check:{comment_id}:{ghost_result}")
            except Exception:
                pass

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
