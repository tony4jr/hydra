#!/usr/bin/env python3
"""AdsPower SunBrowser 커널 프리로드 — 실측 기반 최종 구현.

실측 발견 (probe 결과):
  - v1 /user/list 가 페이지당 100개 제대로 반환 (v2 /browser-profile/list 는
    page_size 무시하고 1개씩만 줌)
  - /kernels 응답: data.list[*].{kernel_type, kernel, is_downloaded}
  - /ua 엔드포인트가 프로필 UA → Chrome/{version} 사전 파악 가능
    (브라우저 기동 전에 필요 커널 버전 수집)
  - download-kernel 응답: data.{status, progress} (msg 없음)

전략:
  1. v1 list 로 50 프로필 전체 조회
  2. v2 ua 로 각 프로필 의도 UA → Chrome 버전 추출 (브라우저 안 열고)
  3. 필요 커널 set 계산
  4. /kernels 로 현재 설치 상태 확인
  5. 누락된 버전들 → download-kernel 일괄 트리거
  6. /kernels 폴링 (30초마다, 최대 15분) → is_downloaded: true 확인
  7. 모든 커널 준비되면 각 프로필 v2 start/stop 으로 기동 검증
  8. 결과를 서버 worker_errors 로 업로드
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import httpx

POLL_INTERVAL_SEC = 30
MAX_POLL_MINUTES = 15
REQ_SPACING_SEC = 0.6     # 일반 2 req/sec
LIST_SPACING_SEC = 1.2    # list 엔드포인트 1 req/sec

CHROME_VER_RE = re.compile(r"Chrome/(\d+)\.", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_api_key() -> str:
    try:
        from worker.config import config as _cfg
        base = _cfg.server_url.rstrip("/")
        tok = _cfg.worker_token
        if base and tok:
            with httpx.Client(timeout=10) as c:
                r = c.post(
                    f"{base}/api/workers/heartbeat/v2",
                    headers={"X-Worker-Token": tok},
                    json={"version": "preload", "os_type": "windows"},
                )
                if r.status_code == 200:
                    return r.json().get("adspower_api_key") or ""
    except Exception:
        pass
    return os.environ.get("ADSPOWER_API_KEY", "")


def _h(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def list_profiles_v1(base_url: str, api_key: str) -> list[dict]:
    """v1 user/list — page_size 존중. 페이지네이션 돌려 전부 수집."""
    out: list[dict] = []
    page = 1
    while True:
        time.sleep(LIST_SPACING_SEC)
        with httpx.Client(timeout=20) as c:
            r = c.get(
                f"{base_url}/api/v1/user/list",
                params={"page": page, "page_size": 100},
                headers=_h(api_key),
            )
            d = r.json()
            if d.get("code") != 0:
                break
            lst = d.get("data", {}).get("list", [])
            if not lst:
                break
            out.extend(lst)
            if len(lst) < 100:
                break
            page += 1
    return out


def query_profile_ua(base_url: str, api_key: str, profile_id: str) -> str | None:
    """v2 ua 엔드포인트 — 기동 없이 프로필의 의도 UA 조회."""
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(
                f"{base_url}/api/v2/browser-profile/ua",
                headers=_h(api_key),
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


def get_kernels(base_url: str, api_key: str) -> dict[tuple[str, str], bool]:
    """설치 상태 맵 — (type, version) → is_downloaded."""
    with httpx.Client(timeout=15) as c:
        r = c.get(f"{base_url}/api/v2/browser-profile/kernels", headers=_h(api_key))
        d = r.json()
        if d.get("code") != 0:
            return {}
        out: dict[tuple[str, str], bool] = {}
        for k in d.get("data", {}).get("list", []):
            kt = k.get("kernel_type", "")
            kv = str(k.get("kernel", ""))
            out[(kt, kv)] = bool(k.get("is_downloaded", False))
        return out


def download_kernel(base_url: str, api_key: str,
                    kernel_type: str, kernel_version: str) -> dict:
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{base_url}/api/v2/browser-profile/download-kernel",
            headers=_h(api_key),
            json={"kernel_type": kernel_type, "kernel_version": kernel_version},
        )
        try:
            return r.json()
        except Exception:
            return {"code": -1, "msg": f"http {r.status_code}"}


def verify_profile(base_url: str, api_key: str, profile_id: str) -> dict:
    """v2 start → (성공 시) v1 stop 으로 정리."""
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=30) as c:
            r = c.post(
                f"{base_url}/api/v2/browser-profile/start",
                headers=_h(api_key),
                json={"profile_id": profile_id, "headless": "1", "open_tabs": "0"},
            )
            d = r.json()
            ms = round((time.perf_counter() - t0) * 1000, 1)
            if d.get("code") == 0:
                # stop 정리
                try:
                    c.get(f"{base_url}/api/v1/browser/stop",
                          params={"user_id": profile_id}, headers=_h(api_key))
                except Exception:
                    pass
                return {"ok": True, "ms": ms}
            return {"ok": False, "ms": ms, "msg": d.get("msg", "?")[:120]}
    except Exception as e:
        return {"ok": False, "msg": f"{type(e).__name__}: {e}"[:120]}


def report_to_server(summary: dict) -> None:
    try:
        from worker.config import config as _cfg
        base = _cfg.server_url.rstrip("/")
        tok = _cfg.worker_token
        with httpx.Client(timeout=20) as c:
            r = c.post(
                f"{base}/api/workers/report-error",
                headers={"X-Worker-Token": tok},
                json={
                    "kind": "diagnostic",
                    "message": f"kernel preload final: {summary.get('summary_line', '?')}",
                    "context": summary,
                },
            )
            print(f"[preload] uploaded: http {r.status_code}")
    except Exception as e:
        print(f"[preload] upload failed: {e}")


def main() -> int:
    base_url = os.environ.get("ADSPOWER_API_URL", "http://127.0.0.1:50325")
    api_key = _get_api_key()
    if not api_key:
        print("[preload] no AdsPower API key")
        return 2
    print(f"[preload] {base_url}")

    # 1. 프로필 수집
    profiles = list_profiles_v1(base_url, api_key)
    print(f"[preload] profiles: {len(profiles)}")
    if not profiles:
        print("[preload] no profiles found")
        return 3

    # 2. 프로필별 UA 조회 → 필요 Chrome 버전 수집
    print(f"[preload] resolving kernel versions via UA (Chrome only)...")
    needed_versions: dict[str, list[str]] = {}  # version → [profile_ids]
    per_profile_version: dict[str, str] = {}
    for p in profiles:
        time.sleep(REQ_SPACING_SEC)
        pid = p.get("user_id") or p.get("profile_id")
        if not pid:
            continue
        ua = query_profile_ua(base_url, api_key, pid)
        if not ua:
            print(f"  ? {pid}: UA query failed")
            continue
        m = CHROME_VER_RE.search(ua)
        if not m:
            print(f"  ? {pid}: UA has no Chrome/NN pattern ({ua[:60]})")
            continue
        v = m.group(1)
        per_profile_version[pid] = v
        needed_versions.setdefault(v, []).append(pid)
    print(f"[preload] versions needed: {sorted(needed_versions.keys())}")
    for v, pids in sorted(needed_versions.items()):
        print(f"  Chrome {v}: {len(pids)} profiles")

    # 3. 현재 설치 상태
    installed = get_kernels(base_url, api_key)
    print(f"[preload] kernels known to AdsPower: {len(installed)}")
    downloaded_chrome = {v for (kt, v), ok in installed.items() if kt == "Chrome" and ok}
    print(f"[preload] Chrome versions already downloaded: {sorted(downloaded_chrome)}")

    # 4. 누락된 버전 다운로드 트리거
    to_download = [v for v in needed_versions if v not in downloaded_chrome]
    print(f"[preload] to download: {to_download}")
    for v in to_download:
        time.sleep(REQ_SPACING_SEC)
        r = download_kernel(base_url, api_key, "Chrome", v)
        status = r.get("data", {}).get("status", "?") if isinstance(r.get("data"), dict) else "?"
        print(f"  ⬇ Chrome {v} → code={r.get('code')} status={status}")

    # 5. 폴링 — 전부 다운로드 완료될 때까지
    if to_download:
        print(f"[preload] polling every {POLL_INTERVAL_SEC}s (max {MAX_POLL_MINUTES}min)...")
        deadline = time.time() + MAX_POLL_MINUTES * 60
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_SEC)
            installed = get_kernels(base_url, api_key)
            downloaded_chrome = {v for (kt, v), ok in installed.items() if kt == "Chrome" and ok}
            still_missing = [v for v in to_download if v not in downloaded_chrome]
            pct = round(100 * (len(to_download) - len(still_missing)) / max(len(to_download), 1), 1)
            elapsed = int(time.time() - (deadline - MAX_POLL_MINUTES * 60))
            print(f"  [{elapsed:3d}s] {pct}% — missing: {still_missing}")
            if not still_missing:
                print(f"[preload] all target kernels downloaded")
                break
        else:
            print(f"[preload] timeout — some kernels still missing")

    # 6. 프로필별 기동 검증
    print(f"[preload] verifying profile launch (v2 start → stop)...")
    results: dict[str, dict] = {}
    for pid, v in per_profile_version.items():
        time.sleep(REQ_SPACING_SEC)
        res = verify_profile(base_url, api_key, pid)
        results[pid] = {"version": v, **res}
        mark = "✓" if res.get("ok") else "✗"
        print(f"  {mark} {pid} (Chrome {v})  {res.get('ms','?')}ms  {res.get('msg','')[:60]}")

    ok_count = sum(1 for r in results.values() if r.get("ok"))
    print(f"\n[preload] FINAL: {ok_count}/{len(results)} profiles verified healthy")

    report_to_server({
        "total_profiles": len(profiles),
        "versions_needed": {k: len(v) for k, v in needed_versions.items()},
        "versions_downloaded_triggered": to_download,
        "per_profile_results": results,
        "ok_count": ok_count,
        "summary_line": f"{ok_count}/{len(results)} profiles verified",
    })

    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
