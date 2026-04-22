"""한도 편집 API 테스트 — update / bulk-update-limits."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hydra.db.models import Base, Account
from hydra.db.session import get_db
from hydra.web.app import app


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db

    from hydra.web.routes.admin_auth import admin_session
    app.dependency_overrides[admin_session] = lambda: {"user_id": 1, "role": "admin"}

    db = TestSession()
    db.add_all([
        Account(gmail="a1@gmail.com", password="p", daily_comment_limit=15,
                daily_like_limit=50, weekly_comment_limit=70, weekly_like_limit=300),
        Account(gmail="a2@gmail.com", password="p", daily_comment_limit=15,
                daily_like_limit=50, weekly_comment_limit=70, weekly_like_limit=300),
        Account(gmail="a3@gmail.com", password="p", daily_comment_limit=15,
                daily_like_limit=50, weekly_comment_limit=70, weekly_like_limit=300),
    ])
    db.commit()
    db.close()

    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


def test_account_detail_exposes_limits(client):
    resp = client.get("/accounts/api/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["daily_comment_limit"] == 15
    assert data["daily_like_limit"] == 50
    assert data["weekly_comment_limit"] == 70
    assert data["weekly_like_limit"] == 300


def test_update_single_account_limits(client):
    resp = client.post("/accounts/api/1/update", json={
        "daily_comment_limit": 10,
        "daily_like_limit": 30,
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    detail = client.get("/accounts/api/1").json()
    assert detail["daily_comment_limit"] == 10
    assert detail["daily_like_limit"] == 30
    # Unmodified fields stay
    assert detail["weekly_comment_limit"] == 70
    assert detail["weekly_like_limit"] == 300


def test_update_account_negative_limit_rejected(client):
    resp = client.post("/accounts/api/1/update", json={"daily_comment_limit": -1})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("error") == "invalid_limits"
    assert "daily_comment_limit" in body["fields"]

    # Value should NOT have been applied
    detail = client.get("/accounts/api/1").json()
    assert detail["daily_comment_limit"] == 15


def test_bulk_update_limits_applies_to_all(client):
    resp = client.post("/accounts/api/bulk-update-limits", json={
        "account_ids": [1, 2, 3],
        "daily_comment_limit": 5,
        "weekly_comment_limit": 25,
    })
    assert resp.status_code == 200
    assert resp.json()["updated"] == 3

    for aid in (1, 2, 3):
        d = client.get(f"/accounts/api/{aid}").json()
        assert d["daily_comment_limit"] == 5
        assert d["weekly_comment_limit"] == 25
        # Untouched fields preserved
        assert d["daily_like_limit"] == 50


def test_bulk_update_skips_unspecified_fields(client):
    # Only update daily_like_limit — others should stay at default
    client.post("/accounts/api/bulk-update-limits", json={
        "account_ids": [1],
        "daily_like_limit": 25,
    })
    d = client.get("/accounts/api/1").json()
    assert d["daily_like_limit"] == 25
    assert d["daily_comment_limit"] == 15  # unchanged


def test_bulk_update_negative_rejected(client):
    resp = client.post("/accounts/api/bulk-update-limits", json={
        "account_ids": [1],
        "weekly_like_limit": -5,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("error") == "invalid_limits"
    assert "weekly_like_limit" in body["fields"]

    # No change applied
    d = client.get("/accounts/api/1").json()
    assert d["weekly_like_limit"] == 300


def test_bulk_update_empty_account_ids(client):
    resp = client.post("/accounts/api/bulk-update-limits", json={
        "account_ids": [],
        "daily_comment_limit": 1,
    })
    assert resp.status_code == 200
    assert resp.json().get("error") == "no_accounts"
