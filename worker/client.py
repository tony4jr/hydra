"""서버 API 클라이언트."""
import httpx
import platform
from worker.config import config


class ServerClient:
    def __init__(self):
        self.base_url = config.server_url.rstrip("/")
        if not self.base_url.startswith("https") and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            print("[WARNING] Server URL is not HTTPS. Credentials may be exposed in transit.")
        self.headers = {"X-Worker-Token": config.worker_token}
        self.http = httpx.Client(timeout=30)

    def heartbeat(self) -> dict:
        """Heartbeat 전송."""
        resp = self.http.post(
            f"{self.base_url}/api/workers/heartbeat",
            headers=self.headers,
            json={
                "version": config.worker_version,
                "os_type": platform.system().lower(),
            },
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_tasks(self) -> list[dict]:
        """서버에서 태스크 가져오기."""
        resp = self.http.post(
            f"{self.base_url}/api/tasks/fetch",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    def complete_task(self, task_id: int, result: str = None) -> dict:
        """태스크 완료 보고."""
        resp = self.http.post(
            f"{self.base_url}/api/tasks/complete",
            headers=self.headers,
            json={"task_id": task_id, "result": result},
        )
        resp.raise_for_status()
        return resp.json()

    def fail_task(self, task_id: int, error: str) -> dict:
        """태스크 실패 보고."""
        resp = self.http.post(
            f"{self.base_url}/api/tasks/fail",
            headers=self.headers,
            json={"task_id": task_id, "error": error},
        )
        resp.raise_for_status()
        return resp.json()

    def reschedule_task(self, task_id: int, reason: str = "ip_rotation_failed") -> dict:
        """태스크 IP 로테이션 실패로 재스케줄 요청."""
        resp = self.http.post(
            f"{self.base_url}/api/tasks/{task_id}/reschedule-ip-failure",
            headers=self.headers,
            json={"reason": reason},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def close(self):
        self.http.close()
