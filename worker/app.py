"""Worker 메인 앱 — heartbeat + task fetch + execute loop.

PR-A: 워커는 stateless executor. 서버가 보낸 TaskEnvelope 만 사용하고
local SQLite 의 Account/Worker 테이블을 lookup 하지 않는다. 로컬 DB 는
IpLog 같은 워커 측 쓰기 로그용으로만 남는다.
"""
import asyncio
import signal
import sys
from collections import defaultdict
from datetime import datetime, UTC
from worker.config import config
from worker.client import ServerClient
from worker.executor import TaskExecutor
from worker.log_shipper import install_log_shipping
from hydra.protocol import AccountSnapshot, TaskEnvelope, WorkerConfig


def _envelope_from_task(task: dict) -> TaskEnvelope | None:
    """Parse envelope from server response.

    Prefers the new `envelope` field. Falls back to legacy flat shape
    (id + task_type + account_snapshot) so workers can roll out before
    server. Returns None if neither shape is parseable — caller should
    treat that as a server contract violation and fail the task.
    """
    env = task.get("envelope")
    if env:
        try:
            return TaskEnvelope.model_validate(env)
        except Exception as e:
            # PR-A B++: pydantic ValidationError 가 input data 를 메시지에 넣을 수 있으므로
            # 클래스명만 노출. encrypted_password 같은 secret 이 print 로 새지 않게.
            print(f"[Worker] envelope parse failed ({type(e).__name__}), trying legacy shape")
    snap = task.get("account_snapshot")
    if not snap or task.get("id") is None or not task.get("task_type"):
        return None
    try:
        return TaskEnvelope(
            task_id=task["id"],
            task_type=task["task_type"],
            priority=task.get("priority") or "normal",
            payload=task.get("payload"),
            account=AccountSnapshot.model_validate(snap),
            worker_config=WorkerConfig(),
        )
    except Exception as e:
        print(f"[Worker] legacy envelope construction failed ({type(e).__name__})")
        return None


