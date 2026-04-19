"""구독 한국어 필터 + 비한국 채널 구독 취소 테스트."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_contains_korean():
    from worker.subscription_hygiene import contains_korean
    assert contains_korean("침착맨 하이라이트") is True
    assert contains_korean("ILLIT") is False
    assert contains_korean("LCK 플레이오프") is True
    assert contains_korean("") is False
    assert contains_korean(None) is False


@pytest.mark.asyncio
async def test_current_video_is_korean_detects_title():
    from worker import subscription_hygiene

    page = MagicMock()
    page.evaluate = AsyncMock(return_value={"title": "손흥민 토트넘 하이라이트", "channel": "ESPN"})
    assert await subscription_hygiene.current_video_is_korean(page) is True


@pytest.mark.asyncio
async def test_current_video_is_korean_non_kr():
    from worker import subscription_hygiene

    page = MagicMock()
    page.evaluate = AsyncMock(return_value={"title": "How to be cool", "channel": "Random"})
    assert await subscription_hygiene.current_video_is_korean(page) is False


@pytest.mark.asyncio
async def test_subscribe_skips_non_korean():
    from worker import subscription_hygiene

    page = MagicMock()
    page.evaluate = AsyncMock(return_value={"title": "English video", "channel": "English channel"})
    page.locator = MagicMock()

    # probability=1.0 ensures we would try, but KR check blocks
    with patch("worker.subscription_hygiene.random") as rng:
        rng.random.return_value = 0.0
        ok = await subscription_hygiene.maybe_subscribe_if_korean(page, probability=1.0)
    assert ok is False
    page.locator.assert_not_called()


@pytest.mark.asyncio
async def test_subscribe_clicks_when_korean_and_not_subscribed(monkeypatch):
    from worker import subscription_hygiene

    page = MagicMock()
    page.evaluate = AsyncMock(return_value={"title": "침착맨 하이라이트", "channel": "침착맨"})
    btn = MagicMock()
    btn.count = AsyncMock(return_value=1)
    btn.inner_text = AsyncMock(return_value="구독")
    btn.click = AsyncMock()
    locator = MagicMock()
    locator.first = btn
    page.locator = MagicMock(return_value=locator)

    monkeypatch.setattr(subscription_hygiene, "random_delay", AsyncMock())
    monkeypatch.setattr(subscription_hygiene.random, "random", lambda: 0.0)

    ok = await subscription_hygiene.maybe_subscribe_if_korean(page, probability=1.0)
    assert ok is True
    btn.click.assert_called_once()


@pytest.mark.asyncio
async def test_subscribe_skips_already_subscribed(monkeypatch):
    from worker import subscription_hygiene

    page = MagicMock()
    page.evaluate = AsyncMock(return_value={"title": "한국 영상", "channel": "한국 채널"})
    btn = MagicMock()
    btn.count = AsyncMock(return_value=1)
    btn.inner_text = AsyncMock(return_value="구독 중")
    btn.click = AsyncMock()
    locator = MagicMock()
    locator.first = btn
    page.locator = MagicMock(return_value=locator)

    monkeypatch.setattr(subscription_hygiene, "random_delay", AsyncMock())
    monkeypatch.setattr(subscription_hygiene.random, "random", lambda: 0.0)

    ok = await subscription_hygiene.maybe_subscribe_if_korean(page, probability=1.0)
    assert ok is False
    btn.click.assert_not_called()


@pytest.mark.asyncio
async def test_unsubscribe_picks_only_non_korean(monkeypatch):
    from worker import subscription_hygiene

    page = MagicMock()
    page.goto = AsyncMock()

    call_count = {"n": 0}
    returns = [
        # first evaluate: channel list
        [
            {"idx": 0, "name": "침착맨"},
            {"idx": 1, "name": "ESPN FC"},
            {"idx": 2, "name": "Tasty"},
            {"idx": 3, "name": "손흥민 공식"},
        ],
        # 2nd call: clicked subscribe button → True
        True,
        # 3rd call: confirmation dialog → True
        True,
    ]
    call_count_ref = {"i": 0}

    async def fake_eval(*args, **kwargs):
        i = call_count_ref["i"]
        call_count_ref["i"] += 1
        return returns[min(i, len(returns) - 1)]

    page.evaluate = fake_eval
    monkeypatch.setattr(subscription_hygiene, "random_delay", AsyncMock())
    monkeypatch.setattr(subscription_hygiene.random, "random", lambda: 0.0)
    monkeypatch.setattr(subscription_hygiene.random, "shuffle", lambda x: None)
    monkeypatch.setattr(subscription_hygiene.random, "randint", lambda a, b: 1)

    removed = await subscription_hygiene.maybe_unsubscribe_non_korean(
        page, max_actions=1, probability=1.0,
    )
    assert removed == 1
