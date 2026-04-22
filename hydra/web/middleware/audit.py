"""감사 로그 자동 기록 헬퍼.

FastAPI 에서는 실제 DB insert 를 라우트 트랜잭션 안에서 하는 게 일관성 좋음.
이 모듈은 **"이 요청이 감사 대상이면 어떤 entry 를 만들지"** 결정 로직만 제공.

사용 패턴 (라우트 또는 dependency 에서):
    entry = build_audit_entry(req_info, session, body)
    if entry:
        db.add(AuditLog(**entry))
        # db.commit() 은 라우트 메인 트랜잭션과 함께
"""
from __future__ import annotations

import json
import re


# /api/admin/* 경로 → action 이름 매핑.
# 정규식 순서대로 매칭 (첫 일치 우선).
ACTION_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^/api/admin/auth/login(?:$|/)"),    "login"),
    (re.compile(r"^/api/admin/auth/logout(?:$|/)"),   "logout"),
    (re.compile(r"^/api/admin/deploy(?:$|/)"),        "deploy"),
    (re.compile(r"^/api/admin/pause(?:$|/)"),         "pause"),
    (re.compile(r"^/api/admin/unpause(?:$|/)"),       "unpause"),
    (re.compile(r"^/api/admin/canary(?:$|/)"),        "canary_change"),
    (re.compile(r"^/api/admin/campaigns(?:$|/)"),     "campaign_change"),
    (re.compile(r"^/api/admin/avatars(?:$|/)"),       "avatar_change"),
    (re.compile(r"^/api/admin/workers(?:$|/)"),       "worker_change"),
    (re.compile(r"^/api/admin/accounts(?:$|/)"),      "account_change"),
    (re.compile(r"^/api/admin/presets(?:$|/)"),       "preset_change"),
    (re.compile(r"^/api/admin/brands(?:$|/)"),        "brand_change"),
]

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 민감 필드 — metadata 저장 시 제거. 로그에 평문으로 남으면 보안 사고.
SENSITIVE_FIELDS = frozenset({
    "password", "pwd", "token", "enrollment_token", "api_key",
    "secret", "jwt", "auth", "authorization", "cookie",
    "access_token", "refresh_token", "client_secret",
})


def _infer_action(path: str) -> str | None:
    """요청 경로 → action 이름. 매핑 없으면 None."""
    for pattern, action in ACTION_MAP:
        if pattern.search(path):
            return action
    return None


def _redact(body: dict) -> dict:
    """민감 필드를 body 복사본에서 제거."""
    return {k: v for k, v in body.items() if k.lower() not in SENSITIVE_FIELDS}


def build_audit_entry(
    req_info: dict,
    session: dict,
    body: dict | None,
) -> dict | None:
    """감사 기록 엔트리 dict 생성. None 이면 기록 대상 아님.

    Args:
        req_info: {"method", "path", "client_ip", "user_agent"}
        session:  {"user_id", "role"} — 로그인 전이면 {}
        body:     요청 body 를 파싱한 dict (없으면 None)

    Returns:
        AuditLog 생성자 kwargs dict — 없으면 None.
    """
    method = (req_info.get("method") or "").upper()
    path = req_info.get("path") or ""

    if method not in WRITE_METHODS:
        return None
    if not path.startswith("/api/admin/"):
        return None

    action = _infer_action(path)
    if action is None:
        return None  # 매핑 안 된 /api/admin/* 는 noise 방지로 기록 안 함

    meta: dict = {"method": method, "path": path}
    if body:
        meta["body"] = _redact(body)

    return {
        "user_id": session.get("user_id"),
        "action": action,
        "target_type": None,
        "target_id": None,
        "metadata_json": json.dumps(meta, ensure_ascii=False),
        "ip_address": req_info.get("client_ip"),
        "user_agent": req_info.get("user_agent"),
    }
