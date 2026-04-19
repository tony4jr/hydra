"""온보딩 세션 단위 테스트."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_onboard_uses_search_pool_for_search():
    """검색이 일어나면 search_pool.pick 이 persona age 로 호출된다."""
    from worker.onboard_session import run_onboard_session

    page = MagicMock()
    page.goto = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)  # not logged in check might fail — use mock
    page.locator = MagicMock()
    page.locator.return_value.wait_for = AsyncMock()
    page.locator.return_value.click = AsyncMock()
    page.locator.return_value.fill = AsyncMock()
    page.locator.return_value.count = AsyncMock(return_value=5)
    page.locator.return_value.nth = MagicMock(return_value=MagicMock(
        click=AsyncMock()
    ))
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.go_back = AsyncMock()

    with patch("worker.onboard_session.check_logged_in", AsyncMock(return_value=True)), \
         patch("worker.onboard_session.ensure_korean_language", AsyncMock(return_value=True)), \
         patch("worker.onboard_session.pick_query", return_value="테스트 쿼리 입니다") as mock_pick, \
         patch("worker.onboard_session.random_delay", AsyncMock()), \
         patch("worker.onboard_session.scroll_page", AsyncMock()), \
         patch("worker.onboard_session.watch_video", AsyncMock()), \
         patch("worker.onboard_session.handle_ad", AsyncMock()), \
         patch("worker.onboard_session.click_like_button", AsyncMock()), \
         patch("hydra.browser.actions.type_human", AsyncMock()):
        result = await run_onboard_session(
            page,
            persona={"age": 25},
            duration_min_sec=30, duration_max_sec=30,
            search_probability=1.0,
        )

    assert "language_ko" in result.actions
    assert mock_pick.call_count >= 1
    assert mock_pick.call_args[0][0] == 25


@pytest.mark.asyncio
async def test_onboard_skips_login_when_already_logged_in():
    from worker.onboard_session import run_onboard_session

    page = MagicMock()
    page.goto = AsyncMock()
    page.locator = MagicMock()
    page.locator.return_value.wait_for = AsyncMock()
    page.locator.return_value.click = AsyncMock()
    page.locator.return_value.fill = AsyncMock()
    page.locator.return_value.count = AsyncMock(return_value=0)
    page.locator.return_value.nth = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.go_back = AsyncMock()

    auto_login_mock = AsyncMock(return_value=True)
    with patch("worker.onboard_session.check_logged_in", AsyncMock(return_value=True)), \
         patch("worker.onboard_session.auto_login", auto_login_mock), \
         patch("worker.onboard_session.ensure_korean_language", AsyncMock(return_value=True)), \
         patch("worker.onboard_session.random_delay", AsyncMock()), \
         patch("worker.onboard_session.scroll_page", AsyncMock()), \
         patch("worker.onboard_session.pick_query", return_value="ㅋ"):
        result = await run_onboard_session(
            page, persona={"age": 25},
            duration_min_sec=0, duration_max_sec=1,
            search_probability=0.0,
        )
    auto_login_mock.assert_not_called()
    assert "already_logged_in" in result.actions
    assert "language_ko" in result.actions


@pytest.mark.asyncio
async def test_onboard_refuses_when_no_creds_and_logged_out():
    from worker.onboard_session import run_onboard_session

    page = MagicMock()
    page.goto = AsyncMock()
    with patch("worker.onboard_session.check_logged_in", AsyncMock(return_value=False)), \
         patch("worker.onboard_session.random_delay", AsyncMock()):
        result = await run_onboard_session(
            page, persona={"age": 25},
            duration_min_sec=0, duration_max_sec=1,
        )
    assert not result.ok
    assert "no credentials" in (result.error or "")
