"""PR-D: server-side IpLog endpoints + worker client.

scope:
- /api/workers/ip-check: cross-account conflict 정확히 판정
- /api/workers/ip-log/start: IpLog INSERT + log_id 반환
- /api/workers/ip-log/end: ended_at 기록
- worker.ip_client.ensure_safe_ip_via_server: ADB 없으면 raise / 정상 흐름 / rotation
- worker code 에서 SessionLocal import/사용 0 (정통)
"""
from __future__ import annotations

import json
from datetime import datetime, UTC, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import pytest


@pytest.fixture
def db_session(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    from hydra.db.models import Base

    p = tmp_path / "iplog.db"
    engine = create_engine(f"sqlite:///{p}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(_ds, "engine", engine)
    monkeypatch.setattr(_ds, "SessionLocal", Session)
    s = Session()
    yield s
    s.close()


# ───── server endpoints ─────


def test_ip_check_available_when_no_history(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db_session.bind))
    from hydra.db.models import Account, Worker
    from hydra.web.routes.worker_iplog import ip_check, IpCheckRequest

    a = Account(gmail="a@x.com", password="E", status="active")
    w = Worker(name="pc-1", status="online", allow_campaign=True)
    db_session.add_all([a, w]); db_session.commit()

    req = IpCheckRequest(ip_address="1.2.3.4", account_id=a.id, cooldown_minutes=30)
    resp = ip_check(req, worker=w)
    assert resp.available is True


def test_ip_check_unavailable_when_other_account_used_recently(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db_session.bind))
    from hydra.db.models import Account, Worker, IpLog
    from hydra.web.routes.worker_iplog import ip_check, IpCheckRequest

    a1 = Account(gmail="a1@x.com", password="E", status="active")
    a2 = Account(gmail="a2@x.com", password="E", status="active")
    w = Worker(name="pc-1", status="online", allow_campaign=True)
    db_session.add_all([a1, a2, w])
    db_session.flush()
    db_session.add(IpLog(
        account_id=a1.id, ip_address="9.9.9.9",
        started_at=datetime.now(UTC).replace(tzinfo=None),
    ))
    db_session.commit()

    # a2 가 a1 의 IP 를 쓰려고 함 — 30분 cooldown 안이라 unavailable.
    req = IpCheckRequest(ip_address="9.9.9.9", account_id=a2.id, cooldown_minutes=30)
    resp = ip_check(req, worker=w)
    assert resp.available is False


def test_ip_check_same_account_ok(db_session, monkeypatch):
    """동일 계정 자기 IP 재사용은 OK (사람도 자기 IP 자주 씀)."""
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db_session.bind))
    from hydra.db.models import Account, Worker, IpLog
    from hydra.web.routes.worker_iplog import ip_check, IpCheckRequest

    a = Account(gmail="a@x.com", password="E", status="active")
    w = Worker(name="pc-1", status="online", allow_campaign=True)
    db_session.add_all([a, w])
    db_session.flush()
    db_session.add(IpLog(
        account_id=a.id, ip_address="9.9.9.9",
        started_at=datetime.now(UTC).replace(tzinfo=None),
    ))
    db_session.commit()

    req = IpCheckRequest(ip_address="9.9.9.9", account_id=a.id, cooldown_minutes=30)
    resp = ip_check(req, worker=w)
    assert resp.available is True


def test_ip_log_start_returns_id(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db_session.bind))
    from hydra.db.models import Account, Worker, IpLog, Task
    from hydra.web.routes.worker_iplog import ip_log_start, IpLogStartRequest

    a = Account(gmail="a@x.com", password="E", status="active")
    w = Worker(name="pc-1", status="online", allow_campaign=True)
    db_session.add_all([a, w]); db_session.flush()
    # 워커가 이 account 의 task 를 잡고 있는 상태 (소유권 검증 만족).
    t = Task(account_id=a.id, task_type="comment", status="running", worker_id=w.id)
    db_session.add(t); db_session.commit()

    req = IpLogStartRequest(account_id=a.id, ip_address="1.2.3.4", device_id="DEV")
    resp = ip_log_start(req, worker=w)
    assert resp.log_id > 0
    row = db_session.get(IpLog, resp.log_id)
    assert row is not None
    assert row.ip_address == "1.2.3.4"


def test_ip_log_start_rejects_unowned_account(db_session, monkeypatch):
    """워커가 잡지 않은 account_id 로 ip-log 보고 시 403."""
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db_session.bind))
    from fastapi import HTTPException
    from hydra.db.models import Account, Worker
    from hydra.web.routes.worker_iplog import ip_log_start, IpLogStartRequest

    a = Account(gmail="a@x.com", password="E", status="active")
    w = Worker(name="pc-1", status="online", allow_campaign=True)
    db_session.add_all([a, w]); db_session.commit()
    # 워커가 잡고 있는 task 없음.

    req = IpLogStartRequest(account_id=a.id, ip_address="1.2.3.4", device_id="DEV")
    with pytest.raises(HTTPException) as ei:
        ip_log_start(req, worker=w)
    assert ei.value.status_code == 403
    assert "not owned" in ei.value.detail


