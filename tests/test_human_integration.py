"""Phase 1.5.5 — hydra 통합 검증.

워커 driver 가 HYDRA_HUMAN_PATCH env flag 따라 patch_context_async 호출 여부 결정.
실제 AdsPower/Playwright 없이 mock 으로 핵심 분기만 검증.
"""
import os
from unittest.mock import MagicMock, patch
import pytest


def _make_session(monkeypatch, flag_value=None, preset_value=None):
    """Mock BrowserSession with mock context."""
    from hydra.browser.driver import BrowserSession
    sess = BrowserSession.__new__(BrowserSession)
    sess._context = MagicMock()
    sess._context.pages = []
    sess._context.on = MagicMock()

    if flag_value is None:
        monkeypatch.delenv("HYDRA_HUMAN_PATCH", raising=False)
    else:
        monkeypatch.setenv("HYDRA_HUMAN_PATCH", flag_value)
    if preset_value:
        monkeypatch.setenv("HYDRA_HUMAN_PRESET", preset_value)
    else:
        monkeypatch.delenv("HYDRA_HUMAN_PRESET", raising=False)
    return sess


def test_human_patch_disabled_by_default(monkeypatch):
    """flag 없으면 patch_context_async 호출 안 됨."""
    sess = _make_session(monkeypatch, flag_value=None)
    with patch("hydra.browser.human.patch_context_async") as mock_patch:
        sess._apply_human_patch_if_enabled()
        mock_patch.assert_not_called()


def test_human_patch_false_string_no_op(monkeypatch):
    """HYDRA_HUMAN_PATCH=false → no-op."""
    sess = _make_session(monkeypatch, flag_value="false")
    with patch("hydra.browser.human.patch_context_async") as mock_patch:
        sess._apply_human_patch_if_enabled()
        mock_patch.assert_not_called()


def test_human_patch_true_applies(monkeypatch):
    """HYDRA_HUMAN_PATCH=true → patch_context_async called once."""
    sess = _make_session(monkeypatch, flag_value="true")
    with patch("hydra.browser.human.patch_context_async") as mock_patch:
        sess._apply_human_patch_if_enabled()
        assert mock_patch.call_count == 1


def test_human_patch_uses_default_preset(monkeypatch):
    """preset 미지정 시 'careful' 사용."""
    sess = _make_session(monkeypatch, flag_value="1")
    with patch("hydra.browser.human.patch_context_async") as mock_patch, \
         patch("hydra.browser.human.resolve_config") as mock_resolve:
        sess._apply_human_patch_if_enabled()
        mock_resolve.assert_called_once_with("careful")


def test_human_patch_custom_preset(monkeypatch):
    """HYDRA_HUMAN_PRESET=default → default preset 사용."""
    sess = _make_session(monkeypatch, flag_value="1", preset_value="default")
    with patch("hydra.browser.human.patch_context_async") as mock_patch, \
         patch("hydra.browser.human.resolve_config") as mock_resolve:
        sess._apply_human_patch_if_enabled()
        mock_resolve.assert_called_once_with("default")


def test_human_patch_failure_is_non_fatal(monkeypatch, caplog):
    """patch 적용 실패는 task 실행 안 막음."""
    sess = _make_session(monkeypatch, flag_value="true")
    with patch("hydra.browser.human.patch_context_async",
               side_effect=RuntimeError("CDP unavailable")):
        # 예외 propagate X
        sess._apply_human_patch_if_enabled()


def test_worker_config_reads_env(monkeypatch):
    """WorkerConfig 가 HYDRA_HUMAN_PATCH/PRESET env 정확히 반영."""
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt")
    for k in ("SERVER_URL", "WORKER_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HYDRA_HUMAN_PATCH", "true")
    monkeypatch.setenv("HYDRA_HUMAN_PRESET", "default")

    from worker.config import WorkerConfig
    cfg = WorkerConfig()
    assert cfg.human_patch_enabled is True
    assert cfg.human_patch_preset == "default"


def test_worker_config_default_disabled(monkeypatch):
    """env 없으면 default = disabled + careful."""
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt")
    for k in ("SERVER_URL", "WORKER_TOKEN", "HYDRA_HUMAN_PATCH", "HYDRA_HUMAN_PRESET"):
        monkeypatch.delenv(k, raising=False)

    from worker.config import WorkerConfig
    cfg = WorkerConfig()
    assert cfg.human_patch_enabled is False
    assert cfg.human_patch_preset == "careful"
