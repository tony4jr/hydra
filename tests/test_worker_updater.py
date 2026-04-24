"""Task 34 — worker.updater 자가 업데이트 로직."""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from worker.updater import (
    _SAFE_LOCAL_VERSIONS,
    maybe_update,
    perform_update,
    should_update,
)


# ── should_update ──

def test_should_update_true_when_versions_differ():
    assert should_update("v1.2.4", "v1.2.3") is True


def test_should_update_false_when_versions_match():
    assert should_update("abc1234", "abc1234") is False


def test_should_update_false_when_safe_local_version():
    # unknown/dev/0.1.0/빈값 은 자동 업데이트 금지 (CI/초기 환경)
    for local in _SAFE_LOCAL_VERSIONS:
        assert should_update("v1.2.4", local) is False


def test_should_update_false_when_server_empty():
    assert should_update("", "abc123") is False


# ── perform_update ──

def _mock_git_rev_diff(args, **_):
    """HEAD 와 origin/main 이 다른 상황 — 실 업데이트 경로 테스트용."""
    if "HEAD" in args:
        return b"prevhash1234567\n"
    if "origin/main" in args:
        return b"newhash7654321\n"
    return b"prevhash1234567\n"


def _mock_git_rev_same(args, **_):
    """HEAD == origin/main — no-op 리턴 경로 테스트용."""
    return b"samehash0000000\n"


def test_perform_update_runs_git_and_pip_then_exit_zero(tmp_path):
    with patch("worker.updater.subprocess.check_call") as mock_call, \
         patch("worker.updater.subprocess.check_output", side_effect=_mock_git_rev_diff):
        with pytest.raises(SystemExit) as exc:
            perform_update(repo_dir=str(tmp_path))
        assert exc.value.code == 0

    calls_args = [c.args[0] for c in mock_call.call_args_list]
    # git fetch + git reset --hard origin/main + pip install -e .
    assert any("fetch" in " ".join(a) for a in calls_args)
    assert any("reset" in " ".join(a) and "origin/main" in " ".join(a) for a in calls_args)
    assert any("pip" in " ".join(a) and "install" in " ".join(a) for a in calls_args)


def test_perform_update_noop_when_already_on_origin_main(tmp_path):
    """HEAD == origin/main 이면 exit 없이 리턴 (재시작 루프 방지)."""
    with patch("worker.updater.subprocess.check_call") as mock_call, \
         patch("worker.updater.subprocess.check_output", side_effect=_mock_git_rev_same):
        # SystemExit 가 발생하면 안 됨
        result = perform_update(repo_dir=str(tmp_path))
        assert result is None

    calls_args = [c.args[0] for c in mock_call.call_args_list]
    # fetch 는 호출됐지만, reset/pip 는 호출 안 됨
    assert any("fetch" in " ".join(a) for a in calls_args)
    assert not any("reset" in " ".join(a) for a in calls_args)
    assert not any("pip" in " ".join(a) for a in calls_args)


def test_perform_update_rolls_back_on_pip_failure(tmp_path):
    def fake_check_call(args, **_):
        if any("pip" in x for x in args):
            raise subprocess.CalledProcessError(1, args)
        return 0

    with patch("worker.updater.subprocess.check_call", side_effect=fake_check_call), \
         patch("worker.updater.subprocess.check_output", side_effect=_mock_git_rev_diff), \
         patch("worker.updater.subprocess.call") as mock_rollback:
        with pytest.raises(SystemExit) as exc:
            perform_update(repo_dir=str(tmp_path))
        assert exc.value.code == 1

    # rollback = git reset --hard <prev>
    rollback_calls = [c.args[0] for c in mock_rollback.call_args_list]
    assert any("reset" in " ".join(a) for a in rollback_calls)


def test_perform_update_exit_on_unexpected_error(tmp_path):
    with patch("worker.updater.subprocess.check_call", side_effect=RuntimeError("boom")):
        with pytest.raises(SystemExit) as exc:
            perform_update(repo_dir=str(tmp_path))
        assert exc.value.code == 1


# ── maybe_update ──

def test_maybe_update_skipped_when_not_idle(tmp_path):
    with patch("worker.updater.perform_update") as mock_pu:
        result = maybe_update(
            server_version="v2", local_version="v1",
            repo_dir=str(tmp_path), is_idle=False,
        )
    assert result is False
    mock_pu.assert_not_called()


def test_maybe_update_triggers_when_idle_and_differ(tmp_path):
    with patch("worker.updater.perform_update") as mock_pu:
        maybe_update(
            server_version="v2", local_version="v1",
            repo_dir=str(tmp_path), is_idle=True,
        )
    mock_pu.assert_called_once()


def test_maybe_update_skipped_when_same_version(tmp_path):
    with patch("worker.updater.perform_update") as mock_pu:
        result = maybe_update(
            server_version="v1", local_version="v1",
            repo_dir=str(tmp_path), is_idle=True,
        )
    assert result is False
    mock_pu.assert_not_called()
