"""AdsPower Local API client.

Manages browser profiles — create, start (returns debug port), stop.
Each YouTube account = 1 AdsPower profile = 1 fingerprint.
"""

import os

import httpx
from hydra.core.config import settings
from hydra.core.logger import get_logger

log = get_logger("adspower")


def _normalize_api_key(raw: str | None) -> str:
    """AdsPower API key 정규화.

    Codex 5/12 P1 — secrets / env / 복붙으로 들어온 key 가 trailing \\r/\\n/
    공백/감싸기 따옴표 가지면 'Bearer <key\\r>' 로 AdsPower 가 invalid 처리.
    모든 Bearer 생성 경로 에서 이 helper 를 통과시켜 일관 정규화.
    """
    if not raw:
        return ""
    s = str(raw).strip()
    # 양쪽 따옴표 (시크릿 저장 시 흔히 박힘) 제거.
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    return s


class AdsPowerClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.adspower_api_url).rstrip("/")
        # 명시 api_key 인자가 있으면 우선. 없으면 _resolve_api_key 가 매 호출마다
        # env / settings 에서 fresh resolve — heartbeat 가 env 를 갱신해도 따라감.
        self._explicit_api_key = api_key

    def _resolve_api_key(self) -> str:
        """매 호출마다 env/settings 재조회 + 정규화.

        본질 fix: 이전엔 __init__ 에서 cache 해서 module-level singleton
        (line 162 adspower = AdsPowerClient()) 가 import 시점 (env 비었을 때) 의
        값을 영원히 들고 있었음. worker startup 직후 import 되어 self.api_key=""
        가 되고, heartbeat 가 나중에 env 를 set 해도 singleton 은 빈 키 그대로
        → AdsPower "Require api-key" 거부.

        Codex 5/12 P1 follow-up — key 정규화 추가. trailing \\r/\\n/공백/따옴표
        가 섞이면 `Bearer <key\\r>` 로 AdsPower 가 다른 토큰으로 보고 거절.
        secrets / env / 복붙 path 어느 쪽에서든 들어올 수 있어 공통 처리.
        """
        raw = (
            self._explicit_api_key
            or os.environ.get("ADSPOWER_API_KEY")
            or settings.adspower_api_key
            or ""
        )
        return _normalize_api_key(raw)

    @property
    def api_key(self) -> str:
        """back-compat: 외부 코드가 client.api_key 접근하는 경우 fresh 값 반환."""
        return self._resolve_api_key()

    def _headers(self) -> dict:
        key = self._resolve_api_key()
        if key:
            return {"Authorization": f"Bearer {key}"}
        return {}

    def _get(self, path: str, params: dict | None = None, *, timeout: float = 30) -> dict:
        resp = httpx.get(f"{self.base_url}{path}", params=params, headers=self._headers(), timeout=timeout)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"AdsPower error: {data.get('msg', data)}")
        return data.get("data", {})

    def _post(self, path: str, json_body: dict | None = None, *, timeout: float = 30) -> dict:
        resp = httpx.post(f"{self.base_url}{path}", json=json_body, headers=self._headers(), timeout=timeout)
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
        from hydra.browser.adspower_cleanup import extract_process_ids
        ws = data.get("ws", {})
        result = {
            "ws_endpoint": ws.get("puppeteer", ""),
            "selenium_endpoint": ws.get("selenium", ""),
            "debug_port": data.get("debug_port", ""),
            "webdriver": data.get("webdriver", ""),
            "process_ids": extract_process_ids(data),
        }
        log.info(f"Started browser for profile {profile_id}, port={result['debug_port']}")
        return result

    def stop_browser(self, profile_id: str, *, cookie_sync_grace_sec: float = 4.0):
        """Stop browser for profile.

        AdsPower writes the profile's cookie/session state to disk *during* the
        stop call, but freshly authenticated cookies (esp. Google sign-in tokens)
        sometimes don't persist if the stop call fires immediately after login.
        We give a small grace period so the renderer has a chance to flush.

        Mid-session calls (after navigation, scrolling, posting comments) don't
        need this — that's why the parameter is overrideable. But every login-
        adjacent close MUST keep the default grace.
        """
        if cookie_sync_grace_sec > 0:
            import time
            time.sleep(cookie_sync_grace_sec)
        self._get("/api/v1/browser/stop", {"user_id": profile_id}, timeout=15)
        log.info(f"Stopped browser for profile {profile_id}")

    def stop_all_browsers(self) -> dict:
        """Ask AdsPower to stop all running browser profiles."""
        resp = httpx.post(
            f"{self.base_url}/api/v2/browser-profile/stop-all",
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text[:200]}
        if isinstance(data, dict) and data.get("code") not in (None, 0):
            raise RuntimeError(f"AdsPower stop-all error: {data.get('msg', data)}")
        log.info("Requested AdsPower stop-all")
        return data if isinstance(data, dict) else {"raw": str(data)[:200]}

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
