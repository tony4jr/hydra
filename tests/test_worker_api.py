import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from hydra.db.models import Base
from hydra.web.app import app
from hydra.db.session import get_db

@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()

def test_register_worker(client):
    resp = client.post("/api/workers/register", json={"name": "PC-1", "registration_secret": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "PC-1"
    assert "token" in data

def test_heartbeat(client):
    resp = client.post("/api/workers/register", json={"name": "PC-1", "registration_secret": ""})
    token = resp.json()["token"]
    resp = client.post("/api/workers/heartbeat", json={"version": "1.0.0", "os_type": "windows"}, headers={"X-Worker-Token": token})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_heartbeat_invalid_token(client):
    resp = client.post("/api/workers/heartbeat", json={}, headers={"X-Worker-Token": "invalid"})
    assert resp.status_code == 401

def test_list_workers(client):
    client.post("/api/workers/register", json={"name": "PC-1", "registration_secret": ""})
    client.post("/api/workers/register", json={"name": "PC-2", "registration_secret": ""})
    resp = client.get("/api/workers/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
