"""Worker 메인 앱 — heartbeat + task fetch + execute loop."""
import asyncio
import time
import signal
import sys
from collections import defaultdict
from datetime import datetime, UTC
from worker.config import config
from worker.client import ServerClient
from worker.executor import TaskExecutor


class WorkerApp:
    def __init__(self):
        self.client = ServerClient()
        self.executor = TaskExecutor()
        self.running = True
        self.last_heartbeat = None
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, *args):
        print("\n[Worker] Shutting down...")
        self.running = False

    def run(self):
        """메인 루프."""
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
                self._tick()
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[Worker] Error in main loop: {e}")
                time.sleep(5)

        self.client.close()
        print("[Worker] Stopped")

    def _tick(self):
        """한 사이클: heartbeat -> fetch -> execute (세션 기반)."""
        now = datetime.now(UTC)

        # Heartbeat
        if self.last_heartbeat is None or (now - self.last_heartbeat).total_seconds() >= config.heartbeat_interval:
            try:
                self.client.heartbeat()
                self.last_heartbeat = now
            except Exception as e:
                print(f"[Worker] Heartbeat failed: {e}")

        # Fetch tasks & group by account
        try:
            tasks = self.client.fetch_tasks()
            if tasks:
                tasks_by_account = defaultdict(list)
                for task in tasks:
                    key = (task.get("profile_id", ""), task.get("account_id", 0))
                    tasks_by_account[key].append(task)

                for (profile_id, account_id), account_tasks in tasks_by_account.items():
                    asyncio.run(
                        self._execute_session(account_tasks, profile_id, account_id)
                    )
        except Exception as e:
            print(f"[Worker] Task fetch failed: {e}")

        time.sleep(config.task_fetch_interval)

    async def _execute_session(self, tasks: list, profile_id: str, account_id: int):
        """한 계정의 세션 — 여러 태스크를 자연스럽게 실행."""
        from worker.session import WorkerSession

        session = WorkerSession(
            profile_id, account_id, device_id=config.adb_device_id
        )

        if not await session.start():
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
            await session.close()


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
