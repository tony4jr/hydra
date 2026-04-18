"""AdsPower Local API client.

Manages browser profiles — create, start (returns debug port), stop.
Each YouTube account = 1 AdsPower profile = 1 fingerprint.
"""

import httpx
from hydra.core.config import settings
from hydra.core.logger import get_logger

log = get_logger("adspower")


class AdsPowerClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.adspower_api_url).rstrip("/")
        self.api_key = api_key or settings.adspower_api_key

    def _headers(self) -> dict:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = httpx.get(f"{self.base_url}{path}", params=params, headers=self._headers(), timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"AdsPower error: {data.get('msg', data)}")
        return data.get("data", {})

    def _post(self, path: str, json_body: dict | None = None) -> dict:
        resp = httpx.post(f"{self.base_url}{path}", json=json_body, headers=self._headers(), timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"AdsPower error: {data.get('msg', data)}")
        return data.get("data", {})

    # --- Profile CRUD ---

    def create_profile(
        self,
        name: str,
        group_id: str = "0",
        fingerprint_config: dict | None = None,
        remark: str = "",
    ) -> str:
        """Create a new browser profile. Returns profile ID.

        `fingerprint_config` is the AdsPower fingerprint_config dict produced
        by `hydra.browser.fingerprint_bundle.build_fingerprint_payload`.
        """
        from hydra.browser.adspower_errors import (
            AdsPowerAPIError, AdsPowerQuotaExceeded,
        )

        body = {
            "name": name,
            "group_id": group_id,
            "remark": remark,
            "user_proxy_config": {"proxy_soft": "no_proxy"},
            "fingerprint_config": fingerprint_config or {
                "language": ["ko-KR", "ko", "en-US", "en"],
            },
        }

        try:
            data = self._post("/api/v1/user/create", body)
        except RuntimeError as e:
            msg = str(e).lower()
            if any(k in msg for k in ["limit exceeded", "quota", "package limit"]):
                raise AdsPowerQuotaExceeded(str(e)) from e
            raise AdsPowerAPIError(str(e)) from e

        profile_id = data.get("id", "")
        log.info(f"Created AdsPower profile: {name} → {profile_id}")
        return profile_id

    def delete_profile(self, profile_id: str):
        """Delete a browser profile."""
        self._post("/api/v1/user/delete", {"user_ids": [profile_id]})
        log.info(f"Deleted AdsPower profile: {profile_id}")

    def list_profiles(self, page: int = 1, page_size: int = 100) -> list[dict]:
        """List all browser profiles."""
        data = self._get("/api/v1/user/list", {"page": page, "page_size": page_size})
        return data.get("list", [])

    def get_profile_count(self) -> int:
        """Total profiles visible to this AdsPower account."""
        data = self._get("/api/v1/user/list", {"page": 1, "page_size": 1})
        return int(data.get("total", 0))

    # --- Browser start/stop ---

    def start_browser(self, profile_id: str, extra_args: list[str] | None = None) -> dict:
        """Start browser for profile. Returns {ws_endpoint, debug_port, webdriver}.

        Always passes `--force-device-scale-factor=1.0` so the Mac host's Retina
        DPR=2 does not leak through Windows-spoofed profiles. Windows Worker
        hosts are unaffected (they already have DPR=1).
        """
        args = ["--force-device-scale-factor=1.0"]
        if extra_args:
            args.extend(extra_args)
        import json as _json
        params = {
            "user_id": profile_id,
            "launch_args": _json.dumps(args),
        }
        data = self._get("/api/v1/browser/start", params)
        ws = data.get("ws", {})
        result = {
            "ws_endpoint": ws.get("puppeteer", ""),
            "selenium_endpoint": ws.get("selenium", ""),
            "debug_port": data.get("debug_port", ""),
            "webdriver": data.get("webdriver", ""),
        }
        log.info(f"Started browser for profile {profile_id}, port={result['debug_port']}")
        return result

    def stop_browser(self, profile_id: str):
        """Stop browser for profile."""
        self._get("/api/v1/browser/stop", {"user_id": profile_id})
        log.info(f"Stopped browser for profile {profile_id}")

    def check_browser_active(self, profile_id: str) -> bool:
        """Check if browser is running."""
        try:
            data = self._get("/api/v1/browser/active", {"user_id": profile_id})
            return data.get("status") == "Active"
        except Exception:
            return False

    # --- Proxy update ---

    def update_proxy(self, profile_id: str, proxy_config: dict):
        """Update proxy settings for a profile."""
        self._post("/api/v1/user/update", {
            "user_id": profile_id,
            "user_proxy_config": proxy_config,
        })
        log.info(f"Updated proxy for profile {profile_id}")


adspower = AdsPowerClient()
