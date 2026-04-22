"""인증 헬퍼 — bcrypt 비밀번호 해시 + JWT 세션 토큰.

사용처:
- `scripts/create_admin.py` : 초기 관리자 생성 시 비번 해시
- `hydra/web/routes/admin_auth.py` (예정, Task 18) : 로그인 API
- `hydra/web/middleware/audit.py` (예정, Task 16) : 현재 로그인 user_id 추출
- 모든 `/api/admin/*` 라우트의 `Depends(admin_session)` : 세션 검증

JWT secret 은 호출 시 인자로 받음 (모듈이 env 에서 직접 읽지 않음) — 테스트 격리 용이.
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC

import bcrypt
import jwt

# 세션 기본 만료 — 7일. 짧게 원하면 환경변수로 override 가능하게 추후 확장.
SESSION_EXP_HOURS = 24 * 7

# JWT 알고리즘 — 대칭 HMAC-SHA256. 비대칭(RS256) 필요해지는 시점엔 교체.
JWT_ALGO = "HS256"


def hash_password(plain: str) -> str:
    """bcrypt 로 비밀번호 해시. salt 자동 생성 (cost factor 12).

    Returns: "$2b$12$..." 형태의 문자열.
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """비밀번호 검증. 예외 절대 던지지 않음 — 실패/이상 입력 모두 False.

    잘못된 hash 형식이어도 조용히 False (공격자 정보 차단).
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_session_token(user_id: int, role: str, secret: str) -> str:
    """세션 JWT 발급.

    payload:
      user_id : int   — users.id
      role    : str   — admin | operator | customer
      exp     : int   — UTC unix timestamp (SESSION_EXP_HOURS 뒤)
      iat     : int   — 발급 시각

    Returns: 서명된 JWT 문자열 (header.payload.signature).
    """
    now = datetime.now(UTC)
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": now + timedelta(hours=SESSION_EXP_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGO)


def verify_session_token(token: str, secret: str) -> dict:
    """JWT 검증 + payload 반환.

    실패 케이스 (예외 발생):
    - 서명 불일치 (secret 틀림 or 토큰 변조) → InvalidSignatureError
    - 만료 → ExpiredSignatureError
    - 포맷 깨짐 → DecodeError

    Returns: payload dict (`{"user_id", "role", "exp", "iat"}`)
    """
    return jwt.decode(token, secret, algorithms=[JWT_ALGO])
