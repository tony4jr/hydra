"""태스크 실행기 — 실제 브라우저 자동화 기반 핸들러 디스패치."""
import json
import random

from hydra.browser.actions import (
    random_delay,
    scroll_page,
    scroll_to_comments,
    click_like_button,
    post_comment,
    post_reply,
    watch_video,
    handle_ad,
    check_ghost,
)
from worker.mouse import click_with_mouse_move
from worker.login import auto_login
from worker.warmup import WarmupExecutor
from worker.session import WorkerSession


class TaskExecutor:
    def __init__(self):
        self.handlers = {
            "comment": self._handle_comment,
            "reply": self._handle_reply,
            "like": self._handle_like,
            "like_boost": self._handle_like_boost,
            "subscribe": self._handle_subscribe,
            "warmup": self._handle_warmup,
            "ghost_check": self._handle_ghost_check,
            "login": self._handle_login,
            "channel_setup": self._handle_channel_setup,
        }

    async def execute(self, task: dict, session: WorkerSession) -> str:
        """태스크 실행. 결과 JSON 문자열 반환."""
        task_type = task["task_type"]
        payload = json.loads(task.get("payload") or "{}")
        handler = self.handlers.get(task_type)
        if not handler:
            raise ValueError(f"Unknown task type: {task_type}")
        return await handler(task, payload, session)

    # ── helpers ──────────────────────────────────────────────

    async def _navigate_to_video(self, session: WorkerSession, video_id: str):
        """영상 페이지로 이동."""
        page = session.browser.page
        url = f"https://www.youtube.com/watch?v={video_id}"
        await session.browser.goto(url)
        await random_delay(2.0, 4.0)
        await handle_ad(page)

    # ── handlers ─────────────────────────────────────────────

    async def _handle_comment(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """영상에 댓글 작성."""
        page = session.browser.page
        video_id = payload["video_id"]
        text = payload["text"]

        await self._navigate_to_video(session, video_id)

        # 영상 잠시 시청
        watch_sec = random.randint(5, 30)
        await watch_video(page, watch_sec)

        # 댓글 영역으로 스크롤
        await scroll_to_comments(page)

        # 기존 댓글 읽는 시간
        await random_delay(3.0, 10.0)

        # 댓글 작성
        comment_id = await post_comment(page, text)

        return json.dumps({
            "action": "comment",
            "video_id": video_id,
            "comment_id": comment_id,
            "watched_sec": watch_sec,
        })

    async def _handle_reply(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """댓글에 대댓글 작성."""
        page = session.browser.page
        video_id = payload["video_id"]
        target_comment_selector = payload.get("target_selector", "")
        text = payload["text"]

        await self._navigate_to_video(session, video_id)

        # 댓글 영역으로 스크롤
        await scroll_to_comments(page)
        await random_delay(2.0, 5.0)

        # 대댓글 작성
        reply_id = await post_reply(page, target_comment_selector, text)

        return json.dumps({
            "action": "reply",
            "video_id": video_id,
            "reply_id": reply_id,
        })

    async def _handle_like(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """영상 좋아요."""
        page = session.browser.page
        video_id = payload["video_id"]

        await self._navigate_to_video(session, video_id)

        # 영상 시청
        watch_sec = random.randint(5, 30)
        await watch_video(page, watch_sec)

        # 좋아요 클릭
        liked = await click_like_button(page, target="video")

        return json.dumps({
            "action": "like",
            "video_id": video_id,
            "liked": liked,
            "watched_sec": watch_sec,
        })

    async def _handle_like_boost(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """댓글 좋아요 부스트 — 위장용 댓글도 함께 좋아요."""
        page = session.browser.page
        video_id = payload["video_id"]
        target_comment_id = payload.get("target_comment_id", "")

        await self._navigate_to_video(session, video_id)

        # 영상 잠시 시청
        watch_sec = random.randint(3, 15)
        await watch_video(page, watch_sec)

        # 댓글 영역으로 스크롤
        await scroll_to_comments(page)
        await random_delay(2.0, 5.0)

        # 위장용 주변 댓글 좋아요 (2~4개)
        camouflage_count = random.randint(2, 4)
        camouflaged = 0
        comment_buttons = page.locator(
            "ytd-comment-thread-renderer ytd-menu-renderer "
            "yt-icon-button#like-button, "
            "ytd-comment-thread-renderer like-button-view-model button"
        )
        total_comments = await comment_buttons.count()
        if total_comments > 0:
            indices = random.sample(
                range(min(total_comments, 20)),
                min(camouflage_count, total_comments),
            )
            for idx in indices:
                try:
                    await comment_buttons.nth(idx).click()
                    camouflaged += 1
                    await random_delay(1.0, 3.0)
                except Exception:
                    pass

        # 타겟 댓글 좋아요
        target_liked = False
        if target_comment_id:
            target_sel = f"ytd-comment-thread-renderer[comment-id='{target_comment_id}']"
            target_like = page.locator(
                f"{target_sel} like-button-view-model button, "
                f"{target_sel} yt-icon-button#like-button"
            )
            try:
                if await target_like.count() > 0:
                    await target_like.first.click()
                    target_liked = True
            except Exception:
                pass

        return json.dumps({
            "action": "like_boost",
            "video_id": video_id,
            "target_comment_id": target_comment_id,
            "target_liked": target_liked,
            "camouflaged": camouflaged,
        })

    async def _handle_subscribe(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """채널 구독."""
        page = session.browser.page
        video_id = payload["video_id"]

        await self._navigate_to_video(session, video_id)

        # 구독 버튼 클릭
        subscribe_btn = page.locator(
            "ytd-subscribe-button-renderer button, "
            "yt-subscribe-button-view-model button"
        )
        subscribed = False
        try:
            if await subscribe_btn.count() > 0:
                await click_with_mouse_move(page, "ytd-subscribe-button-renderer button")
                subscribed = True
                await random_delay(1.0, 2.0)
        except Exception:
            pass

        return json.dumps({
            "action": "subscribe",
            "video_id": video_id,
            "subscribed": subscribed,
        })

    async def _handle_warmup(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """워밍업 세션 — WarmupExecutor에 위임."""
        day = payload.get("day", 1)
        persona = payload.get("persona", {})

        executor = WarmupExecutor(session, day=day, persona=persona)
        result = await executor.run()

        return json.dumps({"action": "warmup", **result})

    async def _handle_ghost_check(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """고스트 체크 — 댓글이 다른 사용자에게 보이는지 확인."""
        page = session.browser.page
        video_id = payload["video_id"]
        youtube_comment_id = payload.get("youtube_comment_id", "")

        await self._navigate_to_video(session, video_id)

        # 댓글 영역으로 스크롤
        await scroll_to_comments(page)
        await random_delay(2.0, 4.0)

        # 최신순 정렬로 전환
        sort_button = page.locator("yt-sort-filter-sub-menu-renderer tp-yt-paper-dropdown-menu")
        try:
            if await sort_button.count() > 0:
                await sort_button.first.click()
                await random_delay(0.5, 1.0)
                newest = page.locator("tp-yt-paper-listbox a, yt-dropdown-menu a").nth(1)
                await newest.click()
                await random_delay(2.0, 4.0)
        except Exception:
            pass

        # 고스트 DOM 체크
        status = await check_ghost(page, youtube_comment_id)

        return json.dumps({
            "action": "ghost_check",
            "video_id": video_id,
            "youtube_comment_id": youtube_comment_id,
            "status": status,
        })

    async def _handle_login(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """로그인 — auto_login에 위임."""
        page = session.browser.page
        email = payload["email"]
        password = payload["password"]
        totp_secret = payload.get("totp_secret")

        success = await auto_login(page, email, password, totp_secret)

        return json.dumps({
            "action": "login",
            "email": email,
            "success": success,
        })

    async def _handle_channel_setup(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """채널 설정 — YouTube Studio (향후 구현)."""
        # placeholder
        return json.dumps({
            "action": "channel_setup",
            "status": "not_implemented",
        })
