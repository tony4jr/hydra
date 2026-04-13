"""IP rotation via ADB airplane mode toggle.

Spec Part 10:
- Absolute rule: 1 IP = 1 account at a time
- Airplane on → 3s → off → 15s → verify new IP
- Max 3 retries per rotation
- Log IP-account mapping to DB
"""

import asyncio
import subprocess
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from hydra.core.config import settings
from hydra.core.logger import get_logger
from hydra.db.models import IpLog

log = get_logger("ip")


async def _adb_shell(device_id: str, command: str) -> str:
    """Run ADB shell command."""
    cmd = ["adb", "-s", device_id, "shell", command]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ADB error: {stderr.decode().strip()}")
    return stdout.decode().strip()


async def _get_current_ip(device_id: str) -> str:
    """Get current public IP from the device."""
    # Use Android's connectivity to get external IP
    result = await _adb_shell(device_id, "curl -s ifconfig.me")
    return result.strip()


async def rotate_ip(device_id: str, max_retries: int = 3) -> str:
    """Rotate IP using the active provider, falling back to ADB.

    Returns new IP address.
    Raises RuntimeError after max_retries failures.
    """
    # Use pluggable provider if available
    from hydra.infra.ip_provider import get_provider
    provider = get_provider()
    if provider:
        return await provider.rotate()

    # Fallback: original ADB airplane mode
    previous_ip = await _get_current_ip(device_id)

    for attempt in range(1, max_retries + 1):
        log.info(f"IP rotation attempt {attempt}/{max_retries} (current: {previous_ip})")

        # Airplane ON
        await _adb_shell(device_id, "cmd connectivity airplane-mode enable")
        await asyncio.sleep(3)

        # Airplane OFF
        await _adb_shell(device_id, "cmd connectivity airplane-mode disable")

        # Wait for network reconnect (escalating wait)
        wait = 15 * attempt
        await asyncio.sleep(wait)

        # Check new IP
        try:
            new_ip = await _get_current_ip(device_id)
        except Exception as e:
            log.warning(f"IP check failed on attempt {attempt}: {e}")
            continue

        if new_ip and new_ip != previous_ip:
            log.info(f"IP rotated: {previous_ip} → {new_ip}")
            return new_ip

        log.warning(f"IP unchanged on attempt {attempt}: {new_ip}")

    from hydra.infra import telegram
    telegram.warning(f"IP 변경 실패 {max_retries}회 연속 (device: {device_id})")
    raise RuntimeError(f"IP rotation failed after {max_retries} attempts")


def check_ip_available(db: Session, ip_address: str, cooldown_minutes: int = 30) -> bool:
    """Check if IP was NOT used by another account in the last N minutes.

    Spec: same IP + another account within 30min = blocked.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    recent = (
        db.query(IpLog)
        .filter(
            IpLog.ip_address == ip_address,
            IpLog.started_at >= cutoff,
        )
        .first()
    )
    return recent is None


def log_ip_usage(db: Session, account_id: int, ip_address: str, device_id: str) -> IpLog:
    """Record IP-account mapping."""
    record = IpLog(
        account_id=account_id,
        ip_address=ip_address,
        device_id=device_id,
    )
    db.add(record)
    db.commit()
    return record


def end_ip_usage(db: Session, ip_log_id: int):
    """Mark IP usage as ended."""
    record = db.query(IpLog).get(ip_log_id)
    if record:
        record.ended_at = datetime.now(timezone.utc)
        db.commit()
