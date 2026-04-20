from hydra.services.account_limits import check_daily_limit, check_weekly_limit, can_execute_task
from hydra.db.models import Base, Account, ActionLog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, UTC

import pytest


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # Create test account
    account = Account(gmail="test@gmail.com", password="pass", daily_comment_limit=5, daily_like_limit=10, weekly_comment_limit=20, weekly_like_limit=50)
    session.add(account)
    session.commit()
    yield session
    session.close()


def test_check_daily_limit_under(db):
    result = check_daily_limit(db, 1)
    assert result["allowed"] is True
    assert result["comment_allowed"] is True
    assert result["today_comments"] == 0


def test_check_daily_limit_over(db):
    # Add 5 comments
    for _ in range(5):
        db.add(ActionLog(account_id=1, action_type="comment", created_at=datetime.now(UTC)))
    db.commit()
    result = check_daily_limit(db, 1)
    assert result["comment_allowed"] is False


def test_can_execute_task_allowed(db):
    allowed, reason = can_execute_task(db, 1, "comment")
    assert allowed is True


def test_can_execute_task_limit_reached(db):
    for _ in range(5):
        db.add(ActionLog(account_id=1, action_type="comment", created_at=datetime.now(UTC)))
    db.commit()
    allowed, reason = can_execute_task(db, 1, "comment")
    assert allowed is False
    assert reason == "daily_comment_limit"


def test_get_effective_limit_handles_null_fields(db):
    """레거시 행이 NULL 을 가져도 기본값으로 안전하게 계산되는지."""
    from hydra.services.account_limits import get_effective_limit
    # Simulate a legacy row with NULL fields
    acct = Account(gmail="legacy@gmail.com", password="p", status="active")
    db.add(acct)
    db.commit()
    # SQLAlchemy may apply model default; force NULL via direct SQL
    from sqlalchemy import text
    db.execute(text(
        "UPDATE accounts SET daily_comment_limit=NULL, daily_like_limit=NULL, "
        "weekly_comment_limit=NULL, weekly_like_limit=NULL WHERE id=:id"
    ), {"id": acct.id})
    db.commit()
    db.refresh(acct)
    # Should not raise
    assert get_effective_limit(acct, "daily_comment_limit") == 15
    assert get_effective_limit(acct, "daily_like_limit") == 50
    assert get_effective_limit(acct, "weekly_comment_limit") == 70
    assert get_effective_limit(acct, "weekly_like_limit") == 300
