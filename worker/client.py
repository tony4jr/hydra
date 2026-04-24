"""서버 API 클라이언트.

dual-stack (IPv4/IPv6) 환경에서 네트워크 불안정성에 견디는 설계:
1. 요청마다 세 번 시도: dual-stack → IPv4-only → dual-stack (fresh)
2. 각 시도는 새 httpx.Client — stale 커넥션풀/리졸버 캐시 오염 회피
3. 선호 모드 (v4/dual) 를 세션 동안 기억하되, 실패 시 반대 모드로 폴백

Happy Eyeballs (RFC 8305) + 매 요청 fresh client = Windows 에서 간헐적
getaddrinfo 실패 + IPv6 NAT64 경로 불안정에도 안정적 동작.
"""
import httpx
import platform
import time
from worker.config import config


_RETRY_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.ConnectTimeout,
)


def _mk_client(ipv4_only: bool) -> httpx.Client:
    if ipv4_only:
        return httpx.Client(
            timeout=30,
            transport=httpx.HTTPTransport(local_address="0.0.0.0"),
        )
    return httpx.Client(timeout=30)


class ServerClient:
    def __init__(self):
        self.base_url = config.server_url.rstrip("/")
        if not self.base_url.startswith("https") and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            print("[WARNING] Server URL is not HTTPS. Credentials may be exposed in transit.")
        self.headers = {"X-Worker-Token": config.worker_token}

        # 세션 선호 — 마지막에 성공한 모드 기억 (첫 요청 비용 절감)
        self._prefer_v4 = False
        # self.http 속성은 하위호환/테스트 편의용. 테스트가 Mock 을 주입하면
        # 그 경로가 먼저 사용됨.
        self.http: httpx.Client | None = None

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """최대 3번 시도 — 각 시도는 새 클라이언트.

        순서: [선호 모드] → [반대 모드] → [선호 모드 fresh].
        테스트가 self.http 주입해 놓은 경우는 그대로 그 인스턴스 사용 (Mock).
        """
        url = f"{self.base_url}{path}"

        # 테스트 경로: self.http 가 주입돼 있으면 그걸 그대로 씀
        if self.http is not None:
            return self.http.request(method, url, **kwargs)

        attempts = [self._prefer_v4, not self._prefer_v4, self._prefer_v4]
        last_exc: Exception | None = None
        for i, ipv4_only in enumerate(attempts):
            client = _mk_client(ipv4_only)
            try:
                resp = client.request(method, url, **kwargs)
                # 성공 — 이 모드를 세션 선호로 기억
                if self._prefer_v4 != ipv4_only:
                    mode = "IPv4-only" if ipv4_only else "dual-stack"
                    print(f"[Worker] switched transport preference → {mode}")
                    self._prefer_v4 = ipv4_only
                return resp
            except _RETRY_EXCEPTIONS as e:
                last_exc = e
                if i < len(attempts) - 1:
                    time.sleep(0.5)  # 짧은 breather — DNS/소켓 상태 정리
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        assert last_exc is not None
        raise last_exc

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

    def report_error(
        self,
        kind: str,
        message: str,
        traceback: str | None = None,
        context: dict | None = None,
    ) -> None:
        """워커 에러/진단 리포트 — 서버의 worker_errors 테이블에 기록.

        절대 예외를 propagate 하지 않음 (에러 리포트 자체가 에러나면 조용히 포기,
        원래 실패가 더 중요).
        """
        from datetime import datetime, timezone
        body = {
            "kind": kind,
            "message": message[:2000],
            "traceback": traceback,
            "context": context or {},
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._request(
                "POST", "/api/workers/report-error",
                headers=self.headers,
                json=body,
                timeout=10,
            )
        except Exception:
            pass

    def close(self):
        if self.http is not None:
            try:
                self.http.close()
            except Exception:
                pass
