"""Worker 메인 앱 — heartbeat + task fetch + execute loop."""
import time
import signal
import sys
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
        """한 사이클: heartbeat -> fetch -> execute."""
        now = datetime.now(UTC)

        # Heartbeat
        if self.last_heartbeat is None or (now - self.last_heartbeat).total_seconds() >= config.heartbeat_interval:
            try:
                self.client.heartbeat()
                self.last_heartbeat = now
            except Exception as e:
                print(f"[Worker] Heartbeat failed: {e}")

        # Fetch tasks
        try:
            tasks = self.client.fetch_tasks()
            for task in tasks:
                self._execute_task(task)
        except Exception as e:
            print(f"[Worker] Task fetch failed: {e}")

        time.sleep(config.task_fetch_interval)

    def _execute_task(self, task: dict):
        """태스크 실행 — executor를 통해 핸들러 디스패치."""
        task_id = task["id"]
        task_type = task["task_type"]
        print(f"[Worker] Executing task {task_id} ({task_type})")

        try:
            result = self.executor.execute(task)
            self.client.complete_task(task_id, result)
            print(f"[Worker] Task {task_id} completed")
        except Exception as e:
            error = str(e)
            print(f"[Worker] Task {task_id} failed: {error}")
            try:
                self.client.fail_task(task_id, error)
            except Exception:
                pass


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
