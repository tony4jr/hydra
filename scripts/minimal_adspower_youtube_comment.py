"""Minimal AdsPower -> YouTube comment reproducer.

Scope:
- Start or attach to one AdsPower profile.
- Navigate one browser tab to one YouTube video.
- Type one top-level comment.
- Optionally submit it with --submit.

Hard boundary: this script never closes the AdsPower browser profile. It does
not call browser.close(), AdsPower stop_browser(), or stop_all_browsers().
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_log_dir() -> Path:
    return _repo_root() / ".manual_runs" / "minimal_comment"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _select_all_modifier() -> str:
    from hydra.core.config import settings

    return "Meta" if settings.adspower_profile_os.lower() == "mac" else "Control"


def _video_url(args: argparse.Namespace) -> str:
    if args.url:
        return args.url
    if args.video_id:
        return f"https://www.youtube.com/watch?v={args.video_id}"
    raise RuntimeError("missing --video-id or --url")


def _read_comment_text(args: argparse.Namespace) -> str:
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    else:
        text = args.text or ""
    text = text.strip()
    if not text:
        raise RuntimeError("empty comment text")
    return text


class Recorder:
    def __init__(self, run_id: str, log_dir: Path):
        self.run_id = run_id
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.log_dir / f"{run_id}.jsonl"
        self.last_event: dict[str, Any] | None = None

    def event(self, step: str, ok: bool, **data: Any) -> dict[str, Any]:
        event = {
            "at": _now(),
            "run_id": self.run_id,
            "step": step,
            "ok": ok,
            "data": data,
        }
        self.last_event = event
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return event


async def _connect_page(ws_endpoint: str, *, new_tab: bool):
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(ws_endpoint)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    if new_tab or not context.pages:
        page = await context.new_page()
    else:
        page = context.pages[0]
    await page.bring_to_front()
    return pw, page


async def _page_snapshot(page) -> dict[str, Any]:
    return {
        "url": page.url,
        "title": await page.title(),
        "simplebox_count": await page.locator("ytd-comment-simplebox-renderer").count(),
        "thread_count": await page.locator("ytd-comment-thread-renderer").count(),
        "signin_button_count": await page.locator(
            "a[href*='ServiceLogin'], a[href*='signin'], ytd-button-renderer:has-text('Sign in')"
        ).count(),
    }


async def _navigate(page, url: str, timeout_ms: int) -> dict[str, Any]:
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    await page.wait_for_timeout(1800)
    return await _page_snapshot(page)


async def _scroll_to_comment_box(page, timeout_ms: int) -> dict[str, Any]:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last: dict[str, Any] = {}
    scrolls = 0

    while time.monotonic() < deadline:
        simplebox = page.locator("ytd-comment-simplebox-renderer")
        count = await simplebox.count()
        thread_count = await page.locator("ytd-comment-thread-renderer").count()
        last = {"simplebox_count": count, "thread_count": thread_count, "scrolls": scrolls}
        if count:
            await simplebox.first.scroll_into_view_if_needed()
            await page.wait_for_timeout(600)
            return last | {"found": True}

        await page.evaluate(
            "() => window.scrollBy({top: Math.max(700, window.innerHeight * 0.85), behavior: 'instant'})"
        )
        scrolls += 1
        await page.wait_for_timeout(900)

    return last | {"found": False}


async def _expand_comment_box(page, timeout_ms: int) -> dict[str, Any]:
    simplebox = page.locator("ytd-comment-simplebox-renderer").first
    await simplebox.wait_for(state="visible", timeout=timeout_ms)
    await simplebox.scroll_into_view_if_needed()
    await page.wait_for_timeout(500)

    placeholder = simplebox.locator("#simplebox-placeholder, #placeholder-area").first
    await placeholder.click(timeout=timeout_ms)

    input_box = simplebox.locator("#contenteditable-root").first
    await input_box.wait_for(state="visible", timeout=timeout_ms)
    await input_box.click(timeout=timeout_ms)

    submit = simplebox.locator("ytd-button-renderer#submit-button button, #submit-button button").first
    return {
        "input_visible": await input_box.is_visible(),
        "submit_count": await submit.count(),
    }


async def _set_comment_text(page, text: str, timeout_ms: int) -> dict[str, Any]:
    simplebox = page.locator("ytd-comment-simplebox-renderer").first
    input_box = simplebox.locator("#contenteditable-root").first
    await input_box.click(timeout=timeout_ms)
    await page.keyboard.press(f"{_select_all_modifier()}+A")
    await page.keyboard.press("Backspace")
    await page.wait_for_timeout(250)

    try:
        await input_box.fill(text, timeout=timeout_ms)
    except Exception:
        await page.keyboard.insert_text(text)

    await page.wait_for_timeout(700)
    current = await input_box.evaluate("(el) => el.innerText || el.textContent || ''")
    if _clean_text(text) != _clean_text(current):
        await input_box.click(timeout=timeout_ms)
        await page.keyboard.press(f"{_select_all_modifier()}+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(text)
        await page.wait_for_timeout(700)
        current = await input_box.evaluate("(el) => el.innerText || el.textContent || ''")

    return {
        "expected_chars": len(text),
        "draft_chars": len(current or ""),
        "draft_matches": _clean_text(text) == _clean_text(current),
    }


async def _submit_ready_button(page, timeout_ms: int):
    simplebox = page.locator("ytd-comment-simplebox-renderer").first
    candidates = [
        simplebox.locator("ytd-button-renderer#submit-button button").first,
        simplebox.locator("#submit-button button").first,
        simplebox.get_by_role("button", name=re.compile(r"댓글|Comment", re.I)).first,
    ]
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_error = "submit button not ready"

    while time.monotonic() < deadline:
        for button in candidates:
            try:
                if await button.count() == 0:
                    continue
                visible = await button.is_visible()
                enabled = await button.is_enabled()
                aria = await button.get_attribute("aria-disabled")
                disabled = await button.get_attribute("disabled")
                if visible and enabled and aria != "true" and disabled is None:
                    return button
                last_error = f"visible={visible} enabled={enabled} aria={aria} disabled={disabled}"
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
        await page.wait_for_timeout(400)

    raise RuntimeError(last_error)


async def _extract_comment_id(page, text: str, timeout_ms: int) -> dict[str, Any]:
    js = """(needle) => {
        const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
        const wanted = clean(needle);
        const readId = (node) => {
            const direct = node.getAttribute('data-cid')
                || node.getAttribute('data-comment-id')
                || node.getAttribute('comment-id');
            if (direct) return direct;
            const child = node.querySelector('[data-cid], [data-comment-id], [comment-id]');
            if (child) {
                return child.getAttribute('data-cid')
                    || child.getAttribute('data-comment-id')
                    || child.getAttribute('comment-id');
            }
            const link = node.querySelector('a[href*="lc="]')?.href || '';
            const m = link.match(/[?&]lc=([^&]+)/);
            return m ? decodeURIComponent(m[1]) : '';
        };
        const nodes = [...document.querySelectorAll(
            'ytd-comment-thread-renderer, ytd-comment-view-model, ytd-comment-renderer'
        )];
        for (const node of nodes) {
            const body = clean(node.querySelector('#content-text')?.innerText || node.innerText || '');
            if (wanted && body.includes(wanted)) {
                return {visible: true, comment_id: readId(node) || ''};
            }
        }
        return {visible: false, comment_id: ''};
    }"""
    deadline = time.monotonic() + (timeout_ms / 1000)
    result = {"visible": False, "comment_id": ""}
    while time.monotonic() < deadline:
        result = await page.evaluate(js, text)
        if result.get("visible"):
            return result
        await page.wait_for_timeout(600)
    return result


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    from hydra.browser.adspower import adspower

    run_id = args.run_id or f"min-comment-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    recorder = Recorder(run_id, Path(args.log_dir) if args.log_dir else _default_log_dir())
    text = _read_comment_text(args)
    url = _video_url(args)

    pw = None
    try:
        info = adspower.start_browser(args.profile_id)
        recorder.event(
            "adspower_start_or_attach",
            True,
            profile_id=args.profile_id,
            debug_port=info.get("debug_port"),
            process_ids=info.get("process_ids", []),
            has_ws=bool(info.get("ws_endpoint")),
        )
        ws_endpoint = info.get("ws_endpoint")
        if not ws_endpoint:
            raise RuntimeError("AdsPower did not return a ws_endpoint")

        pw, page = await _connect_page(ws_endpoint, new_tab=bool(args.new_tab))
        recorder.event("cdp_connect", True, page_url=page.url)

        nav = await _navigate(page, url, args.timeout_ms)
        recorder.event("navigate_video", True, **nav)

        comments = await _scroll_to_comment_box(page, args.timeout_ms)
        recorder.event("scroll_to_comment_box", bool(comments.get("found")), **comments)
        if not comments.get("found"):
            raise RuntimeError(f"comment box not found: {comments}")

        expanded = await _expand_comment_box(page, args.timeout_ms)
        recorder.event("expand_comment_box", bool(expanded.get("input_visible")), **expanded)
        if not expanded.get("input_visible"):
            raise RuntimeError(f"comment input not visible: {expanded}")

        draft = await _set_comment_text(page, text, args.timeout_ms)
        recorder.event("type_comment", bool(draft.get("draft_matches")), **draft)
        if not draft.get("draft_matches"):
            raise RuntimeError(f"draft text did not match: {draft}")

        if not args.submit:
            return recorder.event("done_draft_only", True, submitted=False, browser_left_open=True)

        button = await _submit_ready_button(page, args.timeout_ms)
        await button.click(timeout=args.timeout_ms)
        await page.wait_for_timeout(args.after_submit_wait_ms)

        posted = await _extract_comment_id(page, text, args.timeout_ms)
        ok = bool(posted.get("visible"))
        return recorder.event(
            "submit_comment",
            ok,
            submitted=True,
            browser_left_open=True,
            comment_id=posted.get("comment_id", ""),
            visible_in_dom=posted.get("visible", False),
        )
    except Exception as e:
        return recorder.event(
            "fatal",
            False,
            error=f"{type(e).__name__}: {e}",
            browser_left_open=True,
        )
    finally:
        # Do not close the CDP browser. Stopping Playwright only disconnects
        # this controller process from the already-running AdsPower browser.
        if pw is not None:
            await pw.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal AdsPower YouTube comment repro")
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--video-id")
    parser.add_argument("--url")
    parser.add_argument("--text")
    parser.add_argument("--text-file")
    parser.add_argument("--run-id")
    parser.add_argument("--log-dir")
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--after-submit-wait-ms", type=int, default=3500)
    parser.add_argument("--new-tab", action="store_true")
    parser.add_argument("--submit", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        event = asyncio.run(_run(args))
        print(json.dumps(event, ensure_ascii=False, sort_keys=True))
        return 0 if event.get("ok") else 1
    except Exception as e:
        event = {
            "at": _now(),
            "ok": False,
            "step": "fatal",
            "error": f"{type(e).__name__}: {e}",
        }
        print(json.dumps(event, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
