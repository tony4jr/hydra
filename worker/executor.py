"""태스크 실행기 — 실제 브라우저 자동화 기반 핸들러 디스패치."""
import json
import os as _os
import random


def _parse_dry_run_flag() -> bool:
    return _os.getenv("HYDRA_WORKER_DRY_RUN", "").strip().lower() in (
        "1", "true", "yes",
    )


_DRY_RUN = _parse_dry_run_flag()

from hydra.browser.actions import (
    human_click,
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
from worker.comment_behavior import read_comments_before_posting
from worker.account_snapshot import AccountSnapshot
from hydra.browser.adspower import adspower


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
            "create_profile": self._handle_create_profile,
            "retire_profile": self._handle_retire_profile,
            "onboard": self._handle_onboard,
        }

    async def execute(self, task: dict, session: WorkerSession = None) -> str:
        """태스크 실행. 결과 JSON 문자열 반환."""
        # M2.1-1: DRY-RUN 모드 — 실 로직 건너뛰고 즉시 성공
        if _DRY_RUN:
            import asyncio
            await asyncio.sleep(0.5)
            return {
                "ok": True,
                "dry_run": True,
                "task_type": task.get("task_type"),
            }
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
                await human_click(search_btn.first)
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
                    await human_click(links.nth(i))
                    await random_delay(2.0, 4.0)
                    return True
            # 스크롤해서 더 보기
            await page.keyboard.press("PageDown")
            await random_delay(1.0, 2.0)
        return False

    # ── handlers ─────────────────────────────────────────────

    async def _generate_comment_text(self, payload: dict) -> str:
        """서버에서 AI 텍스트 생성 요청."""
        # Worker는 직접 AI를 호출하지 않음 — 서버에 요청
        # 서버의 content_agent가 transcript + persona로 생성
        import httpx
        from worker.config import config
        resp = httpx.post(
            f"{config.server_url}/api/generate-comment",
            headers={"X-Worker-Token": config.worker_token},
            json=payload,
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("text", "")
        return ""

    async def _handle_comment(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """영상에 댓글 작성."""
        page = session.browser.page
        video_id = payload.get("video_id", "")
        text = payload.get("text", "")

        # AI 자동 생성 (text가 없는 경우)
        if not text and payload.get("ai_generated") is not True:
            try:
                text = await self._generate_comment_text(payload)
            except Exception as e:
                print(f"  [Executor] AI generation failed, using fallback: {e}")
                text = ""

        if not text:
            return json.dumps({"action": "comment", "error": "no_text"})

        await self._navigate_to_video(session, video_id, payload.get("video_title", ""))

        # 영상 잠시 시청
        watch_sec = random.randint(5, 30)
        await watch_video(page, watch_sec)

        # 댓글 영역으로 스크롤
        await scroll_to_comments(page)

        # 기존 댓글 읽기 (사람처럼)
        await read_comments_before_posting(page)

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
        video_id = payload.get("video_id", "")
        target_comment_selector = payload.get("target_selector", "")
        text = payload.get("text", "")

        # AI 자동 생성 (text가 없는 경우)
        if not text and payload.get("ai_generated") is not True:
            try:
                text = await self._generate_comment_text(payload)
            except Exception as e:
                print(f"  [Executor] AI generation failed for reply: {e}")
                text = ""

        if not text:
            return json.dumps({"action": "reply", "error": "no_text"})

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

        # 타이밍 설정 — VPS 가 task payload 에 like_boost_config 를 동봉하면 사용,
        # 없으면 DEFAULTS. 워커는 로컬 DB 를 보지 않는다 (M1-12).
        from hydra.services.like_boost_config import DEFAULTS as _LB_DEFAULTS
        tc = dict(_LB_DEFAULTS)
        override = payload.get("like_boost_config") or {}
        if isinstance(override, dict):
            for k, v in override.items():
                if k in tc and v is not None:
                    tc[k] = v

        await self._navigate_to_video(session, video_id, payload.get("video_title", ""))

        # 영상 잠시 시청
        watch_sec = random.randint(tc["like_boost.watch_sec_min"], tc["like_boost.watch_sec_max"])
        await watch_video(page, watch_sec)

        # 댓글 영역으로 스크롤
        await scroll_to_comments(page)
        await random_delay(tc["like_boost.scroll_delay_min"], tc["like_boost.scroll_delay_max"])

        # 위장용 주변 댓글 좋아요
        camouflage_count = random.randint(
            tc["like_boost.surrounding_count_min"],
            tc["like_boost.surrounding_count_max"],
        )
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
                    await human_click(comment_buttons.nth(idx))
                    camouflaged += 1
                    await random_delay(
                        tc["like_boost.click_delay_min"],
                        tc["like_boost.click_delay_max"],
                    )
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
                    await human_click(target_like.first)
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

        session_context = payload.get("session_context", {})
        executor = WarmupExecutor(session, day=day, persona=persona, session_context=session_context)
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
                await human_click(sort_button.first)
                await random_delay(0.5, 1.0)
                newest = page.locator("tp-yt-paper-listbox a, yt-dropdown-menu a").nth(1)
                await human_click(newest)
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
                await human_click(name_input)
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
                await human_click(avatar_btn)
                await random_delay(1.0, 2.0)

                # 파일 업로드
                file_input = page.locator("input[type='file']").first
                await file_input.set_input_files(avatar_path)
                await random_delay(3.0, 5.0)

                # 완료/저장 버튼
                done_btn = page.locator("button:has-text('완료'), button:has-text('Done'), #done-button").first
                await human_click(done_btn)
                await random_delay(2.0, 3.0)
            except Exception as e:
                print(f"[ChannelSetup] Avatar upload failed: {e}")

        # 게시/저장 버튼
        try:
            publish_btn = page.locator("button:has-text('게시'), button:has-text('Publish'), #publish-button").first
            await human_click(publish_btn)
            await random_delay(2.0, 4.0)
        except Exception:
            pass

        return json.dumps({
            "action": "channel_setup",
            "channel_name": channel_name,
            "avatar_uploaded": bool(avatar_path),
        })

    async def _handle_create_profile(self, task, payload, session):
        """Create an AdsPower profile with the given fingerprint bundle.

        session is unused — this handler doesn't need a browser.
        """
        name = payload["profile_name"]
        group_id = payload.get("group_id", "0")
        remark = payload.get("remark", "")
        fingerprint_config = payload.get("fingerprint_payload") or {}

        profile_id = adspower.create_profile(
            name=name,
            group_id=group_id,
            fingerprint_config=fingerprint_config,
            remark=remark,
        )
        return json.dumps({
            "profile_id": profile_id,
            "account_id": payload["account_id"],
            "device_hint": payload.get("device_hint"),
        })

    async def _handle_retire_profile(self, task, payload, session):
        profile_id = payload["profile_id"]
        adspower.delete_profile(profile_id)
        return json.dumps({
            "retired_profile_id": profile_id,
            "reason": payload.get("reason", ""),
        })

    async def _handle_onboard(self, task, payload, session):
        """최초 온보딩 세션 — 로그인 + 언어 설정 + 자연 탐색 + 채널 커스터마이즈.

        worker/onboard_session.run_onboard_session 에 모든 로직 위임.
        session 은 이미 WorkerSession.start() 이후 상태 (ensure_safe_ip 완료).
        """
        from worker.onboard_session import run_onboard_session
        from hydra.core import crypto

        # AccountSnapshot 에서 기본 자격증명 복원 (payload override 우선).
        snap = None
        try:
            if task.get("account_snapshot"):
                snap = AccountSnapshot.from_payload(task)
        except Exception:
            snap = None

        persona = payload.get("persona") or (snap.persona if snap else {}) or {}
        if isinstance(persona, str):
            try:
                persona = json.loads(persona)
            except Exception:
                persona = {}

        email = payload.get("email") or (snap.gmail if snap else None)
        password = payload.get("password") or (snap.password if snap else None)
        recovery_email = payload.get("recovery_email") or (snap.recovery_email if snap else None)

        page = session.browser.page
        result = await run_onboard_session(
            page,
            persona=persona,
            email=email,
            password=password,
            recovery_email=recovery_email,
            duration_min_sec=payload.get("duration_min_sec", 120),
            duration_max_sec=payload.get("duration_max_sec", 300),
        )

        # OTP 시크릿 등록됐으면 결과 JSON 에 암호화하여 포함 — 서버가 complete 처리 시
        # Account.totp_secret 에 반영한다 (M1-12: 워커는 로컬 DB 접근 금지).
        encrypted_otp_secret = (
            crypto.encrypt(result.otp_secret) if result.otp_secret else None
        )

        # 본인 인증 잠금(7일 쿨다운) — 서버가 error 메시지의 magic string 을 보고
        # 계정 status 를 identity_challenge 로 전환 + 7일 cooldown 설정. 워커는
        # 더 이상 직접 DB 를 쓰지 않는다 (M1-12).
        if any("identity_challenge:locked" in f for f in result.critical_failures):
            raise RuntimeError(
                "onboard blocked by identity challenge — account marked for 7-day cooldown"
            )

        # critical_failures 있으면 예외 raise → worker 가 fail_task 로 처리 → retry_count
        # 증가 후 재스케줄. max_retries 초과 시 최종 failed. 이미 성공한 단계(google_name,
        # otp 등)는 DB 에 반영됐으니 재시도 시 idempotent 하게 skip 됨.
        if result.critical_failures:
            raise RuntimeError(
                f"onboard critical failure(s): {','.join(result.critical_failures)}"
                + (f" — {result.error}" if result.error else "")
            )

        return json.dumps({
            "ok": result.ok,
            "duration_sec": result.duration_sec,
            "actions": result.actions,
            "searched_query": result.searched_query,
            "otp_registered": bool(result.otp_secret),
            "encrypted_otp_secret": encrypted_otp_secret,
            "critical_failures": result.critical_failures,
            "error": result.error,
        }, ensure_ascii=False)
