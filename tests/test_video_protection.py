from hydra.services.video_protection import check_video_campaign_limit, check_account_video_duplicate
from hydra.db.models import Base, Account, Campaign, ActionLog, Brand, Video
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
    # Setup
    brand = Brand(name="TestBrand")
    session.add(brand)
    session.flush()
    video = Video(id="vid_123", url="https://youtube.com/watch?v=vid_123")
    session.add(video)
    account = Account(gmail="test@gmail.com", password="pass")
    session.add(account)
    session.commit()
    yield session
    session.close()


def test_video_campaign_limit_under(db):
    allowed, count = check_video_campaign_limit(db, "vid_123")
    assert allowed is True
    assert count == 0


def test_video_campaign_limit_over(db):
    for i in range(2):
        db.add(Campaign(video_id="vid_123", brand_id=1, scenario="A", status="completed"))
    db.commit()
    allowed, count = check_video_campaign_limit(db, "vid_123")
    assert allowed is False
    assert count == 2


def test_account_video_duplicate_none(db):
    assert check_account_video_duplicate(db, 1, "vid_123") is True


def test_account_video_duplicate_exists(db):
    db.add(ActionLog(account_id=1, video_id="vid_123", action_type="comment", created_at=datetime.now(UTC)))
    db.commit()
    assert check_account_video_duplicate(db, 1, "vid_123") is False
