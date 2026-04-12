"""
AdsPower Local API Client
http://local.adspower.net:50325/api/v1/...
"""

import time
import httpx


class AdsPowerClient:
    def __init__(self, base_url: str = "http://local.adspower.net:50325"):
        self.base_url = base_url
        self.api = f"{base_url}/api/v1"

    def is_running(self) -> bool:
        """Check if AdsPower app is running."""
        try:
            r = httpx.get(f"{self.api}/browser/active", timeout=3)
            return r.status_code == 200
        except httpx.ConnectError:
            return False

    def create_profile(self, name: str, group_id: str = "0") -> dict:
        """Create a new browser profile."""
        r = httpx.post(f"{self.api}/user/create", json={
            "name": name,
            "group_id": group_id,
            "repeat_config": ["0"],  # No repeat check
        }, timeout=10)
        data = r.json()
        if data.get("code") != 0:
            raise Exception(f"Create profile failed: {data.get('msg')}")
        return data.get("data", {})

    def start_browser(self, profile_id: str, timeout: int = 30) -> dict:
        """
        Start browser for profile.
        Returns: {"ws": {"selenium": "127.0.0.1:PORT", "puppeteer": "ws://..."}, ...}
        """
        # Stop first if already running
        self.stop_browser(profile_id)
        time.sleep(1)

        r = httpx.get(
            f"{self.api}/browser/start",
            params={"user_id": profile_id},
            timeout=timeout,
        )
        data = r.json()
        if data.get("code") != 0:
            raise Exception(f"Start browser failed: {data.get('msg')}")
        return data.get("data", {})

    def stop_browser(self, profile_id: str) -> bool:
        """Stop browser for profile."""
        try:
            r = httpx.get(
                f"{self.api}/browser/stop",
                params={"user_id": profile_id},
                timeout=10,
            )
            return r.json().get("code") == 0
        except Exception:
            return False

    def get_active_browsers(self) -> list:
        """Get list of currently running browser profiles."""
        try:
            r = httpx.get(f"{self.api}/browser/active", timeout=5)
            data = r.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("list", [])
        except Exception:
            pass
        return []

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a browser profile."""
        try:
            r = httpx.post(
                f"{self.api}/user/delete",
                json={"user_ids": [profile_id]},
                timeout=10,
            )
            return r.json().get("code") == 0
        except Exception:
            return False

    def list_profiles(self, page: int = 1, page_size: int = 100) -> list:
        """List all profiles."""
        try:
            r = httpx.get(
                f"{self.api}/user/list",
                params={"page": page, "page_size": page_size},
                timeout=10,
            )
            data = r.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("list", [])
        except Exception:
            pass
        return []
