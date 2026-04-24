#!/usr/bin/env python3
"""AdsPower SunBrowser 커널 프리로드 — v2 API 사용 (명시적 다운로드).

이전 버전은 browser/start 실패 메시지에서 필요 버전을 추측하는 반강제식이었음.
AdsPower 공식 v2 API 의 download-kernel 엔드포인트가 존재 (Postman 문서에서
확인됨) → 훨씬 깔끔하게 다운로드 가능.

동작:
1. GET  /api/v2/browser-profile/kernels           — 이미 설치된 커널 확인
2. POST /api/v2/browser-profile/list              — 모든 프로필 + 각자 kernel 정보
3. 각 프로필 /api/v1/browser/start 로 즉시성 검증
4. "is updating" / "automatic update failed" / "is not ready" 나오면 버전 추출
5. POST /api/v2/browser-profile/download-kernel   ⭐ 명시적 버전 지정 다운로드
6. 다운로드 완료 대기 (kernels 재조회로 폴링)
7. 재시도

Rate limit:
- /api/v1/user/list, /api/v2/browser-profile/list 는 고정 1 req/sec
- 기타 GET/POST 는 2 req/sec (0-200 프로필 티어)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import httpx


MAX_ROUNDS = 8
ROUND_INTERVAL_SEC = 45
START_TIMEOUT = 30
REQ_SPACING_SEC = 0.6  # 2 req/sec 보다 여유
LIST_SPACING_SEC = 1.2  # list 엔드포인트 1 req/sec

VERSION_RE = re.compile(r"SunBrowser\s+(\d+)", re.IGNORECASE)


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


def _h(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def get_kernels(base_url: str, api_key: str, verbose: bool = True) -> tuple[list, dict]:
    """설치된 커널 리스트 + raw 응답 (디버깅용)."""
    with httpx.Client(timeout=15) as c:
        r = c.get(f"{base_url}/api/v2/browser-profile/kernels", headers=_h(api_key))
        raw_body = r.text
        try:
            d = r.json()
        except Exception:
            return [], {"_raw": raw_body[:500], "_status": r.status_code}
        if verbose:
            print(f"  [kernels raw] status={r.status_code} code={d.get('code')} msg={d.get('msg','')} data_type={type(d.get('data')).__name__}")
        if d.get("code") != 0:
            return [], d
        data = d.get("data")
        # data 가 list 직접일 수도, dict.list 일 수도
        if isinstance(data, list):
            return data, d
        if isinstance(data, dict):
            for key in ("list", "kernels", "items"):
                if isinstance(data.get(key), list):
                    return data[key], d
            return [], d
        return [], d


def list_profiles(base_url: str, api_key: str, verbose: bool = True) -> list[dict]:
    """모든 프로필. v2 시도 → 실패 시 v1 fallback (50개 정상 반환 확인된 경로)."""
    # v2 먼저
    out: list[dict] = []
    page = 1
    while True:
        time.sleep(LIST_SPACING_SEC)
        with httpx.Client(timeout=20) as c:
            r = c.post(
                f"{base_url}/api/v2/browser-profile/list",
                headers=_h(api_key),
                json={"page": page, "page_size": 100},
            )
            try:
                d = r.json()
            except Exception:
                if verbose:
                    print(f"  [list v2] raw body (first 300): {r.text[:300]}")
                break
            if verbose and page == 1:
                print(f"  [list v2] code={d.get('code')} msg={d.get('msg','')} "
                      f"data_keys={list(d.get('data',{}).keys()) if isinstance(d.get('data'), dict) else type(d.get('data')).__name__}")
            if d.get("code") != 0:
                break
            lst = d.get("data", {}).get("list", []) if isinstance(d.get("data"), dict) else []
            if not lst:
                break
            out.extend(lst)
            if len(lst) < 100:
                break
            page += 1

    if out:
        return out

    # v1 fallback
    print("  [list] v2 returned empty, falling back to v1 /api/v1/user/list")
    with httpx.Client(timeout=20) as c:
        r = c.get(
            f"{base_url}/api/v1/user/list",
            params={"page": 1, "page_size": 100},
            headers=_h(api_key),
        )
        d = r.json()
        if d.get("code") == 0:
            return d.get("data", {}).get("list", [])
    return []


def try_start(base_url: str, api_key: str, profile_id: str) -> dict:
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=START_TIMEOUT) as c:
            r = c.get(
                f"{base_url}/api/v1/browser/start",
                params={"user_id": profile_id, "open_tabs": 0, "headless": 1},
                headers=_h(api_key),
            )
            data = r.json()
            elapsed = round((time.perf_counter() - t0) * 1000, 1)
            if data.get("code") == 0:
                return {"ok": True, "ms": elapsed}
            msg = data.get("msg", "?")
            m = VERSION_RE.search(msg)
            return {"ok": False, "ms": elapsed, "msg": msg,
                    "version": int(m.group(1)) if m else None}
    except Exception as e:
        return {"ok": False, "ms": 0, "msg": f"{type(e).__name__}: {e}"}


def try_stop(base_url: str, api_key: str, profile_id: str) -> None:
    try:
        with httpx.Client(timeout=15) as c:
            c.get(f"{base_url}/api/v1/browser/stop",
                  params={"user_id": profile_id}, headers=_h(api_key))
    except Exception:
        pass


def download_kernel(base_url: str, api_key: str, version: int,
                    kernel_type: str = "Chrome") -> dict:
    """명시적 버전 다운로드 요청. 응답은 즉시 — 실제 다운로드는 백그라운드."""
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{base_url}/api/v2/browser-profile/download-kernel",
            headers=_h(api_key),
            json={"kernel_type": kernel_type, "kernel_version": str(version)},
        )
        try:
            d = r.json()
            # 전체 응답 디버그 로깅
            d["_http_status"] = r.status_code
            return d
        except Exception:
            return {"code": -1, "msg": f"http {r.status_code} (non-json): {r.text[:200]}"}


def installed_versions(kernels: list[dict]) -> set[str]:
    """kernels 엔드포인트 응답에서 버전 문자열 집합 추출 (방어적)."""
    out: set[str] = set()
    for k in kernels:
        if isinstance(k, dict):
            for key in ("version", "kernel_version", "chromium_version"):
                if k.get(key):
                    out.add(str(k[key]))
        elif isinstance(k, str):
            out.add(k)
    return out


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
                    "message": f"kernel preload v2: {summary.get('summary_line', '?')}",
                    "context": summary,
                },
            )
            print("[preload] uploaded to server")
    except Exception as e:
        print(f"[preload] server upload FAILED: {e}")


def main() -> int:
    base_url = os.environ.get("ADSPOWER_API_URL", "http://127.0.0.1:50325")
    api_key = _get_api_key_from_heartbeat()
    if not api_key:
        print("[preload] ERROR: AdsPower API key not available")
        return 2

    print(f"[preload] AdsPower URL: {base_url}")
    print(f"[preload] Fetching kernels + profiles...")
    kernels, kernels_raw = get_kernels(base_url, api_key)
    installed = installed_versions(kernels)
    print(f"[preload] installed kernels (parsed): {sorted(installed) if installed else 'empty'}")
    if not installed:
        print(f"[preload] DEBUG — kernels raw response: {json.dumps(kernels_raw, ensure_ascii=False)[:500]}")

    profiles = list_profiles(base_url, api_key)
    print(f"[preload] profiles: {len(profiles)}")
    if len(profiles) < 10:
        print(f"[preload] DEBUG — profiles sample: {json.dumps(profiles[:2], ensure_ascii=False)[:500]}")

    # 상태 초기화
    state: dict[str, dict] = {
        p["profile_id"]: {"name": p.get("name", "?"), "status": "pending",
                          "kernel": p.get("chromium_version") or p.get("kernel_version")}
        for p in profiles
    }

    download_requested: set[str] = set()

    for rnd in range(1, MAX_ROUNDS + 1):
        pending = [pid for pid, s in state.items()
                   if s["status"] in ("pending", "needs_download", "downloading")]
        if not pending:
            print(f"[preload] all profiles ready after round {rnd-1}")
            break
        print(f"\n--- round {rnd}/{MAX_ROUNDS} — {len(pending)} pending ---")

        for pid in pending:
            s = state[pid]
            time.sleep(REQ_SPACING_SEC)
            res = try_start(base_url, api_key, pid)
            if res["ok"]:
                try_stop(base_url, api_key, pid)
                s["status"] = "ok"
                s["ms"] = res["ms"]
                print(f"  ✓ {pid} ({s['name']})  {res['ms']}ms")
                continue

            msg = res.get("msg", "")
            version = res.get("version")
            if version is not None:
                ver_str = str(version)
                s["needs_version"] = ver_str
                s["last_msg"] = msg[:120]
                if ver_str not in download_requested:
                    # 명시적 다운로드 트리거
                    dk = download_kernel(base_url, api_key, version)
                    download_requested.add(ver_str)
                    # 전체 응답 출력 (디버그)
                    print(f"  ⬇ download-kernel v{version} → code={dk.get('code')} msg={dk.get('msg','(empty)')[:150]} http={dk.get('_http_status')}")
                s["status"] = "downloading" if dk.get("code") == 0 else "needs_download"
            else:
                # 버전 추출 불가 — 다른 류 에러
                s["status"] = "broken"
                s["last_msg"] = msg[:120]
                print(f"  ✗ {pid} ({s['name']})  {msg[:100]}")

        # 다운로드 대기 + kernels 재조회
        if rnd < MAX_ROUNDS:
            downloading = [p for p, s in state.items() if s["status"] in ("downloading", "needs_download")]
            if downloading:
                print(f"[preload] sleeping {ROUND_INTERVAL_SEC}s for kernel downloads...")
                time.sleep(ROUND_INTERVAL_SEC)
                # 새 kernels 체크
                new_kernels = installed_versions(get_kernels(base_url, api_key))
                added = new_kernels - installed
                if added:
                    print(f"[preload] new kernels installed: {sorted(added)}")
                installed = new_kernels

    # 요약
    ok = sum(1 for s in state.values() if s["status"] == "ok")
    broken = sum(1 for s in state.values() if s["status"] == "broken")
    pending_left = sum(1 for s in state.values() if s["status"] != "ok" and s["status"] != "broken")

    print("\n" + "=" * 60)
    print(f"[preload] ok: {ok}/{len(state)}  broken: {broken}  pending: {pending_left}")
    print(f"[preload] installed kernels final: {sorted(installed_versions(get_kernels(base_url, api_key)))}")

    summary_line = f"{ok}/{len(state)} ok, {broken} broken, {pending_left} pending"
    report_to_server({
        "total": len(state),
        "ok": ok,
        "broken": broken,
        "pending": pending_left,
        "installed_kernels": sorted(installed),
        "download_triggered": sorted(download_requested),
        "per_profile": state,
        "summary_line": summary_line,
    })
    return 0 if ok == len(state) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[preload] interrupted")
        sys.exit(130)
