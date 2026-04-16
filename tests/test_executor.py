import json
from worker.executor import TaskExecutor


def test_executor_dispatches_comment():
    executor = TaskExecutor()
    task = {"id": 1, "task_type": "comment", "payload": json.dumps({"video_id": "abc123", "text": "great video"})}
    result = executor.execute(task)
    data = json.loads(result)
    assert data["action"] == "comment"
    assert data["video_id"] == "abc123"


def test_executor_dispatches_like_boost():
    executor = TaskExecutor()
    task = {"id": 2, "task_type": "like_boost", "payload": json.dumps({"video_id": "abc123", "target_step": 1})}
    result = executor.execute(task)
    data = json.loads(result)
    assert data["action"] == "like_boost"


def test_executor_dispatches_reply():
    executor = TaskExecutor()
    task = {"id": 3, "task_type": "reply", "payload": json.dumps({"video_id": "abc123", "target": "step_1"})}
    result = executor.execute(task)
    data = json.loads(result)
    assert data["action"] == "reply"
    assert data["target"] == "step_1"


def test_executor_unknown_type():
    executor = TaskExecutor()
    task = {"id": 4, "task_type": "unknown_action", "payload": "{}"}
    try:
        executor.execute(task)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unknown task type" in str(e)


def test_executor_empty_payload():
    executor = TaskExecutor()
    task = {"id": 5, "task_type": "like", "payload": None}
    result = executor.execute(task)
    data = json.loads(result)
    assert data["action"] == "like"
