"""Worker 자동 업데이트 체커."""
import httpx
from worker.config import config


class UpdateChecker:
    def __init__(self):
        self.base_url = config.server_url.rstrip("/")

    def check(self) -> dict | None:
        """새 버전이 있으면 정보 반환, 없으면 None."""
        try:
            resp = httpx.get(f"{self.base_url}/api/version/worker-latest", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            latest = data.get("version", "")
            if latest and latest != config.worker_version:
                return {"current": config.worker_version, "latest": latest, "download_url": data.get("download_url")}
        except Exception:
            pass
        return None
