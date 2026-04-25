"""T11 프로필 fingerprint 검증.

AdsPower /api/v2/browser-profile/ua 로 의도 UA 조회.
Playwright 런타임 navigator.userAgent 와 대조 → 불일치 시 격리.

브라우저 기동 없이 AdsPower 가 알려주는 의도 값만 검증하는 가벼운 모드도 가능.
"""
from __future__ import annotations

import os
import re

import httpx


CHROME_VER_RE = re.compile(r"Chrome/(\d+)\.", re.IGNORECASE)


def get_intended_ua(profile_id: str, base_url: str | None = None,
                    api_key: str | None = None) -> str | None:
    """AdsPower 가 알려주는 프로필의 의도된 UA 문자열."""
    base = (base_url or os.environ.get("ADSPOWER_API_URL", "http://127.0.0.1:50325")).rstrip("/")
    key = api_key or os.environ.get("ADSPOWER_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(
                f"{base}/api/v2/browser-profile/ua",
                headers=headers,
                json={"profile_id": [profile_id]},
            )
            d = r.json()
            if d.get("code") != 0:
                return None
            lst = d.get("data", {}).get("list", [])
            if lst:
                return lst[0].get("ua")
    except Exception:
        pass
    return None


def extract_chrome_version(ua: str | None) -> int | None:
    if not ua:
        return None
    m = CHROME_VER_RE.search(ua)
    return int(m.group(1)) if m else None


def compare_ua(intended: str, runtime: str) -> dict:
    """의도 UA vs 런타임 UA 비교. Chrome 버전 일치, 플랫폼 일치 등.

    Returns: {"match": bool, "details": dict}
    """
    iv = extract_chrome_version(intended)
    rv = extract_chrome_version(runtime)
    platform_match = _extract_platform(intended) == _extract_platform(runtime)
    chrome_match = iv is not None and iv == rv

    details = {
        "intended_chrome": iv,
        "runtime_chrome": rv,
        "intended_platform": _extract_platform(intended),
        "runtime_platform": _extract_platform(runtime),
        "chrome_version_match": chrome_match,
        "platform_match": platform_match,
    }
    return {"match": chrome_match and platform_match, "details": details}


_PLATFORM_RE = re.compile(r"\(([^)]+)\)")


def _extract_platform(ua: str | None) -> str | None:
    """User-Agent 의 첫 괄호 안 (OS 정보) 추출."""
    if not ua:
        return None
    m = _PLATFORM_RE.search(ua)
    return m.group(1).strip() if m else None
