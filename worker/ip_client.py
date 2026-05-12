"""PR-D: 워커 측 IP rotation — server endpoint 만 호출.

워커 로컬 SQLite IpLog 사용 안 함. ensure_safe_ip 흐름:
1. ADB device id 확인 (envelope.worker_config.adb_device_id or settings)
2. _get_current_ip(device_id) — ADB shell 호출
3. POST /api/workers/ip-check {ip, account_id} → available?
4. available=False 면 rotate_and_verify (mobile data toggle) → new_ip
5. POST /api/workers/ip-log/start {account_id, ip, device_id} → log_id

session 종료 시 POST /api/workers/ip-log/end {log_id}.

Source of truth = server Postgres. 워커는 stateless executor.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from hydra.core.config import settings
from hydra.core.logger import get_logger
from hydra.infra.ip import _get_current_ip, rotate_ip
from hydra.infra.ip_errors import IPRotationFailed

log = get_logger("worker.ip_client")


async def ensure_safe_ip_via_server(
    client,
    *,
    account_id: int,
    adb_device_id: Optional[str],
    cooldown_minutes: int = 30,
) -> Optional[int]:
    """Server-side IpLog 만 사용. 워커 SQLite 0 호출.

    Args:
        client: worker.ServerClient instance — _request 호출 가능
        account_id: envelope.account.id
        adb_device_id: envelope.worker_config.adb_device_id 또는 local settings
        cooldown_minutes: cross-account IP cooldown window

    Returns:
        log_id (int) — session.start 가 보관 후 session_end 에서 ip_log_end 호출용.
        None — log endpoint 호출 실패 시 (rotation 자체는 정상이지만 log 못 남김).

    Raises:
        IPRotationFailed — ADB device 미설정 또는 rotate 실패.
    """
    device_id = adb_device_id or settings.adb_device_id or None
    if not device_id:
        log.error(
            f"no_adb_device_configured for account={account_id} — "
            "envelope.worker_config + settings.adb_device_id both empty"
        )
        raise IPRotationFailed("no_adb_device_configured")

    # 1. 현재 phone IP 조회
    current_ip = await _get_current_ip(device_id)
    if not current_ip:
        raise IPRotationFailed(f"_get_current_ip returned empty for device={device_id}")

    # 2. 서버에 cross-account conflict check
    try:
        resp = client._request(
            "POST", "/api/workers/ip-check",
            headers=client.headers,
            json={
                "ip_address": current_ip,
                "account_id": account_id,
                "cooldown_minutes": cooldown_minutes,
            },
            timeout=10,
        )
        resp.raise_for_status()
        available = bool(resp.json().get("available"))
    except Exception as e:
        log.warning(f"ip-check API failed ({type(e).__name__}): {e}. Forcing rotation.")
        available = False

    # 3. 충돌이면 rotate — DB 의존 없는 rotate_ip 직접 호출 (PR-D 순수성).
    final_ip = current_ip
    if not available:
        try:
            final_ip = await rotate_ip(device_id)
        except IPRotationFailed:
            raise
        except RuntimeError as e:
            log.warning(f"rotate_ip RuntimeError: {e}")
            raise IPRotationFailed(f"rotation error: {e}")
        except Exception as e:
            log.warning(f"rotate_ip unexpected: {type(e).__name__}: {e}")
            raise IPRotationFailed(f"rotation error: {type(e).__name__}")

    # 4. 서버에 ip-log/start 보고
    try:
        resp = client._request(
            "POST", "/api/workers/ip-log/start",
            headers=client.headers,
            json={
                "account_id": account_id,
                "ip_address": final_ip,
                "device_id": device_id,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return int(resp.json().get("log_id"))
    except Exception as e:
        log.warning(f"ip-log/start API failed ({type(e).__name__}): {e}. log_id=None.")
        return None


def end_ip_log_via_server(client, log_id: Optional[int]) -> None:
    """session 종료 시 ip-log/end 호출. log_id None 이면 skip. best-effort."""
    if log_id is None:
        return
    try:
        client._request(
            "POST", "/api/workers/ip-log/end",
            headers=client.headers,
            json={"log_id": log_id},
            timeout=10,
        )
    except Exception:
        pass
