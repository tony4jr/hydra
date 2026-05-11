"""PR-K: mock YouTube + CI 회귀 테스트.

worker session pipeline (login_check → ip_rotate → adspower_open → cdp_connect →
video_goto → compose → submit) 을 mock 으로 시뮬레이션. 각 시나리오 결과 검증.
"""
from __future__ import annotations

import asyncio

import pytest

from hydra.testing.mock_youtube import (
    MockBrowserSession, MockYouTube, MockYouTubeResponse, SCENARIOS,
)


# ───── mock 기본 동작 ─────


def test_scenarios_complete():
    """expected 시나리오 다 정의됨."""
    expected = {
        "happy_path", "captcha_at_login", "ghost_comment", "rate_limited",
        "video_unavailable", "slow_load_video_goto", "slow_load_compose", "slow_load_submit",
    }
    assert set(SCENARIOS) == expected


def test_mock_yt_invalid_scenario_rejected():
    with pytest.raises(ValueError):
        MockYouTube(scenario="not-a-scenario")


@pytest.mark.asyncio
async def test_happy_path_submits_comment():
    yt = MockYouTube(scenario="happy_path")
    r = await yt.submit_comment(video_id="abc", text="hi", account_id=1)
    assert r.status == "ok"
    assert r.comment_id is not None
    assert len(yt.get_visible_comments("abc")) == 1


@pytest.mark.asyncio
async def test_captcha_blocks_login():
    yt = MockYouTube(scenario="captcha_at_login")
    r = await yt.login_check(account_id=1)
    assert r.status == "captcha"
    assert "captcha" in r.error


@pytest.mark.asyncio
async def test_video_unavailable_navigation():
    yt = MockYouTube(scenario="video_unavailable")
    r = await yt.navigate_to_video("abc")
    assert r.status == "unavailable"


@pytest.mark.asyncio
async def test_rate_limit_second_submit_within_minute():
    """rate_limited 시나리오 — 1건째는 통과, 2건째부터 거부."""
    yt = MockYouTube(scenario="rate_limited")
    r1 = await yt.submit_comment(video_id="v1", text="first", account_id=42)
    assert r1.status == "ok"
    r2 = await yt.submit_comment(video_id="v1", text="second", account_id=42)
    assert r2.status == "rate_limited"
    # 다른 계정은 영향 없음.
    r3 = await yt.submit_comment(video_id="v1", text="other", account_id=43)
    assert r3.status == "ok"


@pytest.mark.asyncio
async def test_ghost_comment_invisible_to_viewers():
    yt = MockYouTube(scenario="ghost_comment")
    r = await yt.submit_comment(video_id="v1", text="hi", account_id=1)
    assert r.status == "ghost"
    assert r.comment_id is not None
    # 작성자는 작성됐다고 봄
    by_acct = yt.get_comments_by_account(1)
    assert len(by_acct) == 1
    # 다른 viewer 입장: 보이는 댓글 0
    visible = yt.get_visible_comments("v1")
    assert len(visible) == 0


@pytest.mark.asyncio
async def test_like_comment():
    yt = MockYouTube()
    r = await yt.submit_comment("v1", "hi", account_id=1)
    cid = r.comment_id
    # 5 different accounts like the comment
    for acct in range(2, 7):
        await yt.like_comment(cid, account_id=acct)
    assert yt.total_likes_on_comment(cid) == 5
    # 같은 계정 중복 like 는 unique set 이므로 1로 카운트
    await yt.like_comment(cid, account_id=2)
    assert yt.total_likes_on_comment(cid) == 5


# ───── slow_load timeout 시나리오 — wait_for 와 통합 ─────


@pytest.mark.asyncio
async def test_slow_load_video_goto_triggers_phase_timeout():
    """video_goto phase 의 wait_for 가 mock slow_load 와 정확히 트립."""
    import time
    yt = MockYouTube(scenario="slow_load_video_goto")
    # phase_config video_goto timeout=60s 보다 mock 지연(120s) 길음 → wait_for 가 cancel.
    # 테스트에서 60s 기다리기 어려우니, mock 자체 동작만 직접 검증 (실제 timeout 은 phase_config 테스트가 cover).
    start = time.monotonic()
    task = asyncio.create_task(yt.navigate_to_video("v1"))
    try:
        await asyncio.wait_for(task, timeout=0.5)
        assert False, "should timeout"
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        assert 0.5 <= elapsed < 1.0


# ───── MockBrowserSession + 워커 통합 ─────


@pytest.mark.asyncio
async def test_mock_browser_session_navigates():
    yt = MockYouTube()
    bs = MockBrowserSession("profile-x", yt)
    await bs.start()
    assert bs.started is True
    await bs.goto("https://www.youtube.com/watch?v=abc123")
    # 영상 navigate 성공이면 예외 없음.


@pytest.mark.asyncio
async def test_mock_browser_session_fails_on_unavailable_video():
    yt = MockYouTube(scenario="video_unavailable")
    bs = MockBrowserSession("profile-x", yt)
    await bs.start()
    with pytest.raises(RuntimeError) as ei:
        await bs.goto("https://www.youtube.com/watch?v=deleted")
    assert "unavailable" in str(ei.value).lower() or "deleted" in str(ei.value).lower()


# ───── 시나리오: 50 계정이 한 영상에 like 박기 ─────


@pytest.mark.asyncio
async def test_like_boost_50_distinct_accounts():
    """smoke 의 like_boost 시나리오 — 영상당 ~20 likes 가 distinct account 로 누적."""
    yt = MockYouTube()
    # 1) account=1 이 main comment 작성
    main = await yt.submit_comment(video_id="v1", text="main", account_id=1)
    assert main.status == "ok"
    cid = main.comment_id
    # 2) 20 distinct accounts 가 like
    for acct in range(2, 22):
        r = await yt.like_comment(cid, account_id=acct)
        assert r.status == "ok"
    assert yt.total_likes_on_comment(cid) == 20


# ───── 시나리오: 3-tier reply chain (G-T3 pattern) ─────


@pytest.mark.asyncio
async def test_reply_chain_3_tier():
    """A → B(reply A) → C(reply B): G-T3 패턴."""
    yt = MockYouTube()
    a = await yt.submit_comment(video_id="v1", text="main A", account_id=1)
    b = await yt.submit_comment(video_id="v1", text="reply B", account_id=2, parent_id=a.comment_id)
    c = await yt.submit_comment(video_id="v1", text="reply C", account_id=3, parent_id=b.comment_id)
    assert a.status == b.status == c.status == "ok"
    # tree 검증
    assert yt.comments_db[b.comment_id]["parent_id"] == a.comment_id
    assert yt.comments_db[c.comment_id]["parent_id"] == b.comment_id
