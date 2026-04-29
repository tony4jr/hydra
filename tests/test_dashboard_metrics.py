"""dashboard_metrics 단위 테스트.

PR-2b-1.

각 stage 의 윈도우/필터 정확성 + pass_rate + bottleneck 검증.
캐시 자체 검증은 test_cache.py 가 담당.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hydra.db.models import ActionLog, Base, CommentSnapshot, Task, Video
from hydra.services import _cache
from hydra.services.dashboard_metrics import get_pipeline_flow

UTC = timezone.utc


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def _clear_cache():
    """모든 테스트 전후 _cache 초기화 (테스트 간 누수 방지)."""
    _cache.invalidate()
    yield
    _cache.invalidate()


def _now() -> datetime:
    return datetime.now(UTC)


def test_empty_db_all_zero(db):
    res = get_pipeline_flow(db, window_hours=24)

    assert res.window_hours == 24
    assert len(res.stages) == 5
    for s in res.stages:
        assert s.count == 0
        assert s.pass_rate is None
        assert s.is_bottleneck is False
    assert res.bottleneck_message is None


def test_discovered_window_filter(db):
    now = _now()
    # 윈도우 내 5개
    for i in range(5):
        db.add(Video(
            id=f"in{i}",
            url=f"https://yt/{i}",
            collected_at=now - timedelta(hours=1),
        ))
    # 윈도우 밖 3개 (24h 이전)
    for i in range(3):
        db.add(Video(
            id=f"out{i}",
            url=f"https://yt/o{i}",
            collected_at=now - timedelta(hours=30),
        ))
    db.commit()

    res = get_pipeline_flow(db, window_hours=24)
    discovered = next(s for s in res.stages if s.stage == "discovered")
    assert discovered.count == 5


def test_market_fit_threshold_filter(db):
    now = _now()
    # threshold = 0.65 — 통과: 0.7, 0.8 (2개) / 탈락: 0.5
    for i, score in enumerate([0.5, 0.7, 0.8]):
        db.add(Video(
            id=f"v{i}",
            url=f"https://yt/{i}",
            collected_at=now - timedelta(hours=1),
            embedding_score=score,
        ))
    db.commit()

    res = get_pipeline_flow(db, window_hours=24)
    market_fit = next(s for s in res.stages if s.stage == "market_fit")
    assert market_fit.count == 2


def test_task_created_comment_reply_only(db):
    now = _now()
    for tt in ["comment", "reply", "like", "ghost_check"]:
        db.add(Task(
            task_type=tt,
            created_at=now - timedelta(hours=1),
        ))
    db.commit()

    res = get_pipeline_flow(db, window_hours=24)
    task_created = next(s for s in res.stages if s.stage == "task_created")
    assert task_created.count == 2  # comment + reply


def test_comment_posted_promo_only(db):
    now = _now()
    # promo 3개, non-promo 2개
    for _ in range(3):
        db.add(ActionLog(
            account_id=1,
            action_type="comment",
            is_promo=True,
            created_at=now - timedelta(hours=1),
        ))
    for _ in range(2):
        db.add(ActionLog(
            account_id=1,
            action_type="comment",
            is_promo=False,
            created_at=now - timedelta(hours=1),
        ))
    db.commit()

    res = get_pipeline_flow(db, window_hours=24)
    posted = next(s for s in res.stages if s.stage == "comment_posted")
    assert posted.count == 3


def test_survived_24h_distinct_excludes_held_deleted(db):
    now = _now()
    cutoff_24h = now - timedelta(hours=25)  # 25h 전 (24h 이상)

    # 살아있는 댓글 (distinct id 2개, snapshot 3개 — distinct 검증)
    for cid in ["c1", "c1", "c2"]:  # c1 두 번
        db.add(CommentSnapshot(
            account_id=1,
            video_id="v1",
            youtube_comment_id=cid,
            posted_at=cutoff_24h,
            captured_at=now - timedelta(hours=1),
            is_held=False,
            is_deleted=False,
        ))
    # held=True (제외)
    db.add(CommentSnapshot(
        account_id=1,
        video_id="v1",
        youtube_comment_id="c3",
        posted_at=cutoff_24h,
        captured_at=now - timedelta(hours=1),
        is_held=True,
        is_deleted=False,
    ))
    # deleted=True (제외)
    db.add(CommentSnapshot(
        account_id=1,
        video_id="v1",
        youtube_comment_id="c4",
        posted_at=cutoff_24h,
        captured_at=now - timedelta(hours=1),
        is_held=False,
        is_deleted=True,
    ))
    db.commit()

    res = get_pipeline_flow(db, window_hours=24)
    survived = next(s for s in res.stages if s.stage == "survived_24h")
    assert survived.count == 2  # c1, c2 distinct


def test_survived_24h_window_under_24h_returns_zero(db):
    now = _now()
    db.add(CommentSnapshot(
        account_id=1,
        video_id="v1",
        youtube_comment_id="c1",
        posted_at=now - timedelta(hours=25),
        captured_at=now - timedelta(minutes=30),
        is_held=False,
        is_deleted=False,
    ))
    db.commit()

    res = get_pipeline_flow(db, window_hours=1)
    survived = next(s for s in res.stages if s.stage == "survived_24h")
    assert survived.count == 0


def test_pass_rate_and_bottleneck_at_30_percent(db):
    """discovered 10 → market_fit 2 (20%) → bottleneck 트리거 + 한국어 메시지."""
    now = _now()
    # discovered 10개, 그 중 2개만 market_fit 통과
    for i in range(10):
        db.add(Video(
            id=f"v{i}",
            url=f"https://yt/{i}",
            collected_at=now - timedelta(hours=1),
            embedding_score=0.7 if i < 2 else 0.5,
        ))
    db.commit()

    res = get_pipeline_flow(db, window_hours=24)

    discovered = next(s for s in res.stages if s.stage == "discovered")
    market_fit = next(s for s in res.stages if s.stage == "market_fit")

    assert discovered.count == 10
    assert market_fit.count == 2
    assert market_fit.pass_rate == 0.2
    assert market_fit.is_bottleneck is True
    assert res.bottleneck_message is not None
    assert "시장 적합도" in res.bottleneck_message
    assert "20%" in res.bottleneck_message
