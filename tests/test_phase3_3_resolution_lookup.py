"""Phase 3.3 — ScreenResolution lookup + apply + capture wiring."""
from datetime import UTC, datetime
import asyncio
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.auth import hash_password
from hydra.db.models import Base, ScreenResolution, Worker


def _sha(s): return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture
def api_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TS)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")
    monkeypatch.setenv("ENROLLMENT_SECRET", "x" * 32)
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")

    s = TS()
    wtok = "w-" + "x" * 32
    w = Worker(name="pc-01", status="online", current_version="v1",
               last_heartbeat=datetime.now(UTC),
               token_hash=hash_password(wtok),
               token_sha256=_sha(wtok), token_prefix=wtok[:8])
    s.add(w); s.commit(); s.refresh(w)
    s.close()
    from hydra.web.app import app
    yield {"client": TestClient(app), "Session": TS, "wtok": wtok}
    engine.dispose()


def _seed_res(TS, **kw):
    s = TS()
    defaults = dict(
        screen_state="trust_device_prompt",
        resolution_type="auto_click_skip",
        action_config=json.dumps({"selector": "button:has-text('나중에')"}),
        approved=True,
    )
    defaults.update(kw)
    if "action_config" in kw and isinstance(kw["action_config"], dict):
        defaults["action_config"] = json.dumps(kw["action_config"])
    r = ScreenResolution(**defaults)
    s.add(r); s.commit(); s.refresh(r); rid = r.id
    s.close()
    return rid


def test_lookup_no_match_returns_match_false(api_env):
    r = api_env["client"].post(
        "/api/workers/resolution-lookup",
        headers={"X-Worker-Token": api_env["wtok"]},
        json={"screen_state": "nonexistent_state"},
    )
    assert r.status_code == 200
    assert r.json()["match"] is False


def test_lookup_screen_state_only_match(api_env):
    rid = _seed_res(api_env["Session"], screen_state="trust_device_prompt",
                    url_pattern=None, title_pattern=None, dom_signature=None)
    r = api_env["client"].post(
        "/api/workers/resolution-lookup",
        headers={"X-Worker-Token": api_env["wtok"]},
        json={"screen_state": "trust_device_prompt"},
    )
    body = r.json()
    assert body["match"] is True
    assert body["resolution_id"] == rid
    assert body["resolution_type"] == "auto_click_skip"
    assert body["action_config"]["selector"] == "button:has-text('나중에')"


def test_lookup_unapproved_is_skipped(api_env):
    _seed_res(api_env["Session"], screen_state="x", approved=False)
    r = api_env["client"].post(
        "/api/workers/resolution-lookup",
        headers={"X-Worker-Token": api_env["wtok"]},
        json={"screen_state": "x"},
    )
    assert r.json()["match"] is False


def test_lookup_url_pattern_beats_screen_state_only(api_env):
    """url_pattern 매치가 screen_state-only 보다 우선."""
    TS = api_env["Session"]
    _seed_res(TS, screen_state="s1", url_pattern=None, title_pattern=None,
              dom_signature=None, action_config={"selector": "GENERIC"})
    rid_url = _seed_res(TS, screen_state="s1", url_pattern="/challenge/recaptcha",
                        title_pattern=None, dom_signature=None,
                        action_config={"selector": "URL_MATCH"})
    r = api_env["client"].post(
        "/api/workers/resolution-lookup",
        headers={"X-Worker-Token": api_env["wtok"]},
        json={"screen_state": "s1",
              "url": "https://accounts.google.com/challenge/recaptcha?foo=1"},
    )
    body = r.json()
    assert body["match"] is True
    assert body["resolution_id"] == rid_url
    assert body["action_config"]["selector"] == "URL_MATCH"


def test_lookup_dom_signature_beats_all(api_env):
    TS = api_env["Session"]
    _seed_res(TS, screen_state="s2", url_pattern="/foo", title_pattern=None,
              dom_signature=None, action_config={"selector": "URL"})
    rid_dom = _seed_res(TS, screen_state="other", url_pattern=None,
                        title_pattern=None, dom_signature="abc123",
                        action_config={"selector": "DOM"})
    r = api_env["client"].post(
        "/api/workers/resolution-lookup",
        headers={"X-Worker-Token": api_env["wtok"]},
        json={"screen_state": "s2", "url": "https://x/foo",
              "dom_signature": "abc123"},
    )
    body = r.json()
    assert body["match"] is True
    assert body["resolution_id"] == rid_dom


def test_lookup_bumps_hit_count(api_env):
    rid = _seed_res(api_env["Session"], screen_state="s3")
    for _ in range(3):
        api_env["client"].post(
            "/api/workers/resolution-lookup",
            headers={"X-Worker-Token": api_env["wtok"]},
            json={"screen_state": "s3"},
        )
    s = api_env["Session"]()
    r = s.get(ScreenResolution, rid)
    assert r.hit_count == 3
    assert r.last_hit_at is not None
    s.close()