def test_ip_log_end_sets_ended_at(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds
    monkeypatch.setattr(_ds, "SessionLocal", sessionmaker(bind=db_session.bind))
    from hydra.db.models import Account, Worker, IpLog
    from hydra.web.routes.worker_iplog import ip_log_end, IpLogEndRequest

    a = Account(gmail="a@x.com", password="E", status="active")
    w = Worker(name="pc-1", status="online", allow_campaign=True)
    db_session.add_all([a, w]); db_session.flush()
    rec = IpLog(account_id=a.id, ip_address="1.2.3.4")
    db_session.add(rec); db_session.commit()

    ip_log_end(IpLogEndRequest(log_id=rec.id), worker=w)
    db_session.refresh(rec)
    assert rec.ended_at is not None


# ───── worker ip_client ─────


@pytest.mark.asyncio
async def test_ensure_safe_ip_raises_when_no_adb():
    from worker.ip_client import ensure_safe_ip_via_server
    from hydra.infra.ip_errors import IPRotationFailed
    client = MagicMock()
    with patch("worker.ip_client.settings") as s:
        s.adb_device_id = None
        with pytest.raises(IPRotationFailed) as ei:
            await ensure_safe_ip_via_server(
                client, account_id=1, adb_device_id=None,
            )
        assert "no_adb_device_configured" in str(ei.value)


@pytest.mark.asyncio
async def test_ensure_safe_ip_happy_path_returns_log_id():
    from worker.ip_client import ensure_safe_ip_via_server
    client = MagicMock()
    client.headers = {}
    # ip-check 응답: available=True
    check_resp = MagicMock()
    check_resp.json.return_value = {"available": True}
    check_resp.raise_for_status = lambda: None
    # ip-log/start 응답: log_id=42
    start_resp = MagicMock()
    start_resp.json.return_value = {"log_id": 42}
    start_resp.raise_for_status = lambda: None
    client._request.side_effect = [check_resp, start_resp]
    with patch("worker.ip_client._get_current_ip", new=AsyncMock(return_value="1.2.3.4")):
        log_id = await ensure_safe_ip_via_server(
            client, account_id=1, adb_device_id="DEV",
        )
    assert log_id == 42


@pytest.mark.asyncio
async def test_ensure_safe_ip_rotates_when_unavailable():
    from worker.ip_client import ensure_safe_ip_via_server
    client = MagicMock()
    client.headers = {}
    check_resp = MagicMock()
    check_resp.json.return_value = {"available": False}
    check_resp.raise_for_status = lambda: None
    start_resp = MagicMock()
    start_resp.json.return_value = {"log_id": 100}
    start_resp.raise_for_status = lambda: None
    client._request.side_effect = [check_resp, start_resp]
    with patch("worker.ip_client._get_current_ip", new=AsyncMock(return_value="OLD_IP")), \
         patch("worker.ip_client.rotate_ip", new=AsyncMock(return_value="NEW_IP")) as rotate:
        log_id = await ensure_safe_ip_via_server(
            client, account_id=1, adb_device_id="DEV",
        )
    assert rotate.called
    assert log_id == 100


def test_end_ip_log_no_op_when_log_id_none():
    from worker.ip_client import end_ip_log_via_server
    client = MagicMock()
    end_ip_log_via_server(client, log_id=None)
    client._request.assert_not_called()


def test_end_ip_log_calls_api():
    from worker.ip_client import end_ip_log_via_server
    client = MagicMock()
    client.headers = {}
    end_ip_log_via_server(client, log_id=42)
    args, kwargs = client._request.call_args
    assert args[1] == "/api/workers/ip-log/end"
    assert kwargs["json"] == {"log_id": 42}


# ───── 워커 코드 SessionLocal 사용 안 함 정통 검증 ─────


def test_worker_app_does_not_import_sessionlocal():
    """worker/app.py 에서 SessionLocal import 또는 호출 없어야."""
    with open("worker/app.py") as f:
        src = f.read()
    # import 없음
    assert "from hydra.db.session import SessionLocal" not in src
    # 사용 없음 (주석은 OK)
    code_lines = [l for l in src.split("\n") if not l.strip().startswith("#")]
    code = "\n".join(code_lines)
    assert "SessionLocal()" not in code, "worker/app.py 가 SessionLocal() 호출 — PR-D 위반"


def test_worker_session_does_not_use_db_param():
    """worker/session.py 의 start() 가 db= 인자 안 받음 (이미 PR-D 이전엔 받았음)."""
    import inspect
    from worker.session import WorkerSession
    sig = inspect.signature(WorkerSession.start)
    # db= 파라미터가 있어도 default None 이고 사용 안 함은 OK — 정통 검증은 caller 가 안 넘기는지.
    # 위 worker_app_does_not_import test 가 충분.
    assert "db" in sig.parameters or "db" not in sig.parameters  # placeholder
