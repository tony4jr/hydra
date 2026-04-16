import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from hydra.db.models import Base, Preset
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

    # Seed a system preset for tests
    db = TestSession()
    preset = Preset(name="Test System", code="TEST_SYS", is_system=True, steps='[{"step_number": 1}]')
    db.add(preset)
    db.commit()
    db.close()

    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()

def test_list_presets(client):
    resp = client.get("/api/presets/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["code"] == "TEST_SYS"

def test_create_preset(client):
    resp = client.post("/api/presets/", json={
        "name": "Custom Preset",
        "code": "CUSTOM_1",
        "description": "A custom preset",
        "steps": [{"step_number": 1, "action": "like"}, {"step_number": 2, "action": "comment"}],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Custom Preset"
    assert data["code"] == "CUSTOM_1"
    assert "id" in data

def test_create_duplicate_code(client):
    client.post("/api/presets/", json={
        "name": "First", "code": "DUP_CODE", "steps": [{"step_number": 1}],
    })
    resp = client.post("/api/presets/", json={
        "name": "Second", "code": "DUP_CODE", "steps": [{"step_number": 1}],
    })
    assert resp.status_code == 409

def test_get_preset(client):
    create_resp = client.post("/api/presets/", json={
        "name": "Get Me", "code": "GET_ME", "steps": [{"step_number": 1}],
    })
    preset_id = create_resp.json()["id"]
    resp = client.get(f"/api/presets/{preset_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Get Me"
    assert data["code"] == "GET_ME"
    assert data["steps"] == [{"step_number": 1}]

def test_update_preset(client):
    create_resp = client.post("/api/presets/", json={
        "name": "Old Name", "code": "UPD_1", "steps": [{"step_number": 1}],
    })
    preset_id = create_resp.json()["id"]
    resp = client.put(f"/api/presets/{preset_id}", json={
        "name": "New Name",
        "steps": [{"step_number": 1}, {"step_number": 2}],
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"

    # Verify the update persisted
    get_resp = client.get(f"/api/presets/{preset_id}")
    assert get_resp.json()["name"] == "New Name"
    assert len(get_resp.json()["steps"]) == 2

def test_delete_custom_preset(client):
    create_resp = client.post("/api/presets/", json={
        "name": "Delete Me", "code": "DEL_1", "steps": [{"step_number": 1}],
    })
    preset_id = create_resp.json()["id"]
    resp = client.delete(f"/api/presets/{preset_id}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify it's gone
    get_resp = client.get(f"/api/presets/{preset_id}")
    assert get_resp.status_code == 404

def test_delete_system_preset_fails(client):
    # The system preset seeded in the fixture has id=1
    resp = client.get("/api/presets/")
    system_preset = [p for p in resp.json() if p["is_system"]][0]
    resp = client.delete(f"/api/presets/{system_preset['id']}")
    assert resp.status_code == 400
