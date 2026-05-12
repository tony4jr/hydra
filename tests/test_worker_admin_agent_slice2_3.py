"""Slice 2.3 — Windows Service Installer (NSSM) static verification.

PowerShell 실행 의존하지 않고 script text/regex 정적 검증. mac/linux CI 에서도
통과해야 함. pwsh 가 있으면 `-DryRun -Action status` syntax check 추가 (없으면
skip).

Coverage (Codex 명시 6개 + 금지 검증):
  a. script 존재 + Action param values (install/start/stop/restart/status/uninstall)
  b. NSSM install/set/start/remove path 있음
  c. python.exe -m worker.admin_agent 호출
  d. AppEnvironmentExtra 에 HYDRA_AGENT_WORKER_TOKEN, HYDRA_DISABLE_TASK_REGISTER=1,
     HYDRA_UPDATE_OWNER=agent 포함
  e. token 원문 출력 방지 — Write-Host $AgentWorkerToken 같은 패턴 금지
  f. 금지 명령 (Task Scheduler / desktop worker) 부재
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PS1 = REPO_ROOT / "setup" / "install-admin-agent-service.ps1"
BAT = REPO_ROOT / "setup" / "install-admin-agent-service.bat"


@pytest.fixture(scope="module")
def ps1_text() -> str:
    assert PS1.exists(), f"installer script missing: {PS1}"
    return PS1.read_text(encoding="utf-8")


# ───────── a. script + Action params ─────────

def test_installer_script_exists():
    assert PS1.exists()
    assert PS1.stat().st_size > 1000  # 너무 짧으면 stub


def test_installer_has_action_param_with_all_values(ps1_text):
    # ValidateSet 또는 switch 안에서 모든 action 등장해야
    required_actions = {"install", "start", "stop", "restart", "status", "uninstall"}
    for action in required_actions:
        # Do-<Action> 또는 'action' 문자열 둘 다 OK — 정적으로 어휘 검출
        assert action in ps1_text.lower(), f"action missing in script: {action}"
    # ValidateSet 명시 확인
    assert re.search(
        r"ValidateSet\(\s*'install'\s*,\s*'start'\s*,\s*'stop'\s*,\s*'restart'\s*,\s*'status'\s*,\s*'uninstall'\s*\)",
        ps1_text,
    ), "ValidateSet for Action with all values not found"


def test_installer_has_param_block_with_expected_options(ps1_text):
    """주요 param 모두 존재 확인."""
    for name in (
        "Action", "ServerUrl", "InstallPath", "ServiceName",
        "AgentWorkerToken", "EnrollmentToken", "NssmPath",
        "Start", "Force", "DryRun",
    ):
        assert re.search(rf"\$\b{name}\b", ps1_text), f"param ${name} not found"


# ───────── b. NSSM command path ─────────

def test_installer_uses_nssm_install_set_start_remove(ps1_text):
    """NSSM 의 각 sub-command 가 script 안에 등장."""
    # install
    assert re.search(r"'install',\s*\$ServiceName,\s*\$python", ps1_text), \
        "nssm install <name> <python> 명령 호출 미발견"
    # set (여러 곳)
    assert ps1_text.count("'set', $ServiceName,") >= 5, "nssm set 호출 부족"
    # start / stop / restart
    assert "'start', $ServiceName" in ps1_text
    assert "'stop', $ServiceName" in ps1_text
    assert "'restart', $ServiceName" in ps1_text
    # remove (uninstall 안)
    assert "'remove', $ServiceName" in ps1_text


# ───────── c. python.exe -m worker.admin_agent ─────────

def test_installer_runs_admin_agent_module(ps1_text):
    """service executable = python.exe + args = -m worker.admin_agent."""
    assert ".venv\\Scripts\\python.exe" in ps1_text
    assert "'-m', 'worker.admin_agent'" in ps1_text or \
           "-m worker.admin_agent" in ps1_text


# ───────── d. AppEnvironmentExtra 4종 env ─────────

def test_installer_sets_required_env_vars(ps1_text):
    """AppEnvironmentExtra block 에 4종 env entry 가 포함."""
    assert "HYDRA_SERVER_URL=" in ps1_text
    assert "HYDRA_AGENT_WORKER_TOKEN=" in ps1_text
    assert "HYDRA_DISABLE_TASK_REGISTER=1" in ps1_text
    assert "HYDRA_UPDATE_OWNER=agent" in ps1_text
    # AppEnvironmentExtra 명시 호출
    assert "AppEnvironmentExtra" in ps1_text


# ───────── e. token 원문 출력 방지 ─────────

def test_installer_does_not_print_token_to_host(ps1_text):
    """Write-Host / Write-Output / echo 로 $AgentWorkerToken 또는 $token 원문 직접 출력 금지.

    허용 패턴: $token.Length, $AgentWorkerToken.Length, "len=$(...)" 형태.
    """
    # 직접 출력 안티패턴 — 어떤 형태로든 token 원문이 redirect 되거나 표시되면 fail.
    forbidden = [
        r"Write-Host\s+\$AgentWorkerToken\b(?!\.)",
        r"Write-Host\s+\$EnrollmentToken\b(?!\.)",
        r"Write-Host\s+\$token\b(?!\.)",
        r"Write-Output\s+\$AgentWorkerToken\b(?!\.)",
        r"Write-Output\s+\$token\b(?!\.)",
        r"\bWrite-Information\s+\$AgentWorkerToken\b(?!\.)",
        # 단순 echo (대소문자 무관 PowerShell)
        r"^\s*echo\s+\$AgentWorkerToken\b(?!\.)",
        r"^\s*echo\s+\$token\b(?!\.)",
    ]
    for pat in forbidden:
        m = re.search(pat, ps1_text, flags=re.IGNORECASE | re.MULTILINE)
        assert m is None, f"forbidden token output pattern matched: {pat!r}\nfound: {m.group(0) if m else None}"


def test_installer_uses_token_length_only_for_diagnostics(ps1_text):
    """진단 출력은 length/존재만 — 'len=' 또는 '.Length' 사용 확인."""
    # 최소 1군데는 length 보고 패턴
    assert re.search(r"\.Length", ps1_text), "token 길이 출력 패턴 없음"


# ───────── f. 2.4/2.5 금지 명령 부재 ─────────

def test_installer_does_not_touch_task_scheduler(ps1_text):
    """기존 HydraWorker Task Scheduler 건드림 = 2.5 cutover. 여기선 금지."""
    forbidden = [
        r"Unregister-ScheduledTask",
        r"Disable-ScheduledTask",
        r"Start-ScheduledTask\s+-TaskName\s+HydraWorker",
        r"Stop-ScheduledTask\s+-TaskName\s+HydraWorker",
        r"schtasks\s+/delete\s+/tn\s+HydraWorker",
        r"schtasks\s+/disable",
    ]
    for pat in forbidden:
        assert not re.search(pat, ps1_text, flags=re.IGNORECASE), \
            f"forbidden Task Scheduler operation: {pat!r}"


def test_installer_does_not_spawn_desktop_worker(ps1_text):
    """desktop worker process 직접 spawn/kill = 2.4. 여기선 금지."""
    forbidden = [
        r"Start-Process\s+.*python.*-m\s+worker\s*(?!\.admin_agent)",
        r"Stop-Process\s+",
        r"taskkill\s+",
        # desktop worker module 직접 호출 패턴
        r"-m\s+worker\.app",
        r"-m\s+worker\s*$",
    ]
    for pat in forbidden:
        assert not re.search(pat, ps1_text, flags=re.IGNORECASE | re.MULTILINE), \
            f"forbidden desktop worker operation: {pat!r}"


def test_installer_does_not_perform_update_ownership_transfer(ps1_text):
    """update ownership 실제 동작 (git pull / pip install via agent) = 2.5. 여기선 금지."""
    forbidden = [
        r"git\s+pull",
        r"git\s+reset\s+--hard",
        r"pip\s+install",
        # perform_update / maybe_update 직접 호출
        r"perform_update",
        r"maybe_update",
    ]
    for pat in forbidden:
        # script body 안에서만 — 주석/문서 매치 줄이려고 lowercase 비교
        assert not re.search(pat, ps1_text, flags=re.IGNORECASE), \
            f"forbidden update ownership operation: {pat!r}"


# ───────── bat wrapper ─────────

def test_bat_wrapper_exists_and_invokes_ps1():
    assert BAT.exists()
    text = BAT.read_text(encoding="utf-8")
    assert "install-admin-agent-service.ps1" in text
    # UAC 승격 패턴
    assert "RunAs" in text
    # 인자 그대로 전달
    assert "%*" in text


# ───────── pwsh syntax check (optional) ─────────

def test_pwsh_dryrun_status_syntax_when_available():
    """pwsh 가 설치돼 있으면 -DryRun -Action status 한 줄로 syntax check.

    pwsh 없으면 skip — mac/linux CI 에서 정상.
    """
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh unavailable, static tests only")

    # -NoProfile + -Command 로 import 만 시도. status action 은 NSSM 없으면
    # 'Resolve-Nssm' 단계에서 throw — 정상. 우리는 syntax 만 검증.
    # parser-only check: -Command "&{ . <file> }" 는 실행하므로 PSScriptAnalyzer 흉내로
    # tokenize 만 시도.
    proc = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-Command",
         f"$null = [System.Management.Automation.PSParser]::Tokenize("
         f"(Get-Content -Raw '{PS1}'), [ref]$null)"],
        capture_output=True, timeout=20,
    )
    assert proc.returncode == 0, \
        f"pwsh tokenize failed (syntax error?):\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
