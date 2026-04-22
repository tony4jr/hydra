"""hydra.core.enrollment — JWT 1회용 등록 토큰."""
import pytest

from hydra.core.enrollment import (
    generate_enrollment_token,
    verify_enrollment_token,
)


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enrollment-secret-12345")


def test_round_trip_returns_worker_name_and_type():
    token = generate_enrollment_token("worker-test", ttl_hours=24)
    data = verify_enrollment_token(token)
    assert data["worker_name"] == "worker-test"
    assert data["type"] == "enrollment"
    assert "nonce" in data and len(data["nonce"]) == 32  # 16 bytes hex


def test_expired_token_rejected():
    token = generate_enrollment_token("w", ttl_hours=-1)
    with pytest.raises(Exception):  # jwt.ExpiredSignatureError
        verify_enrollment_token(token)


def test_session_token_rejected_due_to_missing_type(monkeypatch):
    """세션 JWT (type 없음) 는 enrollment 검증에서 거절."""
    import jwt
    from datetime import datetime, timedelta, UTC

    payload = {
        "user_id": 1,
        "role": "admin",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    session_like = jwt.encode(payload, "test-enrollment-secret-12345", algorithm="HS256")

    with pytest.raises(ValueError, match="not an enrollment token"):
        verify_enrollment_token(session_like)


def test_wrong_secret_rejected(monkeypatch):
    token = generate_enrollment_token("w", ttl_hours=1)
    monkeypatch.setenv("ENROLLMENT_SECRET", "different-secret")
    with pytest.raises(Exception):
        verify_enrollment_token(token)


# === API 레벨: /api/admin/workers/enroll (admin_session 필수) ===

import os
import jwt as _jwt
from datetime import datetime, timedelta, UTC

from fastapi.testclient import TestClient


def _make_admin_jwt(secret: str) -> str:
    now = datetime.now(UTC)
    return _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        secret, algorithm="HS256",
    )


def test_enroll_endpoint_requires_bearer_token():
    os.environ["JWT_SECRET"] = "test-jwt-secret-123456789"
    os.environ["SERVER_URL"] = "https://test.example.com"
    from hydra.web.app import app
    client = TestClient(app)

    resp = client.post("/api/admin/workers/enroll", json={"worker_name": "w1"})
    assert resp.status_code == 401


def test_enroll_endpoint_returns_token_and_install_command():
    os.environ["JWT_SECRET"] = "test-jwt-secret-123456789"
    os.environ["ENROLLMENT_SECRET"] = "test-enrollment-secret-12345"
    os.environ["SERVER_URL"] = "https://test.example.com"
    from hydra.web.app import app
    client = TestClient(app)

    admin_token = _make_admin_jwt("test-jwt-secret-123456789")
    resp = client.post(
        "/api/admin/workers/enroll",
        json={"worker_name": "pc-01", "ttl_hours": 12},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["expires_in_hours"] == 12
    assert "enrollment_token" in body and body["enrollment_token"].count(".") == 2
    assert "setup.ps1" in body["install_command"]
    assert "https://test.example.com" in body["install_command"]

    # 발급된 토큰이 실제로 verify 가능
    data = verify_enrollment_token(body["enrollment_token"])
    assert data["worker_name"] == "pc-01"
