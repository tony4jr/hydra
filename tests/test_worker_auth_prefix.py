"""worker_auth 성능 최적화 — token_prefix 인덱스로 O(1) 조회.

근본문제: worker_auth 가 모든 워커 bcrypt 순회 → N×250ms → 워커 30대 면 8초.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, Worker


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
    w = Worker(name="w1", token_hash=hash_password(token), token_prefix=token[:8])
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
    w = Worker(name="w1", token_hash=hash_password(real), token_prefix=real[:8])
    db.add(w); db.commit(); db.close()

    fake = "sameprfx-fake-token-bbbbbbbbbbbbbbbb"  # 앞 8자 동일, 뒤는 다름
    r = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": fake},
        json={"version": "v"},
    )
    assert r.status_code == 401


def test_auth_legacy_worker_without_prefix_still_works_and_backfills(env):
    """기존 워커가 prefix 컬럼 null 인 상태여도 인증 통과 + prefix 자동 백필."""
    client, Session = env
    db = Session()
    token = "legacy00-old-token-no-prefix-xxxxxxxxxx"
    w = Worker(name="legacy", token_hash=hash_password(token), token_prefix=None)
    db.add(w); db.commit()
    worker_id = w.id
    db.close()

    r = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": token},
        json={"version": "v"},
    )
    assert r.status_code == 200

    # prefix 가 채워졌는지 확인
    db2 = Session()
    saved = db2.get(Worker, worker_id)
    assert saved.token_prefix == token[:8]
    db2.close()


def test_auth_skips_bcrypt_for_non_matching_prefix(env):
    """30개 워커 중 1개만 내 prefix → 29개는 bcrypt 안 함 → 응답 빠름."""
    import time
    client, Session = env
    db = Session()
    # 더미 워커 20개 (prefix 다 다름)
    for i in range(20):
        dummy_tok = f"dummy{i:03d}-token-aaaaaaaaaaaaaaaaaaaaa"
        db.add(Worker(
            name=f"dummy{i}",
            token_hash=hash_password(dummy_tok),
            token_prefix=dummy_tok[:8],
        ))
    # 진짜 워커
    real = "realreal-is-the-token-xxxxxxxxxxxxxxxxxx"
    db.add(Worker(name="real", token_hash=hash_password(real), token_prefix=real[:8]))
    db.commit(); db.close()

    t0 = time.time()
    r = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": real},
        json={"version": "v"},
    )
    elapsed = time.time() - t0
    assert r.status_code == 200
    # bcrypt 1번만 ≈ 300ms. 전수순회면 21번 ≈ 6초+. 2초 이내로 끝나야 정상.
    assert elapsed < 2.0, f"auth took {elapsed:.2f}s — 전수순회 의심"
