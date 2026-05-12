"""Worker self-rescue — parent python (워커) kill + 새 워커 spawn.

배경: 워커 메모리에 cp949-die print 가 박혀있는 옛 코드. restart command 가
sys.exit 도달 못 함 (UnicodeEncodeError). 디스크엔 fix 가 있는데 메모리만
갱신 안 됨. SSH/원격 process kill 채널 없음.

우회 메커니즘: worker/commands.py 의 run_diag (legacy script mode) 가
_spawn_diag(script) 로 detached subprocess 띄움. 그 subprocess 가 본 스크립트.
parent (워커 python) PID 받아서 taskkill + 새 python -m worker spawn.

사용:
  admin 이 WorkerCommand 발행:
    command="run_diag"
    payload={"mode":"legacy", "script":"rescue_kill_worker.py"}
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def _log(msg: str) -> None:
    # stdout 도 utf-8 일 가능성 있지만 ASCII 만 써서 cp949 안전.
    try:
        print(f"[rescue] {msg}", flush=True)
    except Exception:
        pass


def _spawn_new_worker(repo_dir: Path) -> None:
    """새 워커 detached 로 띄움. Task Scheduler 거치지 않고 직접 python -m worker."""
    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        venv_py = repo_dir / ".venv" / "Scripts" / "python.exe"
        py = str(venv_py) if venv_py.exists() else sys.executable
        try:
            subprocess.Popen(
                [py, "-m", "worker"],
                cwd=str(repo_dir),
                creationflags=flags,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _log(f"new worker spawned via {py}")
        except Exception as e:
            _log(f"direct spawn failed: {e}, falling back to Task Scheduler")
            try:
                subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-Command",
                     "Start-ScheduledTask -TaskName HydraWorker"],
                    creationflags=flags,
                    close_fds=True,
                )
                _log("scheduled task triggered")
            except Exception as e2:
                _log(f"task scheduler also failed: {e2}")


def _kill_parent(parent_pid: int) -> None:
    if sys.platform == "win32":
        try:
            subprocess.call(
                ["taskkill", "/F", "/PID", str(parent_pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _log(f"taskkill /F /PID {parent_pid} issued")
        except Exception as e:
            _log(f"taskkill failed: {e}")
    else:
        try:
            os.kill(parent_pid, 15)
        except Exception as e:
            _log(f"SIGTERM failed: {e}")


def main() -> int:
    repo_dir = Path(__file__).resolve().parent.parent
    parent_pid = os.getppid()
    _log(f"parent pid = {parent_pid}, repo = {repo_dir}")

    # 1. 새 워커 먼저 spawn — 죽기 전에 시동.
    _spawn_new_worker(repo_dir)

    # 2. 새 워커가 socket / port 안 충돌하게 잠시 대기.
    time.sleep(3)

    # 3. parent kill.
    _kill_parent(parent_pid)
    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
