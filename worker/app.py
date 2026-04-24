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

    async def _async_run(self):
        """Persistent async event loop for Playwright compatibility."""
        print(f"[Worker] Starting v{config.worker_version}")
        print(f"[Worker] Server: {config.server_url}")

        # 초기 연결 확인
        try:
            self.client.heartbeat()
            print("[Worker] Connected to server")
        except Exception as e:
            print(f"[Worker] Failed to connect: {e}")
            sys.exit(1)

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
        except Exception as e:
            # sleep 없이 return 하면 while 루프가 즉시 재진입 → 초당 수십 번 spam.
            # 네트워크 일시 장애 시 exponential backoff 대신 heartbeat_interval 대기.
            print(f"[Worker] Heartbeat failed: {e}")
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
            token_hash = hashlib.sha256(config.worker_token.encode()).hexdigest()
            worker = db.query(Worker).filter(Worker.token_hash == token_hash).first()

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
