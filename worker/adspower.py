"""AdsPower 로컬 API 클라이언트 — Worker PC에서 실행.

PR-Debug: api-key 누락 fix. 모든 호출에 ADSPOWER_API_KEY env 자동 첨부.
서버가 heartbeat 응답으로 보내는 키 (worker_api heartbeat_v2: adspower_api_key 필드)
가 worker/app.py 에서 os.environ 에 set 되고, 이 client 가 그 env 를 매 호출에 첨부.
"""
import httpx
import os


class AdsPowerClient:
    def __init__(self):
        self.base_url = os.getenv("ADSPOWER_API_URL", "http://127.0.0.1:50325")
        self.http = httpx.Client(timeout=60)

    def _params(self, **kwargs) -> dict:
        """공통 params — api-key 자동 첨부 (env 에서). AdsPower V1/V2 호환."""
        p = dict(kwargs)
        key = os.environ.get("ADSPOWER_API_KEY", "")
        if key:
            p["api_key"] = key      # V2 API spec
            p["api-key"] = key      # V1 일부 docs
        return p

    def _headers(self) -> dict:
        """헤더 — 일부 AdsPower 버전이 X-API-KEY 헤더 요구."""
        h = {}
        key = os.environ.get("ADSPOWER_API_KEY", "")
        if key:
            h["X-API-KEY"] = key
        return h

    def open_browser(self, profile_id: str) -> dict:
        """AdsPower 프로필로 브라우저 열기."""
        resp = self.http.get(
            f"{self.base_url}/api/v1/browser/start",
            params=self._params(user_id=profile_id),
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"AdsPower error: {data.get('msg')}")
        return data.get("data", {})

    def close_browser(self, profile_id: str) -> dict:
        """브라우저 닫기."""
        resp = self.http.get(
            f"{self.base_url}/api/v1/browser/stop",
            params=self._params(user_id=profile_id),
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def check_status(self) -> bool:
        """AdsPower 연결 상태 확인."""
        try:
            resp = self.http.get(f"{self.base_url}/status")
            return resp.status_code == 200
        except Exception:
            return False

    def close(self):
        self.http.close()
