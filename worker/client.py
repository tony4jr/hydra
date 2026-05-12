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
import socket
import time
from worker.config import config


# Windows + 모바일/wifi resolver 가 IPv6 record lookup 깜박이로 던지는 모든 transient.
# httpx 가 socket.gaierror 를 ConnectError 로 감싸지만, 일부 경로에선 ReadTimeout/
# PoolTimeout 으로 표출되기도 한다. transient 는 광범위하게 잡고 backoff.
_RETRY_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.PoolTimeout,
    httpx.NetworkError,
    socket.gaierror,
    OSError,  # WinError 11001 등 raw OSError 도 포괄
)


def _mk_client(ipv4_only: bool, *, persistent: bool = False) -> httpx.Client:
    """persistent=True: keepalive 살아있는 pool — DNS lookup 1회 후 재사용.
    persistent=False: fresh client — pool 오염 회피용 fallback.

    httpx 0.28: Client(transport=...) 와 Client(limits=...) 를 같이 주면 limits
    는 무시된다. transport 자체에 limits 를 박아야 keepalive_expiry 가 실제 적용.
    """
    # keepalive_expiry: server-side (nginx/cloudflare 보통 30-60s) 보다 짧게.
    # 25s 면 30s heartbeat 사이클에서 한 번은 재사용 가능, stale 진입 직전 폐기.
    limits = (
        httpx.Limits(max_keepalive_connections=4, keepalive_expiry=25.0)
        if persistent
        else httpx.Limits(max_keepalive_connections=0, keepalive_expiry=5.0)
    )
    if ipv4_only:
        transport = httpx.HTTPTransport(local_address="0.0.0.0", retries=1, limits=limits)
    else:
        transport = httpx.HTTPTransport(retries=1, limits=limits)
    return httpx.Client(timeout=30, transport=transport)


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
        # persistent pool — 첫 성공 후 keepalive 살려 DNS lookup 누적 0 만든다.
        # transient 발생 시 닫고 fresh fallback.
        self._persistent: httpx.Client | None = None

    def _get_persistent(self) -> httpx.Client:
        if self._persistent is None:
            self._persistent = _mk_client(self._prefer_v4, persistent=True)
        return self._persistent

    def _drop_persistent(self) -> None:
        if self._persistent is not None:
            try:
                self._persistent.close()
            except Exception:
                pass
            self._persistent = None

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """retry 정책: persistent(살아있는 pool) → fresh fallback × 4회 exp backoff.

        - 첫 시도: 살아있는 connection pool. 성공 시 DNS lookup 0회 (keepalive).
        - 실패 시: persistent 폐기, fresh client 로 dual/v4 토글하며 4회 재시도.
        - sleep: 1s, 2s, 4s, 8s — Windows DNS 깜박이 (보통 1-3s) 흡수.

        테스트가 self.http 주입해 놓은 경우는 그대로 그 인스턴스 사용 (Mock).
        """
        url = f"{self.base_url}{path}"

        # 테스트 경로
        if self.http is not None:
            return self.http.request(method, url, **kwargs)

        # 1차: persistent pool
        try:
            client = self._get_persistent()
            return client.request(method, url, **kwargs)
        except _RETRY_EXCEPTIONS as e:
            first_exc: Exception = e
            self._drop_persistent()

        # 2차~5차: fresh client × 4회 exp backoff.
        # 첫 fresh 는 prefer 모드 — persistent 실패는 보통 stale connection
        # (server-side keepalive 짧음) 이라 mode 문제 아닌 경우가 대부분.
        # 같은 모드로 fresh 가 풀어주면 prefer 진동 없음. 그래도 실패면
        # 진짜 mode 깨진 거 — 그제서야 반대 모드로 토글.
        last_exc: Exception = first_exc
        for attempt in range(4):
            if attempt < 2:
                ipv4_only = self._prefer_v4
            else:
                ipv4_only = not self._prefer_v4
            time.sleep(min(2 ** attempt, 8))  # 1, 2, 4, 8
            client = _mk_client(ipv4_only, persistent=False)
            try:
                resp = client.request(method, url, **kwargs)
                if self._prefer_v4 != ipv4_only:
                    mode = "IPv4-only" if ipv4_only else "dual-stack"
                    print(f"[Worker] switched transport preference → {mode}")
                    self._prefer_v4 = ipv4_only
                return resp
            except _RETRY_EXCEPTIONS as e:
                last_exc = e
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        raise last_exc

    def heartbeat(self) -> dict:
        """Heartbeat 전송 (M1-10: v2 엔드포인트).

        PR-Preflight: 실시간 capability 측정 (ADB devices / AdsPower / system).
        서버가 health_snapshot 보고 워커 환경 파악 → worker.ip_config 자동 세팅.
        측정 실패해도 fallback default → heartbeat 자체는 절대 막지 않음.
        """
        try:
            from worker.preflight import collect_health
            health = collect_health()
        except Exception:
            health = {
                "os_type": platform.system().lower(),
                "cpu_percent": 0.0,
                "mem_used_mb": 0,
                "disk_free_gb": 0.0,
                "adb_devices": [],
                "adspower_version": "",
                "playwright_browsers_ok": True,
            }
        body = {
            "version": config.worker_version,
            **health,
        }
        # heartbeat 는 짧은 timeout — blackhole 시 backoff 합산 폭주 (최악 150s+)
        # 으로 다음 tick 막히는 것 방지. 한 시도당 10s, 4회 backoff 합쳐 ~55s.
        resp = self._request(
            "POST", "/api/workers/heartbeat/v2",
            headers=self.headers,
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def sync_data(self) -> dict:
        """Pull accounts + workers from server for local DB sync.

        Used at worker startup so ensure_safe_ip can find the account/worker
        rows it needs to enforce the 1-account-1-IP invariant.
        """
        resp = self._request("GET", "/api/workers/sync", headers=self.headers)
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

        PR-A: context 에 envelope 또는 secret 필드가 섞이지 않도록 redact 적용.
        """
        from datetime import datetime, timezone
        from hydra.protocol import redact_for_logging
        body = {
            "kind": kind,
            "message": message[:2000],
            "traceback": traceback,
            "context": redact_for_logging(context or {}),
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

    def report_progress(
        self,
        *,
        session_uuid: str,
        task_id: int | None,
        attempt_no: int,
        sequence_no: int,
        phase: str,
        message: str | None = None,
        is_phase_change: bool = False,
    ) -> None:
        """PR-C: phase 변경/heartbeat 보고. 절대 예외 propagate X (best-effort)."""
        try:
            self._request(
                "POST", "/api/tasks/v2/progress",
                headers=self.headers,
                json={
                    "session_uuid": session_uuid,
                    "task_id": task_id,
                    "attempt_no": attempt_no,
                    "sequence_no": sequence_no,
                    "phase": phase,
                    "message": message,
                    "is_phase_change": is_phase_change,
                },
                timeout=10,
            )
        except Exception:
            pass

    def session_heartbeat(
        self,
        *,
        session_uuid: str,
        worker_id: int,
        account_id: int | None,
        status: str = "active",
    ) -> None:
        """PR-C: WorkerSession 단위 heartbeat. best-effort."""
        try:
            self._request(
                "POST", "/api/tasks/v2/session-heartbeat",
                headers=self.headers,
                json={
                    "session_uuid": session_uuid,
                    "worker_id": worker_id,
                    "account_id": account_id,
                    "status": status,
                },
                timeout=10,
            )
        except Exception:
            pass

    def report_log_tail(self, entries: list[dict]) -> None:
        """verbose_mode 일 때 INFO+ 활동 로그 batch push. 조용히 실패."""
        if not entries:
            return
        try:
            self._request(
                "POST", "/api/workers/log-tail",
                headers=self.headers,
                json={"entries": entries},
                timeout=10,
            )
        except Exception:
            pass

    def report_error_with_screenshot(
        self,
        kind: str,
        message: str,
        screenshot_bytes: bytes,
        traceback: str | None = None,
        context: dict | None = None,
        filename: str = "screenshot.png",
    ) -> None:
        """에러 + 스크린샷 multipart 업로드. 절대 예외 propagate X."""
        import json as _json
        from hydra.protocol import redact_for_logging
        files = {"screenshot": (filename, screenshot_bytes, "image/png")}
        data: dict = {"kind": kind, "message": message[:2000]}
        if traceback:
            data["traceback"] = traceback
        if context:
            data["context"] = _json.dumps(redact_for_logging(context), ensure_ascii=False)
        url = f"{self.base_url}/api/workers/report-error-with-screenshot"
        # multipart 는 기존 _request 흐름(JSON) 과 다르므로 직접 호출 — 간단한 단일 시도
        try:
            with _mk_client(self._prefer_v4) as c:
                c.post(url, headers=self.headers, files=files, data=data, timeout=30)
        except Exception:
            try:
                with _mk_client(not self._prefer_v4) as c:
                    c.post(url, headers=self.headers, files=files, data=data, timeout=30)
            except Exception:
                pass

    def close(self):
        if self.http is not None:
            try:
                self.http.close()
            except Exception:
                pass
        # persistent pool 도 정리 — 워커 종료시 누수 방지
        self._drop_persistent()
