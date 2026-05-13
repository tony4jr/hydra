"""Codex 5/12 review 의 P1 두 가지 (Phase 2 closure 후 B 옵션):

  1. AdsPower API key normalize — secrets/env/copy-paste 의 trailing
     whitespace / quotes 가 Bearer 헤더에 새는 위험 차단
  2. Task Scheduler 자가 등록의 WorkingDirectory 명시 — 부팅 시 default cwd
     (C:\\Windows\\System32) 로 시작하면 import/config 경로 깨짐
"""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


# ───────── 1. AdsPower key normalize ─────────

def test_normalize_strips_whitespace():
    from hydra.browser.adspower import _normalize_api_key
    assert _normalize_api_key("abc123") == "abc123"
    assert _normalize_api_key("abc123\n") == "abc123"
    assert _normalize_api_key("abc123\r\n") == "abc123"
    assert _normalize_api_key("  abc123  ") == "abc123"
    assert _normalize_api_key("\tabc123\t") == "abc123"


def test_normalize_strips_wrapping_quotes():
    from hydra.browser.adspower import _normalize_api_key
    assert _normalize_api_key('"abc123"') == "abc123"
    assert _normalize_api_key("'abc123'") == "abc123"
    # mixed 이면 따옴표로 안 봄 (의도된 값일 수도)
    assert _normalize_api_key('"abc123\'') == '"abc123\''
    # 따옴표 안에 trailing whitespace
    assert _normalize_api_key('  "abc123"  ') == "abc123"


def test_normalize_empty_or_none():
    from hydra.browser.adspower import _normalize_api_key
    assert _normalize_api_key("") == ""
    assert _normalize_api_key(None) == ""
    assert _normalize_api_key("   ") == ""


def test_browser_adspower_client_uses_normalized_key(monkeypatch):
    """hydra.browser.AdsPowerClient._headers() 가 정규화된 key 로 Bearer 생성."""
    monkeypatch.setenv("ADSPOWER_API_KEY", "  abc123\r\n")
    from hydra.browser.adspower import AdsPowerClient
    c = AdsPowerClient()
    headers = c._headers()
    assert headers["Authorization"] == "Bearer abc123"
    # raw \r\n 가 헤더에 새지 않아야
    assert "\r" not in headers["Authorization"]
    assert "\n" not in headers["Authorization"]


def test_worker_adspower_client_uses_normalized_key(monkeypatch):
    """worker.adspower.AdsPowerClient._headers() / _params() 도 정규화 적용."""
    monkeypatch.setenv("ADSPOWER_API_KEY", '"AGENT-TOKEN\n"')
    from worker.adspower import AdsPowerClient
    c = AdsPowerClient()
    h = c._headers()
    assert h["Authorization"] == "Bearer AGENT-TOKEN"
    assert h["X-API-KEY"] == "AGENT-TOKEN"
    p = c._params(user_id="prof1")
    assert p["api_key"] == "AGENT-TOKEN"
    assert p["api-key"] == "AGENT-TOKEN"


def test_worker_app_normalizes_heartbeat_response_key():
    """worker/app.py 가 server 가 보낸 key 도 정규화하는지 (현재 source 검증)."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "worker" / "app.py").read_text(
        encoding="utf-8"
    )
    # heartbeat 응답 처리 부근에 _normalize_api_key 호출 패턴 존재
    assert "_normalize_api_key" in src


# ───────── 2. Task Scheduler WorkingDirectory ─────────

def test_task_register_uses_powershell_with_working_directory(monkeypatch):
    """worker/task_register.py 가 PowerShell New-ScheduledTaskAction 사용 +
    -WorkingDirectory 인자 포함."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "worker" / "task_register.py").read_text(
        encoding="utf-8"
    )
    # schtasks /create 직접 호출 패턴이 사라지고 PS 로 변경됐는지
    assert "New-ScheduledTaskAction" in src
    assert "-WorkingDirectory" in src
    assert "Register-ScheduledTask" in src


def test_task_register_skips_when_disable_flag_set(monkeypatch):
    """HYDRA_DISABLE_TASK_REGISTER=1 이면 register 안 함 (Slice 1 의 기존 정책)."""
    monkeypatch.setenv("HYDRA_DISABLE_TASK_REGISTER", "1")
    monkeypatch.setattr(sys, "platform", "win32")
    with patch("worker.task_register.subprocess.run") as spy:
        from worker.task_register import ensure_registered
        ensure_registered()
    spy.assert_not_called()


def test_task_register_invokes_powershell_when_not_disabled(monkeypatch):
    """Windows 환경 + flag 없으면 PowerShell 호출 (실제 등록 안 되도록 mock)."""
    monkeypatch.delenv("HYDRA_DISABLE_TASK_REGISTER", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")

    call_args: list[list[str]] = []
    def fake_run(args, **kwargs):
        call_args.append(args)
        # 1st call: schtasks /query → returncode != 0 (등록 안 됨)
        # 2nd call: powershell.exe -Command Register-ScheduledTask
        class FakeResult:
            returncode = 1 if call_args[0][0] == "schtasks" and len(call_args) == 1 else 0
            stdout = b""
            stderr = b""
        # query 시도 후 register 시도
        if args[0] == "schtasks" and "/query" in args:
            return FakeResult()
        return FakeResult()

    with patch("worker.task_register.subprocess.run", side_effect=fake_run):
        from worker.task_register import ensure_registered
        ensure_registered()

    # 두 번째 call 이 powershell 이어야
    ps_calls = [a for a in call_args if a[0].endswith("powershell.exe") or a[0] == "powershell.exe"]
    assert len(ps_calls) >= 1
    ps_args = ps_calls[0]
    # WorkingDirectory + Register-ScheduledTask 가 같은 command string 안에
    command = " ".join(ps_args)
    assert "-WorkingDirectory" in command
    assert "Register-ScheduledTask" in command
    assert "HydraWorker" in command


def test_task_register_no_op_on_non_windows(monkeypatch):
    monkeypatch.delenv("HYDRA_DISABLE_TASK_REGISTER", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    with patch("worker.task_register.subprocess.run") as spy:
        from worker.task_register import ensure_registered
        ensure_registered()
    spy.assert_not_called()
