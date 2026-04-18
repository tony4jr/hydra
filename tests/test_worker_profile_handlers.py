import json
import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_handle_create_profile_returns_profile_id():
    from worker.executor import TaskExecutor
    ex = TaskExecutor()

    task = {
        "task_type": "create_profile",
        "payload": json.dumps({
            "account_id": 1,
            "profile_name": "hydra_1_test",
            "group_id": "0",
            "remark": "test",
            "device_hint": "windows_heavy",
            "fingerprint_payload": {"timezone": "Asia/Seoul"},
        }),
    }

    with patch("worker.executor.adspower") as m:
        m.create_profile.return_value = "gen123"
        result = await ex.execute(task, session=None)

    assert isinstance(result, str)
    data = json.loads(result)
    assert data["profile_id"] == "gen123"


@pytest.mark.asyncio
async def test_handle_create_profile_propagates_quota_error():
    from worker.executor import TaskExecutor
    from hydra.browser.adspower_errors import AdsPowerQuotaExceeded
    ex = TaskExecutor()

    task = {
        "task_type": "create_profile",
        "payload": json.dumps({
            "account_id": 1,
            "profile_name": "n",
            "group_id": "0",
            "fingerprint_payload": {},
        }),
    }

    with patch("worker.executor.adspower") as m:
        m.create_profile.side_effect = AdsPowerQuotaExceeded("limit")
        with pytest.raises(AdsPowerQuotaExceeded):
            await ex.execute(task, session=None)


@pytest.mark.asyncio
async def test_handle_retire_profile_calls_delete():
    from worker.executor import TaskExecutor
    ex = TaskExecutor()

    task = {
        "task_type": "retire_profile",
        "payload": json.dumps({
            "profile_id": "to_delete",
            "reason": "ghost",
        }),
    }

    with patch("worker.executor.adspower") as m:
        result = await ex.execute(task, session=None)
        m.delete_profile.assert_called_once_with("to_delete")

    data = json.loads(result)
    assert data["retired_profile_id"] == "to_delete"
