"""T1 스크린샷 캡처 — multipart 업로드 + 어드민 조회."""
import hashlib
import io
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, Worker, WorkerError


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _tiny_png_bytes() -> bytes:
    # 1x1 투명 PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x03\xfe\x8a\xcb\xd8\x00\x00\x00\x00IEND\xaeB`\x82"
    )


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
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")
    screenshot_dir = tmp_path / "screenshots"
    monkeypatch.setenv("HYDRA_SCREENSHOT_DIR", str(screenshot_dir))

    db = TestSession()
    raw_token = "worker-token-shot-xxxxxxxxxxxxxxxxxxxx"
    w = Worker(
        name="shot-worker",
        token_hash=hash_password(raw_token),
        token_prefix=raw_token[:8],
        token_sha256=_sha(raw_token),
    )
    db.add(w); db.commit(); db.refresh(w)
    worker_id = w.id
    db.close()

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {
        "client": client,
        "worker_token": raw_token,
        "worker_id": worker_id,
        "admin_jwt": admin_jwt,
        "Session": TestSession,
        "screenshot_dir": screenshot_dir,
    }
    engine.dispose()


def test_upload_saves_file_and_db_url(env):
    png = _tiny_png_bytes()
    r = env["client"].post(
        "/api/workers/report-error-with-screenshot",
        headers={"X-Worker-Token": env["worker_token"]},
        data={"kind": "task_fail", "message": "comment click missed",
              "traceback": "Traceback...", "context": json.dumps({"task_id": 123})},
        files={"screenshot": ("shot.png", png, "image/png")},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "deduped": False}

    db = env["Session"]()
    err = db.query(WorkerError).first()
    assert err.screenshot_url is not None
    # 파일 실제 존재
    saved = env["screenshot_dir"] / err.screenshot_url
    assert saved.is_file()
    assert saved.read_bytes() == png
    # context json parsing
    assert json.loads(err.context) == {"task_id": 123}
    db.close()


def test_upload_rejects_non_image_extension(env):
    r = env["client"].post(
        "/api/workers/report-error-with-screenshot",
        headers={"X-Worker-Token": env["worker_token"]},
        data={"kind": "task_fail", "message": "bad"},
        files={"screenshot": ("evil.exe", b"MZ\x00", "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "extension" in r.json().get("detail", "")


def test_upload_rejects_too_large(env):
    huge = b"x" * (5 * 1024 * 1024)
    r = env["client"].post(
        "/api/workers/report-error-with-screenshot",
        headers={"X-Worker-Token": env["worker_token"]},
        data={"kind": "task_fail", "message": "big"},
        files={"screenshot": ("big.png", huge, "image/png")},
    )
    assert r.status_code == 413


def test_upload_rejects_unauthenticated(env):
    r = env["client"].post(
        "/api/workers/report-error-with-screenshot",
        data={"kind": "task_fail", "message": "x"},
        files={"screenshot": ("s.png", _tiny_png_bytes(), "image/png")},
    )
    assert r.status_code == 401


def test_dedupe_within_window_updates_screenshot_url(env):
    """같은 (worker, kind, message) 10분 내면 DB row 는 중복 생성 안 함.
    단 screenshot_url 은 최신 것으로 업데이트 (최근 실패 화면이 더 중요)."""
    png1 = _tiny_png_bytes()
    png2 = _tiny_png_bytes() + b"modified"
    # 1회
    env["client"].post(
        "/api/workers/report-error-with-screenshot",
        headers={"X-Worker-Token": env["worker_token"]},
        data={"kind": "task_fail", "message": "same msg"},
        files={"screenshot": ("1.png", png1, "image/png")},
    )
    # 2회 (dedupe)
    r2 = env["client"].post(
        "/api/workers/report-error-with-screenshot",
        headers={"X-Worker-Token": env["worker_token"]},
        data={"kind": "task_fail", "message": "same msg"},
        files={"screenshot": ("2.png", png2, "image/png")},
    )
    assert r2.json()["deduped"] is True

    db = env["Session"]()
    errs = db.query(WorkerError).all()
    assert len(errs) == 1  # DB row 는 1개
    # screenshot_url 이 최신 파일 가리킴
    latest_file = env["screenshot_dir"] / errs[0].screenshot_url
    assert latest_file.read_bytes() == png2
    db.close()


def test_admin_list_errors_includes_screenshot_url(env):
    env["client"].post(
        "/api/workers/report-error-with-screenshot",
        headers={"X-Worker-Token": env["worker_token"]},
        data={"kind": "task_fail", "message": "m"},
        files={"screenshot": ("s.png", _tiny_png_bytes(), "image/png")},
    )
    r = env["client"].get(
        "/api/admin/workers/errors",
        headers={"Authorization": f"Bearer {env['admin_jwt']}"},
    )
    items = r.json()
    assert len(items) == 1
    assert items[0]["screenshot_url"] is not None


def test_admin_can_fetch_screenshot_file(env):
    env["client"].post(
        "/api/workers/report-error-with-screenshot",
        headers={"X-Worker-Token": env["worker_token"]},
        data={"kind": "task_fail", "message": "m"},
        files={"screenshot": ("s.png", _tiny_png_bytes(), "image/png")},
    )
    db = env["Session"]()
    path = db.query(WorkerError).first().screenshot_url
    db.close()

    r = env["client"].get(
        f"/api/admin/workers/errors/screenshot/{path}",
        headers={"Authorization": f"Bearer {env['admin_jwt']}"},
    )
    assert r.status_code == 200
    assert r.content == _tiny_png_bytes()


def test_admin_screenshot_rejects_path_traversal(env):
    r = env["client"].get(
        "/api/admin/workers/errors/screenshot/../../etc/passwd",
        headers={"Authorization": f"Bearer {env['admin_jwt']}"},
    )
    assert r.status_code in (400, 404)


def test_admin_screenshot_requires_admin_auth(env):
    r = env["client"].get("/api/admin/workers/errors/screenshot/any.png")
    assert r.status_code == 401