# ───────── apply_resolution handler ─────────

@pytest.mark.asyncio
async def test_apply_auto_click_skip_success():
    from worker.resolution import apply_resolution
    page = MagicMock()
    locator = MagicMock()
    locator.first.click = AsyncMock(return_value=None)
    page.locator.return_value = locator
    ok = await apply_resolution(page, {
        "resolution_id": 1,
        "resolution_type": "auto_click_skip",
        "action_config": {"selector": "button.skip"},
    })
    assert ok is True
    page.locator.assert_called_with("button.skip")
    locator.first.click.assert_awaited()


@pytest.mark.asyncio
async def test_apply_auto_click_skip_failure_returns_false():
    from worker.resolution import apply_resolution
    page = MagicMock()
    locator = MagicMock()
    locator.first.click = AsyncMock(side_effect=RuntimeError("timeout"))
    page.locator.return_value = locator
    ok = await apply_resolution(page, {
        "resolution_id": 2,
        "resolution_type": "auto_click_skip",
        "action_config": {"selector": "button.skip"},
    })
    assert ok is False


@pytest.mark.asyncio
async def test_apply_missing_selector_returns_false():
    from worker.resolution import apply_resolution
    ok = await apply_resolution(MagicMock(), {
        "resolution_id": 3,
        "resolution_type": "auto_click_skip",
        "action_config": {},
    })
    assert ok is False


@pytest.mark.asyncio
async def test_apply_unimplemented_type_returns_false():
    from worker.resolution import apply_resolution
    for t in ("auto_enter_code", "retry_after_cooldown", "fail_task",
              "escalate_manual"):
        ok = await apply_resolution(MagicMock(), {
            "resolution_id": 1, "resolution_type": t, "action_config": {},
        })
        assert ok is False, f"{t} should not be handled yet"


# ───────── capture_unknown_screen wiring ─────────

@pytest.mark.asyncio
async def test_capture_skips_when_resolution_applied():
    """resolution 매치+성공 시 캡처/업로드 안 함."""
    from worker.capture import capture_unknown_screen
    from hydra.protocol.failure_taxonomy import FailureTaxonomy

    page = MagicMock()
    page.url = "https://x/y"
    page.title = AsyncMock(return_value="T")
    locator = MagicMock(); locator.first.click = AsyncMock(return_value=None)
    page.locator.return_value = locator
    page.screenshot = AsyncMock(return_value=b"png")
    page.content = AsyncMock(return_value="<html></html>")

    client = MagicMock()
    client.lookup_resolution.return_value = {
        "resolution_id": 9,
        "resolution_type": "auto_click_skip",
        "action_config": {"selector": "button.skip"},
        "screen_state": "X",
    }
    await capture_unknown_screen(
        page, screen_state="X", taxonomy=FailureTaxonomy.PAGE_VARIANT,
        reason="t", client=client, task_id=1, account_id=2,
    )
    # 캡처 업로드 함수 호출 안 함
    assert not client.report_error_with_screenshot.called
    assert not client.report_error.called
    # account_event 는 'other' (resolution_applied 마커) 로 emit
    assert client.report_account_event.called


@pytest.mark.asyncio
async def test_capture_falls_through_when_no_match():
    from worker.capture import capture_unknown_screen
    from hydra.protocol.failure_taxonomy import FailureTaxonomy
    page = MagicMock()
    page.url = "https://x/y"
    page.title = AsyncMock(return_value="T")
    page.screenshot = AsyncMock(return_value=b"png")
    page.content = AsyncMock(return_value="<html></html>")
    client = MagicMock()
    client.lookup_resolution.return_value = None
    await capture_unknown_screen(
        page, screen_state="X", taxonomy=FailureTaxonomy.PAGE_VARIANT,
        reason="t", client=client, task_id=1, account_id=2,
    )
    assert client.report_error_with_screenshot.called


@pytest.mark.asyncio
async def test_capture_falls_through_when_handler_fails():
    from worker.capture import capture_unknown_screen
    from hydra.protocol.failure_taxonomy import FailureTaxonomy
    page = MagicMock()
    page.url = "https://x/y"
    page.title = AsyncMock(return_value="T")
    locator = MagicMock(); locator.first.click = AsyncMock(side_effect=RuntimeError("nope"))
    page.locator.return_value = locator
    page.screenshot = AsyncMock(return_value=b"png")
    page.content = AsyncMock(return_value="<html></html>")
    client = MagicMock()
    client.lookup_resolution.return_value = {
        "resolution_id": 9, "resolution_type": "auto_click_skip",
        "action_config": {"selector": "button.skip"}, "screen_state": "X",
    }
    await capture_unknown_screen(
        page, screen_state="X", taxonomy=FailureTaxonomy.PAGE_VARIANT,
        reason="t", client=client, task_id=1, account_id=2,
    )
    # 핸들러 실패 → 캡처 fallback
    assert client.report_error_with_screenshot.called
