"""Phase 3.2 — AccountEvent timeline + worker ingest + admin query."""
from datetime import UTC, datetime
import hashlib
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Account, AccountEvent, Base, Task, Worker


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(Account(id=1, gmail="a@b.com", password="x",
                  adspower_profile_id="p1", status="active"))
    s.add(Worker(id=1, name="pc-01", status="online", current_version="v1",
                 last_heartbeat=datetime.now(UTC)))
    s.commit()
    yield s
    s.close()
    engine.dispose()


def test_account_event_model_columns():
    cols = {c.name for c in AccountEvent.__table__.columns}
    expected = {
        "id", "account_id", "worker_id", "task_id", "event_type",
        "screen_state", "failure_taxonomy", "message", "context", "created_at",
    }
    assert expected.issubset(cols)


def test_account_event_insert_and_query(db):
    db.add(AccountEvent(
        account_id=1, worker_id=1, event_type="task_fail",
        message="login fail post_password_unknown",
        screen_state="post_password_unknown",
        failure_taxonomy="page_variant",
        context=json.dumps({"reason": "no email input"}),
    ))
    db.commit()
    rows = db.query(AccountEvent).filter(AccountEvent.account_id == 1).all()
    assert len(rows) == 1
    assert rows[0].event_type == "task_fail"
    assert rows[0].screen_state == "post_password_unknown"


