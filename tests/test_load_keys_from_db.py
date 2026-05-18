"""Regression: _load_keys_from_db restored after removal in #46.

Two callers depend on it:
  - hydra/services/background.py _phase1_poll_sync (5min throttle count)
  - hydra/web/routes/admin_video_pool.py /quota endpoint
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import Base, YouTubeApiKey


@pytest.fixture
def db_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TS)
    # youtube_api 모듈이 `from hydra.db.session import SessionLocal` 로
    # 이름을 직접 바인딩했으므로 거기도 패치.
    import hydra.collection.youtube_api as yt_api
    monkeypatch.setattr(yt_api, "SessionLocal", TS)
    yield TS
    engine.dispose()


def test_load_keys_from_db_returns_active_only(db_env):
    s = db_env()
    s.add(YouTubeApiKey(key="AIzaACTIVE1", status="active"))
    s.add(YouTubeApiKey(key="AIzaACTIVE2", status="active"))
    s.add(YouTubeApiKey(key="AIzaEXHAUSTED", status="exhausted"))
    s.add(YouTubeApiKey(key="AIzaDISABLED", status="disabled"))
    s.commit()
    s.close()

    from hydra.collection.youtube_api import _load_keys_from_db
    keys = _load_keys_from_db()
    assert sorted(keys) == ["AIzaACTIVE1", "AIzaACTIVE2"]


def test_load_keys_from_db_empty_when_none(db_env):
    from hydra.collection.youtube_api import _load_keys_from_db
    assert _load_keys_from_db() == []


def test_admin_video_pool_imports_load_keys():
    """admin_video_pool 의 ImportError 방지 — 함수 존재 확인."""
    import hydra.collection.youtube_api as mod
    assert callable(mod._load_keys_from_db)


def test_background_scheduler_imports_load_keys():
    """background.py 가 import 가능."""
    import hydra.collection.youtube_api as mod
    assert hasattr(mod, "_load_keys_from_db")
    assert hasattr(mod, "search_videos")
