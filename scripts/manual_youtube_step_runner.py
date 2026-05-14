"""Manual YouTube operation step runner.

This is intentionally lower-level than WorkerApp. Each invocation performs one
small browser step, writes state to disk, and appends a JSONL event. It is meant
for operator-led debugging from admin_agent shell_exec.

Safety boundary:
- This script never kills the AdsPower desktop app.
- `stop_profile` only asks AdsPower Local API to close the selected browser
  profile. It does not call process cleanup.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_dir() -> Path:
    base = os.environ.get("HYDRA_MANUAL_RUN_DIR")
    return Path(base) if base else _repo_root() / ".manual_runs"


def _state_path(run_id: str) -> Path:
    return _run_dir() / f"{run_id}.json"


def _events_path(run_id: str) -> Path:
    return _run_dir() / f"{run_id}.jsonl"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_state(run_id: str) -> dict[str, Any]:
    path = _state_path(run_id)
    if not path.exists():
        return {"run_id": run_id, "created_at": _now(), "events": 0}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(state: dict[str, Any]) -> None:
    _run_dir().mkdir(parents=True, exist_ok=True)
    _state_path(state["run_id"]).write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _append_event(run_id: str, event: dict[str, Any]) -> None:
    _run_dir().mkdir(parents=True, exist_ok=True)
    with _events_path(run_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _record(
    state: dict[str, Any],
    *,
    step: str,
    ok: bool,
    data: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    event = {
        "at": _now(),
        "run_id": state["run_id"],
        "step": step,
        "ok": ok,
        "data": data or {},
        "error": error,
    }
    state["events"] = int(state.get("events") or 0) + 1
    state["updated_at"] = event["at"]
    state["last_step"] = step
    state["last_ok"] = ok
    state["last_error"] = error
    if data:
        state.setdefault("step_data", {})[step] = data
    _save_state(state)
    _append_event(state["run_id"], event)
    return event


def _print(event: dict[str, Any]) -> None:
    print(json.dumps(event, ensure_ascii=False, sort_keys=True))


def _require(value: Any, name: str) -> Any:
    if value in (None, ""):
        raise RuntimeError(f"missing {name}; pass it or run the prior step")
    return value


def _read_text(args: argparse.Namespace, state: dict[str, Any]) -> str:
    if getattr(args, "text_file", None):
        return Path(args.text_file).read_text(encoding="utf-8").strip()
    if getattr(args, "text", None):
        return str(args.text).strip()
    text = state.get("draft_text") or state.get("text")
    return str(text or "").strip()


def process_snapshot(run_id: str) -> dict[str, Any]:
    try:
        import psutil  # type: ignore

        rows: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = str(proc.info.get("name") or "")
                cmdline = proc.info.get("cmdline") or []
                cmd = " ".join(str(x) for x in cmdline)
                if "adspower" not in f"{name} {cmd}".lower():
                    continue
                cpu = proc.cpu_times()
                rows.append({
                    "pid": proc.pid,
                    "name": name,
                    "cpu_sec": round(float(cpu.user + cpu.system), 3),
                    "has_remote_debugging": "--remote-debugging-port" in cmd,
                    "cmdline": cmd[:500],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return {"count": len(rows), "processes": rows, "source": "psutil"}
    except ModuleNotFoundError:
        return _process_snapshot_fallback()


def _process_snapshot_fallback() -> dict[str, Any]:
    if os.name == "nt":
        script = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -like '*AdsPower*' -or $_.CommandLine -like '*adspower*' } | "
            "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
        )
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        raw = (proc.stdout or "").strip()
        if not raw:
            return {"count": 0, "processes": [], "source": "powershell"}
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = [parsed]
        rows = []
        for item in parsed or []:
            cmd = str(item.get("CommandLine") or "")
            rows.append({
                "pid": item.get("ProcessId"),
                "name": item.get("Name"),
                "has_remote_debugging": "--remote-debugging-port" in cmd,
                "cmdline": cmd[:500],
            })
        return {"count": len(rows), "processes": rows, "source": "powershell"}

    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,comm=,args="],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as e:
        return {
            "count": None,
            "processes": [],
            "source": "unavailable",
            "warning": f"{type(e).__name__}: {e}",
        }
    rows = []
    for line in (proc.stdout or "").splitlines():
        if "adspower" not in line.lower():
            continue
        parts = line.strip().split(None, 2)
        rows.append({
            "pid": int(parts[0]) if parts and parts[0].isdigit() else None,
            "name": parts[1] if len(parts) > 1 else "",
            "has_remote_debugging": "--remote-debugging-port" in line,
            "cmdline": line[:500],
        })
    return {"count": len(rows), "processes": rows, "source": "ps"}


def cmd_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.run_id)
    data = process_snapshot(args.run_id)
    state["last_process_snapshot"] = data
    return _record(state, step="snapshot", ok=True, data=data)


def cmd_start_profile(args: argparse.Namespace) -> dict[str, Any]:
    from hydra.browser.adspower import adspower

    state = _load_state(args.run_id)
    profile_id = args.profile_id or state.get("profile_id")
    _require(profile_id, "profile_id")
    info = adspower.start_browser(str(profile_id))
    data = {
        "profile_id": profile_id,
        "ws_endpoint": info.get("ws_endpoint"),
        "debug_port": info.get("debug_port"),
        "process_ids": info.get("process_ids", []),
    }
    state.update(data)
    return _record(state, step="start_profile", ok=True, data=data)


async def _connect_page(state: dict[str, Any]):
    from playwright.async_api import async_playwright

    ws_endpoint = _require(state.get("ws_endpoint"), "ws_endpoint")
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(str(ws_endpoint))
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = context.pages[0] if context.pages else await context.new_page()
    return pw, browser, context, page


async def _with_page(state: dict[str, Any], fn):
    pw = browser = None
    try:
        pw, browser, _context, page = await _connect_page(state)
        return await fn(page)
    finally:
        # Do not call browser.close(); for CDP sessions that can close the
        # browser profile. Stopping Playwright disconnects this controller.
        if pw is not None:
            await pw.stop()


async def _cmd_page_info(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.run_id)

    async def fn(page):
        title = await page.title()
        return {"url": page.url, "title": title}

    data = await _with_page(state, fn)
    state["page"] = data
    return _record(state, step="page_info", ok=True, data=data)


async def _cmd_goto_video(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.run_id)
    video_id = args.video_id or state.get("video_id")
    _require(video_id, "video_id")
    url = f"https://www.youtube.com/watch?v={video_id}"

    async def fn(page):
        await page.goto(url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        await page.wait_for_timeout(1500)
        return {"video_id": video_id, "url": page.url, "title": await page.title()}

    data = await _with_page(state, fn)
    state["video_id"] = video_id
    state["page"] = data
    return _record(state, step="goto_video", ok=True, data=data)


async def _cmd_watch(args: argparse.Namespace) -> dict[str, Any]:
    from hydra.browser.actions import watch_video

    state = _load_state(args.run_id)

    async def fn(page):
        start = time.monotonic()
        await watch_video(page, int(args.seconds))
        return {"seconds": int(args.seconds), "elapsed_sec": round(time.monotonic() - start, 3)}

    data = await _with_page(state, fn)
    return _record(state, step="watch", ok=True, data=data)


async def _cmd_scroll_comments(args: argparse.Namespace) -> dict[str, Any]:
    from hydra.browser.actions import scroll_to_comments

    state = _load_state(args.run_id)

    async def fn(page):
        found = await scroll_to_comments(page)
        count = await page.locator("ytd-comment-thread-renderer").count()
        return {"found": bool(found), "comment_count": count}

    data = await _with_page(state, fn)
    return _record(state, step="scroll_comments", ok=True, data=data)


async def _cmd_read_comments(args: argparse.Namespace) -> dict[str, Any]:
    from worker.comment_behavior import read_comments_before_posting

    state = _load_state(args.run_id)

    async def fn(page):
        before = await page.locator("ytd-comment-thread-renderer").count()
        await read_comments_before_posting(page)
        return {"comment_count": before}

    data = await _with_page(state, fn)
    return _record(state, step="read_comments", ok=True, data=data)


async def _cmd_probe_comment_box(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.run_id)

    async def fn(page):
        simplebox = page.locator("ytd-comment-simplebox-renderer")
        placeholder = simplebox.first.locator("#simplebox-placeholder, #placeholder-area")
        input_box = simplebox.first.locator("#contenteditable-root")
        submit = simplebox.first.locator(
            "ytd-button-renderer#submit-button button, "
            "#submit-button button:not([aria-disabled='true'])"
        )
        return {
            "simplebox_count": await simplebox.count(),
            "placeholder_count": await placeholder.count(),
            "input_count": await input_box.count(),
            "submit_count": await submit.count(),
        }

    data = await _with_page(state, fn)
    return _record(state, step="probe_comment_box", ok=True, data=data)


async def _cmd_expand_comment_box(args: argparse.Namespace) -> dict[str, Any]:
    from hydra.browser.actions import random_delay

    state = _load_state(args.run_id)

    async def fn(page):
        simplebox = page.locator("ytd-comment-simplebox-renderer").first
        await simplebox.scroll_into_view_if_needed()
        await random_delay(0.5, 1.0)
        placeholder = simplebox.locator("#simplebox-placeholder, #placeholder-area").first
        await placeholder.click()
        await random_delay(0.8, 1.5)
        input_box = simplebox.locator("#contenteditable-root")
        submit = simplebox.locator(
            "ytd-button-renderer#submit-button button, "
            "#submit-button button:not([aria-disabled='true'])"
        )
        return {
            "input_count": await input_box.count(),
            "submit_count": await submit.count(),
            "active": await input_box.first.is_visible() if await input_box.count() else False,
        }

    data = await _with_page(state, fn)
    return _record(state, step="expand_comment_box", ok=True, data=data)


async def _cmd_draft_comment(args: argparse.Namespace) -> dict[str, Any]:
    from hydra.browser.actions import _paste_modifier, random_delay

    state = _load_state(args.run_id)
    text = _read_text(args, state)
    _require(text, "text")

    async def fn(page):
        simplebox = page.locator("ytd-comment-simplebox-renderer").first
        await simplebox.scroll_into_view_if_needed()
        await random_delay(0.5, 1.0)
        await simplebox.locator("#simplebox-placeholder, #placeholder-area").first.click()
        await random_delay(0.5, 1.0)
        await simplebox.locator("#contenteditable-root").first.click()
        await page.evaluate("text => navigator.clipboard.writeText(text)", text)
        await page.keyboard.press(f"{_paste_modifier()}+v")
        await random_delay(0.5, 1.0)
        current = await simplebox.locator("#contenteditable-root").first.inner_text()
        return {"chars": len(text), "draft_visible_chars": len(current or "")}

    data = await _with_page(state, fn)
    state["draft_text"] = text
    return _record(state, step="draft_comment", ok=True, data=data)


async def _cmd_submit_comment(args: argparse.Namespace) -> dict[str, Any]:
    from hydra.browser.actions import _extract_new_comment_id, random_delay

    state = _load_state(args.run_id)
    text = _read_text(args, state)
    _require(text, "text")

    async def fn(page):
        simplebox = page.locator("ytd-comment-simplebox-renderer").first
        submit = simplebox.locator(
            "ytd-button-renderer#submit-button button, "
            "#submit-button button:not([aria-disabled='true'])"
        )
        if await submit.count() == 0:
            import re
            submit = simplebox.get_by_role("button", name=re.compile(r"댓글|Comment", re.I))
        await submit.first.click()
        await random_delay(2.0, 4.0)
        comment_id = await _extract_new_comment_id(page, text=text)
        return {"comment_id": comment_id or "", "chars": len(text)}

    data = await _with_page(state, fn)
    state["last_comment_id"] = data.get("comment_id", "")
    return _record(state, step="submit_comment", ok=True, data=data)


async def _cmd_post_comment(args: argparse.Namespace) -> dict[str, Any]:
    from hydra.browser.actions import post_comment

    state = _load_state(args.run_id)
    text = _read_text(args, state)
    _require(text, "text")

    async def fn(page):
        comment_id = await post_comment(page, text)
        return {"comment_id": comment_id or "", "posted": comment_id is not None, "chars": len(text)}

    data = await _with_page(state, fn)
    state["last_comment_id"] = data.get("comment_id", "")
    return _record(state, step="post_comment", ok=bool(data.get("posted")), data=data)


def cmd_stop_profile(args: argparse.Namespace) -> dict[str, Any]:
    from hydra.browser.adspower import adspower

    state = _load_state(args.run_id)
    profile_id = args.profile_id or state.get("profile_id")
    _require(profile_id, "profile_id")
    adspower.stop_browser(str(profile_id), cookie_sync_grace_sec=float(args.cookie_sync_grace_sec))
    data = {"profile_id": profile_id, "stopped": True}
    return _record(state, step="stop_profile", ok=True, data=data)


def cmd_state(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.run_id)
    return {"ok": True, "state_path": str(_state_path(args.run_id)), "state": state}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run one manual YouTube/AdsPower step")
    p.add_argument("--run-id", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("snapshot")

    s = sub.add_parser("start_profile")
    s.add_argument("--profile-id")

    g = sub.add_parser("goto_video")
    g.add_argument("--video-id")
    g.add_argument("--timeout-ms", type=int, default=30000)

    sub.add_parser("page_info")

    w = sub.add_parser("watch")
    w.add_argument("--seconds", type=int, default=8)

    sub.add_parser("scroll_comments")
    sub.add_parser("read_comments")
    sub.add_parser("probe_comment_box")
    sub.add_parser("expand_comment_box")

    d = sub.add_parser("draft_comment")
    d.add_argument("--text")
    d.add_argument("--text-file")

    sc = sub.add_parser("submit_comment")
    sc.add_argument("--text")
    sc.add_argument("--text-file")

    pc = sub.add_parser("post_comment")
    pc.add_argument("--text")
    pc.add_argument("--text-file")

    st = sub.add_parser("stop_profile")
    st.add_argument("--profile-id")
    st.add_argument("--cookie-sync-grace-sec", type=float, default=4.0)

    sub.add_parser("state")
    return p


async def _amain(args: argparse.Namespace) -> dict[str, Any]:
    if args.cmd == "page_info":
        return await _cmd_page_info(args)
    if args.cmd == "goto_video":
        return await _cmd_goto_video(args)
    if args.cmd == "watch":
        return await _cmd_watch(args)
    if args.cmd == "scroll_comments":
        return await _cmd_scroll_comments(args)
    if args.cmd == "read_comments":
        return await _cmd_read_comments(args)
    if args.cmd == "probe_comment_box":
        return await _cmd_probe_comment_box(args)
    if args.cmd == "expand_comment_box":
        return await _cmd_expand_comment_box(args)
    if args.cmd == "draft_comment":
        return await _cmd_draft_comment(args)
    if args.cmd == "submit_comment":
        return await _cmd_submit_comment(args)
    if args.cmd == "post_comment":
        return await _cmd_post_comment(args)
    raise RuntimeError(f"unknown async cmd: {args.cmd}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "snapshot":
            event = cmd_snapshot(args)
        elif args.cmd == "start_profile":
            event = cmd_start_profile(args)
        elif args.cmd == "stop_profile":
            event = cmd_stop_profile(args)
        elif args.cmd == "state":
            event = cmd_state(args)
        else:
            event = asyncio.run(_amain(args))
        _print(event)
        return 0 if event.get("ok", True) else 1
    except Exception as e:
        state = _load_state(args.run_id)
        event = _record(state, step=args.cmd, ok=False, error=f"{type(e).__name__}: {e}")
        _print(event)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
