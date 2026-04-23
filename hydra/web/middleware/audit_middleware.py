"""FastAPI 미들웨어 — /api/admin/* 쓰기 요청을 audit_logs 에 기록.

build_audit_entry (Task 16) 를 실제로 호출하는 진입점. 응답 상태 2xx/3xx 일 때만
기록해 에러 노이즈 방지.
"""
from __future__ import annotations

import json
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from hydra.core.auth import verify_session_token
from hydra.db import session as _db_session
from hydra.db.models import AuditLog
from hydra.web.middleware.audit import build_audit_entry

log = logging.getLogger("hydra.audit")


async def _read_body_json(request: Request) -> dict | None:
    """body 를 캐시 후 재주입 — 이후 라우트가 정상적으로 다시 읽을 수 있게.

    Starlette BaseHTTPMiddleware 에서 request.body() 는 스트림을 소비하므로
    receive 를 교체해 이후 핸들러도 동일 바이트를 받도록 한다.
    """
    try:
        raw = await request.body()
    except Exception:
        return None

    # receive 재주입 — 다음 호출자가 같은 body 를 받게
    async def receive() -> dict:
        return {"type": "http.request", "body": raw, "more_body": False}

    request._receive = receive  # type: ignore[attr-defined]

    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _session_from_auth(auth_header: str | None) -> dict:
    if not auth_header or not auth_header.startswith("Bearer "):
        return {}
    import os
    secret = os.getenv("JWT_SECRET")
    if not secret:
        return {}
    try:
        return verify_session_token(auth_header[len("Bearer "):], secret)
    except Exception:
        return {}


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method.upper()

        # 감사 대상일 때만 body 읽기 (성능)
        is_admin_write = (
            path.startswith("/api/admin/")
            and method in {"POST", "PUT", "PATCH", "DELETE"}
        )

        body_json = await _read_body_json(request) if is_admin_write else None

        response = await call_next(request)

        if not is_admin_write:
            return response
        if response.status_code >= 400:
            return response

        session = _session_from_auth(request.headers.get("authorization"))
        req_info = {
            "method": method,
            "path": path,
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", ""),
        }

        entry = build_audit_entry(req_info, session, body_json)
        if entry is None:
            return response

        try:
            db = _db_session.SessionLocal()
            try:
                db.add(AuditLog(**entry))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            log.warning("audit log insert failed: %s", e)

        return response
