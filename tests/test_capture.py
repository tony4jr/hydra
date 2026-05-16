"""Phase 1.1 — capture_unknown_screen + FailureTaxonomy 검증."""
from unittest.mock import AsyncMock, MagicMock
import pytest

from hydra.protocol.failure_taxonomy import FailureTaxonomy
from worker.capture import capture_unknown_screen


def _make_page(url="https://accounts.google.com/x", title="login",
               html="<html></html>", screenshot=b"PNG"):
    page = MagicMock()
    page.url = url
    page.screenshot = AsyncMock(return_value=screenshot)
    page.content = AsyncMock(return_value=html)
    page.title = AsyncMock(return_value=title)
    return page


def test_taxonomy_has_7_categories():
    """spec: 7 종 — selector_missing, page_variant, auth_challenge,
    rate_limit, browser_crash, unknown_outcome, policy_block."""
    expected = {
        "selector_missing", "page_variant", "auth_challenge", "rate_limit",
        "browser_crash", "unknown_outcome", "policy_block",
    }
    actual = {t.value for t in FailureTaxonomy}
    assert actual == expected


def test_taxonomy_string_enum():
    assert FailureTaxonomy.SELECTOR_MISSING == "selector_missing"
    assert str(FailureTaxonomy.PAGE_VARIANT) == "page_variant"


@pytest.mark.asyncio
async def test_capture_uploads_with_screenshot():
    page = _make_page()
    client = MagicMock()
    await capture_unknown_screen(
        page,
        screen_state="POST_PASSWORD_UNKNOWN",
        taxonomy=FailureTaxonomy.PAGE_VARIANT,
        reason="no email input no known url",
        client=client,
        task_id=42,
        account_id=7,
        failed_selector="input[type=email]",
    )
    # report_error_with_screenshot 호출됨
    assert client.report_error_with_screenshot.call_count == 1
    kwargs = client.report_error_with_screenshot.call_args.kwargs
    assert kwargs["kind"] == "unknown_screen"
    assert "POST_PASSWORD_UNKNOWN" in kwargs["message"]
    assert kwargs["screenshot_bytes"] == b"PNG"
    ctx = kwargs["context"]
    assert ctx["screen_state"] == "POST_PASSWORD_UNKNOWN"
    assert ctx["failure_taxonomy"] == "page_variant"
    assert ctx["task_id"] == 42
    assert ctx["account_id"] == 7
    assert ctx["failed_selector"] == "input[type=email]"
    assert ctx["captured_url"] == "https://accounts.google.com/x"


@pytest.mark.asyncio
async def test_capture_falls_back_when_screenshot_empty():
    page = _make_page(screenshot=b"")
    client = MagicMock()
    await capture_unknown_screen(
        page,
        screen_state="TEST",
        taxonomy=FailureTaxonomy.SELECTOR_MISSING,
        client=client,
    )
    # screenshot empty → report_error_with_screenshot 안 부르고 report_error 만
    assert client.report_error_with_screenshot.call_count == 0
    assert client.report_error.call_count == 1


@pytest.mark.asyncio
async def test_capture_screenshot_failure_does_not_raise():
    """screenshot 실패해도 caller 에 예외 propagate X."""
    page = MagicMock()
    page.url = "x"
    page.screenshot = AsyncMock(side_effect=RuntimeError("page closed"))
    page.content = AsyncMock(return_value="")
    page.title = AsyncMock(return_value="")

    client = MagicMock()
    # 예외 propagate 안 됨
    await capture_unknown_screen(
        page,
        screen_state="CRASHED",
        taxonomy=FailureTaxonomy.BROWSER_CRASH,
        client=client,
    )


@pytest.mark.asyncio
async def test_capture_no_client_logs_only():
    """client=None 이면 업로드 안 하고 로컬 로그만."""
    page = _make_page()
    # 예외 없이 통과
    await capture_unknown_screen(
        page,
        screen_state="TEST",
        taxonomy=FailureTaxonomy.UNKNOWN_OUTCOME,
        client=None,
    )


@pytest.mark.asyncio
async def test_capture_html_truncation():
    """매우 큰 HTML 도 50KB 로 잘라서 저장."""
    big_html = "<div>" + "a" * 100_000 + "</div>"
    page = _make_page(html=big_html)
    client = MagicMock()
    await capture_unknown_screen(
        page,
        screen_state="BIG",
        taxonomy=FailureTaxonomy.PAGE_VARIANT,
        client=client,
    )
    ctx = client.report_error_with_screenshot.call_args.kwargs["context"]
    # context snippet 은 더 짧게 (2000)
    assert len(ctx["captured_html_snippet"]) <= 2000


@pytest.mark.asyncio
async def test_capture_upload_failure_silent():
    """업로드 자체 실패해도 caller 에 예외 propagate X."""
    page = _make_page()
    client = MagicMock()
    client.report_error_with_screenshot = MagicMock(side_effect=RuntimeError("network"))

    await capture_unknown_screen(
        page,
        screen_state="X",
        taxonomy=FailureTaxonomy.RATE_LIMIT,
        client=client,
    )  # no exception
