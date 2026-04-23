"""Task 35 — AccountSnapshot + fetch 응답에 account_snapshot 포함."""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core import crypto
from hydra.core.enrollment import generate_enrollment_token
from hydra.db.models import Account, Base, Task
from worker.account_snapshot import AccountSnapshot


@pytest.fixture(autouse=True)
def _fernet_key(monkeypatch):
    # 테스트용 32바이트 base64 urlsafe key
    monkeypatch.setenv(
        "HYDRA_ENCRYPTION_KEY",
        "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=",
    )


# ── AccountSnapshot unit ──

def test_from_payload_decrypts_password():
    encrypted = crypto.encrypt("MySecret!123")
    payload = {"account_snapshot": {
        "id": 42,
        "gmail": "x@y.com",
        "encrypted_password": encrypted,
        "adspower_profile_id": "p-xyz",
        "persona": {"name": "홍길동", "age": 28},
    }}
    snap = AccountSnapshot.from_payload(payload)
    assert snap.id == 42
    assert snap.gmail == "x@y.com"
    assert snap.password == "MySecret!123"
    assert snap.adspower_profile_id == "p-xyz"
    assert snap.persona["name"] == "홍길동"


def test_from_payload_persona_json_string_parsed():
    payload = {"account_snapshot": {
        "id": 1, "gmail": "a@b.c",
        "adspower_profile_id": "p",
        "encrypted_password": crypto.encrypt("x"),
        "persona": '{"name": "이순신"}',
    }}
    snap = AccountSnapshot.from_payload(payload)
    assert isinstance(snap.persona, dict)
    assert snap.persona["name"] == "이순신"


def test_from_payload_empty_password_ok():
    payload = {"account_snapshot": {
        "id": 1, "gmail": "a@b.c",
        "adspower_profile_id": "p",
    }}
    snap = AccountSnapshot.from_payload(payload)
    assert snap.password == ""
    assert snap.totp_secret is None


def test_from_payload_decrypts_totp_when_present():
    enc_totp = crypto.encrypt("ABCDEF12345")
    payload = {"account_snapshot": {
        "id": 1, "gmail": "a@b.c",
        "encrypted_password": crypto.encrypt("pw"),
        "adspower_profile_id": "p",
        "encrypted_totp_secret": enc_totp,
    }}
    snap = AccountSnapshot.from_payload(payload)
    assert snap.totp_secret == "ABCDEF12345"


# ── fetch 응답에 account_snapshot 포함 (integration) ──

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
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-secret-12345")
    monkeypatch.setenv("SERVER_URL", "https://test.example.com")

    from hydra.web.app import app
    client = TestClient(app)
    etoken = generate_enrollment_token("pc-snap", ttl_hours=1)
    enr = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": etoken, "hostname": "pc-snap"},
    ).json()

    db = TestSession()
    acc = Account(
        gmail="snap@x.com",
        password=crypto.encrypt("RealPass!"),
        adspower_profile_id="p-snap",
        persona='{"name":"test"}',
        totp_secret=crypto.encrypt("TOTP_SECRET"),
        status="active",
        recovery_email="r@x.com",
    )
    db.add(acc); db.flush()
    task = Task(
        account_id=acc.id, task_type="comment", status="pending",
        priority="normal", payload="{}",
    )
    db.add(task); db.commit()

    yield {"client": client, "worker_token": enr["worker_token"], "account_id": acc.id}
    engine.dispose()


def test_fetch_response_includes_account_snapshot(env):
    resp = env["client"].post(
        "/api/tasks/v2/fetch",
        headers={"X-Worker-Token": env["worker_token"]},
    )
    body = resp.json()
    assert len(body["tasks"]) == 1
    snap_raw = body["tasks"][0]["account_snapshot"]
    assert snap_raw["gmail"] == "snap@x.com"
    assert snap_raw["adspower_profile_id"] == "p-snap"
    assert "encrypted_password" in snap_raw
    assert snap_raw["recovery_email"] == "r@x.com"

    # AccountSnapshot 으로 복호화 → 평문 복구
    snap = AccountSnapshot.from_payload({"account_snapshot": snap_raw})
    assert snap.password == "RealPass!"
    assert snap.totp_secret == "TOTP_SECRET"
