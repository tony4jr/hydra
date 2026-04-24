#!/usr/bin/env python3
"""DNS + HTTP 간헐 실패 진단 스크립트.

3분간 3초마다 다음을 동시 측정:
  1) socket.getaddrinfo(host, 443) — AF_UNSPEC
  2) socket.getaddrinfo(host, 443, AF_INET)  — IPv4 only
  3) socket.getaddrinfo(host, 443, AF_INET6) — IPv6 only
  4) httpx GET /healthz (dual-stack)
  5) httpx GET /healthz (IPv4 forced via local_address)
  6) httpx POST /api/workers/heartbeat/v2 (IPv4 forced, probe token)
  7) Windows ipconfig DNS 서버 목록

각 시각의 결과를 diag_dns_http_<epoch>.log 에 JSON lines 로 기록.
실행 끝나면 실패율 요약 출력.

사용:
    cd C:\\hydra
    .\\.venv\\Scripts\\python.exe scripts\\diag_dns_http.py
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

import httpx

HOST = "hydra-prod.duckdns.org"
URL_HEALTH = f"https://{HOST}/healthz"
URL_HB = f"https://{HOST}/api/workers/heartbeat/v2"
DURATION_SEC = 180
INTERVAL_SEC = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def probe_getaddrinfo(family: int | None) -> dict:
    t0 = time.perf_counter()
    try:
        if family is None:
            result = socket.getaddrinfo(HOST, 443)
        else:
            result = socket.getaddrinfo(HOST, 443, family)
        return {
            "ok": True,
            "ms": round((time.perf_counter() - t0) * 1000, 1),
            "addrs": [r[4][0] for r in result],
        }
    except Exception as e:
        return {
            "ok": False,
            "ms": round((time.perf_counter() - t0) * 1000, 1),
            "err": f"{type(e).__name__}: {e}",
        }


def probe_httpx(url: str, method: str, ipv4_only: bool, **kwargs) -> dict:
    t0 = time.perf_counter()
    transport = httpx.HTTPTransport(local_address="0.0.0.0") if ipv4_only else None
    try:
        with httpx.Client(timeout=10, transport=transport) as c:
            resp = c.request(method, url, **kwargs)
            return {
                "ok": True,
                "ms": round((time.perf_counter() - t0) * 1000, 1),
                "status": resp.status_code,
            }
    except Exception as e:
        return {
            "ok": False,
            "ms": round((time.perf_counter() - t0) * 1000, 1),
            "err": f"{type(e).__name__}: {e}",
        }


def get_dns_servers() -> list[str]:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-DnsClientServerAddress -AddressFamily IPv4,IPv6 | "
             "Where-Object {$_.ServerAddresses}).ServerAddresses"],
            timeout=5, text=True,
        )
        return [s.strip() for s in out.splitlines() if s.strip()]
    except Exception:
        return []


def report_to_server(summary: dict) -> bool:
    """진단 결과를 서버 /api/workers/report-error 로 업로드.

    worker_token 을 env 또는 config 에서 읽음. 실패 시 False.
    """
    import os
    try:
        from worker.config import config as _cfg
        token = _cfg.worker_token or os.environ.get("WORKER_TOKEN", "")
        base_url = _cfg.server_url.rstrip("/")
    except Exception:
        token = os.environ.get("WORKER_TOKEN", "")
        base_url = os.environ.get("SERVER_URL", "").rstrip("/")
    if not token or not base_url:
        print("[diag] server upload skipped — no WORKER_TOKEN/SERVER_URL")
        return False

    try:
        with httpx.Client(timeout=15) as c:
            r = c.post(
                f"{base_url}/api/workers/report-error",
                headers={"X-Worker-Token": token},
                json={
                    "kind": "diagnostic",
                    "message": f"dns_http diag: {summary.get('summary_line', '?')}",
                    "context": summary,
                },
            )
            r.raise_for_status()
            print(f"[diag] uploaded to server ({r.status_code})")
            return True
    except Exception as e:
        print(f"[diag] server upload FAILED: {type(e).__name__}: {e}")
        return False


def run() -> None:
    log_path = f"diag_dns_http_{int(time.time())}.log"
    print(f"[diag] Logging to {log_path}")
    print(f"[diag] Running for {DURATION_SEC}s, every {INTERVAL_SEC}s")
    print(f"[diag] DNS servers: {get_dns_servers()}")
    print("-" * 60)

    start = time.time()
    records = []
    iteration = 0
    with open(log_path, "w", encoding="utf-8") as f:
        while time.time() - start < DURATION_SEC:
            iteration += 1
            rec = {
                "iter": iteration,
                "t": _now(),
                "gai_any": probe_getaddrinfo(None),
                "gai_v4": probe_getaddrinfo(socket.AF_INET),
                "gai_v6": probe_getaddrinfo(socket.AF_INET6),
                "http_get_any": probe_httpx(URL_HEALTH, "GET", ipv4_only=False),
                "http_get_v4": probe_httpx(URL_HEALTH, "GET", ipv4_only=True),
                "http_post_v4": probe_httpx(
                    URL_HB, "POST", ipv4_only=True,
                    headers={"X-Worker-Token": "probe"},
                    json={"version": "diag", "os_type": "windows"},
                ),
            }
            records.append(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()

            # 콘솔 한 줄 요약
            marks = []
            for k in ("gai_any", "gai_v4", "gai_v6",
                      "http_get_any", "http_get_v4", "http_post_v4"):
                marks.append("✓" if rec[k]["ok"] else "✗")
            print(f"[{iteration:3d}] {' '.join(marks)}  "
                  f"gai_any={rec['gai_any'].get('ms', '?')}ms  "
                  f"get_any={rec['http_get_any'].get('ms', '?')}ms")

            time.sleep(INTERVAL_SEC)

    # 요약
    print("-" * 60)
    print(f"[diag] Completed {iteration} iterations")
    keys = ["gai_any", "gai_v4", "gai_v6",
            "http_get_any", "http_get_v4", "http_post_v4"]
    per_key: dict = {}
    for k in keys:
        fails = [r[k] for r in records if not r[k]["ok"]]
        errs: dict = {}
        for r in fails:
            e = r.get("err", "?")
            errs[e] = errs.get(e, 0) + 1
        per_key[k] = {
            "fail_count": len(fails),
            "fail_rate_pct": round(100 * len(fails) / max(iteration, 1), 1),
            "top_errors": dict(sorted(errs.items(), key=lambda x: -x[1])[:3]),
        }
        print(f"  {k:14s}: {len(fails)}/{iteration} fail "
              f"({per_key[k]['fail_rate_pct']}%)")
        for e, c in per_key[k]["top_errors"].items():
            print(f"      {c}x  {e}")

    print(f"\n로그 전체: {log_path}")

    # 서버 업로드
    summary_line = " / ".join(
        f"{k}:{per_key[k]['fail_rate_pct']}%" for k in keys
    )
    print("-" * 60)
    report_to_server({
        "iterations": iteration,
        "duration_sec": DURATION_SEC,
        "dns_servers": get_dns_servers(),
        "per_probe": per_key,
        "summary_line": summary_line,
        # 실패 샘플 10건 (원인 진단용)
        "fail_samples": [
            {k: r[k] for k in keys if not r[k]["ok"]} | {"iter": r["iter"], "t": r["t"]}
            for r in records
            if any(not r[k]["ok"] for k in keys)
        ][:10],
    })


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n[diag] Interrupted")
        sys.exit(130)
