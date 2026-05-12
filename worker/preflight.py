"""PR-Preflight: 워커 환경 진단 — heartbeat / run_diag command 에서 호출.

목적:
- 워커가 자기 ADB / AdsPower / 시스템 자원 상태를 매 heartbeat 마다 서버에 보고.
- 서버가 capability 불완전 워커에겐 task 안 줌 (fetch gate).
- 사용자가 워커 PC 직접 안 만지고도 admin UI 에서 진단 가능.

설계:
- 가벼운 호출 (timeout 짧음, 캐시 X) — 매 heartbeat 마다 새로 측정.
- 실패해도 default 값 반환 — heartbeat 자체는 절대 막지 않음.
"""
from __future__ import annotations

import os
import platform
import subprocess
from typing import Optional

try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def list_adb_devices(timeout_sec: int = 3) -> list[str]:
    """`adb devices` 실행해서 device ID 목록 반환.

    실패/timeout/adb 미설치 등 모든 예외 → 빈 배열.
    """
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True, text=True, timeout=timeout_sec,
        )
        # 출력 예:
        #   List of devices attached
        #   R3CRA0QNFXK	device
        #   1234        unauthorized
        # → "device" 상태인 라인만 ID 추출.
        ids = []
        for line in result.stdout.strip().split("\n")[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                ids.append(parts[0])
        return ids
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    except Exception:
        return []


def adspower_ping(timeout_sec: int = 3) -> dict:
    """AdsPower local API 헬스 체크. 응답 없으면 ok=False.

    Returns: {"ok": bool, "version": str | None, "error": str | None}
    """
    import urllib.request
    import json
    url = "http://localhost:50325/api/v1/user/list?page=1&page_size=1"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode())
            return {"ok": data.get("code") == 0, "version": "unknown", "error": None}
    except Exception as e:
        return {"ok": False, "version": None, "error": f"{type(e).__name__}"}


def system_health() -> dict:
    """CPU / 메모리 / 디스크 사용량. psutil 없으면 0 반환."""
    if not _HAS_PSUTIL:
        return {"cpu_percent": 0.0, "mem_used_mb": 0, "disk_free_gb": 0.0}
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        vm = psutil.virtual_memory()
        # Windows 워킹디렉토리 기준 디스크.
        try:
            disk = psutil.disk_usage(os.getcwd() if os.name == "nt" else "/")
            disk_free_gb = round(disk.free / 1024**3, 1)
        except Exception:
            disk_free_gb = 0.0
        return {
            "cpu_percent": round(float(cpu), 1),
            "mem_used_mb": int(vm.used / 1024**2),
            "disk_free_gb": disk_free_gb,
        }
    except Exception:
        return {"cpu_percent": 0.0, "mem_used_mb": 0, "disk_free_gb": 0.0}


def collect_health(*, include_adspower: bool = True) -> dict:
    """heartbeat 한 번에 다 넘길 통합 health.

    Returns:
        {
            "version": str (코드 호출 측에서 주입),
            "os_type": str,
            "cpu_percent": float,
            "mem_used_mb": int,
            "disk_free_gb": float,
            "adb_devices": list[str],
            "adspower_version": str,
            "playwright_browsers_ok": bool,
        }
    """
    adb = list_adb_devices()
    sys_h = system_health()
    adspower = adspower_ping() if include_adspower else {"ok": True, "version": "skipped"}
    return {
        "os_type": platform.system().lower(),
        "cpu_percent": sys_h["cpu_percent"],
        "mem_used_mb": sys_h["mem_used_mb"],
        "disk_free_gb": sys_h["disk_free_gb"],
        "adb_devices": adb,
        "adspower_version": adspower.get("version") or "",
        "playwright_browsers_ok": True,  # PR-Preflight2 에서 실제 체크 추가
    }