def test_account_event_cascade_declared_in_migration():
    """migration 에 ondelete=CASCADE 가 선언되어 있는지 (SQLite 는 PRAGMA 없으면
    enforce 안 함 — Postgres prod 동작 검증은 파일 텍스트로 확인)."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "ph4_account_events.py"
    src = p.read_text()
    assert 'ondelete="CASCADE"' in src
    assert 'fk_acctevt_account' in src


def test_admin_timeline_router_registered():
    from hydra.web.app import app
    paths = [r.path for r in app.routes]
    assert any("/accounts/{account_id}/timeline" in p for p in paths)
    assert any("/accounts/{account_id}/note" in p for p in paths)


def test_worker_account_event_endpoint_registered():
    from hydra.web.app import app
    paths = [r.path for r in app.routes]
    assert any("/api/workers/account-event" in p for p in paths)


def test_allowed_event_types_set():
    from hydra.web.routes.worker_api import _ALLOWED_EVENT_TYPES
    for t in ("task_start", "task_complete", "task_fail",
              "login_success", "login_fail", "unknown_screen", "note", "other"):
        assert t in _ALLOWED_EVENT_TYPES


def test_capture_unknown_screen_emits_account_event(monkeypatch):
    """capture_unknown_screen 가 client.report_account_event 도 호출."""
    import asyncio
    from worker.capture import capture_unknown_screen
    from hydra.protocol.failure_taxonomy import FailureTaxonomy

    page = MagicMock()
    async def _ss(**kw): return b"png"
    async def _content(): return "<html></html>"
    async def _title(): return "T"
    page.screenshot = _ss
    page.content = _content
    page.title = _title
    page.url = "https://accounts.google.com/x"

    client = MagicMock()
    asyncio.run(capture_unknown_screen(
        page, screen_state="POST_PASSWORD_UNKNOWN",
        taxonomy=FailureTaxonomy.PAGE_VARIANT, reason="no email input",
        client=client, task_id=42, account_id=1,
    ))
    assert client.report_account_event.called
    kwargs = client.report_account_event.call_args.kwargs
    assert kwargs["account_id"] == 1
    assert kwargs["event_type"] == "unknown_screen"
    assert kwargs["task_id"] == 42
    assert kwargs["screen_state"] == "POST_PASSWORD_UNKNOWN"


# ───────── Endpoint behavior tests (Codex P2 fix — was registration-only) ─────────

def _sha(s): return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture
def api_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TS)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")
    monkeypatch.setenv("ENROLLMENT_SECRET", "x" * 32)
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")

    s = TS()
    wtok = "w-" + "x" * 32
    w = Worker(name="pc-01", status="online", current_version="v1",
               last_heartbeat=datetime.now(UTC),
               token_hash=hash_password(wtok),
               token_sha256=_sha(wtok), token_prefix=wtok[:8])
    s.add(w); s.commit(); s.refresh(w); wid = w.id

    wtok2 = "w-" + "y" * 32
    w2 = Worker(name="pc-02", status="online", current_version="v1",
                last_heartbeat=datetime.now(UTC),
                token_hash=hash_password(wtok2),
                token_sha256=_sha(wtok2), token_prefix=wtok2[:8])
    s.add(w2); s.commit(); s.refresh(w2); wid2 = w2.id

    a = Account(gmail="a@b.com", password="x", adspower_profile_id="p1", status="active")
    s.add(a); s.commit(); s.refresh(a); aid = a.id

    # Task owned by w (wid), bound to account aid
    t_ok = Task(task_type="comment", status="running", worker_id=wid, account_id=aid)
    s.add(t_ok); s.commit(); s.refresh(t_ok); tid_ok = t_ok.id

    # Task owned by w2
    t_other = Task(task_type="comment", status="running", worker_id=wid2, account_id=aid)
    s.add(t_other); s.commit(); s.refresh(t_other); tid_other = t_other.id

    s.close()

    from hydra.web.app import app
    client = TestClient(app)
    yield {"client": client, "Session": TS,
           "wtok": wtok, "wtok2": wtok2,
           "wid": wid, "aid": aid,
           "tid_ok": tid_ok, "tid_other": tid_other}
    engine.dispose()


def test_account_event_endpoint_persists(api_env):
    r = api_env["client"].post(
        "/api/workers/account-event",
        headers={"X-Worker-Token": api_env["wtok"]},
        json={"account_id": api_env["aid"], "event_type": "task_complete",
              "message": "ok", "task_id": api_env["tid_ok"]},
    )
    assert r.status_code == 200, r.text
    s = api_env["Session"]()
    rows = s.query(AccountEvent).all()
    s.close()
    assert len(rows) == 1
    assert rows[0].event_type == "task_complete"
    assert rows[0].task_id == api_env["tid_ok"]


def test_account_event_endpoint_404_on_unknown_account(api_env):
    r = api_env["client"].post(
        "/api/workers/account-event",
        headers={"X-Worker-Token": api_env["wtok"]},
        json={"account_id": 99999, "event_type": "note", "message": "x"},
    )
    assert r.status_code == 404


def test_account_event_endpoint_403_on_foreign_task(api_env):
    """Codex P1 fix — w 가 w2 의 task 로 emit 시도하면 403."""
    r = api_env["client"].post(
        "/api/workers/account-event",
        headers={"X-Worker-Token": api_env["wtok"]},
        json={"account_id": api_env["aid"], "event_type": "task_fail",
              "message": "poison", "task_id": api_env["tid_other"]},
    )
    assert r.status_code == 403


def test_account_event_endpoint_404_on_unknown_task(api_env):
    r = api_env["client"].post(
        "/api/workers/account-event",
        headers={"X-Worker-Token": api_env["wtok"]},
        json={"account_id": api_env["aid"], "event_type": "task_fail",
              "message": "x", "task_id": 99999},
    )
    assert r.status_code == 404


def test_capture_skips_account_event_when_no_account_id(monkeypatch):
    """account_id 없으면 report_account_event 호출 안 함."""
    import asyncio
    from worker.capture import capture_unknown_screen
    from hydra.protocol.failure_taxonomy import FailureTaxonomy

    page = MagicMock()
    async def _ss(**kw): return b"png"
    async def _content(): return ""
    async def _title(): return ""
    page.screenshot = _ss
    page.content = _content
    page.title = _title
    page.url = ""

    client = MagicMock()
    asyncio.run(capture_unknown_screen(
        page, screen_state="X", taxonomy=FailureTaxonomy.PAGE_VARIANT,
        reason="", client=client, task_id=None, account_id=None,
    ))
    assert not client.report_account_event.called