class WorkerApp:
    def __init__(self):
        self.client = ServerClient()
        self.executor = TaskExecutor()
        self.running = True
        self.last_heartbeat = None
        self._current_task_id = None
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, *args):
        print("\n[Worker] Shutting down...")
        self.running = False

    def _worker_id_cache(self) -> int:
        """heartbeat 응답에서 받은 worker id 캐시. 없으면 -1 (서버가 token 으로 식별).

        Note: heartbeat 응답에 worker_id 가 포함되지 않을 수도 있어 None 안전.
        """
        return getattr(self, "_cached_worker_id", -1)

    def run(self):
        """메인 루프 — 단일 async 이벤트 루프로 실행."""
        asyncio.run(self._async_run())

    # PR-A: _sync_local_db 제거 — 워커는 envelope 만으로 작동. 서버 = SoT.
    # 로컬 DB 는 IpLog 등 워커 측 쓰기 로그 전용 (PR-B 에서 IpLog 도 서버화 예정).

    async def _async_run(self):
        """Persistent async event loop for Playwright compatibility."""
        print(f"[Worker] Starting v{config.worker_version}")
        print(f"[Worker] Server: {config.server_url}")

        # Python 로그(WARNING+) 와 미처 잡히지 않은 예외를 서버 worker_errors 로 전송
        install_log_shipping(self.client)

        # 초기 연결 확인
        try:
            self.client.heartbeat()
            print("[Worker] Connected to server")
        except Exception as e:
            print(f"[Worker] Failed to connect: {e}")
            sys.exit(1)

        # PR-A: 로컬 DB sync 불필요. 워커는 TaskEnvelope (서버 응답) 만 사용.
        # 서버가 보내는 envelope.account / envelope.worker_config 만으로 동작.

        while self.running:
            try:
                await self._async_tick()
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[Worker] Error in main loop: {e}")
                await asyncio.sleep(5)

        self.client.close()
        print("[Worker] Stopped")

    async def _async_tick(self):
        """한 사이클: heartbeat -> fetch -> execute (세션 기반)."""
        now = datetime.now(UTC)

        # Heartbeat (M1-11: 매 tick 마다 호출 — paused/version 반응 위함)
        hb: dict = {}
        try:
            hb = self.client.heartbeat() or {}
            self.last_heartbeat = now
            # 서버가 푸시한 AdsPower API 키를 프로세스 env 에 반영 —
            # 워커마다 키가 다를 수 있고 관리는 어드민 UI 에서 중앙집중.
            import os as _os
            import logging as _logging
            _hb_log = _logging.getLogger("hydra.worker.heartbeat_debug")
            # Codex 5/12 P1 — server 가 보낸 key 도 정규화. trailing whitespace /
            # 따옴표 가 secrets storage 거치며 섞이는 경우 Bearer 가 invalid 됨.
            from hydra.browser.adspower import _normalize_api_key
            srv_key_raw = hb.get("adspower_api_key")
            srv_key = _normalize_api_key(srv_key_raw) if srv_key_raw else None
            srv_key_len = len(srv_key) if isinstance(srv_key, str) else -1
            env_key = _os.environ.get("ADSPOWER_API_KEY", "")
            _hb_log.warning(
                f"adspower_key_debug: srv_present={srv_key is not None} "
                f"srv_truthy={bool(srv_key)} srv_len={srv_key_len} "
                f"env_len={len(env_key)} hb_keys={sorted(hb.keys())[:15]}"
            )
            if srv_key and _os.environ.get("ADSPOWER_API_KEY") != srv_key:
                _os.environ["ADSPOWER_API_KEY"] = srv_key
                _hb_log.warning(f"adspower_key_debug: env updated, new_len={len(srv_key)}")

            # Verbose 디버그 모드 — 어드민이 켜면 INFO+ 로그가 서버로 push 됨.
            from worker.log_shipper import set_verbose_mode
            set_verbose_mode(bool(hb.get("verbose_mode")))

            # 어드민이 발행한 원격 명령 처리 (heartbeat 응답에 같이 옴)
            pending = hb.get("pending_commands") or []
            if pending:
                from worker.commands import execute_command
                for cmd in pending:
                    try:
                        await execute_command(self.client, cmd)
                    except SystemExit:
                        raise  # restart/update_now 는 그대로 빠짐
                    except Exception as e:
                        print(f"[Worker] command {cmd.get('id')} crash: {e}")
        except Exception as e:
            # 서버 재시작/일시 장애 시 빠르게 복구. 30초가 아닌 5초 retry —
            # systemctl restart hydra-server 가 5~10초 다운인데 30초 기다리면
            # 서버가 stale_timeout (90s) 으로 offline 마킹할 위험.
            # 5초 retry 면 서버 살아나는 즉시 워커 자동 재연결.
            print(f"[Worker] Heartbeat failed: {e}")
            import traceback as _tb
            self.client.report_error(
                kind="heartbeat_fail",
                message=f"{type(e).__name__}: {e}",
                traceback=_tb.format_exc(),
                context={"server_url": config.server_url},
            )
            await asyncio.sleep(5)
            return

        # 본질 fix: paused (전역 kill switch) 면 fetch 만 막고 maybe_update 는 가야 함.
        # 이전 코드는 paused 시 update 도 같이 skip → 새 코드 영원히 못 받는 deadlock.
        # 순서: maybe_update 먼저 → paused 체크 후 fetch skip.

        # M1-11: current_version 감지 → updater (idle 일 때만 업데이트)
        try:
            from worker.updater import maybe_update
            is_idle = getattr(self, "_current_task_id", None) is None
            maybe_update(
                server_version=hb.get("current_version", ""),
                local_version=config.worker_version,
                is_idle=is_idle,
            )
        except SystemExit:
            raise
        except Exception as e:
            print(f"[Worker] updater error: {e}")

        # paused (server_config.paused) 면 fetch 스킵 — update 는 위에서 이미 처리.
        if hb.get("paused"):
            await asyncio.sleep(config.task_fetch_interval)
            return

        # Fetch tasks & group by envelope (canonical source).
        # PR-A B++: flat 필드(adspower_profile_id, account_id) 로 그룹핑하면
        # envelope 과 불일치 시 flat 기준으로 세션이 열려 envelope 의 보장이 깨짐.
        # envelope 우선으로 그룹핑하고, 파싱 실패 task 는 즉시 fail 처리.
        try:
            tasks = self.client.fetch_tasks()
            if tasks:
                tasks_by_account: defaultdict = defaultdict(list)
                for task in tasks:
                    env = _envelope_from_task(task)
                    if env is None:
                        try:
                            self.client.fail_task(task["id"], "envelope_missing")
                        except Exception:
                            pass
                        continue
                    key = (env.account.adspower_profile_id or "", env.account.id)
                    # task dict 에 parsed envelope 동봉 — 하위에서 재파싱 안 하게.
                    task["_envelope"] = env
                    tasks_by_account[key].append(task)

                for (profile_id, account_id), account_tasks in tasks_by_account.items():
                    await self._execute_session(account_tasks, profile_id, account_id)
        except Exception as e:
            print(f"[Worker] Task fetch failed: {e}")
            import traceback as _tb
            self.client.report_error(
                kind="fetch_fail",
                message=f"{type(e).__name__}: {e}",
                traceback=_tb.format_exc(),
            )

        await asyncio.sleep(config.task_fetch_interval)

    async def _execute_session(self, tasks: list, profile_id: str, account_id: int):
        """한 계정의 세션 — 여러 태스크를 자연스럽게 실행."""
        # M2.1 DRY-RUN: WorkerSession/AdsPower/Playwright 를 완전히 우회하고
        # 각 태스크를 즉시 complete 처리. executor 내부 DRY-RUN 가드보다 먼저.
        import os
        if os.getenv("HYDRA_WORKER_DRY_RUN", "").strip().lower() in ("1", "true", "yes"):
            import asyncio
            for task in tasks:
                task_id = task["id"]
                task_type = task.get("task_type", "?")
                print(f"[Worker DRY-RUN] complete task {task_id} ({task_type})")
                self._current_task_id = task_id
                await asyncio.sleep(0.5)
                try:
                    self.client.complete_task(task_id, result='{"dry_run":true}')
                except Exception as e:
                    print(f"[Worker DRY-RUN] complete failed for {task_id}: {e}")
                self._current_task_id = None
            return

        from worker.session import WorkerSession
        from hydra.infra.ip_errors import IPRotationFailed
        from hydra.protocol.phase_config import PhaseTimeout

        # PR-A B++: envelope 은 위 그룹핑에서 이미 파싱·검증된 상태로 task["_envelope"] 에 동봉.
        first_envelope = tasks[0].get("_envelope") if tasks else None
        if first_envelope is None:
            # 호출 경로상 도달 불가 (그룹핑이 envelope 없는 task 를 걸러냄). 방어 코드.
            print("[Worker] FATAL: missing parsed envelope on task.")
            for task in tasks:
                try:
                    self.client.fail_task(task["id"], "envelope_missing")
                except Exception:
                    pass
            return
        account_snapshot = first_envelope.account
        worker_config = first_envelope.worker_config

        # PR-D: 워커 측 로컬 DB 사용 X. IpLog 는 server endpoint 호출.
        try:
            # PR-C: progress reporter — server 보고 콜백.
            def _progress_cb(**kw):
                self.client.report_progress(**kw)

            session = WorkerSession(
                profile_id, account_id,
                device_id=worker_config.adb_device_id or config.adb_device_id,
                account_snapshot=account_snapshot,
                worker_config=worker_config,
                progress_reporter=_progress_cb,
                server_client=self.client,  # PR-D: IpLog server-side via API
            )
            # PR-C: WorkerSession 등록 (heartbeat 시작).
            self.client.session_heartbeat(
                session_uuid=session.session_uuid,
                worker_id=self._worker_id_cache(),
                account_id=account_id,
                status="active",
            )

            def _close_session_failed(reason: str):
                """세션 시작 실패 경로 공통 처리 — worker_sessions status='failed'."""
                try:
                    self.client.session_heartbeat(
                        session_uuid=session.session_uuid,
                        worker_id=self._worker_id_cache(),
                        account_id=account_id,
                        status="failed",
                    )
                except Exception:
                    pass

            try:
                # PR-D: db 인자 제거. session 내부에서 server_client 로 IpLog 처리.
                started = await session.start()
            except IPRotationFailed as ipre:
                # IP rotation failed — reschedule + worker_error 보고 (PR-Kill 시그널).
                # 어제 ADB 미연결로 무한 reschedule 루프 사고 후, IPRotationFailed 도
                # worker_error 에 기록하고 phase_timeout 류 시그널로 카운트.
                ip_msg = f"ip_rotation_failed: {ipre}"
                print(f"[Worker] {ip_msg}")
                _close_session_failed("ip_rotation_failed")
                try:
                    self.client.report_error(
                        kind="phase_timeout",  # PR-Kill suspend_guard 가 카운트하는 kind
                        message=ip_msg[:200],
                        context={
                            "phase": "ip_rotate",
                            "reason": "ip_rotation_failed",
                            "task_count": len(tasks),
                            "profile_id": profile_id,
                            "account_id": account_id,
                        },
                    )
                except Exception:
                    pass
                for task in tasks:
                    try:
                        self.client.reschedule_task(task["id"], reason="ip_rotation_failed")
                    except Exception as e:
                        print(f"[Worker] Failed to reschedule task {task['id']}: {e}")
                return
            except PhaseTimeout as pt:
                # PR-E: phase timeout — 정책별 처리.
                # reschedule/unknown → reschedule (워커-환경 책임).
                # fail → task fail (의도된 실패 — 현재 start phase 들엔 fail 없음).
                err_msg = pt.to_error_message()
                print(f"[Worker] {err_msg}")
                # worker_error 보고 (phase 정보 포함).
                try:
                    self.client.report_error(
                        kind="phase_timeout",
                        message=err_msg,
                        context={
                            "phase": pt.phase,
                            "elapsed_sec": pt.elapsed_sec,
                            "threshold_sec": pt.threshold_sec,
                            "policy": pt.policy,
                            "task_count": len(tasks),
                            "profile_id": profile_id,
                            "account_id": account_id,
                        },
                    )
                except Exception:
                    pass
                _close_session_failed(err_msg)
                for task in tasks:
                    try:
                        if pt.policy == "fail":
                            self.client.fail_task(task["id"], err_msg)
                        else:
                            self.client.reschedule_task(task["id"], reason=err_msg)
                    except Exception:
                        pass
                return

            if not started:
                _close_session_failed("session_start_failed")
                for task in tasks:
                    try:
                        self.client.fail_task(task["id"], "Session start failed")
                    except Exception:
                        pass
                return

            try:
                for task in tasks:
                    if not await session.should_continue():
                        print(f"[Worker] Session limit reached, skipping remaining tasks")
                        break

                    if session.tasks_completed > 0:
                        await session.do_natural_browsing()

                    task_id = task["id"]
                    task_type = task["task_type"]
                    print(f"[Worker] Executing task {task_id} ({task_type})")

                    self._current_task_id = task_id
                    session.current_task_id = task_id
                    try:
                        try:
                            # PR-E: executor.execute() 전체를 phase=compose timeout 으로 래핑.
                            # 본문 hang (캡차, AI gen 무한 대기, playwright deadlock) 방지.
                            result = await session.run_phase(
                                "compose",
                                self.executor.execute(task, session),
                            )
                            session._emit_phase("submit", message=f"task={task_id} done")
                            self.client.complete_task(task_id, result)
                            session.tasks_completed += 1
                            print(f"[Worker] Task {task_id} completed")
                        except PhaseTimeout as pt:
                            # PR-E: task 실행 중 phase timeout.
                            err_msg = pt.to_error_message()
                            print(f"[Worker] Task {task_id} {err_msg}")
                            try:
                                self.client.report_error(
                                    kind="phase_timeout",
                                    message=err_msg,
                                    context={
                                        "task_id": task_id,
                                        "task_type": task_type,
                                        "phase": pt.phase,
                                        "elapsed_sec": pt.elapsed_sec,
                                        "threshold_sec": pt.threshold_sec,
                                        "policy": pt.policy,
                                    },
                                )
                            except Exception:
                                pass
                            try:
                                if pt.policy == "fail":
                                    self.client.fail_task(task_id, err_msg)
                                else:
                                    self.client.reschedule_task(task_id, reason=err_msg)
                            except Exception:
                                pass
                        except Exception as e:
                            error = str(e)
                            print(f"[Worker] Task {task_id} failed: {error}")
                            try:
                                self.client.fail_task(task_id, error)
                            except Exception:
                                pass
                            # 스크린샷 캡처 + 서버 업로드 (실 YouTube 실패 디버깅)
                            try:
                                import traceback as _tb
                                shot = await session.capture_screenshot()
                                if shot:
                                    self.client.report_error_with_screenshot(
                                        kind="task_fail",
                                        message=f"{type(e).__name__}: {error}",
                                        screenshot_bytes=shot,
                                        traceback=_tb.format_exc(),
                                        context={
                                            "task_id": task_id,
                                            "task_type": task_type,
                                            "account_id": account_id,
                                            "profile_id": profile_id,
                                        },
                                    )
                            except Exception:
                                pass
                    finally:
                        self._current_task_id = None
                        session.current_task_id = None
            finally:
                # PR-C: 세션 종료 phase + heartbeat status=ended.
                try:
                    session._emit_phase("session_end")
                    self.client.session_heartbeat(
                        session_uuid=session.session_uuid,
                        worker_id=self._worker_id_cache(),
                        account_id=account_id,
                        status="ended",
                    )
                except Exception:
                    pass
                await session.close()
        finally:
            # PR-D: 워커는 더 이상 로컬 DB 세션 안 만듦. 정리 필요 없음.
            pass


