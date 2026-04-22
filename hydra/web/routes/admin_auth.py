"""어드민 로그인/로그아웃 엔드포인트 + 세션 Depends 헬퍼.

- POST /api/admin/auth/login   : email+password → JWT
- POST /api/admin/auth/logout  : stateless — no-op (클라가 토큰 삭제)
- admin_session                : 다른 /api/admin/* 라우트에서 Depends 로 사용
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from hydra.core.auth import (
    create_session_token,
    verify_password,
    verify_session_token,
)
from hydra.db import session as _db_session
from hydra.db.models import User

router = APIRouter()


def _jwt_secret() -> str:
    """요청 시점에 env 조회 — 테스트/배포 모두에서 최신 값 반영."""
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(500, "JWT_SECRET not configured")
    return secret


class LoginRequest(BaseModel):
    # 내부 운영 툴 — 엄격 email 검증 대신 str (원격 도메인 .local 등도 허용)
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: int
    email: str
    role: str


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    db = _db_session.SessionLocal()
    try:
        user = db.query(User).filter_by(email=req.email).first()
        # 존재 여부 노출 방지 — 성공 제외 전부 동일 메시지
        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(401, "invalid credentials")
        token = create_session_token(user.id, user.role, _jwt_secret())
        return LoginResponse(
            token=token, user_id=user.id, email=user.email, role=user.role
        )
    finally:
        db.close()


@router.post("/logout")
def logout() -> dict:
    return {"ok": True}


def admin_session(authorization: str = Header(default="")) -> dict:
    """세션 JWT 검증. Raises 401 on invalid, 403 on insufficient role."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization[len("Bearer ") :]
    try:
        data = verify_session_token(token, _jwt_secret())
    except Exception:
        raise HTTPException(401, "invalid session")
    if data.get("role") not in ("admin", "operator"):
        raise HTTPException(403, "insufficient role")
    return data
