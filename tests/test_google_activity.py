"""Google activity 테스트 — search_pool 연동."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_maybe_google_search_uses_search_pool_with_age(monkeypatch):
    from worker import google_activity

    captured = {}

    def fake_pick(age):
        captured["age"] = age
        return "테스트 쿼리"

    monkeypatch.setattr(google_activity, "pick_query", fake_pick)
    monkeypatch.setattr(google_activity.random, "random", lambda: 0.0)  # always proceed
    monkeypatch.setattr(google_activity, "random_delay", AsyncMock())
    monkeypatch.setattr(google_activity, "type_human", AsyncMock())

    page = MagicMock()
    page.goto = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.locator = MagicMock()
    results = MagicMock()
    results.count = AsyncMock(return_value=0)
    page.locator.return_value = results

    ok = await google_activity.maybe_google_search(page, age=28, probability=1.0)
    assert ok is True
    assert captured["age"] == 28


@pytest.mark.asyncio
async def test_maybe_google_search_defaults_when_no_age(monkeypatch):
    from worker import google_activity

    captured = {}

    def fake_pick(age):
        captured["age"] = age
        return "x"

    monkeypatch.setattr(google_activity, "pick_query", fake_pick)
    monkeypatch.setattr(google_activity.random, "random", lambda: 0.0)
    monkeypatch.setattr(google_activity, "random_delay", AsyncMock())
    monkeypatch.setattr(google_activity, "type_human", AsyncMock())

    page = MagicMock()
    page.goto = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.locator = MagicMock()
    results = MagicMock()
    results.count = AsyncMock(return_value=0)
    page.locator.return_value = results

    await google_activity.maybe_google_search(page, probability=1.0)
    assert captured["age"] == 25  # fallback


@pytest.mark.asyncio
async def test_maybe_google_search_respects_probability(monkeypatch):
    from worker import google_activity

    monkeypatch.setattr(google_activity.random, "random", lambda: 0.99)  # > probability
    page = MagicMock()
    page.goto = AsyncMock()
    ok = await google_activity.maybe_google_search(page, age=25, probability=0.1)
    assert ok is False
    page.goto.assert_not_called()
