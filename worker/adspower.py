"""AdsPower 로컬 API 클라이언트 — Worker PC에서 실행."""
import httpx
import os


class AdsPowerClient:
    def __init__(self):
        self.base_url = os.getenv("ADSPOWER_API_URL", "http://local.adspower.net:50325")
        self.http = httpx.Client(timeout=60)

    def open_browser(self, profile_id: str) -> dict:
        """AdsPower 프로필로 브라우저 열기."""
        resp = self.http.get(
            f"{self.base_url}/api/v1/browser/start",
            params={"user_id": profile_id},
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
            params={"user_id": profile_id},
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
