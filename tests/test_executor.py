"""Executor 테스트 — 디스패치 로직 검증 (브라우저 불필요)."""
from worker.executor import TaskExecutor

def test_executor_has_all_handlers():
    executor = TaskExecutor()
    expected = {"comment", "reply", "like", "like_boost", "subscribe", "warmup",
                "ghost_check", "login", "channel_setup",
                "create_profile", "retire_profile", "onboard"}
    assert set(executor.handlers.keys()) == expected

def test_executor_handler_count():
    executor = TaskExecutor()
    assert len(executor.handlers) == 12

def test_executor_handlers_are_callable():
    executor = TaskExecutor()
    for name, handler in executor.handlers.items():
        assert callable(handler), f"Handler '{name}' is not callable"
