"""Phase 4 Slice 4.1b — admin agent terminal session host.

admin_agent runtime 안에서 persistent shell process 를 띄워 server 측
terminal_sessions 와 매핑. payload 받아 spawn + active POST. close 받아
terminate + closed POST. shutdown 시 registry 전체 cleanup.

핵심:
- idempotent open: 같은 session_id 가 이미 registry 에 있고 살아있으면
  no-op (재배달 시 shell 중복 spawn 금지)
- UTF-8: PowerShell startup 에서 chcp 65001 + Console::InputEncoding /
  OutputEncoding UTF8
- active POST 실패 → process kill + ack failed (caller 책임)
- shutdown_all(): admin_agent service stop / KeyboardInterrupt 시 호출.
  Codex 권고로 4.1b 부터 포함 (orphan PowerShell 위험 방지).
- Slice 4.1b 는 spawn + active POST + close + shutdown 만. input/output
  IO thread 는 4.2a/4.2b 에서.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from worker.client import ServerClient


# session_id → {"proc": Popen, "session_token": str, "shell": str}
# Codex Slice 4.1b 권고: token 도 함께 보관해서 close/shutdown 시 callback
# 가능. lock 은 dict 조작만 보호 (network call 은 lock 밖).
_REGISTRY: dict[int, dict] = {}
_REGISTRY_LOCK = threading.Lock()


# PowerShell startup script — UTF-8 강제 + prompt 짧게.
_PS_STARTUP_SCRIPT = (
    "chcp 65001 > $null; "
    "[Console]::InputEncoding=[Text.Encoding]::UTF8; "
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
    "$OutputEncoding=[Text.Encoding]::UTF8; "
    "function global:prompt { 'PS> ' }"
)


def _spawn_shell(shell: str) -> subprocess.Popen:
    """플랫폼 + shell 별로 persistent process Popen.

    PowerShell: -NoExit -NoLogo -NoProfile -Command "<startup>"
    bash: bash -i with LANG=en_US.UTF-8

    stdin/stdout/stderr = PIPE, text mode utf-8.
    """
    if shell == "powershell":
        if sys.platform == "win32":
            argv = [
                "powershell.exe",
                "-NoExit", "-NoLogo", "-NoProfile",
                "-Command", _PS_STARTUP_SCRIPT,
            ]
        else:
            # dev fallback — POSIX 에서 bash 로 흉내. 같은 startup 의미 없으나
            # tests/dev 환경에서 process 구조 검증용.
            argv = ["bash", "-i"]
    elif shell == "sh":
        argv = ["bash", "-i"]
    else:
        raise ValueError(f"unsupported shell: {shell!r}")

    env = os.environ.copy()
    env.setdefault("LANG", "en_US.UTF-8")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        env=env,
        text=False,  # binary; decode 는 IO thread 가 (4.2 에서)
        close_fds=(sys.platform != "win32"),
    )


def _is_alive(proc: subprocess.Popen) -> bool:
    return proc.poll() is None


def _post_active(client: "ServerClient", session_id: int, session_token: str) -> bool:
    """server 에 active 마킹. HTTP 200 + ok=True 만 성공."""
    try:
        resp = client._request(
            "POST",
            f"/api/workers/terminal/{session_id}/active",
            headers={**client.headers, "X-Terminal-Session-Token": session_token},
        )
        if resp.status_code != 200:
            return False
        try:
            return bool(resp.json().get("ok") is True)
        except Exception:
            return False
    except Exception:
        return False


def _post_closed(client: "ServerClient", session_id: int, session_token: str) -> bool:
    try:
        resp = client._request(
            "POST",
            f"/api/workers/terminal/{session_id}/closed",
            headers={**client.headers, "X-Terminal-Session-Token": session_token},
        )
        return resp.status_code == 200
    except Exception:
        return False


# Phase 4 Slice 4.2a — input poller
INPUT_POLL_INTERVAL_SEC = 1.0


def _get_inputs(
    client: "ServerClient", session_id: int, session_token: str, after_seq: int,
) -> tuple[list[dict], str]:
    """GET /inputs short-poll. (rows, status) 반환."""
    try:
        resp = client._request(
            "GET",
            f"/api/workers/terminal/{session_id}/inputs?after_seq={after_seq}",
            headers={**client.headers, "X-Terminal-Session-Token": session_token},
        )
        if resp.status_code != 200:
            return [], "unknown"
        body = resp.json()
        return body.get("inputs", []), body.get("status", "unknown")
    except Exception:
        return [], "unknown"


def _post_consumed(
    client: "ServerClient", session_id: int, session_token: str, consumed_seq: int,
) -> bool:
    try:
        resp = client._request(
            "POST",
            f"/api/workers/terminal/{session_id}/input-consumed?consumed_seq={consumed_seq}",
            headers={**client.headers, "X-Terminal-Session-Token": session_token},
        )
        return resp.status_code == 200
    except Exception:
        return False


def _input_poller_loop(
    client: "ServerClient",
    session_id: int,
    session_token: str,
    proc: subprocess.Popen,
    stop_event: threading.Event,
) -> None:
    """워커 측 short-poll thread. active 동안 inputs poll → stdin write.

    종료 조건:
      - stop_event set (close_session 시)
      - process 죽음 (proc.poll() != None)
      - server 가 status != active 반환 (closing/closed/failed)
    """
    after_seq = 0
    while not stop_event.is_set():
        if proc.poll() is not None:
            return
        rows, status = _get_inputs(client, session_id, session_token, after_seq)
        # Codex Slice 4.2a blocker fix: status != active 면 write 전에 즉시 return.
        # 서버가 closing 응답해도 queued input 실행되는 race 회피.
        if status in ("closing", "closed", "timeout", "failed"):
            return
        if rows and status == "active":
            try:
                for r in rows:
                    data = r["data"]
                    if isinstance(data, str):
                        proc.stdin.write(data.encode("utf-8"))
                    else:
                        proc.stdin.write(data)
                    after_seq = max(after_seq, int(r["seq"]))
                try:
                    proc.stdin.flush()
                except Exception:
                    pass
                _post_consumed(client, session_id, session_token, after_seq)
            except Exception:
                # stdin closed 등 — process 곧 종료될 가능성. 다음 iter 에서 detect.
                pass
        stop_event.wait(INPUT_POLL_INTERVAL_SEC)


# Phase 4 Slice 4.2b — output chunks
CHUNK_FLUSH_BYTES = 64 * 1024
CHUNK_FLUSH_INTERVAL_SEC = 0.1


def _post_chunks(
    client: "ServerClient",
    session_id: int,
    session_token: str,
    chunks: list[dict],
) -> bool:
    if not chunks:
        return True
    try:
        resp = client._request(
            "POST",
            f"/api/workers/terminal/{session_id}/chunks",
            headers={**client.headers, "X-Terminal-Session-Token": session_token},
            json={"chunks": chunks},
        )
        return resp.status_code == 200
    except Exception:
        return False


def _stream_reader_loop(
    client: "ServerClient",
    session_id: int,
    session_token: str,
    stream_name: str,
    stream_fileobj,
    stop_event: threading.Event,
) -> None:
    """워커 측 stdout 또는 stderr reader. 64KB 또는 100ms 단위로 batch POST.

    종료 조건:
      - stream 닫힘 (read 가 빈 bytes 반환)
      - stop_event set
    """
    buf = bytearray()
    last_flush = time.monotonic()
    while not stop_event.is_set():
        try:
            chunk = stream_fileobj.read1(CHUNK_FLUSH_BYTES) if hasattr(stream_fileobj, "read1") else stream_fileobj.read(CHUNK_FLUSH_BYTES)
        except Exception:
            return
        if not chunk:
            # EOF — 남은 buffer flush 후 종료
            if buf:
                _post_chunks(client, session_id, session_token, [{
                    "stream": stream_name,
                    "data": buf.decode("utf-8", errors="replace"),
                    "byte_size": len(buf),
                }])
            return
        buf.extend(chunk)
        now = time.monotonic()
        if len(buf) >= CHUNK_FLUSH_BYTES or (now - last_flush) >= CHUNK_FLUSH_INTERVAL_SEC:
            data = bytes(buf)
            buf.clear()
            last_flush = now
            ok = _post_chunks(client, session_id, session_token, [{
                "stream": stream_name,
                "data": data.decode("utf-8", errors="replace"),
                "byte_size": len(data),
            }])
            if not ok:
                # 400 (size limit) 등 — server 가 closing 트리거. 다음 iter 에서
                # poller 가 status closing 받고 정리.
                pass


def _post_failed(
    client: "ServerClient", session_id: int, session_token: str, error: str = "",
) -> bool:
    try:
        path = f"/api/workers/terminal/{session_id}/failed"
        if error:
            path += f"?error={error}"
        resp = client._request(
            "POST", path,
            headers={**client.headers, "X-Terminal-Session-Token": session_token},
        )
        return resp.status_code == 200
    except Exception:
        return False


def open_session(
    client: "ServerClient",
    session_id: int,
    session_token: str,
    shell: str,
) -> dict:
    """admin agent terminal session 열기. idempotent.

    1. registry 에 session_id 있고 살아있음 → no-op, active POST 재시도
    2. registry 에 있지만 죽음 → 정리 후 새로 spawn
    3. spawn 성공 → active POST → 실패 시 kill + failed POST

    Codex Slice 4.1b 권고: network call 은 lock 밖에서 수행 (다른 thread
    의 registry 조회 지연 회피).
    """
    # 1) lock 안: 기존 session 검사. spawn / network 는 밖에서.
    with _REGISTRY_LOCK:
        existing = _REGISTRY.get(session_id)
        existing_proc = existing.get("proc") if existing else None
        existing_alive = existing_proc is not None and _is_alive(existing_proc)
        if existing and not existing_alive:
            # dead — 정리
            _REGISTRY.pop(session_id, None)

    if existing_alive:
        # idempotent — active POST 재시도 (lease redelivery 케이스).
        ok = _post_active(client, session_id, session_token)
        return {"ok": ok, "noop": True, "pid": existing_proc.pid}

    # 2) spawn — lock 밖
    try:
        proc = _spawn_shell(shell)
    except Exception as e:
        _post_failed(client, session_id, session_token, f"spawn_error:{type(e).__name__}")
        return {"ok": False, "error": f"spawn_error: {e}"}

    # spawn 직후 process 가 즉시 죽었는지 점검 (잘못된 shell 등)
    try:
        rc = proc.wait(timeout=0.1)
    except subprocess.TimeoutExpired:
        rc = None
    if rc is not None:
        _post_failed(
            client, session_id, session_token,
            f"spawn_exited:rc={rc}",
        )
        return {"ok": False, "error": f"spawn exited rc={rc}"}

    # 3) active POST — lock 밖
    if not _post_active(client, session_id, session_token):
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        _post_failed(client, session_id, session_token, "active_post_failed")
        return {"ok": False, "error": "active_post_failed"}

    # 4) input poller thread 시작 (Phase 4 Slice 4.2a)
    stop_event = threading.Event()
    poller = threading.Thread(
        target=_input_poller_loop,
        args=(client, session_id, session_token, proc, stop_event),
        name=f"term-input-poller-{session_id}",
        daemon=True,
    )
    poller.start()

    # 5) output reader threads (Phase 4 Slice 4.2b)
    stdout_thread = threading.Thread(
        target=_stream_reader_loop,
        args=(client, session_id, session_token, "stdout", proc.stdout, stop_event),
        name=f"term-stdout-reader-{session_id}",
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_stream_reader_loop,
        args=(client, session_id, session_token, "stderr", proc.stderr, stop_event),
        name=f"term-stderr-reader-{session_id}",
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    # 6) lock 안: registry 등록
    with _REGISTRY_LOCK:
        _REGISTRY[session_id] = {
            "proc": proc, "session_token": session_token, "shell": shell,
            "input_stop": stop_event, "input_thread": poller,
            "stdout_thread": stdout_thread, "stderr_thread": stderr_thread,
        }
    return {"ok": True, "pid": proc.pid}


def close_session(
    client: "ServerClient",
    session_id: int,
    session_token: str,
) -> dict:
    """admin agent terminal session 종료. terminate (5s) → kill fallback.
    server 에 closed POST.

    network call 은 lock 밖.
    """
    with _REGISTRY_LOCK:
        entry = _REGISTRY.pop(session_id, None)
    proc = entry.get("proc") if entry else None
    stop_event = entry.get("input_stop") if entry else None
    if stop_event is not None:
        stop_event.set()

    if proc is not None and _is_alive(proc):
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    _post_closed(client, session_id, session_token)
    return {"ok": True}


def shutdown_all(client: Optional["ServerClient"] = None) -> int:
    """admin_agent service stop / SIGTERM / KeyboardInterrupt 시 호출.
    registry 모든 process 정리 + (client 있으면) server 에 closed POST.

    Codex Slice 4.1b 요구: orphan PowerShell 방지 (4.3 까지 미루지 말 것).
    """
    with _REGISTRY_LOCK:
        items = list(_REGISTRY.items())
        _REGISTRY.clear()
    count = 0
    for sid, entry in items:
        proc = entry.get("proc")
        token = entry.get("session_token", "")
        stop_event = entry.get("input_stop")
        if stop_event is not None:
            try:
                stop_event.set()
            except Exception:
                pass
        try:
            if proc is not None and _is_alive(proc):
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            # client 가 있으면 closed POST (lock 밖)
            if client is not None and token:
                try:
                    _post_closed(client, sid, token)
                except Exception:
                    pass
            count += 1
        except Exception:
            pass
    return count


def get_registered_sessions() -> list[int]:
    """현재 살아있는 session_id 리스트 — 4.3 stale recovery hook 용."""
    with _REGISTRY_LOCK:
        return [sid for sid, e in _REGISTRY.items() if _is_alive(e.get("proc"))]


def clear_registry_for_testing() -> None:
    """테스트 전용 — registry 초기화 + 모든 daemon thread 의 stop_event set.

    Slice 4.2a/4.2b 가 daemon poller/reader thread 를 spawn 하면서 test
    teardown 시 dict 만 비우면 thread 들이 mock client 영원히 호출 → 다음
    테스트 hang. 모든 stop_event set 으로 graceful 종료.
    """
    with _REGISTRY_LOCK:
        for entry in _REGISTRY.values():
            stop_event = entry.get("input_stop")
            if stop_event is not None:
                try:
                    stop_event.set()
                except Exception:
                    pass
            proc = entry.get("proc")
            if proc is not None:
                # mock 들은 terminate 가 무해. real Popen 도 cleanup 도움.
                try:
                    proc.terminate()
                except Exception:
                    pass
        _REGISTRY.clear()