def _ensure_local_schema():
    """PR-D 이후 no-op. WorkerCommand "ensure_schema" 호환성만 유지.

    워커는 더 이상 로컬 SQLite 안 씀 (IpLog 도 서버화). schema 생성 불필요.
    """
    print("[Worker] PR-D: local DB removed — schema ensure no-op")


def main():
    """진입점."""
    # 본질 fix: Windows console 의 기본 codec (cp949 한국어) 가 em-dash/이모지
    # 같은 unicode 못 인코드 → print 에서 UnicodeEncodeError → 상위 흐름 차단
    # (예: restart command 가 print 단계에서 죽고 sys.exit 안 도달).
    # 모든 worker 코드에 ASCII-only print 강제하기 어려우니 stream 자체를
    # utf-8 로 reconfigure + errors='replace' 로 안전망.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # Slice 2.4 follow-up — desktop worker 임을 명시. commands.py 의 desktop_*
    # 분기가 이 marker 를 보고 admin_agent 아니면 거부.
    import os as _os
    _os.environ.setdefault("HYDRA_PROCESS_ROLE", "desktop_worker")

    config.load()
    if not config.worker_token:
        print("[Worker] Error: HYDRA_WORKER_TOKEN not set")
        print("Set via environment variable or run setup first")
        sys.exit(1)
    # 진짜 본질 fix: Task Scheduler 자가 등록. updater.py 가 update 후 sys.exit
    # 하면 Task Scheduler 가 재기동 — 미등록이면 워커가 영원히 죽음 (root cause
    # of "사용자가 매번 워커 PC 가서 cmd 띄운" 야간 패턴).
    try:
        from worker.task_register import ensure_registered
        ensure_registered()
    except Exception as e:
        print(f"[Worker] task_register import 실패: {e}")
    # PR-D: _ensure_local_schema 호출 불필요. 워커는 SessionLocal() 자체 안 만듦.
    app = WorkerApp()
    app.run()


if __name__ == "__main__":
    main()
