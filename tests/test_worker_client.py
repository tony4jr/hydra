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
    assert cfg.worker_version == "0.1.0"


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
