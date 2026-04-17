from unittest.mock import MagicMock
from worker.warmup import WarmupExecutor

def test_pick_video_count_day1():
    session = MagicMock()
    executor = WarmupExecutor(session, day=1)
    for _ in range(20):
        count = executor._pick_video_count()
        assert 1 <= count <= 2

def test_pick_video_count_day2():
    session = MagicMock()
    executor = WarmupExecutor(session, day=2)
    for _ in range(20):
        count = executor._pick_video_count()
        assert 2 <= count <= 3

def test_pick_comment_count_day1():
    session = MagicMock()
    executor = WarmupExecutor(session, day=1)
    assert executor._pick_comment_count() == 0

def test_pick_comment_count_day2():
    session = MagicMock()
    executor = WarmupExecutor(session, day=2)
    for _ in range(20):
        count = executor._pick_comment_count()
        assert 1 <= count <= 2

def test_pick_comment_count_day3():
    session = MagicMock()
    executor = WarmupExecutor(session, day=3)
    for _ in range(20):
        count = executor._pick_comment_count()
        assert 3 <= count <= 5

def test_generate_casual_comment():
    session = MagicMock()
    executor = WarmupExecutor(session, day=2)
    comment = executor._generate_casual_comment()
    assert isinstance(comment, str)
    assert len(comment) > 0

def test_like_probability():
    session = MagicMock()
    e1 = WarmupExecutor(session, day=1)
    e2 = WarmupExecutor(session, day=2)
    assert e1._like_probability() == 0.3
    assert e2._like_probability() == 0.5

def test_persona_occupation():
    session = MagicMock()
    e = WarmupExecutor(session, day=2, persona={"occupation": "회사원"})
    assert e.occupation == "회사원"

def test_persona_default():
    session = MagicMock()
    e = WarmupExecutor(session, day=1)
    assert e.occupation == "default"
