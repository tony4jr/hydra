import asyncio

import pytest


@pytest.mark.asyncio
async def test_start_failure_stops_adspower_and_process_fallback(monkeypatch):
    from hydra.browser import driver

    calls = []

    class FakeAdsPower:
        def start_browser(self, profile_id):
            return {
                "ws_endpoint": "",
                "debug_port": "9222",
                "process_ids": [1234],
            }

        def stop_browser(self, profile_id):
            calls.append(("stop", profile_id))

    def fake_cleanup(**kwargs):
        calls.append(("cleanup", kwargs))
        return {"matched_pids": [1234]}

    monkeypatch.setattr(driver, "adspower", FakeAdsPower())
    monkeypatch.setattr(
        "hydra.browser.adspower_cleanup.cleanup_adspower_processes",
        fake_cleanup,
    )

    with pytest.raises(RuntimeError, match="No WebSocket endpoint"):
        await driver.BrowserSession("prof-1").start()

    assert ("stop", "prof-1") in calls
    cleanup_call = next(item for item in calls if item[0] == "cleanup")
    assert cleanup_call[1]["profile_id"] == "prof-1"
    assert cleanup_call[1]["known_pids"] == {1234}
    assert cleanup_call[1]["debug_port"] == "9222"


@pytest.mark.asyncio
async def test_close_timeout_still_calls_stop_and_cleanup(monkeypatch):
    from hydra.browser import driver

    calls = []

    class HangingBrowser:
        async def close(self):
            await asyncio.sleep(1)

    class FakeAdsPower:
        def stop_browser(self, profile_id):
            calls.append(("stop", profile_id))

    def fake_cleanup(**kwargs):
        calls.append(("cleanup", kwargs))
        return {"matched_pids": []}

    monkeypatch.setattr(driver, "PLAYWRIGHT_CLOSE_TIMEOUT_SEC", 0.01)
    monkeypatch.setattr(driver, "adspower", FakeAdsPower())
    monkeypatch.setattr(
        "hydra.browser.adspower_cleanup.cleanup_adspower_processes",
        fake_cleanup,
    )

    session = driver.BrowserSession("prof-2")
    session._browser = HangingBrowser()
    session._adspower_started = True

    await session.close()

    assert ("stop", "prof-2") in calls
    assert any(item[0] == "cleanup" for item in calls)
