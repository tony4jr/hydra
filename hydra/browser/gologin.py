"""GoLogin API client — drop-in alternative to AdsPowerClient.

Mirrors the interface of hydra.browser.adspower.AdsPowerClient so driver.py
can swap backends via settings. Uses Cloud Browser mode by default
(no local Orbita install required).

Reference: https://gologin.com/docs
"""

import httpx
from hydra.core.config import settings
from hydra.core.logger import get_logger

log = get_logger("gologin")

API_BASE = "https://api.gologin.com"
CLOUD_CONNECT = "https://cloudbrowser.gologin.com/connect"


class GoLoginClient:
    def __init__(self, api_token: str | None = None):
        self.api_token = api_token or settings.gologin_api_token
        if not self.api_token:
            log.warning("GoLogin API token not set — client will fail")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = httpx.get(f"{API_BASE}{path}", headers=self._headers(),
                         params=params, timeout=30)
        if resp.status_code == 429:
            raise RuntimeError(
                "GoLogin rate limit hit (429). Token may be invalidated — "
                "regenerate at https://app.gologin.com/#/personalArea/TokenApi"
            )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json_body: dict | None = None) -> dict:
        resp = httpx.post(f"{API_BASE}{path}", headers=self._headers(),
                          json=json_body, timeout=30)
        if resp.status_code == 429:
            raise RuntimeError("GoLogin rate limit hit — regenerate token")
        resp.raise_for_status()
        # Some endpoints return empty body on success
        try:
            return resp.json()
        except Exception:
            return {}

    def _delete(self, path: str, json_body: dict | None = None) -> dict:
        resp = httpx.request("DELETE", f"{API_BASE}{path}", headers=self._headers(),
                             json=json_body, timeout=30)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {}

    def _put(self, path: str, json_body: dict | None = None) -> dict:
        resp = httpx.put(f"{API_BASE}{path}", headers=self._headers(),
                         json=json_body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # --- Profile CRUD ---

    def create_profile(self, name: str, group_id: str = "",
                       os_type: str = "lin", language: str = "ko-KR",
                       proxy: dict | None = None) -> str:
        """Create a custom profile. Returns profile ID.

        os_type: "win" | "mac" | "lin" | "android" | "ios"
        """
        body = {
            "name": name,
            "os": os_type,
            "navigator": {
                "language": language,
                "resolution": "1920x1080",
            },
            "timezone": {"timezone": "Asia/Seoul"},
            "webRTC": {"mode": "alerted"},
            "canvas": {"mode": "noise"},
            "webGL": {"mode": "noise"},
        }
        if group_id:
            body["folderName"] = group_id
        if proxy:
            body["proxy"] = proxy
        data = self._post("/browser/custom", body)
        profile_id = data.get("id", "")
        log.info(f"Created GoLogin profile: {name} → {profile_id}")
        return profile_id

    def delete_profile(self, profile_id: str):
        """Delete a browser profile (batch API expects list)."""
        self._delete("/browser", {"ids": [profile_id]})
        log.info(f"Deleted GoLogin profile: {profile_id}")

    def list_profiles(self, page: int = 1, page_size: int = 30) -> list[dict]:
        data = self._get("/browser/v2", {"page": page, "limit": page_size})
        # v2 returns object with `profiles` array
        return data.get("profiles", data.get("list", []))

    # --- Browser start/stop (Cloud Browser mode) ---

    def start_browser(self, profile_id: str) -> dict:
        """Start cloud browser session. Returns Playwright-compatible endpoint."""
        # Trigger session creation (also returns cloud hostname)
        self._post(f"/browser/{profile_id}/web")

        # Cloud Browser uses token-based connect URL directly
        ws_endpoint = f"{CLOUD_CONNECT}?token={self.api_token}&profile={profile_id}"
        result = {
            "ws_endpoint": ws_endpoint,
            "selenium_endpoint": "",  # not supported via cloud
            "debug_port": "",
            "webdriver": "",
        }
        log.info(f"Started cloud browser for profile {profile_id}")
        return result

    def stop_browser(self, profile_id: str):
        """Stop cloud browser session."""
        self._delete(f"/browser/{profile_id}/web")
        log.info(f"Stopped cloud browser for profile {profile_id}")

    def check_browser_active(self, profile_id: str) -> bool:
        """GoLogin has no direct endpoint — caller must track state.

        Returns True conservatively; use browser.is_connected() on
        Playwright side for real verification.
        """
        return True

    # --- Proxy update ---

    def update_proxy(self, profile_id: str, proxy_config: dict):
        """Update proxy settings via profile edit."""
        # PUT /browser/{id}/custom replaces entire profile
        # For just proxy change, use PATCH /browser/proxy/many/v2
        self._post("/browser/proxy/many/v2", {
            "browserIds": [profile_id],
            "proxy": proxy_config,
        })
        log.info(f"Updated proxy for profile {profile_id}")


gologin = GoLoginClient()
