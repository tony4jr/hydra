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
    type_human,
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

    async def _navigate_to_video(self, session: WorkerSession, video_id: str, video_title: str = ""):
        """영상으로 이동 (검색/추천 or 직접 URL)."""
        page = session.browser.page
        use_search = random.random() < 0.7 and video_title  # 70% 검색, 제목 있을 때만

        if use_search:
            try:
                # YouTube 홈에서 검색
                await session.browser.goto("https://www.youtube.com")
                await random_delay(1.5, 3.0)

                # 검색바 클릭
                search_btn = page.locator("button#search-icon-legacy, input#search")
                await search_btn.first.click()
                await random_delay(0.5, 1.0)

                # 검색어 입력 (영상 제목 일부)
                search_query = self._make_search_query(video_title)
                search_input = page.locator("input#search")
                await search_input.fill("")
                await type_human(page, "input#search", search_query)
                await random_delay(0.5, 1.5)
                await page.keyboard.press("Enter")
                await random_delay(2.0, 4.0)

                # 검색 결과에서 영상 찾기 (video_id 매칭)
                found = await self._find_video_in_results(page, video_id, timeout=15)
                if found:
                    await handle_ad(page)
                    return  # 검색으로 성공
            except Exception:
                pass  # 검색 실패 → 직접 URL 폴백

        # 직접 URL (폴백 or 30%)
        await page.goto(f"https://www.youtube.com/watch?v={video_id}")
        await random_delay(2.0, 4.0)
        await handle_ad(page)

    def _make_search_query(self, title: str) -> str:
        """영상 제목에서 자연스러운 검색어 생성."""
        # 제목에서 핵심 단어 2~4개 추출
        words = title.split()
        if len(words) <= 3:
            return title
        num_words = random.randint(2, min(4, len(words)))
        # 앞쪽 단어 위주 (사람은 제목 앞부분을 기억)
        selected = words[:num_words]
        return " ".join(selected)

    async def _find_video_in_results(self, page, video_id: str, timeout: int = 15) -> bool:
        """검색 결과에서 video_id에 해당하는 영상 클릭."""
        import time
        start = time.time()
        while time.time() - start < timeout:
            # 검색 결과의 링크들 확인
            links = page.locator("ytd-video-renderer a#video-title, ytd-video-renderer a#thumbnail")
            count = await links.count()
            for i in range(min(count, 20)):
                href = await links.nth(i).get_attribute("href")
                if href and video_id in href:
                    await links.nth(i).click()
                    await random_delay(2.0, 4.0)
                    return True
            # 스크롤해서 더 보기
            await page.keyboard.press("PageDown")
            await random_delay(1.0, 2.0)
        return False

    # ── handlers ─────────────────────────────────────────────

    async def _handle_comment(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """영상에 댓글 작성."""
        page = session.browser.page
        video_id = payload["video_id"]
        text = payload["text"]

        await self._navigate_to_video(session, video_id, payload.get("video_title", ""))

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

        await self._navigate_to_video(session, video_id, payload.get("video_title", ""))

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

        await self._navigate_to_video(session, video_id, payload.get("video_title", ""))

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

        await self._navigate_to_video(session, video_id, payload.get("video_title", ""))

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

        await self._navigate_to_video(session, video_id, payload.get("video_title", ""))

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

        await self._navigate_to_video(session, video_id, payload.get("video_title", ""))

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
        """유튜브 채널 설정 (이름, 아바타)."""
        page = session.browser.page
        channel_name = payload.get("channel_name", "")
        avatar_path = payload.get("avatar_path", "")

        # YouTube Studio 접속
        await page.goto("https://studio.youtube.com")
        await random_delay(3.0, 5.0)

        # 채널 커스터마이즈 페이지
        await page.goto("https://studio.youtube.com/channel/editing/basic")
        await random_delay(2.0, 4.0)

        # 채널 이름 변경
        if channel_name:
            try:
                name_input = page.locator("input#text-input[aria-label*='이름'], input#given-name-input, #name-container input").first
                await name_input.wait_for(timeout=10000)
                await name_input.click()
                await page.keyboard.press("Control+a")
                await random_delay(0.3, 0.5)
                await type_human(page, "input#text-input, input#given-name-input, #name-container input", channel_name)
                await random_delay(1.0, 2.0)
            except Exception as e:
                print(f"[ChannelSetup] Name change failed: {e}")

        # 아바타 업로드
        if avatar_path:
            try:
                # 프로필 사진 변경 버튼 찾기
                avatar_btn = page.locator("button:has-text('변경'), button:has-text('업로드'), #avatar-editor button").first
                await avatar_btn.click()
                await random_delay(1.0, 2.0)

                # 파일 업로드
                file_input = page.locator("input[type='file']").first
                await file_input.set_input_files(avatar_path)
                await random_delay(3.0, 5.0)

                # 완료/저장 버튼
                done_btn = page.locator("button:has-text('완료'), button:has-text('Done'), #done-button").first
                await done_btn.click()
                await random_delay(2.0, 3.0)
            except Exception as e:
                print(f"[ChannelSetup] Avatar upload failed: {e}")

        # 게시/저장 버튼
        try:
            publish_btn = page.locator("button:has-text('게시'), button:has-text('Publish'), #publish-button").first
            await publish_btn.click()
            await random_delay(2.0, 4.0)
        except Exception:
            pass

        return json.dumps({
            "action": "channel_setup",
            "channel_name": channel_name,
            "avatar_uploaded": bool(avatar_path),
        })
