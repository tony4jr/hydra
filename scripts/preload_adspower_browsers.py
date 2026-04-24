#!/usr/bin/env python3
"""AdsPower SunBrowser 버전 프리로드 유틸리티.

각 AdsPower 프로필은 독립적으로 SunBrowser(Chromium fork) 버전을 고정하므로,
처음 기동 시 해당 버전이 로컬에 없으면 "is updating, waiting for download"
에러로 실패. 실운영 전 이 스크립트로 모든 버전을 미리 다운받아 두면
이후 기동이 빠름.

동작:
1. /api/v1/user/list 로 전 프로필 조회 (각 프로필의 browser_kernel 포함)
2. 프로필별로 browser/start 시도 → 실패 메시지에서 필요 버전 추출
3. AdsPower 는 실패 시 백그라운드로 해당 버전 다운로드 시작
4. 대기 후 재시도 — 전부 기동 성공할 때까지 max_rounds 반복
5. 결과를 서버 worker_errors (kind=diagnostic) 로 업로드

사용:
    cd C:\\hydra
    .\\.venv\\Scripts\\python.exe scripts\\preload_adspower_browsers.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import httpx


MAX_ROUNDS = 6         # 최대 6회 재시도 라운드
ROUND_INTERVAL_SEC = 60  # 각 라운드 사이 60초 대기 (AdsPower 다운로드 진행)
START_TIMEOUT = 30
# AdsPower 공식 rate limit: 0-200 프로필 티어에서 2 req/sec.
# 안전 여유로 프로필당 600ms 간격 (1.66 req/sec).
REQ_SPACING_SEC = 0.6

VERSION_RE = re.compile(r"SunBrowser\s+(\d+)\s+is updating", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_api_key_from_heartbeat() -> str:
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


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def ads_list_profiles(base_url: str, api_key: str) -> list[dict]:
    with httpx.Client(timeout=15) as c:
        r = c.get(
            f"{base_url}/api/v1/user/list",
            params={"page": 1, "page_size": 100},
            headers=_headers(api_key),
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"user/list failed: {data}")
        return data["data"]["list"]


def try_start(base_url: str, api_key: str, profile_id: str) -> dict:
    """기동 시도 — 성공/실패 모두 dict 로 반환."""
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=START_TIMEOUT) as c:
            r = c.get(
                f"{base_url}/api/v1/browser/start",
                params={"user_id": profile_id, "open_tabs": 0, "headless": 1},
                headers=_headers(api_key),
            )
            data = r.json()
            elapsed = round((time.perf_counter() - t0) * 1000, 1)
            if data.get("code") == 0:
                return {"ok": True, "ms": elapsed, "ws": data["data"]["ws"]["puppeteer"]}
            msg = data.get("msg", "?")
            m = VERSION_RE.search(msg)
            return {"ok": False, "ms": elapsed, "msg": msg,
                    "needs_version": int(m.group(1)) if m else None}
    except Exception as e:
        return {"ok": False, "ms": round((time.perf_counter() - t0) * 1000, 1),
                "msg": f"{type(e).__name__}: {e}"}


def try_stop(base_url: str, api_key: str, profile_id: str) -> None:
    try:
        with httpx.Client(timeout=15) as c:
            c.get(
                f"{base_url}/api/v1/browser/stop",
                params={"user_id": profile_id},
                headers=_headers(api_key),
            )
    except Exception:
        pass


def report_to_server(summary: dict) -> None:
    try:
        from worker.config import config as _cfg
        base = _cfg.server_url.rstrip("/")
        tok = _cfg.worker_token
        if not (base and tok):
            return
        with httpx.Client(timeout=15) as c:
            c.post(
                f"{base}/api/workers/report-error",
                headers={"X-Worker-Token": tok},
                json={
                    "kind": "diagnostic",
                    "message": f"browser preload: {summary.get('summary_line', '?')}",
                    "context": summary,
                },
            )
            print(f"[preload] uploaded to server")
    except Exception as e:
        print(f"[preload] server upload FAILED: {e}")


def main() -> int:
    base_url = os.environ.get("ADSPOWER_API_URL", "http://127.0.0.1:50325")
    api_key = _get_api_key_from_heartbeat()
    if not api_key:
        print("[preload] ERROR: AdsPower API key not available")
        return 2

    print(f"[preload] AdsPower URL: {base_url}")
    print(f"[preload] Fetching profile list...")
    profiles = ads_list_profiles(base_url, api_key)
    print(f"[preload] Found {len(profiles)} profiles")

    # 프로필별 상태: pending (아직 시도 안 함) / ok / downloading (대기) / broken
    state: dict[str, dict] = {p["user_id"]: {"name": p.get("name", "?"),
                                              "status": "pending"}
                              for p in profiles}

    versions_needed: set[int] = set()

    for round_num in range(1, MAX_ROUNDS + 1):
        pending = [pid for pid, s in state.items()
                   if s["status"] in ("pending", "downloading")]
        if not pending:
            print(f"[preload] all profiles ready after round {round_num - 1}")
            break
        print(f"\n--- round {round_num}/{MAX_ROUNDS} — {len(pending)} profiles to probe ---")
        for pid in pending:
            s = state[pid]
            time.sleep(REQ_SPACING_SEC)  # rate limit 존중
            res = try_start(base_url, api_key, pid)
            if res["ok"]:
                try_stop(base_url, api_key, pid)
                s["status"] = "ok"
                s["ms"] = res["ms"]
                print(f"  ✓ {pid} ({s['name']})  {res['ms']}ms")
            elif res.get("needs_version"):
                v = res["needs_version"]
                versions_needed.add(v)
                s["status"] = "downloading"
                s["needs_version"] = v
                s["last_msg"] = res["msg"]
                print(f"  ⏳ {pid} ({s['name']})  needs SunBrowser {v} — waiting")
            else:
                s["status"] = "broken"
                s["last_msg"] = res.get("msg", "?")
                print(f"  ✗ {pid} ({s['name']})  {res.get('msg', '?')[:80]}")

        still_downloading = [p for p, s in state.items() if s["status"] == "downloading"]
        if still_downloading and round_num < MAX_ROUNDS:
            print(f"[preload] sleeping {ROUND_INTERVAL_SEC}s for AdsPower downloads...")
            time.sleep(ROUND_INTERVAL_SEC)

    # 요약
    ok_count = sum(1 for s in state.values() if s["status"] == "ok")
    downloading_count = sum(1 for s in state.values() if s["status"] == "downloading")
    broken_count = sum(1 for s in state.values() if s["status"] == "broken")

    print("\n" + "=" * 60)
    print(f"[preload] Results:")
    print(f"  ok:          {ok_count}/{len(state)}")
    print(f"  downloading: {downloading_count} (retry later)")
    print(f"  broken:      {broken_count}")
    print(f"  versions encountered: {sorted(versions_needed)}")

    if broken_count:
        print("\n[preload] broken profiles (need manual attention):")
        for pid, s in state.items():
            if s["status"] == "broken":
                print(f"  {pid} ({s['name']}): {s.get('last_msg', '?')}")

    summary_line = f"{ok_count}/{len(state)} ok, {downloading_count} downloading, {broken_count} broken"
    report_to_server({
        "total": len(state),
        "ok": ok_count,
        "downloading": downloading_count,
        "broken": broken_count,
        "versions": sorted(versions_needed),
        "per_profile": state,
        "summary_line": summary_line,
    })

    return 0 if broken_count == 0 and downloading_count == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[preload] interrupted")
        sys.exit(130)
