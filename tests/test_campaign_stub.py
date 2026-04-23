"""Task M1-5: 스텁 캠페인 — active 계정에 comment/like 태스크 1회씩 생성."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hydra.core.campaign_stub import scan_active_accounts
from hydra.db.models import Account, Base, Task


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = S()
    yield s
    s.close()
    engine.dispose()


def test_scan_generates_comment_and_like_for_active(session, monkeypatch):
    monkeypatch.setenv("M1_TEST_VIDEO_ID", "dQw4w9WgXcQ")
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="active", warmup_day=4,
    )
    session.add(acc)
    session.commit()

    count = scan_active_accounts(session)
    assert count == 1

    tasks = session.query(Task).filter_by(account_id=acc.id).all()
    types = sorted(t.task_type for t in tasks)
    assert types == ["comment", "like"]


def test_scan_skips_account_already_processed(session, monkeypatch):
    monkeypatch.setenv("M1_TEST_VIDEO_ID", "dQw4w9WgXcQ")
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="active", warmup_day=4,
    )
    session.add(acc)
    session.flush()
    session.add(Task(account_id=acc.id, task_type="comment", status="done"))
    session.commit()

    assert scan_active_accounts(session) == 0


def test_scan_skips_non_active(session, monkeypatch):
    monkeypatch.setenv("M1_TEST_VIDEO_ID", "dQw4w9WgXcQ")
    session.add_all([
        Account(gmail="a@x.com", password="x", adspower_profile_id="p1",
                status="warmup", warmup_day=2),
        Account(gmail="b@x.com", password="x", adspower_profile_id="p2",
                status="suspended"),
    ])
    session.commit()

    assert scan_active_accounts(session) == 0


def test_scan_raises_without_video_id(session, monkeypatch):
    monkeypatch.delenv("M1_TEST_VIDEO_ID", raising=False)
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="active", warmup_day=4,
    )
    session.add(acc)
    session.commit()
    assert scan_active_accounts(session) == 0
