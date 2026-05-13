"""Slice 3.3 — detached helper that sleeps then runs nssm restart.

Invoked by `python -m worker.agent_self_restart_helper <delay> <service> <nssm> <log>`.

parent (admin agent) 는 ack 후 이 helper 를 detached 로 spawn. parent 가
service stop 으로 죽어도 helper 는 살아남아 sleep 후 nssm restart 실행.

log 파일에 시각 + rc + stdout/stderr 남김 — Popen 실패/nssm 실패 시
운영자가 확인 가능.
"""
from __future__ import annotations

import datetime
import subprocess
import sys
import time
from pathlib import Path


def _log(lf, msg: str) -> None:
    ts = datetime.datetime.now(datetime.UTC).isoformat()
    lf.write(f"[{ts}] {msg}\n")
    lf.flush()


def main() -> int:
    if len(sys.argv) < 5:
        sys.stderr.write(
            "usage: python -m worker.agent_self_restart_helper "
            "<delay_sec> <service_name> <nssm_path> <log_path>\n"
        )
        return 2

    delay_sec = int(sys.argv[1])
    service_name = sys.argv[2]
    nssm_path = sys.argv[3]
    log_path = sys.argv[4]

    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as lf:
        _log(lf, f"helper started delay={delay_sec}s service={service_name} nssm={nssm_path}")
        if delay_sec > 0:
            time.sleep(delay_sec)
        _log(lf, f"invoking: {nssm_path} restart {service_name}")
        try:
            rc = subprocess.run(
                [nssm_path, "restart", service_name],
                capture_output=True, text=True, timeout=60,
            )
            _log(lf, f"rc={rc.returncode} stdout={rc.stdout!r} stderr={rc.stderr!r}")
            return rc.returncode
        except subprocess.TimeoutExpired:
            _log(lf, "TimeoutExpired waiting for nssm restart")
            return 124
        except FileNotFoundError as e:
            _log(lf, f"FileNotFoundError: {e}")
            return 127
        except Exception as e:
            _log(lf, f"unexpected error: {type(e).__name__}: {e}")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
