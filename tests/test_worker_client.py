"""Worker 클라이언트 테스트 (서버 mock 없이 단위 테스트)."""
from worker.config import WorkerConfig
from worker.client import ServerClient
from worker.app import WorkerApp


def test_worker_config_defaults():
    cfg = WorkerConfig()
    assert cfg.server_url == "http://localhost:8000"
    assert cfg.heartbeat_interval == 30
    assert cfg.task_fetch_interval == 5
    assert cfg.max_concurrent_tasks == 3
    # Task 33: worker_version 이 git short hash 로 자동 감지되므로 문자열만 검증
    assert isinstance(cfg.worker_version, str) and len(cfg.worker_version) >= 4


def test_worker_config_from_env(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://example.com:9000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "test_token_123")
    cfg = WorkerConfig()
    assert cfg.server_url == "http://example.com:9000"
    assert cfg.worker_token == "test_token_123"


def test_server_client_init(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://test:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "tok123")
    # Re-init config in all modules that imported it
    new_cfg = WorkerConfig()
    import worker.config as cfg_module
    import worker.client as client_module
    monkeypatch.setattr(cfg_module, "config", new_cfg)
    monkeypatch.setattr(client_module, "config", new_cfg)
    client = ServerClient()
    assert client.base_url == "http://test:8000"
    assert client.headers["X-Worker-Token"] == "tok123"
    client.close()


def test_worker_app_init(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://test:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "tok123")
    new_cfg = WorkerConfig()
    import worker.config as cfg_module
    import worker.client as client_module
    import worker.app as app_module
    monkeypatch.setattr(cfg_module, "config", new_cfg)
    monkeypatch.setattr(client_module, "config", new_cfg)
    monkeypatch.setattr(app_module, "config", new_cfg)
    app = WorkerApp()
    assert app.running is True
    assert app.last_heartbeat is None
    app.client.close()


def test_client_heartbeat_calls_v2_endpoint(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt-123")
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    from worker.config import WorkerConfig
    import worker.config as cfg_module
    import worker.client as client_module
    new_cfg = WorkerConfig()
    monkeypatch.setattr(cfg_module, "config", new_cfg)
    monkeypatch.setattr(client_module, "config", new_cfg)
    from worker.client import ServerClient

    calls = []

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "current_version": "v1", "paused": False,
                "canary_worker_ids": [], "restart_requested": False,
                "worker_config": {"poll_interval_sec": 15},
            }
        def raise_for_status(self):
            pass

    class FakeHttp:
        def post(self, url, **kw):
            calls.append(url)
            return FakeResp()
        def request(self, method, url, **kw):
            calls.append(url)
            return FakeResp()
        def close(self):
            pass

    client = ServerClient()
    client.http = FakeHttp()
    result = client.heartbeat()

    assert any("/api/workers/heartbeat/v2" in u for u in calls)
    assert result["current_version"] == "v1"
    client.close()


def test_client_fetch_tasks_calls_v2_endpoint(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt-123")
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    from worker.config import WorkerConfig
    import worker.config as cfg_module
    import worker.client as client_module
    new_cfg = WorkerConfig()
    monkeypatch.setattr(cfg_module, "config", new_cfg)
    monkeypatch.setattr(client_module, "config", new_cfg)
    from worker.client import ServerClient

    calls = []
    class FakeResp:
        status_code = 200
        def json(self): return {"tasks": []}
        def raise_for_status(self): pass
    class FakeHttp:
        def post(self, url, **kw):
            calls.append(url); return FakeResp()
        def request(self, method, url, **kw):
            calls.append(url); return FakeResp()
        def close(self): pass

    c = ServerClient(); c.http = FakeHttp()
    c.fetch_tasks()
    assert any("/api/tasks/v2/fetch" in u for u in calls)
    c.close()


def test_client_complete_task_calls_v2_endpoint(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt-123")
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    from worker.config import WorkerConfig
    import worker.config as cfg_module
    import worker.client as client_module
    new_cfg = WorkerConfig()
    monkeypatch.setattr(cfg_module, "config", new_cfg)
    monkeypatch.setattr(client_module, "config", new_cfg)
    from worker.client import ServerClient

    calls = []
    class FakeResp:
        status_code = 200
        def json(self): return {"ok": True}
        def raise_for_status(self): pass
    class FakeHttp:
        def post(self, url, **kw):
            calls.append(url); return FakeResp()
        def request(self, method, url, **kw):
            calls.append(url); return FakeResp()
        def close(self): pass

    c = ServerClient(); c.http = FakeHttp()
    c.complete_task(123, result='{"ok":true}')
    assert any("/api/tasks/v2/complete" in u for u in calls)
    c.close()


def test_client_fail_task_calls_v2_endpoint(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt-123")
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    from worker.config import WorkerConfig
    import worker.config as cfg_module
    import worker.client as client_module
    new_cfg = WorkerConfig()
    monkeypatch.setattr(cfg_module, "config", new_cfg)
    monkeypatch.setattr(client_module, "config", new_cfg)
    from worker.client import ServerClient

    calls = []
    class FakeResp:
        status_code = 200
        def json(self): return {"ok": True}
        def raise_for_status(self): pass
    class FakeHttp:
        def post(self, url, **kw):
            calls.append(url); return FakeResp()
        def request(self, method, url, **kw):
            calls.append(url); return FakeResp()
        def close(self): pass

    c = ServerClient(); c.http = FakeHttp()
    c.fail_task(123, error="boom")
    assert any("/api/tasks/v2/fail" in u for u in calls)
    c.close()


def test_worker_app_skips_fetch_when_paused(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt")
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    from worker.config import WorkerConfig
    import worker.config as cfg_mod
    import worker.client as cli_mod
    import worker.app as app_mod
    new_cfg = WorkerConfig()
    for m in (cfg_mod, cli_mod, app_mod):
        monkeypatch.setattr(m, "config", new_cfg)
    from worker.app import WorkerApp

    app = WorkerApp()

    fetch_calls = []

    class FakeClient:
        def heartbeat(self):
            return {"paused": True, "current_version": "v1"}
        def fetch_tasks(self):
            fetch_calls.append(1)
            return []
        def close(self): pass

    app.client = FakeClient()
    import asyncio
    asyncio.run(app._async_tick())

    # paused=True 이므로 fetch 호출되지 않아야
    assert fetch_calls == []


def test_worker_app_current_task_id_default_none(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt")
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    from worker.config import WorkerConfig
    import worker.config as cfg_mod, worker.client as cli_mod, worker.app as app_mod
    new_cfg = WorkerConfig()
    for m in (cfg_mod, cli_mod, app_mod):
        monkeypatch.setattr(m, "config", new_cfg)
    from worker.app import WorkerApp

    app = WorkerApp()
    assert getattr(app, "_current_task_id", "MISSING") is None


def test_client_falls_back_to_ipv4_on_connect_error(monkeypatch):
    """Primary (dual-stack) 가 ConnectError 내면 IPv4 클라이언트로 재시도 성공해야."""
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt")
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    from worker.config import WorkerConfig
    import worker.config as cfg_mod, worker.client as cli_mod
    new_cfg = WorkerConfig()
    for m in (cfg_mod, cli_mod):
        monkeypatch.setattr(m, "config", new_cfg)
    from worker.client import ServerClient
    import httpx

    class FailingHttp:
        def request(self, method, url, **kw):
            raise httpx.ConnectError("IPv6 route broken")
        def close(self): pass

    class FakeResp:
        status_code = 200
        def json(self): return {"current_version": "v1", "paused": False,
                                "canary_worker_ids": [], "restart_requested": False,
                                "worker_config": {}}
        def raise_for_status(self): pass

    # 실제 httpx.Client 생성을 가로채서 두 번째 클라이언트는 성공하도록
    call_count = {"n": 0}
    orig_client = httpx.Client
    def fake_client(*a, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return FailingHttp()  # primary
        class OkHttp:
            def request(self, method, url, **kw):
                return FakeResp()
            def close(self): pass
        return OkHttp()  # fallback (v4)
    monkeypatch.setattr(httpx, "Client", fake_client)

    client = ServerClient()
    result = client.heartbeat()
    assert result["current_version"] == "v1"
    assert client._v4_fallback_used is True
