"""Phase 3.2b — task/login lifecycle 이벤트가 account timeline 에 emit 되는지."""
from unittest.mock import MagicMock, AsyncMock
import asyncio
import json

import pytest


def test_emit_lifecycle_calls_client(monkeypatch):
    """_emit_lifecycle 가 client.report_account_event 를 invoke."""
    from worker.app import WorkerApp
    app = WorkerApp.__new__(WorkerApp)  # __init__ bypass — client 만 필요
    app.client = MagicMock()
    app._emit_lifecycle(42, "task_start", "msg", task_id=99,
                        context={"k": "v"})
    assert app.client.report_account_event.called
    kw = app.client.report_account_event.call_args.kwargs
    assert kw["account_id"] == 42
    assert kw["event_type"] == "task_start"
    assert kw["message"] == "msg"
    assert kw["task_id"] == 99
    assert kw["context"] == {"k": "v"}


def test_emit_lifecycle_noop_when_no_account_id():
    from worker.app import WorkerApp
    app = WorkerApp.__new__(WorkerApp)
    app.client = MagicMock()
    app._emit_lifecycle(None, "task_start", "msg")
    assert not app.client.report_account_event.called


def test_emit_lifecycle_swallows_client_exception():
    from worker.app import WorkerApp
    app = WorkerApp.__new__(WorkerApp)
    app.client = MagicMock()
    app.client.report_account_event.side_effect = RuntimeError("network")
    # 예외 propagate 안 함 (best-effort)
    app._emit_lifecycle(1, "task_fail", "x", task_id=2)
    assert app.client.report_account_event.called


def test_emit_lifecycle_noop_when_client_lacks_method():
    from worker.app import WorkerApp
    app = WorkerApp.__new__(WorkerApp)
    app.client = object()  # report_account_event 없음
    # 예외 안 나야 함
    app._emit_lifecycle(1, "task_start", "x")


@pytest.mark.asyncio
async def test_handle_login_emits_login_success(monkeypatch):
    """_handle_login 가 성공 시 login_success event emit."""
    from worker.executor import TaskExecutor as Executor
    import worker.executor as exe_mod

    # auto_login → True
    async def _fake_login(*a, **kw): return True
    monkeypatch.setattr(exe_mod, "auto_login", _fake_login)

    client = MagicMock()
    session = MagicMock()
    session.server_client = client
    session.browser.page = MagicMock()

    ex = Executor.__new__(Executor)
    task = {"id": 7, "task_type": "login"}
    payload = {"email": "x@y", "password": "p", "account_id": 33}
    res = await ex._handle_login(task, payload, session)
    body = json.loads(res)
    assert body["success"] is True
    assert client.report_account_event.called
    kw = client.report_account_event.call_args.kwargs
    assert kw["event_type"] == "login_success"
    assert kw["account_id"] == 33
    assert kw["task_id"] == 7


@pytest.mark.asyncio
async def test_handle_login_emits_login_fail_and_raises(monkeypatch):
    from worker.executor import TaskExecutor as Executor
    import worker.executor as exe_mod

    async def _fake_login(*a, **kw): return False
    monkeypatch.setattr(exe_mod, "auto_login", _fake_login)

    client = MagicMock()
    session = MagicMock()
    session.server_client = client
    session.browser.page = MagicMock()

    ex = Executor.__new__(Executor)
    task = {"id": 8, "task_type": "login"}
    payload = {"email": "x@y", "password": "p", "account_id": 44}
    with pytest.raises(RuntimeError):
        await ex._handle_login(task, payload, session)
    assert client.report_account_event.called
    kw = client.report_account_event.call_args.kwargs
    assert kw["event_type"] == "login_fail"
    assert kw["account_id"] == 44


@pytest.mark.asyncio
async def test_handle_login_skips_emit_when_no_account_id(monkeypatch):
    from worker.executor import TaskExecutor as Executor
    import worker.executor as exe_mod

    async def _fake_login(*a, **kw): return True
    monkeypatch.setattr(exe_mod, "auto_login", _fake_login)

    client = MagicMock()
    session = MagicMock()
    session.server_client = client
    session.browser.page = MagicMock()

    ex = Executor.__new__(Executor)
    task = {"id": 9, "task_type": "login"}
    payload = {"email": "x@y", "password": "p"}  # account_id 없음
    await ex._handle_login(task, payload, session)
    assert not client.report_account_event.called
