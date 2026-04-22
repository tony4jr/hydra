"""워커 enrollment 토큰 — JWT 기반 1회용 등록 토큰.

- 어드민이 UI 에서 "워커 추가" → `generate_enrollment_token(worker_name)` → PowerShell 설치 명령과 함께 표시
- 워커 PC 가 setup.ps1 실행 시 토큰을 `/api/workers/enroll` 에 POST (Task 20)
- 서버는 `verify_enrollment_token` 으로 검증 후 worker_token 발급

secret 은 `ENROLLMENT_SECRET` env — `JWT_SECRET`(세션) 과 **분리**. 세션 키 유출이
enrollment 위조로 이어지지 않도록. type claim 으로 교차 사용도 차단.
"""
from __future__ import annotations

import os
import secrets as _secrets
from datetime import UTC, datetime, timedelta

import jwt

_ALGO = "HS256"
_TYPE = "enrollment"


def _enrollment_secret() -> str:
    s = os.getenv("ENROLLMENT_SECRET")
    if not s:
        raise RuntimeError("ENROLLMENT_SECRET not configured")
    return s


def generate_enrollment_token(worker_name: str, ttl_hours: int = 24) -> str:
    """1회용 등록 토큰 발급.

    payload:
      worker_name : str  — 등록할 워커 식별자
      nonce       : str  — 재사용 감지용 (Task 20 에서 DB 기록)
      type        : "enrollment"  — 세션 JWT 와 구분
      iat / exp   : UTC unix
    """
    now = datetime.now(UTC)
    payload = {
        "worker_name": worker_name,
        "nonce": _secrets.token_hex(16),
        "type": _TYPE,
        "iat": now,
        "exp": now + timedelta(hours=ttl_hours),
    }
    return jwt.encode(payload, _enrollment_secret(), algorithm=_ALGO)


def verify_enrollment_token(token: str) -> dict:
    """검증 + payload 반환.

    Raises: jwt.ExpiredSignatureError / InvalidSignatureError / ValueError(type).
    """
    data = jwt.decode(token, _enrollment_secret(), algorithms=[_ALGO])
    if data.get("type") != _TYPE:
        raise ValueError("not an enrollment token")
    return data
