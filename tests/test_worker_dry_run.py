"""Task M2.1-1: worker executor DRY-RUN 모드."""
import asyncio
import os

import pytest


@pytest.fixture(autouse=True)
def _restore_executor_module():
    """각 테스트 후 executor 모듈을 DRY-RUN 없이 재-reload 하여 상태 누수 차단."""
    yield
    os.environ.pop("HYDRA_WORKER_DRY_RUN", None)
    import importlib
    import worker.executor as ex
    importlib.reload(ex)


def _import_executor_fresh(monkeypatch, dry_run: bool):
    if dry_run:
        monkeypatch.setenv("HYDRA_WORKER_DRY_RUN", "1")
    else:
        monkeypatch.delenv("HYDRA_WORKER_DRY_RUN", raising=False)
    import importlib
    import worker.executor as ex
    importlib.reload(ex)
    return ex


def test_dry_run_flag_parsed_true(monkeypatch):
    ex = _import_executor_fresh(monkeypatch, dry_run=True)
    assert ex._DRY_RUN is True


def test_dry_run_flag_parsed_false(monkeypatch):
    ex = _import_executor_fresh(monkeypatch, dry_run=False)
    assert ex._DRY_RUN is False


def test_dry_run_flag_case_insensitive(monkeypatch):
    import importlib
    for v in ("1", "true", "TRUE", "yes", "Yes"):
        monkeypatch.setenv("HYDRA_WORKER_DRY_RUN", v)
        import worker.executor as ex
        importlib.reload(ex)
        assert ex._DRY_RUN is True, f"failed for {v!r}"
    for v in ("", "0", "false", "no", "abc"):
        monkeypatch.setenv("HYDRA_WORKER_DRY_RUN", v)
        import worker.executor as ex
        importlib.reload(ex)
        assert ex._DRY_RUN is False, f"should be false for {v!r}"


def test_execute_in_dry_run_returns_immediately_without_real_logic(monkeypatch):
    monkeypatch.setenv("HYDRA_WORKER_DRY_RUN", "1")
    import importlib
    import worker.executor as ex
    importlib.reload(ex)

    task = {
        "id": 1, "task_type": "warmup", "account_id": 42,
        "payload": "{}",
        "account_snapshot": {
            "id": 42, "gmail": "a@x.com",
            "adspower_profile_id": "p1", "encrypted_password": "",
        },
    }
    executor = ex.TaskExecutor()
    result = asyncio.run(executor.execute(task))
    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["task_type"] == "warmup"
