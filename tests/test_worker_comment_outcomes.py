"""PR-3: worker 댓글/답글 post 결과 분기."""
import json

import pytest


class FakeClient:
    def __init__(self):
        self.errors = []
        self.screenshot_errors = []

    def report_error(self, **kwargs):
        self.errors.append(kwargs)

    def report_error_with_screenshot(self, **kwargs):
        self.screenshot_errors.append(kwargs)


class FakePage:
    url = "https://www.youtube.com/watch?v=v1"


class FakeBrowser:
    page = FakePage()


class FakeSession:
    account_id = 10
    profile_id = "profile-10"
    current_phase = "compose"

    def __init__(self):
        self.browser = FakeBrowser()
        self.server_client = FakeClient()

    async def capture_screenshot(self):
        return b"png"


async def _noop(*args, **kwargs):
    return None


async def _fake_nav(self, session, video_id, video_title=""):
    return None


def _patch_comment_path(monkeypatch, executor_mod, post_result):
    async def fake_post_comment(page, text):
        return post_result

    monkeypatch.setattr(executor_mod.TaskExecutor, "_navigate_to_video", _fake_nav)
    monkeypatch.setattr(executor_mod, "watch_video", _noop)
    monkeypatch.setattr(executor_mod, "scroll_to_comments", _noop)
    monkeypatch.setattr(executor_mod, "read_comments_before_posting", _noop)
    monkeypatch.setattr(executor_mod, "post_comment", fake_post_comment)


def _patch_reply_path(monkeypatch, executor_mod, post_result):
    async def fake_post_reply(page, target, text):
        return post_result

    monkeypatch.setattr(executor_mod.TaskExecutor, "_navigate_to_video", _fake_nav)
    monkeypatch.setattr(executor_mod, "scroll_to_comments", _noop)
    monkeypatch.setattr(executor_mod, "random_delay", _noop)
    monkeypatch.setattr(executor_mod, "post_reply", fake_post_reply)


@pytest.mark.asyncio
async def test_handle_comment_none_result_fails_with_post_failed(monkeypatch):
    import worker.executor as executor_mod

    _patch_comment_path(monkeypatch, executor_mod, None)
    session = FakeSession()

    with pytest.raises(RuntimeError) as ei:
        await executor_mod.TaskExecutor()._handle_comment(
            {"id": 1, "task_type": "comment"},
            {"video_id": "v1", "text": "hello"},
            session,
        )

    assert str(ei.value) == "post_failed"
    assert session.server_client.errors == []
    assert session.server_client.screenshot_errors == []


@pytest.mark.asyncio
async def test_handle_comment_empty_id_reports_diagnostic_and_completes(monkeypatch):
    import worker.executor as executor_mod

    _patch_comment_path(monkeypatch, executor_mod, "")
    session = FakeSession()

    result = await executor_mod.TaskExecutor()._handle_comment(
        {"id": 2, "task_type": "comment"},
        {"video_id": "v1", "text": "hello"},
        session,
    )

    data = json.loads(result)
    assert data["comment_id"] == ""
    assert session.server_client.screenshot_errors[0]["kind"] == "comment_id_unknown"
    assert session.server_client.screenshot_errors[0]["screenshot_bytes"] == b"png"


@pytest.mark.asyncio
async def test_handle_comment_valid_id_uses_existing_success_flow(monkeypatch):
    import worker.executor as executor_mod

    _patch_comment_path(monkeypatch, executor_mod, "Ug_VALID")
    session = FakeSession()

    result = await executor_mod.TaskExecutor()._handle_comment(
        {"id": 3, "task_type": "comment"},
        {"video_id": "v1", "text": "hello"},
        session,
    )

    data = json.loads(result)
    assert data["comment_id"] == "Ug_VALID"
    assert session.server_client.errors == []
    assert session.server_client.screenshot_errors == []


@pytest.mark.asyncio
async def test_handle_reply_none_result_fails_with_post_failed(monkeypatch):
    import worker.executor as executor_mod

    _patch_reply_path(monkeypatch, executor_mod, None)

    with pytest.raises(RuntimeError) as ei:
        await executor_mod.TaskExecutor()._handle_reply(
            {"id": 4, "task_type": "reply"},
            {"video_id": "v1", "target_comment_id": "Ug_PARENT", "text": "reply"},
            FakeSession(),
        )

    assert str(ei.value) == "post_failed"


@pytest.mark.asyncio
async def test_handle_reply_empty_id_reports_diagnostic_and_completes(monkeypatch):
    import worker.executor as executor_mod

    _patch_reply_path(monkeypatch, executor_mod, "")
    session = FakeSession()

    result = await executor_mod.TaskExecutor()._handle_reply(
        {"id": 5, "task_type": "reply"},
        {"video_id": "v1", "target_comment_id": "Ug_PARENT", "text": "reply"},
        session,
    )

    data = json.loads(result)
    assert data["reply_id"] == ""
    assert session.server_client.screenshot_errors[0]["kind"] == "reply_id_unknown"
