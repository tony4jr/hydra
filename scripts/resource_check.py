#!/usr/bin/env python3
"""T12 — VPS 리소스 체크 + worker_errors 자동 보고.

cron 매 5분 실행. CPU/RAM/Disk/cert 만료 임계 시 alert.

cron 설치:
    crontab -e
    */5 * * * * /opt/hydra/.venv/bin/python /opt/hydra/scripts/resource_check.py

알림 경로 (우선순위):
1. Telegram (bot token + chat id 있으면) — 즉시 알림
2. worker_errors 테이블 (kind=diagnostic) — 어드민 UI 에서 확인
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# 임계치 (env 로 오버라이드 가능)
CPU_THRESHOLD_PCT = float(os.environ.get("RESOURCE_CPU_THRESHOLD", "85"))
MEM_THRESHOLD_PCT = float(os.environ.get("RESOURCE_MEM_THRESHOLD", "85"))
DISK_THRESHOLD_PCT = float(os.environ.get("RESOURCE_DISK_THRESHOLD", "80"))
CERT_DAYS_THRESHOLD = int(os.environ.get("CERT_DAYS_THRESHOLD", "14"))


def get_cpu_pct() -> float:
    """1초간 CPU 사용률 측정."""
    try:
        # Linux /proc/stat 평균값 — psutil 없이
        import time
        with open("/proc/stat") as f:
            parts1 = f.readline().split()[1:5]
        v1 = [int(x) for x in parts1]
        time.sleep(1)
        with open("/proc/stat") as f:
            parts2 = f.readline().split()[1:5]
        v2 = [int(x) for x in parts2]
        # user + nice + system + idle
        total = sum(v2) - sum(v1)
        idle = v2[3] - v1[3]
        return round(100 * (total - idle) / total, 1) if total > 0 else 0.0
    except Exception:
        return 0.0


def get_mem_pct() -> float:
    try:
        with open("/proc/meminfo") as f:
            lines = f.read().splitlines()
        info = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])  # kB
        total = info.get("MemTotal", 1)
        avail = info.get("MemAvailable", info.get("MemFree", total))
        return round(100 * (total - avail) / total, 1)
    except Exception:
        return 0.0


def get_disk_pct(path: str = "/") -> float:
    try:
        usage = shutil.disk_usage(path)
        return round(100 * usage.used / usage.total, 1)
    except Exception:
        return 0.0


def get_cert_days_remaining(domain: str = "hydra-prod.duckdns.org") -> int | None:
    """Let's Encrypt 인증서 만료까지 남은 일."""
    cert_path = Path(f"/etc/letsencrypt/live/{domain}/cert.pem")
    if not cert_path.is_file():
        return None
    try:
        result = subprocess.run(
            ["openssl", "x509", "-enddate", "-noout", "-in", str(cert_path)],
            capture_output=True, text=True, timeout=10,
        )
        # notAfter=Jul 22 12:34:56 2026 GMT
        line = result.stdout.strip()
        if line.startswith("notAfter="):
            from email.utils import parsedate_to_datetime
            end_str = line.split("=", 1)[1]
            end = datetime.strptime(end_str, "%b %d %H:%M:%S %Y %Z")
            delta = end - datetime.utcnow()
            return delta.days
    except Exception:
        pass
    return None


def report_to_server(level: str, message: str, context: dict) -> None:
    """worker_errors 에 기록 — 워커 토큰이 있으면 사용, 아니면 직접 DB."""
    import httpx
    server = os.environ.get("SERVER_URL", "https://hydra-prod.duckdns.org")
    wt_file = Path(os.environ.get("HYDRA_REPO", "/opt/hydra")) / ".backup_worker_token"
    token = None
    if wt_file.is_file():
        token = wt_file.read_text().strip()

    if token:
        try:
            with httpx.Client(timeout=10) as c:
                c.post(
                    f"{server}/api/workers/report-error",
                    headers={"X-Worker-Token": token},
                    json={
                        "kind": "diagnostic",
                        "message": f"resource_check [{level}]: {message}",
                        "context": context,
                    },
                )
            return
        except Exception:
            pass

    # Fallback: 직접 DB 접근 (cron 이 같은 VPS 에서 돌면 가능)
    try:
        sys.path.insert(0, os.environ.get("HYDRA_REPO", "/opt/hydra"))
        from hydra.db.session import SessionLocal
        from hydra.db.models import WorkerError
        db = SessionLocal()
        try:
            # 직접 보고용 dummy worker_id 가 필요 — id=0 admin/system 으로 등록 필요
            # 또는 가장 첫 워커
            from hydra.db.models import Worker
            w = db.query(Worker).filter(Worker.token_hash.isnot(None)).first()
            if w is None:
                return
            db.add(WorkerError(
                worker_id=w.id,
                kind="diagnostic",
                message=f"resource_check [{level}]: {message}",
                context=json.dumps(context, ensure_ascii=False),
                occurred_at=datetime.now(UTC),
                received_at=datetime.now(UTC),
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[resource_check] report fallback failed: {e}", file=sys.stderr)


def telegram_alert(text: str) -> None:
    """Telegram 봇 알림 (구성된 경우만)."""
    bot = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (bot and chat):
        return
    import httpx
    try:
        with httpx.Client(timeout=10) as c:
            c.post(
                f"https://api.telegram.org/bot{bot}/sendMessage",
                json={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
            )
    except Exception:
        pass


def main() -> int:
    cpu = get_cpu_pct()
    mem = get_mem_pct()
    disk = get_disk_pct()
    cert_days = get_cert_days_remaining()

    metrics = {
        "cpu_pct": cpu, "mem_pct": mem, "disk_pct": disk,
        "cert_days": cert_days,
    }

    alerts = []
    if cpu >= CPU_THRESHOLD_PCT:
        alerts.append(("warning", f"CPU {cpu}% (≥{CPU_THRESHOLD_PCT}%)"))
    if mem >= MEM_THRESHOLD_PCT:
        alerts.append(("warning", f"MEM {mem}% (≥{MEM_THRESHOLD_PCT}%)"))
    if disk >= DISK_THRESHOLD_PCT:
        alerts.append(("critical", f"DISK {disk}% (≥{DISK_THRESHOLD_PCT}%)"))
    if cert_days is not None and cert_days <= CERT_DAYS_THRESHOLD:
        alerts.append(("warning", f"CERT 만료까지 {cert_days}일 (≤{CERT_DAYS_THRESHOLD})"))

    if not alerts:
        # 정상 — 로그만
        print(f"[resource_check] OK cpu={cpu}% mem={mem}% disk={disk}% cert={cert_days}d")
        return 0

    summary = "; ".join(m for _, m in alerts)
    print(f"[resource_check] ALERT {summary}")
    for level, msg in alerts:
        report_to_server(level, msg, metrics)
        telegram_alert(f"⚠️ HYDRA *{level}*: {msg}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
