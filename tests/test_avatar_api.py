"""Task 23 — 아바타 서빙(/api/avatars) + 어드민 업로드(/api/admin/avatars)."""
import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.enrollment import generate_enrollment_token
from hydra.db.models import Base


def _tiny_png() -> bytes:
    """최소 유효 PNG (1x1 투명) — Pillow resize 가 탈없이 지나가게."""
    return bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
        0x89, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x44, 0x41,
        0x54, 0x78, 0x9C, 0x62, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
        0x42, 0x60, 0x82,
    ])


@pytest.fixture
def env(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)

    storage = tmp_path / "avatars"
    storage.mkdir()
    monkeypatch.setenv("AVATAR_STORAGE_DIR", str(storage))
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-secret-12345")
    monkeypatch.setenv("SERVER_URL", "https://test.example.com")

    from hydra.web.app import app
    client = TestClient(app)

    # 워커 enroll 해서 worker_token 확보
    etoken = generate_enrollment_token("pc-a", ttl_hours=1)
    worker_token = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": etoken, "hostname": "pc-a"},
    ).json()["worker_token"]

    # admin JWT 제작
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )

    yield {
        "client": client,
        "storage": storage,
        "worker_token": worker_token,
        "admin_jwt": admin_jwt,
    }
    engine.dispose()


def _admin_hdr(env):
    return {"Authorization": f"Bearer {env['admin_jwt']}"}


def _worker_hdr(env):
    return {"X-Worker-Token": env["worker_token"]}


# ─────────── /api/avatars (worker) ───────────

def test_worker_download_requires_token(env):
    resp = env["client"].get("/api/avatars/x.png")
    assert resp.status_code == 401


def test_worker_download_404_for_missing(env):
    resp = env["client"].get("/api/avatars/nope.png", headers=_worker_hdr(env))
    assert resp.status_code == 404


def test_worker_download_rejects_traversal(env):
    resp = env["client"].get("/api/avatars/../../etc/passwd", headers=_worker_hdr(env))
    assert resp.status_code in (400, 404)


def test_worker_can_download_existing_file(env):
    target = env["storage"] / "female" / "20s" / "a.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(_tiny_png())

    resp = env["client"].get("/api/avatars/female/20s/a.png", headers=_worker_hdr(env))
    assert resp.status_code == 200
    assert resp.content[:8] == bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])


# ─────────── /api/admin/avatars ───────────

def test_admin_upload_requires_auth(env):
    resp = env["client"].post(
        "/api/admin/avatars/upload",
        data={"category": "x"},
        files={"file": ("a.png", _tiny_png(), "image/png")},
    )
    assert resp.status_code == 401


def test_admin_upload_saves_file(env):
    resp = env["client"].post(
        "/api/admin/avatars/upload",
        data={"category": "female/20s"},
        files={"file": ("hero.png", _tiny_png(), "image/png")},
        headers=_admin_hdr(env),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["saved"].replace("\\", "/") == "female/20s/hero.png"
    assert (env["storage"] / "female" / "20s" / "hero.png").is_file()


def test_admin_upload_rejects_traversal_category(env):
    resp = env["client"].post(
        "/api/admin/avatars/upload",
        data={"category": "../etc"},
        files={"file": ("a.png", _tiny_png(), "image/png")},
        headers=_admin_hdr(env),
    )
    assert resp.status_code == 400


def test_admin_upload_rejects_bad_extension(env):
    resp = env["client"].post(
        "/api/admin/avatars/upload",
        data={"category": "male/30s"},
        files={"file": ("malware.exe", b"MZ\x00", "application/octet-stream")},
        headers=_admin_hdr(env),
    )
    assert resp.status_code == 400


def test_admin_list_returns_tree(env):
    (env["storage"] / "male" / "20s").mkdir(parents=True)
    (env["storage"] / "male" / "20s" / "a.png").write_bytes(_tiny_png())
    (env["storage"] / "male" / "20s" / "b.jpg").write_bytes(_tiny_png())

    resp = env["client"].get("/api/admin/avatars/list", headers=_admin_hdr(env))
    assert resp.status_code == 200
    tree = resp.json()
    assert "male" in tree
    files = sorted(tree["male"]["20s"]["__files__"])
    assert files == ["a.png", "b.jpg"]


def test_admin_upload_zip_extracts_images(env):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("1.png", _tiny_png())
        z.writestr("nested/2.jpg", _tiny_png())
        z.writestr("../escape.png", _tiny_png())  # 무시돼야 함
    buf.seek(0)

    resp = env["client"].post(
        "/api/admin/avatars/upload-zip",
        data={"category": "batch"},
        files={"file": ("pack.zip", buf.read(), "application/zip")},
        headers=_admin_hdr(env),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["saved_count"] == 2
    assert (env["storage"] / "batch" / "1.png").is_file()
    assert (env["storage"] / "batch" / "nested" / "2.jpg").is_file()


def test_admin_delete_removes_file(env):
    target = env["storage"] / "x" / "del.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(_tiny_png())

    resp = env["client"].delete("/api/admin/avatars/x/del.png", headers=_admin_hdr(env))
    assert resp.status_code == 200
    assert not target.exists()


def test_admin_delete_404_missing(env):
    resp = env["client"].delete("/api/admin/avatars/nope.png", headers=_admin_hdr(env))
    assert resp.status_code == 404
