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
from hydra.db.session import SessionLocal
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
            srv_key = hb.get("adspower_api_key")
            if srv_key and _os.environ.get("ADSPOWER_API_KEY") != srv_key:
                _os.environ["ADSPOWER_API_KEY"] = srv_key

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

        # M1-11: paused 면 fetch 스킵
        if hb.get("paused"):
            await asyncio.sleep(config.task_fetch_interval)
            return

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

        db = SessionLocal()  # IpLog 쓰기용 — 워커 측 로그. PR-B 에서 서버화 예정.
        try:
            session = WorkerSession(
                profile_id, account_id,
                device_id=worker_config.adb_device_id or config.adb_device_id,
                account_snapshot=account_snapshot,
                worker_config=worker_config,
            )

            try:
                started = await session.start(db=db)
            except IPRotationFailed:
                # IP rotation failed — reschedule each task via server API
                print(f"[Worker] IP rotation failed, rescheduling {len(tasks)} task(s)")
                for task in tasks:
                    try:
                        self.client.reschedule_task(task["id"], reason="ip_rotation_failed")
                    except Exception as e:
                        print(f"[Worker] Failed to reschedule task {task['id']}: {e}")
                return

            if not started:
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
                    try:
                        try:
                            result = await self.executor.execute(task, session)
                            self.client.complete_task(task_id, result)
                            session.tasks_completed += 1
                            print(f"[Worker] Task {task_id} completed")
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
            finally:
                await session.close()
        finally:
            db.close()


def main():
    """진입점."""
    config.load()
    if not config.worker_token:
        print("[Worker] Error: HYDRA_WORKER_TOKEN not set")
        print("Set via environment variable or run setup first")
        sys.exit(1)
    app = WorkerApp()
    app.run()


if __name__ == "__main__":
    main()
