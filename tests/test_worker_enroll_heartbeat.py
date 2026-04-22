"""Task 20 — /api/workers/enroll + /api/workers/heartbeat/v2 API 테스트."""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.enrollment import generate_enrollment_token
from hydra.db.models import Base


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)

    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-secret-123456")
    monkeypatch.setenv("SERVER_URL", "https://test.example.com")
    monkeypatch.setenv("DB_CRYPTO_KEY", "test-crypto-key-xyz")

    from hydra.web.app import app
    yield TestClient(app)
    engine.dispose()


def test_enroll_with_valid_token_creates_worker_and_returns_secrets(client):
    etoken = generate_enrollment_token("pc-01", ttl_hours=1)
    resp = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": etoken, "hostname": "pc-01"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["worker_id"] >= 1
    assert isinstance(body["worker_token"], str) and len(body["worker_token"]) > 30
    assert body["secrets"]["SERVER_URL"] == "https://test.example.com"
    assert body["secrets"]["DB_CRYPTO_KEY"] == "test-crypto-key-xyz"


def test_enroll_with_invalid_token_returns_401(client):
    resp = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": "garbage.token.here", "hostname": "x"},
    )
    assert resp.status_code == 401


def test_heartbeat_v2_without_token_returns_401(client):
    resp = client.post("/api/workers/heartbeat/v2", json={"version": "v1"})
    assert resp.status_code == 401


def test_heartbeat_v2_with_valid_worker_token_returns_config(client):
    # 1) enroll 해서 worker_token 획득
    etoken = generate_enrollment_token("pc-hb", ttl_hours=1)
    enroll_resp = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": etoken, "hostname": "pc-hb"},
    )
    worker_token = enroll_resp.json()["worker_token"]

    # 2) heartbeat
    resp = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": worker_token},
        json={"version": "v0.1.0", "os_type": "windows"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "current_version" in body
    assert body["paused"] is False  # 기본값
    assert isinstance(body["canary_worker_ids"], list)
    assert body["worker_config"]["poll_interval_sec"] == 15


def test_heartbeat_v2_with_bogus_token_returns_401(client):
    # 다른 워커 1대 먼저 enroll 해서 DB 에 token_hash 있는 상태 만들기
    etoken = generate_enrollment_token("pc-other", ttl_hours=1)
    client.post("/api/workers/enroll", json={"enrollment_token": etoken, "hostname": "pc-other"})

    resp = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": "definitely-wrong-token-12345"},
        json={"version": "v1"},
    )
    assert resp.status_code == 401


def test_reenroll_same_worker_rotates_token(client):
    """같은 worker_name 으로 재 enroll 시 동일 worker_id + 새 token."""
    etoken1 = generate_enrollment_token("pc-rot", ttl_hours=1)
    r1 = client.post("/api/workers/enroll", json={"enrollment_token": etoken1, "hostname": "pc-rot"}).json()

    etoken2 = generate_enrollment_token("pc-rot", ttl_hours=1)
    r2 = client.post("/api/workers/enroll", json={"enrollment_token": etoken2, "hostname": "pc-rot"}).json()

    assert r1["worker_id"] == r2["worker_id"]
    assert r1["worker_token"] != r2["worker_token"]

    # old token 무효화 확인
    resp = client.post(
        "/api/workers/heartbeat/v2",
        headers={"X-Worker-Token": r1["worker_token"]},
        json={"version": "v1"},
    )
    assert resp.status_code == 401
