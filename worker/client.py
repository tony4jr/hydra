"""서버 API 클라이언트.

dual-stack (IPv4/IPv6) 환경에서 안정적 동작을 위한 fallback:
1. 기본 transport (OS 가 IPv6 우선, 있으면) 로 먼저 요청
2. 연결/프로토콜 에러 (NAT64 경로 불안정 등) 나면 IPv4-only transport 로 재시도
3. 한 번 IPv4 성공하면 세션 내 계속 IPv4 사용 (sticky) — 재시도 비용 절감

Happy Eyeballs (RFC 8305) 정신: IPv6 을 *끄는* 게 아니라 *안 되면 IPv4* 로.
"""
import httpx
import platform
from worker.config import config


_RETRY_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
)


class ServerClient:
    def __init__(self):
        self.base_url = config.server_url.rstrip("/")
        if not self.base_url.startswith("https") and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            print("[WARNING] Server URL is not HTTPS. Credentials may be exposed in transit.")
        self.headers = {"X-Worker-Token": config.worker_token}

        # http = 현재 활성 클라이언트. 기본은 OS dual-stack, 실패 시 IPv4 강제로 교체.
        # 외부(특히 테스트) 에서 이 속성 직접 교체해도 _request 가 그대로 사용.
        self.http = httpx.Client(timeout=30)
        self._v4_fallback_used = False

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """self.http 로 시도 → 연결류 에러 나면 IPv4-강제 클라이언트로 한 번 재시도.
        성공 시 self.http 를 IPv4 클라이언트로 영구 교체 (sticky).
        """
        url = f"{self.base_url}{path}"
        try:
            return self.http.request(method, url, **kwargs)
        except _RETRY_EXCEPTIONS as e:
            if self._v4_fallback_used:
                raise  # 이미 IPv4 인데도 실패 → 그대로 올림
            print(f"[Worker] primary transport failed ({type(e).__name__}), falling back to IPv4")
            try:
                self.http.close()
            except Exception:
                pass
            self.http = httpx.Client(
                timeout=30,
                transport=httpx.HTTPTransport(local_address="0.0.0.0"),
            )
            self._v4_fallback_used = True
            return self.http.request(method, url, **kwargs)

    def heartbeat(self) -> dict:
        """Heartbeat 전송 (M1-10: v2 엔드포인트)."""
        resp = self._request(
            "POST", "/api/workers/heartbeat/v2",
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
        resp = self._request(
            "POST", "/api/tasks/v2/fetch",
            headers=self.headers,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("tasks", [])
        return data

    def complete_task(self, task_id: int, result: str = None) -> dict:
        """태스크 완료 보고 (M1-10: v2 엔드포인트)."""
        resp = self._request(
            "POST", "/api/tasks/v2/complete",
            headers=self.headers,
            json={"task_id": task_id, "result": result},
        )
        resp.raise_for_status()
        return resp.json()

    def fail_task(self, task_id: int, error: str) -> dict:
        """태스크 실패 보고 (M1-10: v2 엔드포인트)."""
        resp = self._request(
            "POST", "/api/tasks/v2/fail",
            headers=self.headers,
            json={"task_id": task_id, "error": error},
        )
        resp.raise_for_status()
        return resp.json()

    def reschedule_task(self, task_id: int, reason: str = "ip_rotation_failed") -> dict:
        """태스크 IP 로테이션 실패로 재스케줄 요청."""
        resp = self._request(
            "POST", f"/api/tasks/{task_id}/reschedule-ip-failure",
            headers=self.headers,
            json={"reason": reason},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def close(self):
        try:
            self.http.close()
        except Exception:
            pass
