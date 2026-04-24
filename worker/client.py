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
        # IPv4 강제 — 일부 ISP 의 NAT64/IPv6 경로가 TLS 중간 끊김 유발.
        # local_address="0.0.0.0" 는 소켓을 IPv4 로 bind → getaddrinfo 결과에서
        # IPv4 주소만 사용됨.
        transport = httpx.HTTPTransport(local_address="0.0.0.0")
        self.http = httpx.Client(timeout=30, transport=transport)

    def heartbeat(self) -> dict:
        """Heartbeat 전송 (M1-10: v2 엔드포인트)."""
        resp = self.http.post(
            f"{self.base_url}/api/workers/heartbeat/v2",
            headers=self.headers,
            json={
                "version": config.worker_version,
                "os_type": platform.system().lower(),
            },
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_tasks(self) -> list[dict]:
        """서버에서 태스크 가져오기 (M1-10: v2 엔드포인트).

        v2 응답 형식 `{"tasks": [...]}` 에서 list 만 추출하여 기존 호출자 호환 유지.
        """
        resp = self.http.post(
            f"{self.base_url}/api/tasks/v2/fetch",
            headers=self.headers,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("tasks", [])
        return data

    def complete_task(self, task_id: int, result: str = None) -> dict:
        """태스크 완료 보고 (M1-10: v2 엔드포인트)."""
        resp = self.http.post(
            f"{self.base_url}/api/tasks/v2/complete",
            headers=self.headers,
            json={"task_id": task_id, "result": result},
        )
        resp.raise_for_status()
        return resp.json()

    def fail_task(self, task_id: int, error: str) -> dict:
        """태스크 실패 보고 (M1-10: v2 엔드포인트)."""
        resp = self.http.post(
            f"{self.base_url}/api/tasks/v2/fail",
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
