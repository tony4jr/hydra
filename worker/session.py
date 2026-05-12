"""브라우저 세션 관리 — 프로필 열기/닫기/태스크 루프.

PR-A: WorkerSession 은 AccountSnapshot/WorkerConfig 로만 동작.
PR-C: phase reporter 통합 — start_phase / finish_phase 콜백으로 서버 보고.
"""
import asyncio
import json
import random
import uuid as _uuid
from datetime import datetime, UTC
from typing import Callable, Optional
from hydra.browser.driver import BrowserSession
from hydra.browser.actions import (
    human_click, random_delay, scroll_page, click_like_button, watch_video, handle_ad,
    set_speed_multiplier, set_typing_style, set_activity_multiplier,
)
from hydra.infra.ip_errors import IPRotationFailed
from hydra.protocol import AccountSnapshot, WorkerConfig
from hydra.protocol.phase_config import PhaseTimeout, get_phase_spec
from worker.ip_client import ensure_safe_ip_via_server, end_ip_log_via_server
from worker.youtube_habits import maybe_check_notifications, maybe_visit_own_channel


class WorkerSession:
    """한 계정의 브라우저 세션. 여러 태스크를 자연스럽게 실행."""

    def __init__(
        self,
        profile_id: str,
        account_id: int,
        device_id: str | None = None,
        account_snapshot: AccountSnapshot | None = None,
        worker_config: WorkerConfig | None = None,
        progress_reporter: Optional[Callable] = None,
        server_client=None,
    ):
        self.profile_id = profile_id
        self.account_id = account_id
        self.device_id = device_id
        self.account_snapshot = account_snapshot
        self.worker_config = worker_config or WorkerConfig()
        # PR-D: server client 주입 — ensure_safe_ip 가 server endpoint 호출.
        self.server_client = server_client
        self.browser: BrowserSession | None = None
        self.tasks_completed = 0
        _max_tasks = max(3, self.worker_config.max_tasks_per_session)
        _max_minutes = max(20, self.worker_config.max_session_minutes)
        self.max_tasks_per_session = random.randint(3, _max_tasks)
        self.max_session_minutes = random.randint(20, _max_minutes)
        self.started_at: datetime | None = None
        self.ip_log_id: int | None = None
        # PR-C: session 단위 UUID + progress reporter
        self.session_uuid = str(_uuid.uuid4())
        self.sequence_no = 0
        self.current_task_id: int | None = None
        self.current_phase: str = "session_start"
        self._report = progress_reporter or (lambda **kw: None)

    def _emit_phase(self, phase: str, message: str | None = None, is_change: bool = True) -> None:
        """phase 변경 시 서버 보고 + local 상태 갱신.

        is_change=False 면 heartbeat (서버측 UPDATE only, history INSERT 안 함).
        """
        if is_change:
            self.current_phase = phase
            self.sequence_no += 1
        try:
            self._report(
                session_uuid=self.session_uuid,
                task_id=self.current_task_id,
                attempt_no=0,
                sequence_no=self.sequence_no,
                phase=phase,
                message=message,
                is_phase_change=is_change,
            )
        except Exception:
            pass

    async def run_phase(self, phase: str, coro):
        """PR-E: phase 별 wait_for timeout + phase-tagged 에러.

        - emit phase 진입
        - asyncio.wait_for(coro, timeout=phase_spec.timeout_sec)
        - timeout 시 PhaseTimeout(phase, elapsed, threshold, policy) raise

        호출자가 PhaseTimeout 잡아서 정책별 처리 (reschedule/fail/unknown).
        """
        spec = get_phase_spec(phase)
        self._emit_phase(phase)
        start = datetime.now(UTC)
        try:
            return await asyncio.wait_for(coro, timeout=spec.timeout_sec)
        except asyncio.TimeoutError:
            elapsed = (datetime.now(UTC) - start).total_seconds()
            err = PhaseTimeout(phase, elapsed, spec.timeout_sec, spec.policy)
            self._emit_phase(phase, message=err.to_error_message())
            raise err

    @property
    def account(self):
        """Back-compat: 일부 코드가 session.account.persona 등에 접근. snapshot 으로 노출."""
        return self.account_snapshot

    async def start(self, db=None) -> bool:
        """세션 시작: IP 안전 확인 → 프로필 열기 → YouTube 접속.

        PR-C: 각 step 마다 phase 보고.
        PR-E: 각 step asyncio.wait_for(timeout). PhaseTimeout 발생 시
              호출자가 정책(reschedule/fail/unknown) 처리.

        IPRotationFailed from ensure_safe_ip propagates so the caller can
        reschedule the task.
        """
        self._emit_phase("session_start")
        try:
            # persona 기반 세팅 — 매우 빠른 동작이라 wait_for 안 씀.
            try:
                snap = self.account_snapshot
                if snap is not None and snap.persona:
                    p = json.loads(snap.persona)
                    set_speed_multiplier(p.get("speed_multiplier") or random.uniform(0.6, 1.8))
                    set_typing_style(p.get("typing_style") or random.choice(["typist", "typist", "paster"]))
                    set_activity_multiplier(p.get("activity_multiplier") or random.uniform(0.6, 1.5))
                else:
                    set_speed_multiplier(random.uniform(0.6, 1.8))
                    set_typing_style(random.choice(["typist", "typist", "paster"]))
                    set_activity_multiplier(random.uniform(0.6, 1.5))
            except Exception:
                set_speed_multiplier(random.uniform(0.6, 1.8))
                set_typing_style("typist")
                set_activity_multiplier(1.0)

            if self.server_client is not None and self.account_snapshot is not None:
                # PR-D: server endpoint 호출 — 워커 로컬 SQLite IpLog 안 씀.
                self.ip_log_id = await self.run_phase(
                    "ip_rotate",
                    ensure_safe_ip_via_server(
                        self.server_client,
                        account_id=self.account_id,
                        adb_device_id=self.worker_config.adb_device_id or self.device_id,
                        cooldown_minutes=self.worker_config.ip_cooldown_minutes,
                    ),
                )

            self.browser = BrowserSession(self.profile_id)
            await self.run_phase("adspower_open", self.browser.start())

            if self.browser.page is not None:
                await self.run_phase("video_goto", self.browser.goto("https://www.youtube.com"))
                await random_delay(2.0, 4.0)

            self.started_at = datetime.now(UTC)
            self._emit_phase("wait", message="session active")
            return True
        except IPRotationFailed:
            self._emit_phase("ip_rotate", message="failed", is_change=True)
            raise
        except PhaseTimeout:
            # PR-E: timeout 은 호출자가 정책별 처리. 그대로 raise.
            await self.close()
            raise
        except Exception as e:
            # PR-Debug: 자세한 메시지 stdout + server worker_error 로 보고.
            # 이전엔 type 만 phase event 에 들어가서 디버깅 어려웠음.
            err_msg = f"{type(e).__name__}: {e}"
            print(f"[Session] Failed to start: {err_msg}")
            self._emit_phase("session_end", message=f"start_failed: {err_msg[:200]}")
            # server 로 worker_error 보고 — admin gauge / kill switch 시그널.
            if self.server_client is not None:
                try:
                    import traceback as _tb
                    self.server_client.report_error(
                        kind="session_start_fail",
                        message=err_msg[:500],
                        traceback=_tb.format_exc(),
                        context={
                            "account_id": self.account_id,
                            "profile_id": self.profile_id,
                            "phase": self.current_phase,
                        },
                    )
                except Exception:
                    pass
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

        num_shorts = random.randint(2, 10)  # 15 → 10 (데이터 절감)
        for _ in range(num_shorts):
            # full_watch 가중치 20 → 10, skip ↑ (데이터 절감)
            behavior = random.choices(
                ["skip", "short_watch", "full_watch", "rewatch"],
                weights=[55, 30, 10, 5],
            )[0]

            if behavior == "skip":
                await random_delay(1.0, 2.0)
            elif behavior == "short_watch":
                await random_delay(3.0, 10.0)
            elif behavior == "full_watch":
                await random_delay(15.0, 30.0)  # 60 → 30
            elif behavior == "rewatch":
                await random_delay(15.0, 25.0)  # 40 → 25
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
            await human_click(thumbnails.nth(idx))
            await random_delay(2.0, 4.0)
            await handle_ad(page)
            duration = random.randint(10, 45)  # 180 → 45 (데이터 절감)
            await watch_video(page, duration)

    async def capture_screenshot(self) -> bytes | None:
        """현재 활성 페이지 PNG 캡처. 실패 시 None. 절대 예외 propagate X.

        실 YouTube 태스크 실패 시 executor 가 호출 → report_error_with_screenshot
        으로 서버 업로드.
        """
        try:
            if not self.browser or not self.browser.page:
                return None
            return await self.browser.page.screenshot(
                type="png", full_page=False, timeout=5000,
            )
        except Exception:
            return None

    async def close(self):
        """세션 종료."""
        # PR-D: server-side IpLog end 호출 (best-effort).
        if self.server_client is not None and self.ip_log_id is not None:
            try:
                end_ip_log_via_server(self.server_client, self.ip_log_id)
            except Exception:
                pass
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
