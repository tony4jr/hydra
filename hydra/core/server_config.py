"""서버 전역 런타임 설정 — SystemConfig 테이블 위의 singleton-style API.

설계 배경:
- 배포 파이프라인에서 current_version, paused(kill switch), canary_worker_ids
  같은 "서버 전역 한 쌍의 값" 이 필요함.
- 기존 `SystemConfig` 테이블 (key-value 범용 설정) 을 재사용.
  "server_config.*" prefix 로 네임스페이스 분리.
- 새 테이블 안 만듦 — 중복 구조 방지 (꼬임 방지).

저장 형식:
- current_version : str (예: "v1.2.3", "abc123 git hash")
- paused          : "true" | "false" (문자열로 저장, is_paused 가 bool 로 변환)
- canary_worker_ids : JSON 배열 (예: "[1,3,7]")

동시성:
- 단일 VPS 상에서 FastAPI 가 쓰므로 SystemConfig upsert 패턴 충분.
- 멀티 replica 확장 시 row-level lock 고려 (현재 범위 밖).
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from hydra.db.models import SystemConfig
from hydra.db.session import SessionLocal


# Namespace prefix — SystemConfig 의 일반 설정과 충돌 방지
_KEY_CURRENT_VERSION = "server_config.current_version"
_KEY_PAUSED = "server_config.paused"
_KEY_CANARY_IDS = "server_config.canary_worker_ids"


# Default values — row 가 없을 때 반환
_DEFAULT_VERSION = "v0"
_DEFAULT_PAUSED = False
_DEFAULT_CANARY: list[int] = []


def _get_value(key: str, *, session: Session) -> Optional[str]:
    row = session.query(SystemConfig).filter_by(key=key).first()
    return row.value if row else None


def _set_value(key: str, value: str, *, session: Session) -> None:
    """Upsert: 있으면 update, 없으면 insert.

    commit 은 호출자 책임 (session.commit()). FastAPI 의 request-scoped
    세션 안에서 다른 작업과 한 트랜잭션으로 묶을 수 있게.
    """
    row = session.query(SystemConfig).filter_by(key=key).first()
    if row is None:
        session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value


# ----- current_version -----

def get_current_version(*, session: Optional[Session] = None) -> str:
    owned = session is None
    s = session or SessionLocal()
    try:
        v = _get_value(_KEY_CURRENT_VERSION, session=s)
        return v if v is not None else _DEFAULT_VERSION
    finally:
        if owned:
            s.close()


def set_current_version(version: str, *, session: Optional[Session] = None) -> None:
    if not isinstance(version, str) or not version:
        raise ValueError("version must be non-empty string")
    owned = session is None
    s = session or SessionLocal()
    try:
        _set_value(_KEY_CURRENT_VERSION, version, session=s)
        if owned:
            s.commit()
    finally:
        if owned:
            s.close()


# ----- paused (kill switch) -----

def is_paused(*, session: Optional[Session] = None) -> bool:
    owned = session is None
    s = session or SessionLocal()
    try:
        v = _get_value(_KEY_PAUSED, session=s)
        if v is None:
            return _DEFAULT_PAUSED
        return v.lower() == "true"
    finally:
        if owned:
            s.close()


def set_paused(flag: bool, *, session: Optional[Session] = None) -> None:
    if not isinstance(flag, bool):
        raise TypeError("flag must be bool")
    owned = session is None
    s = session or SessionLocal()
    try:
        _set_value(_KEY_PAUSED, "true" if flag else "false", session=s)
        if owned:
            s.commit()
    finally:
        if owned:
            s.close()


# ----- canary_worker_ids -----

def get_canary_worker_ids(*, session: Optional[Session] = None) -> list[int]:
    owned = session is None
    s = session or SessionLocal()
    try:
        v = _get_value(_KEY_CANARY_IDS, session=s)
        if v is None:
            return list(_DEFAULT_CANARY)
        try:
            parsed = json.loads(v)
        except json.JSONDecodeError:
            return list(_DEFAULT_CANARY)
        if not isinstance(parsed, list):
            return list(_DEFAULT_CANARY)
        return [int(x) for x in parsed if isinstance(x, (int, float))]
    finally:
        if owned:
            s.close()


def set_canary_worker_ids(ids: list[int], *, session: Optional[Session] = None) -> None:
    if not isinstance(ids, list):
        raise TypeError("ids must be a list")
    cleaned: list[int] = []
    for x in ids:
        if not isinstance(x, int) or isinstance(x, bool):
            raise ValueError(f"canary id must be int, got {type(x).__name__}: {x!r}")
        cleaned.append(x)
    owned = session is None
    s = session or SessionLocal()
    try:
        _set_value(_KEY_CANARY_IDS, json.dumps(cleaned), session=s)
        if owned:
            s.commit()
    finally:
        if owned:
            s.close()
