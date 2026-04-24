#!/usr/bin/env python3
"""AdsPower v1/v2 API 원샷 프로브.

모든 관련 엔드포인트를 호출해 실제 응답 구조를 **파일 + 서버** 에 동시 저장.
왕복 디버깅 끝내려는 목적 — 실행 1회 → 제대로 된 preload/다른 코드 한 번에 작성.

측정 항목 (각각 raw JSON/text 원문 저장):
  1. GET  /status
  2. GET  /api/v1/user/list?page=1&page_size=100
  3. POST /api/v2/browser-profile/list  (page=1, page_size=100)
  4. GET  /api/v2/browser-profile/kernels
  5. POST /api/v2/browser-profile/download-kernel  (Chrome 144)
  6. GET  /api/v1/browser/start?user_id=<첫 프로필>&open_tabs=0&headless=1
  7. POST /api/v2/browser-profile/ua  (첫 프로필)
  8. GET  /api/v2/browser-profile/active
  9. POST /api/v2/browser-profile/start  (첫 프로필)   ← v2 start 시도
  10. GET  /api/v1/browser/stop?user_id=<첫 프로필>

사용: cd C:\\hydra && .\\.venv\\Scripts\\python.exe scripts\\diag_adspower_api_probe.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx


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
                    json={"version": "probe", "os_type": "windows"},
                )
                if r.status_code == 200:
                    return r.json().get("adspower_api_key") or ""
    except Exception:
        pass
    return os.environ.get("ADSPOWER_API_KEY", "")


def call(method: str, url: str, api_key: str, **kwargs) -> dict:
    t0 = time.perf_counter()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    headers.update(kwargs.pop("extra_headers", {}))
    rec = {"method": method, "url": url, "t": _now()}
    try:
        with httpx.Client(timeout=30) as c:
            r = c.request(method, url, headers=headers, **kwargs)
            rec["status_code"] = r.status_code
            rec["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            rec["response_headers"] = dict(r.headers)
            rec["body_text_first_2k"] = r.text[:2000]
            try:
                rec["body_json"] = r.json()
            except Exception:
                rec["body_json"] = None
    except Exception as e:
        rec["exception"] = f"{type(e).__name__}: {e}"
        rec["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return rec


def run() -> dict:
    base = os.environ.get("ADSPOWER_API_URL", "http://127.0.0.1:50325")
    api_key = _get_api_key()
    if not api_key:
        return {"error": "ADSPOWER_API_KEY not available"}

    probes: list[dict] = []

    # 1. status (baseline)
    p = call("GET", f"{base}/status", api_key)
    p["label"] = "1_status"
    probes.append(p)

    # 2. v1 list (기존 동작 확인용)
    p = call("GET", f"{base}/api/v1/user/list",
             api_key, params={"page": 1, "page_size": 100})
    p["label"] = "2_v1_user_list"
    probes.append(p)

    # 첫 프로필 ID 추출
    first_pid = None
    try:
        first_pid = p["body_json"]["data"]["list"][0]["user_id"]
        print(f"[probe] first profile: {first_pid}")
    except Exception:
        print("[probe] could not extract first profile from v1 list")

    time.sleep(1.2)  # 1 req/sec list limit

    # 3. v2 list
    p = call("POST", f"{base}/api/v2/browser-profile/list",
             api_key, json={"page": 1, "page_size": 100})
    p["label"] = "3_v2_list_page1"
    probes.append(p)

    time.sleep(1.2)

    # 4. kernels
    p = call("GET", f"{base}/api/v2/browser-profile/kernels", api_key)
    p["label"] = "4_v2_kernels"
    probes.append(p)

    time.sleep(0.6)

    # 5. download-kernel Chrome 144
    p = call("POST", f"{base}/api/v2/browser-profile/download-kernel",
             api_key, json={"kernel_type": "Chrome", "kernel_version": "144"})
    p["label"] = "5_v2_download_kernel_chrome_144"
    probes.append(p)

    time.sleep(0.6)

    # 6-10. first profile 관련 (profile 있는 경우만)
    if first_pid:
        # 6. v1 start
        p = call("GET", f"{base}/api/v1/browser/start",
                 api_key, params={"user_id": first_pid, "open_tabs": 0, "headless": 1})
        p["label"] = "6_v1_browser_start"
        probes.append(p)

        time.sleep(0.6)

        # 7. v2 ua
        p = call("POST", f"{base}/api/v2/browser-profile/ua",
                 api_key, json={"profile_id": [first_pid]})
        p["label"] = "7_v2_profile_ua"
        probes.append(p)

        time.sleep(0.6)

        # 8. v2 active
        p = call("GET", f"{base}/api/v2/browser-profile/active",
                 api_key, params={"profile_id": first_pid})
        p["label"] = "8_v2_active"
        probes.append(p)

        time.sleep(0.6)

        # 9. v2 start
        p = call("POST", f"{base}/api/v2/browser-profile/start",
                 api_key,
                 json={"profile_id": first_pid, "headless": "1", "open_tabs": "0"})
        p["label"] = "9_v2_start"
        probes.append(p)

        time.sleep(0.6)

        # 10. v1 stop (정리)
        p = call("GET", f"{base}/api/v1/browser/stop",
                 api_key, params={"user_id": first_pid})
        p["label"] = "10_v1_stop"
        probes.append(p)

    return {"base_url": base, "probes": probes, "first_profile_id": first_pid}


def main() -> int:
    print("[probe] collecting AdsPower API responses...")
    result = run()

    # 로컬 파일
    path = f"adspower_probe_{int(time.time())}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[probe] saved to {path}")

    # 요약
    print("-" * 60)
    for p in result.get("probes", []):
        label = p["label"]
        status = p.get("status_code", "ERR")
        ms = p.get("elapsed_ms", "?")
        bj = p.get("body_json")
        if isinstance(bj, dict):
            code = bj.get("code", "?")
            msg = bj.get("msg", "?")[:60] if isinstance(bj.get("msg"), str) else str(bj.get("msg", ""))[:60]
            print(f"  {label:40s}  http={status}  code={code}  msg={msg}  {ms}ms")
        else:
            print(f"  {label:40s}  http={status}  (non-json)  {ms}ms")

    # 서버 업로드
    try:
        from worker.config import config as _cfg
        base = _cfg.server_url.rstrip("/")
        tok = _cfg.worker_token
        if base and tok:
            with httpx.Client(timeout=20) as c:
                r = c.post(
                    f"{base}/api/workers/report-error",
                    headers={"X-Worker-Token": tok},
                    json={
                        "kind": "diagnostic",
                        "message": f"adspower api probe: {len(result.get('probes', []))} calls",
                        "context": result,
                    },
                )
                print(f"[probe] uploaded: http {r.status_code}")
    except Exception as e:
        print(f"[probe] upload failed: {e}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
