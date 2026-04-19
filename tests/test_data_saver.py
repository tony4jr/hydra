import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_enable_data_saver_returns_true_on_click(monkeypatch):
    from worker import data_saver

    page = MagicMock()
    page.goto = AsyncMock()
    page.evaluate = AsyncMock(return_value="clicked")
    monkeypatch.setattr(data_saver, "random_delay", AsyncMock())

    ok = await data_saver.enable_data_saver(page)
    assert ok is True


@pytest.mark.asyncio
async def test_enable_data_saver_returns_true_when_already(monkeypatch):
    from worker import data_saver

    page = MagicMock()
    page.goto = AsyncMock()
    page.evaluate = AsyncMock(return_value="already")
    monkeypatch.setattr(data_saver, "random_delay", AsyncMock())

    ok = await data_saver.enable_data_saver(page)
    assert ok is True


@pytest.mark.asyncio
async def test_enable_data_saver_returns_false_when_not_found(monkeypatch):
    from worker import data_saver

    page = MagicMock()
    page.goto = AsyncMock()
    page.evaluate = AsyncMock(return_value="not_found")
    monkeypatch.setattr(data_saver, "random_delay", AsyncMock())

    ok = await data_saver.enable_data_saver(page)
    assert ok is False
