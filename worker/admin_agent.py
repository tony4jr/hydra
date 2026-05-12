"""Admin Agent Process Skeleton — Slice 2.2.

PC 관리/PowerShell 전담. AdsPower/Playwright/YouTube task 는 절대 안 함.
heartbeat 만 보내고 응답의 pending_commands 를 순차 처리. 기존
worker.commands.execute_command 를 재사용해서 shell_exec / run_diag / restart
등 현 채널 그대로 탐.

spec: docs/WORKER_ADMIN_AGENT_TASK_0_0.md Phase 2 → Slice 2.2.

scope:
  - local 에서 `python -m worker.admin_agent` 실행 가능
  - heartbeat (role=admin_agent, capabilities 보고)
  - command pickup + execute_command + ack (기존 worker.commands 재사용)
  - SIGINT/SIGTERM graceful shutdown
  - --once one-shot mode (test/수동 검증용)
  - HYDRA_DISABLE_TASK_REGISTER=1 자동 세팅 (Phase 2 의 desktop worker 분리)

out of scope (2.3-2.5):
  - Windows Service / NSSM installer
  - Desktop Worker spawn/stop/restart
  - Task Scheduler disable/cutover
  - update ownership 이전 (HYDRA_UPDATE_OWNER 세팅 가능하지만 동작 변경 X)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from datetime import UTC, datetime

# Admin agent process 가 import 되기 전에 desktop worker 의 task_register 가
# 우연히 schtasks 등록하지 않도록 미리 차단. agent 는 service 가 owned.
os.environ.setdefault("HYDRA_DISABLE_TASK_REGISTER", "1")


AGENT_CAPABILITIES_DEFAULT = [
    "shell_exec",
    "powershell",
    "process_control",
    "scheduler",
    "git",
    "update_owner",
]

DEFAULT_POLL_INTERVAL_SEC = 15
MIN_POLL_INTERVAL_SEC = 1


def _resolve_agent_token() -> str:
    """admin_agent 전용 token 우선순위.

    HYDRA_AGENT_WORKER_TOKEN > HYDRA_ADMIN_AGENT_TOKEN > HYDRA_WORKER_TOKEN.
    """
    for name in ("HYDRA_AGENT_WORKER_TOKEN", "HYDRA_ADMIN_AGENT_TOKEN", "HYDRA_WORKER_TOKEN"):
        v = os.environ.get(name)
        if v:
            return v
    return ""


def _apply_agent_token_to_runtime_config(token: str) -> None:
    """admin agent token 을 runtime config 와 process env 에 **강제** 반영.

    Codex 2.2 review blocker: 기존 main 은 `os.environ[...] = token` + `config.load()`
    로만 처리. 하지만:
      - WorkerConfig.__init__ 가 secrets.load_secrets() 의 WORKER_TOKEN 을 env 보다
        먼저 읽음
      - config.load() 는 config.json 만 읽고 env 다시 안 봄
      - 기존 desktop token 이 secrets/config 에 있으면 agent token 으로 덮어쓰지
        않아서 ServerClient 가 desktop token 으로 heartbeat → role/capabilities 가
        desktop row 에 찍힘 → Phase 2.3-2.5 routing 치명적 충돌

    수정: agent token 을 무조건 config.worker_token 에 박고, env 도 동기화.
    같은 process 의 worker.config / worker.client 모듈이 import 한 `config`
    singleton 을 직접 수정 — 새 ServerClient 인스턴스가 그 값을 헤더에 사용.
    """
    if not token:
        return
    os.environ["HYDRA_WORKER_TOKEN"] = token
    # worker.config 의 module-level `config` singleton 을 직접 overwrite.
    # worker.client 도 같은 인스턴스를 import 해서 사용.
    from worker.config import config as _runtime_config
    _runtime_config.worker_token = token


def _resolve_poll_interval_sec(hb_response: dict | None) -> int:
    """poll interval 결정 — heartbeat 응답 우선, 다음 env, 다음 default.

    heartbeat 응답의 worker_config.poll_interval_sec 이 있으면 사용.
    없으면 env HYDRA_AGENT_POLL_INTERVAL_SEC. 둘 다 없으면 15s.
    """
    if hb_response:
        wc = hb_response.get("worker_config") or {}
        v = wc.get("poll_interval_sec")
        if isinstance(v, int) and v >= MIN_POLL_INTERVAL_SEC:
            return v
    env = os.environ.get("HYDRA_AGENT_POLL_INTERVAL_SEC")
    if env:
        try:
            iv = int(env)
            if iv >= MIN_POLL_INTERVAL_SEC:
                return iv
        except ValueError:
            pass
    return DEFAULT_POLL_INTERVAL_SEC


class AdminAgentApp:
    """Admin Agent 메인 루프.

    desktop worker (WorkerApp) 와 책임 분리:
      - WorkerApp: task fetch + execute (브라우저 자동화)
      - AdminAgentApp: heartbeat + pending_commands 만 (PC 관리)

    하나의 process 안에서 둘 다 띄우지 않는다. service unit (2.3) 또는
    별도 cmd 로 각각 실행.
    """

    def __init__(
        self,
        *,
        capabilities: list[str] | None = None,
        client=None,
    ):
        from worker.client import ServerClient

        self.capabilities = list(capabilities or AGENT_CAPABILITIES_DEFAULT)
        # client 주입 가능 (test 용). 기본은 ServerClient 인스턴스 — config 의
        # worker_token / server_url 사용. admin_agent token 은 process env 로
        # 주입되어 worker.config 가 읽음.
        self.client = client if client is not None else ServerClient()
        self.last_heartbeat_at: datetime | None = None
        self._stop = asyncio.Event()

    # ───────────────── lifecycle ─────────────────

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self, *, once: bool = False) -> int:
        """메인 루프. once=True 면 1 cycle 후 즉시 종료 (수동 검증용).

        --once 의 exit code 정책 (Codex 2.2 follow-up):
          - heartbeat 성공 (hb_response truthy) → rc=0
          - heartbeat 실패 (예외/None) → rc=1 (수동 검증에서 false-positive 방지)
        일반 long-running mode 에선 heartbeat 실패해도 다음 cycle 재시도 (Slice 1
        의 client retry 정책으로 흡수).
        """
        cycles = 0
        while not self._stop.is_set():
            cycles += 1
            hb_response = await self._tick()
            if once:
                return 0 if hb_response else 1
            # poll interval. heartbeat 응답에서 받거나 env 기본.
            interval = _resolve_poll_interval_sec(hb_response)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
        return 0

    async def _tick(self) -> dict | None:
        """1 cycle = heartbeat + pending command 처리.

        heartbeat 실패해도 다음 tick 진행 (worker.client 의 retry 가 흡수).
        예외 발생해도 ack 미스로 그치고 loop 안 죽음.
        """
        hb: dict | None = None
        try:
            hb = self.client.heartbeat(
                role="admin_agent",
                capabilities=self.capabilities,
            ) or {}
            self.last_heartbeat_at = datetime.now(UTC)
        except Exception as e:
            print(f"[admin_agent] heartbeat failed: {type(e).__name__}: {e}", flush=True)
            return None

        # paused / restart_requested 는 admin_agent 에는 의미가 약하지만 (task fetch
        # 안 하므로). 단 restart_requested 는 향후 2.5 에서 agent 자체 재시동에
        # 쓰일 가능성 — 지금은 무시.
        pending = hb.get("pending_commands") or []
        if pending:
            from worker.commands import execute_command
            for cmd in pending:
                try:
                    await execute_command(self.client, cmd)
                except SystemExit:
                    # restart / update_now 같은 self-exit. agent 도 그대로 따름.
                    # service (2.3) 가 재시작. 지금은 process 종료.
                    self._stop.set()
                    raise
                except Exception as e:
                    print(
                        f"[admin_agent] command id={cmd.get('id')} failed: "
                        f"{type(e).__name__}: {e}",
                        flush=True,
                    )
        return hb


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, app: AdminAgentApp) -> None:
    """SIGINT/SIGTERM 받으면 graceful stop. Windows 는 SIGINT 만."""
    def _stop_sig(signame: str) -> None:
        print(f"[admin_agent] received {signame}, stopping...", flush=True)
        app.request_stop()

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _stop_sig, sig_name)
        except NotImplementedError:
            # Windows asyncio 는 add_signal_handler 불가. signal.signal 사용.
            signal.signal(sig, lambda *_a, _n=sig_name: _stop_sig(_n))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="worker.admin_agent",
        description="Hydra Admin Agent — PC 관리/PowerShell 전담 프로세스 (Slice 2.2)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="One-shot mode — 1 heartbeat + command drain 후 즉시 종료 (수동 검증/테스트).",
    )
    parser.add_argument(
        "--capabilities",
        nargs="*",
        default=None,
        help=f"capability list 보고 (default: {AGENT_CAPABILITIES_DEFAULT}).",
    )
    args = parser.parse_args(argv)

    # token 확인 (invalid config 에서 무한 loop 진입 방지).
    token = _resolve_agent_token()
    if not token:
        print(
            "[admin_agent] Error: token not configured.\n"
            "  Set one of: HYDRA_AGENT_WORKER_TOKEN, HYDRA_ADMIN_AGENT_TOKEN, HYDRA_WORKER_TOKEN.",
            file=sys.stderr,
        )
        return 2

    # agent token 강제 반영. WorkerConfig.__init__ 의 secrets/env 우선순위와
    # 무관하게 runtime config singleton 에 직접 박음. 기존 desktop secrets token
    # 이 있어도 agent token 으로 overwrite.
    _apply_agent_token_to_runtime_config(token)

    print(
        f"[admin_agent] Starting (poll_interval={_resolve_poll_interval_sec(None)}s, "
        f"once={args.once}, capabilities={args.capabilities or AGENT_CAPABILITIES_DEFAULT})",
        flush=True,
    )

    app = AdminAgentApp(capabilities=args.capabilities)

    if sys.platform == "win32":
        # Windows: WindowsProactorEventLoopPolicy 가 기본이지만 명시.
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        _install_signal_handlers(loop, app)
        return loop.run_until_complete(app.run(once=args.once))
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
