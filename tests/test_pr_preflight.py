"""PR-Preflight: worker capability auto-diagnosis 테스트.

scope:
- worker/preflight.py: list_adb_devices / adspower_ping / system_health / collect_health
- server heartbeat_v2: adb_devices 보고 시 worker.ip_config 자동 세팅
- worker/commands.py: run_diag preflight 모드
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


# ───── preflight 측정 ─────


def test_list_adb_devices_parses_output():
    """adb devices 출력 정확히 파싱."""
    from worker.preflight import list_adb_devices

    fake_output = "List of devices attached\nR3CRA0QNFXK\tdevice\nXYZ123\tunauthorized\n"
    fake_result = MagicMock(stdout=fake_output, returncode=0)
    with patch("worker.preflight.subprocess.run", return_value=fake_result):
        devices = list_adb_devices()
    assert devices == ["R3CRA0QNFXK"]  # "device" 만, "unauthorized" 제외


def test_list_adb_devices_empty_when_no_devices():
    from worker.preflight import list_adb_devices
    fake_output = "List of devices attached\n\n"
    fake_result = MagicMock(stdout=fake_output, returncode=0)
    with patch("worker.preflight.subprocess.run", return_value=fake_result):
        assert list_adb_devices() == []


def test_list_adb_devices_handles_adb_missing():
    """ADB 미설치 → 빈 배열 (예외 안 던짐)."""
    from worker.preflight import list_adb_devices
    with patch("worker.preflight.subprocess.run", side_effect=FileNotFoundError):
        assert list_adb_devices() == []


def test_list_adb_devices_handles_timeout():
    from worker.preflight import list_adb_devices
    import subprocess
    with patch("worker.preflight.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=3)):
        assert list_adb_devices() == []


def test_collect_health_includes_expected_keys():
    from worker.preflight import collect_health
    with patch("worker.preflight.list_adb_devices", return_value=["DEVABC"]), \
         patch("worker.preflight.adspower_ping", return_value={"ok": True, "version": "5.x"}):
        h = collect_health()
    expected_keys = {
        "os_type", "cpu_percent", "mem_used_mb", "disk_free_gb",
        "adb_devices", "adspower_version", "playwright_browsers_ok",
    }
    assert expected_keys.issubset(set(h.keys()))
    assert h["adb_devices"] == ["DEVABC"]


# ───── server heartbeat: 자동 ip_config 세팅 ─────


@pytest.fixture
def db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    from hydra.db.models import Base

    p = tmp_path / "hb.db"
    engine = create_engine(f"sqlite:///{p}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(_ds, "engine", engine)
    monkeypatch.setattr(_ds, "SessionLocal", Session)
    s = Session()
    yield s
    s.close()


def test_heartbeat_sets_ip_config_when_empty_and_adb_reported(db, monkeypatch):
    from hydra.db.models import Worker
    from hydra.web.routes.worker_api import heartbeat_v2, HeartbeatRequest
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db.bind))

    w = Worker(name="pc-test", status="online", allow_campaign=True,
                token_sha256="x" * 64, ip_config=None)
    db.add(w); db.commit()

    req = HeartbeatRequest(
        version="abc123",
        os_type="windows",
        adb_devices=["DEVICE_AUTO_123"],
    )
    heartbeat_v2(req, worker=w)
    db.refresh(w)
    assert w.ip_config is not None
    cfg = json.loads(w.ip_config)
    assert cfg["adb_device_id"] == "DEVICE_AUTO_123"


def test_heartbeat_does_not_override_existing_ip_config(db, monkeypatch):
    """이미 ip_config 설정된 워커는 손대지 않음 (admin 수동 설정 보존)."""
    from hydra.db.models import Worker
    from hydra.web.routes.worker_api import heartbeat_v2, HeartbeatRequest
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db.bind))

    pre_existing = json.dumps({"adb_device_id": "ADMIN_SET"})
    w = Worker(name="pc-test", status="online", allow_campaign=True,
                token_sha256="x" * 64, ip_config=pre_existing)
    db.add(w); db.commit()

    req = HeartbeatRequest(
        version="abc123",
        os_type="windows",
        adb_devices=["NEW_DEVICE_456"],
    )
    heartbeat_v2(req, worker=w)
    db.refresh(w)
    cfg = json.loads(w.ip_config)
    assert cfg["adb_device_id"] == "ADMIN_SET"  # 보존됨


def test_heartbeat_no_op_when_no_adb_reported(db, monkeypatch):
    from hydra.db.models import Worker
    from hydra.web.routes.worker_api import heartbeat_v2, HeartbeatRequest
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db.bind))

    w = Worker(name="pc-test", status="online", allow_campaign=True,
                token_sha256="x" * 64, ip_config=None)
    db.add(w); db.commit()

    req = HeartbeatRequest(
        version="abc123",
        os_type="windows",
        adb_devices=[],  # 워커가 ADB 측정 못 함 OR 진짜 안 잡힘
    )
    heartbeat_v2(req, worker=w)
    db.refresh(w)
    assert w.ip_config is None  # 그대로 유지
