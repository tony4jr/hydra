#!/usr/bin/env python3
"""Stage B 진단 — AdsPower 3 프로필 실 기동 검증.

각 프로필에 대해:
  1. Local API /api/v1/user/list → 존재 확인
  2. /api/v1/browser/start → 브라우저 기동 (Playwright 연결 URL 획득)
  3. Playwright 로 연결 → about:blank 열기
  4. 1초 대기 후 닫기
  5. /api/v1/browser/stop

YouTube 접근 안 함. 브라우저 안티디텍션 스택(프로필+Playwright) 자체만 검증.
결과를 서버 worker_errors (kind=diagnostic) 로 업로드.

사용:
    cd C:\\hydra
    .\\.venv\\Scripts\\python.exe scripts\\diag_adspower_profiles.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx


TARGET_PROFILES = ["k1bmpnnw", "k1bmpnpk", "k1bmpnry"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_api_key() -> str:
    # secrets.enc → os.environ 주입이 되었거나, setup 에서 Machine env var 로 넣었거나
    key = os.environ.get("ADSPOWER_API_KEY", "")
    if not key:
        try:
            from hydra.core.config import settings
            key = settings.adspower_api_key
        except Exception:
            pass
    return key


def ads_list_profiles(base_url: str, api_key: str) -> dict:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    with httpx.Client(timeout=15) as c:
        r = c.get(f"{base_url}/api/v1/user/list",
                  params={"page": 1, "page_size": 100},
                  headers=headers)
        r.raise_for_status()
        return r.json()


def ads_start_browser(base_url: str, api_key: str, profile_id: str) -> dict:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    with httpx.Client(timeout=60) as c:
        r = c.get(f"{base_url}/api/v1/browser/start",
                  params={"user_id": profile_id, "open_tabs": 0,
                          "launch_args": '["--disable-blink-features=AutomationControlled"]'},
                  headers=headers)
        r.raise_for_status()
        return r.json()


def ads_stop_browser(base_url: str, api_key: str, profile_id: str) -> dict:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{base_url}/api/v1/browser/stop",
                  params={"user_id": profile_id},
                  headers=headers)
        r.raise_for_status()
        return r.json()


async def playwright_touch(puppeteer_ws: str) -> dict:
    from playwright.async_api import async_playwright
    t0 = time.perf_counter()
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(puppeteer_ws)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()
        await page.goto("about:blank", timeout=15000)
        title = await page.title()
        await page.close()
        try:
            await browser.close()  # CDP over remote — might not fully close, we stop via API
        except Exception:
            pass
    return {"ok": True, "ms": round((time.perf_counter() - t0) * 1000, 1), "title": title}


async def probe_one(base_url: str, api_key: str, profile_id: str) -> dict:
    rec: dict = {"profile": profile_id, "t": _now()}

    # 1. start
    t0 = time.perf_counter()
    try:
        start = ads_start_browser(base_url, api_key, profile_id)
        if start.get("code") != 0:
            rec["error"] = f"AdsPower start failed: {start}"
            rec["ok"] = False
            return rec
        ws = start["data"]["ws"]["puppeteer"]
        rec["start_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        rec["ws"] = ws
    except Exception as e:
        rec["error"] = f"start exception: {type(e).__name__}: {e}"
        rec["ok"] = False
        return rec

    # 2. playwright touch
    try:
        touch = await playwright_touch(ws)
        rec["playwright"] = touch
    except Exception as e:
        rec["playwright"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # 3. stop
    try:
        ads_stop_browser(base_url, api_key, profile_id)
        rec["stopped"] = True
    except Exception as e:
        rec["stopped"] = False
        rec["stop_error"] = f"{type(e).__name__}: {e}"

    rec["ok"] = rec.get("playwright", {}).get("ok", False) and rec.get("stopped", False)
    return rec


def report_to_server(summary: dict) -> None:
    try:
        from worker.config import config as _cfg
        token = _cfg.worker_token or os.environ.get("WORKER_TOKEN", "")
        base_url = _cfg.server_url.rstrip("/")
    except Exception:
        token = os.environ.get("WORKER_TOKEN", "")
        base_url = os.environ.get("SERVER_URL", "").rstrip("/")
    if not token or not base_url:
        print("[diag] server upload skipped — no WORKER_TOKEN/SERVER_URL")
        return
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(
                f"{base_url}/api/workers/report-error",
                headers={"X-Worker-Token": token},
                json={
                    "kind": "diagnostic",
                    "message": f"adspower profiles: {summary.get('summary_line', '?')}",
                    "context": summary,
                },
            )
            r.raise_for_status()
            print(f"[diag] uploaded to server ({r.status_code})")
    except Exception as e:
        print(f"[diag] server upload FAILED: {type(e).__name__}: {e}")


async def main() -> int:
    base_url = os.environ.get("ADSPOWER_API_URL", "http://local.adspower.net:50325")
    api_key = _get_api_key()
    if not api_key:
        print("[diag] ERROR: ADSPOWER_API_KEY not set (secrets.enc 또는 Machine env var)")
        return 2

    print(f"[diag] ADSPOWER_API_URL={base_url}")
    print(f"[diag] API key: {api_key[:6]}...{api_key[-4:]}")

    # 1. 존재 확인
    print("[diag] fetching profile list...")
    lst = ads_list_profiles(base_url, api_key)
    if lst.get("code") != 0:
        print(f"[diag] list failed: {lst}")
        return 3
    all_profiles = {p["user_id"]: p.get("name", "?") for p in lst["data"]["list"]}
    print(f"[diag] total profiles on AdsPower: {len(all_profiles)}")

    missing = [p for p in TARGET_PROFILES if p not in all_profiles]
    present = [p for p in TARGET_PROFILES if p in all_profiles]
    print(f"[diag] target present: {present}")
    if missing:
        print(f"[diag] target MISSING: {missing}")

    # 2. 각 존재 프로필 기동
    print("-" * 60)
    results = []
    for pid in present:
        print(f"[diag] probing {pid} ({all_profiles[pid]})...")
        res = await probe_one(base_url, api_key, pid)
        results.append(res)
        mark = "✓" if res.get("ok") else "✗"
        summary = (
            f"start={res.get('start_ms', '?')}ms  "
            f"pw={res.get('playwright', {}).get('ok', '?')}  "
            f"stopped={res.get('stopped', '?')}"
        )
        print(f"  {mark} {pid}  {summary}")
        if not res.get("ok"):
            print(f"    error: {res.get('error') or res.get('playwright', {}).get('error')}")
        await asyncio.sleep(2)  # 연속 기동 간 휴식

    # 3. 요약 + 업로드
    ok_count = sum(1 for r in results if r.get("ok"))
    summary_line = f"{ok_count}/{len(results)} profiles healthy  missing={len(missing)}"
    print("-" * 60)
    print(f"[diag] {summary_line}")

    report_to_server({
        "targets": TARGET_PROFILES,
        "present": present,
        "missing": missing,
        "results": results,
        "summary_line": summary_line,
    })

    return 0 if ok_count == len(TARGET_PROFILES) else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
