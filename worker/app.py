"""Worker 메인 앱 — heartbeat + task fetch + execute loop."""
import asyncio
import hashlib
import signal
import sys
from collections import defaultdict
from datetime import datetime, UTC
from worker.config import config
from worker.client import ServerClient
from worker.executor import TaskExecutor
from worker.log_shipper import install_log_shipping
from hydra.db.session import SessionLocal
from hydra.db.models import Account, Worker


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

    def _sync_local_db(self):
        """Sync accounts + workers from server to local SQLite.

        Runs at worker startup. Required because:
          - WorkerSession.start() calls ensure_safe_ip(db, account, worker),
            which queries the LOCAL db for those rows.
          - Without sync, queries return None → ensure_safe_ip is silently
            skipped → 1-account-1-IP invariant is violated.

        Uses upsert (insert-or-update by id) so this is safe to call repeatedly
        and won't trip foreign-key constraints from existing related rows
        (ProfileLock, IpLog, Task).
        """
        from datetime import datetime as _dt
        from sqlalchemy import DateTime, Boolean
        from hydra.db.session import SessionLocal as _SL
        from hydra.db.models import Account, Worker

        try:
            data = self.client.sync_data()
        except Exception as e:
            print(f"[Worker] sync_data fetch failed: {e}")
            return
        accs = data.get("accounts", [])
        wkrs = data.get("workers", [])

        def _coerce(model_cls, k, v):
            if v is None:
                return None
            col = model_cls.__table__.columns.get(k)
            if col is None:
                return v
            if isinstance(col.type, DateTime) and isinstance(v, str):
                try:
                    return _dt.fromisoformat(v)
                except Exception:
                    return None
            if isinstance(col.type, Boolean) and isinstance(v, (int, str)):
                return bool(v) if not isinstance(v, str) else v.lower() in ("true", "1")
            return v

        db = _SL()
        try:
            acc_cols = {c.name for c in Account.__table__.columns}
            wkr_cols = {c.name for c in Worker.__table__.columns}
            for a in accs:
                fields = {k: _coerce(Account, k, v) for k, v in a.items() if k in acc_cols}
                existing = db.get(Account, fields["id"]) if fields.get("id") else None
                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                else:
                    db.add(Account(**fields))
            for w in wkrs:
                fields = {k: _coerce(Worker, k, v) for k, v in w.items() if k in wkr_cols}
                existing = db.get(Worker, fields["id"]) if fields.get("id") else None
                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                else:
                    db.add(Worker(**fields))
            db.commit()
            print(f"[Worker] synced local DB: {len(accs)} accounts, {len(wkrs)} workers")
        finally:
            db.close()

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

        # Account/Worker 로컬 DB 동기화 — ensure_safe_ip 가 정상 동작하려면
        # 로컬 DB 에 account + worker rows 가 있어야 함 (없으면 IP rotation skip).
        try:
            self._sync_local_db()
        except Exception as e:
            print(f"[Worker] WARNING: local DB sync failed: {e}")

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
            # sleep 없이 return 하면 while 루프가 즉시 재진입 → 초당 수십 번 spam.
            # 네트워크 일시 장애 시 exponential backoff 대신 heartbeat_interval 대기.
            print(f"[Worker] Heartbeat failed: {e}")
            # 리포트 (서버 도달 가능하면) — heartbeat 자체가 실패한 시점이라
            # report_error 도 실패할 수 있지만 내부에서 조용히 삼킴.
            import traceback as _tb
            self.client.report_error(
                kind="heartbeat_fail",
                message=f"{type(e).__name__}: {e}",
                traceback=_tb.format_exc(),
                context={"server_url": config.server_url},
            )
            await asyncio.sleep(config.heartbeat_interval)
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

        # Fetch tasks & group by account
        try:
            tasks = self.client.fetch_tasks()
            if tasks:
                tasks_by_account = defaultdict(list)
                for task in tasks:
                    key = (task.get("adspower_profile_id") or "", task.get("account_id", 0))
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

        db = SessionLocal()
        try:
            account = db.get(Account, account_id) if account_id else None
            token_sha256 = hashlib.sha256(config.worker_token.encode()).hexdigest()
            worker = (
                db.query(Worker).filter(Worker.token_sha256 == token_sha256).first()
                or db.query(Worker).filter(Worker.token_hash == token_sha256).first()
            )
            if worker is None:
                # Fail-secure: refuse task execution rather than silent IP-rotation skip
                # (anti-detection rule: 1 account = 1 IP, never run without rotation guard)
                print(f"[Worker] FATAL: worker row not found in local DB (token mismatch). "
                      f"Refusing tasks to preserve IP rotation invariant.")
                for task in tasks:
                    try:
                        self.client.fail_task(task["id"], "local_worker_row_missing")
                    except Exception:
                        pass
                return
            if account is None and account_id:
                print(f"[Worker] FATAL: account_id={account_id} not in local DB. Refusing task.")
                for task in tasks:
                    try:
                        self.client.fail_task(task["id"], "local_account_row_missing")
                    except Exception:
                        pass
                return

            session = WorkerSession(
                profile_id, account_id,
                device_id=config.adb_device_id,
                account=account,
                worker=worker,
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
