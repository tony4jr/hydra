"""worker_auth 성능 최적화 — SHA-256 O(1) 조회로 bcrypt 제거.

근본문제: 워커 토큰은 256bit 랜덤이라 bcrypt 불필요. 그런데 원래 설계가
bcrypt 였고 worker_auth 가 모든 워커 순회 → N×250ms → 매우 느림.
해결: token_sha256 UNIQUE 인덱스. 잘못된 토큰도 0건 매칭 → 즉시 401.
"""
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, Worker


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@pytest.fixture
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")
    from hydra.web.app import app
    yield TestClient(app), TestSession
    engine.dispose()


def test_auth_accepts_token_with_matching_prefix(env):
    client, Session = env
    db = Session()
    token = "prefix99-therest-of-token-is-long-abcdef"
    w = Worker(
        name="w1",
        token_hash=hash_password(token),
        token_prefix=token[:8],
        token_sha256=_sha(token),
    )
    db.add(w); db.commit(); db.close()

    r = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": token},
        json={"version": "v", "os_type": "linux"},
    )
    assert r.status_code == 200


def test_auth_rejects_wrong_token_with_same_prefix(env):
    """prefix 가 우연히 같은 다른 토큰은 bcrypt 실패 → 401."""
    client, Session = env
    db = Session()
    real = "sameprfx-real-token-aaaaaaaaaaaaaaaa"
    w = Worker(
        name="w1",
        token_hash=hash_password(real),
        token_prefix=real[:8],
        token_sha256=_sha(real),
    )
    db.add(w); db.commit(); db.close()

    fake = "sameprfx-fake-token-bbbbbbbbbbbbbbbb"  # 앞 8자 동일, 뒤는 다름
    r = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": fake},
        json={"version": "v"},
    )
    assert r.status_code == 401


def test_auth_legacy_worker_without_sha256_still_works_and_backfills(env):
    """기존 워커가 token_sha256 null (legacy bcrypt 만) 인 상태여도
    인증 통과 + sha256/prefix 자동 백필. 최근 heartbeat 필수."""
    from datetime import datetime, UTC
    client, Session = env
    db = Session()
    token = "legacy00-old-token-no-sha256-xxxxxxxxxx"
    w = Worker(
        name="legacy",
        token_hash=hash_password(token),
        token_prefix=None,
        token_sha256=None,
        last_heartbeat=datetime.now(UTC),  # 최근 활동 워커여야 legacy fallback 적용
    )
    db.add(w); db.commit()
    worker_id = w.id
    db.close()

    r = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": token},
        json={"version": "v"},
    )
    assert r.status_code == 200

    # sha256 과 prefix 가 모두 채워졌는지 확인
    db2 = Session()
    saved = db2.get(Worker, worker_id)
    assert saved.token_sha256 == _sha(token)
    assert saved.token_prefix == token[:8]
    db2.close()


def test_auth_is_fast_even_with_many_workers(env):
    """21개 워커가 있어도 SHA-256 O(1) 조회로 bcrypt 순회 없이 빠르게 응답."""
    import time
    client, Session = env
    db = Session()
    for i in range(20):
        dummy_tok = f"dummy{i:03d}-token-aaaaaaaaaaaaaaaaaaaaa"
        # 더미도 sha256 세팅 (실제 enroll 시나리오)
        db.add(Worker(
            name=f"dummy{i}",
            token_hash=hash_password(dummy_tok),
            token_prefix=dummy_tok[:8],
            token_sha256=_sha(dummy_tok),
        ))
    real = "realreal-is-the-token-xxxxxxxxxxxxxxxxxx"
    db.add(Worker(
        name="real",
        token_hash=hash_password(real),
        token_prefix=real[:8],
        token_sha256=_sha(real),
    ))
    db.commit(); db.close()

    t0 = time.time()
    r = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": real},
        json={"version": "v"},
    )
    elapsed = time.time() - t0
    assert r.status_code == 200
    # SHA-256 O(1) 조회 → 1초 이내로 끝나야 (bcrypt 0회)
    assert elapsed < 1.0, f"auth took {elapsed:.2f}s — sha256 fast path 안 탐"


def test_invalid_token_is_instant_when_sha256_populated(env):
    """잘못된 토큰 — sha256 이 세팅된 워커만 있으면 bcrypt 없이 즉시 401."""
    import time
    client, Session = env
    db = Session()
    for i in range(10):
        tok = f"tok{i:03d}-is-the-token-xxxxxxxxxxxxxxxxxxx"
        db.add(Worker(
            name=f"w{i}",
            token_hash=hash_password(tok),
            token_prefix=tok[:8],
            token_sha256=_sha(tok),
        ))
    db.commit(); db.close()

    t0 = time.time()
    r = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": "completely-wrong-bogus-token-never-seen"},
        json={"version": "v"},
    )
    elapsed = time.time() - t0
    assert r.status_code == 401
    # bcrypt 순회 없음 → 거의 즉시. 0.5초 이내 기대.
    assert elapsed < 0.5, f"bogus token auth took {elapsed:.2f}s — bcrypt 순회 의심"
