"""Best-effort AdsPower browser process cleanup.

AdsPower's Local API can report browser stop success while a spawned browser
process remains alive. These helpers keep the API call as the primary path and
only use PID/cmdline cleanup as a final guardrail.
"""
from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from typing import Any

from hydra.core.logger import get_logger

log = get_logger("adspower_cleanup")

_PID_KEYS = (
    "pid",
    "browser_pid",
    "process_id",
    "processId",
    "browser_process_id",
    "browserProcessId",
)


def extract_process_ids(data: Mapping[str, Any] | None) -> list[int]:
    """Extract process ids from AdsPower's browser/start response if present."""
    if not data:
        return []
    found: set[int] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if key in _PID_KEYS:
                    _add_pid(nested, found)
                elif key in ("pids", "process_ids", "processIds"):
                    _add_pid(nested, found)
                elif isinstance(nested, (Mapping, list, tuple)):
                    visit(nested)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(data)
    return sorted(found)


def _add_pid(value: Any, out: set[int]) -> None:
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _add_pid(item, out)
        return
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return
    if pid > 0 and pid != os.getpid():
        out.add(pid)


def _debug_port_in_cmdline(cmd: str, debug_port: int | str | None) -> bool:
    if not debug_port:
        return False
    port = str(debug_port)
    return (
        f"--remote-debugging-port={port}" in cmd
        or f"--remote-debugging-port {port}" in cmd
    )


def _browserish(name: str, cmd: str) -> bool:
    hay = f"{name} {cmd}".lower()
    return (
        "adspower" in hay
        or "chrome" in name.lower()
        or "chromium" in name.lower()
        or "msedge" in name.lower()
    )


def _adspowerish(name: str, cmd: str) -> bool:
    return "adspower" in f"{name} {cmd}".lower()


def _has_browser_session_marker(
    *,
    name: str,
    cmd: str,
    profile_id: str | None,
    debug_port: int | str | None,
    include_stale_remote_debugging: bool,
) -> bool:
    """Return True only for AdsPower-launched browser/session processes.

    The AdsPower desktop app itself is also named "AdsPower Global" on Windows.
    Never kill it by name alone; require a profile/debug-port/CDP marker.
    """
    needle = (profile_id or "").lower()
    if debug_port and _debug_port_in_cmdline(cmd, debug_port):
        return True
    if needle and needle in cmd:
        return True
    if include_stale_remote_debugging and "--remote-debugging-port" in cmd:
        return _browserish(name, cmd) or _adspowerish(name, cmd)
    return False


def _cmdline_text(cmdline: Any) -> str:
    if isinstance(cmdline, str):
        return cmdline
    if isinstance(cmdline, Iterable):
        return " ".join(str(part) for part in cmdline)
    return ""


def _candidate_pids(
    *,
    profile_id: str | None,
    debug_port: int | str | None,
    include_stale_remote_debugging: bool,
) -> set[int]:
    import psutil  # type: ignore

    matched: set[int] = set()
    needle = (profile_id or "").lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            info = proc.info
            pid = int(info.get("pid") or 0)
            if pid <= 0 or pid == os.getpid():
                continue
            name = str(info.get("name") or "")
            cmd = _cmdline_text(info.get("cmdline")).lower()
            if not _browserish(name, cmd):
                continue
            if _has_browser_session_marker(
                name=name,
                cmd=cmd,
                profile_id=needle,
                debug_port=debug_port,
                include_stale_remote_debugging=include_stale_remote_debugging,
            ):
                matched.add(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return matched


def _kill_tree(pid: int, *, timeout_sec: float) -> tuple[list[int], list[int], list[str]]:
    import psutil  # type: ignore

    terminated: list[int] = []
    killed: list[int] = []
    errors: list[str] = []
    try:
        parent = psutil.Process(pid)
        procs = parent.children(recursive=True) + [parent]
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
        return terminated, killed, [f"{pid}: {type(e).__name__}"]

    for proc in procs:
        try:
            proc.terminate()
            terminated.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            errors.append(f"{getattr(proc, 'pid', '?')}: terminate {type(e).__name__}")

    _, alive = psutil.wait_procs(procs, timeout=timeout_sec)
    for proc in alive:
        try:
            proc.kill()
            killed.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            errors.append(f"{getattr(proc, 'pid', '?')}: kill {type(e).__name__}")
    if killed:
        psutil.wait_procs(alive, timeout=timeout_sec)
    return terminated, killed, errors


def cleanup_adspower_processes(
    *,
    profile_id: str | None = None,
    known_pids: Iterable[int] | None = None,
    debug_port: int | str | None = None,
    include_stale_remote_debugging: bool = False,
    timeout_sec: float = 3.0,
    reason: str = "session_close",
) -> dict[str, Any]:
    """Terminate leftover AdsPower browser process trees.

    Matching is intentionally narrow for normal session cleanup: known PIDs,
    CDP debug port, or command lines that include the AdsPower profile id.
    Boot cleanup can opt into remote-debugging process cleanup.
    """
    try:
        import psutil  # noqa: F401  # type: ignore
    except Exception as e:
        return {
            "ok": False,
            "reason": reason,
            "matched_pids": [],
            "terminated_pids": [],
            "killed_pids": [],
            "errors": [f"psutil unavailable: {type(e).__name__}"],
        }

    matched: set[int] = set()
    for pid in known_pids or []:
        try:
            n = int(pid)
        except (TypeError, ValueError):
            continue
        if n <= 0 or n == os.getpid():
            continue
        try:
            import psutil  # type: ignore
            proc = psutil.Process(n)
            name = str(proc.name() or "")
            cmd = _cmdline_text(proc.cmdline()).lower()
            if _has_browser_session_marker(
                name=name,
                cmd=cmd,
                profile_id=profile_id,
                debug_port=debug_port,
                include_stale_remote_debugging=True,
            ):
                matched.add(n)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    matched.update(
        _candidate_pids(
            profile_id=profile_id,
            debug_port=debug_port,
            include_stale_remote_debugging=include_stale_remote_debugging,
        )
    )

    terminated: list[int] = []
    killed: list[int] = []
    errors: list[str] = []
    for pid in sorted(matched):
        t, k, e = _kill_tree(pid, timeout_sec=timeout_sec)
        terminated.extend(t)
        killed.extend(k)
        errors.extend(e)

    result = {
        "ok": not errors,
        "reason": reason,
        "matched_pids": sorted(matched),
        "terminated_pids": sorted(set(terminated)),
        "killed_pids": sorted(set(killed)),
        "errors": errors,
    }
    if matched:
        log.warning(f"AdsPower process cleanup: {result}")
    return result


def cleanup_stale_adspower_browsers(*, reason: str = "worker_boot") -> dict[str, Any]:
    """Clean stale AdsPower browser/CDP processes during worker startup."""
    return cleanup_adspower_processes(
        include_stale_remote_debugging=True,
        reason=reason,
    )
