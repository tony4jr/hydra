from hydra.services.ghost_service import report_ghost_check, GHOST_VISIBLE, GHOST_SUSPICIOUS
from hydra.db.models import Base, Campaign, Brand, Video, Task
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    brand = Brand(name="Test")
    session.add(brand)
    session.flush()
    video = Video(id="vid_1", url="https://youtube.com/watch?v=vid_1")
    session.add(video)
    session.flush()
    campaign = Campaign(video_id="vid_1", brand_id=brand.id, scenario="A", status="in_progress", ghost_check_status="pending")
    session.add(campaign)
    session.commit()
    yield session
    session.close()


def test_report_visible(db):
    result = report_ghost_check(db, 1, "comment_123", "visible", 1, 1)
    assert result == GHOST_VISIBLE


def test_report_suspicious_first(db):
    result = report_ghost_check(db, 1, "comment_123", "suspicious", 1, 1)
    assert result == GHOST_SUSPICIOUS
    # Cross-check task should be created
    tasks = db.query(Task).filter(Task.task_type == "ghost_check").all()
    assert len(tasks) == 1


def test_report_suspicious_cross_check(db):
    # First suspicious
    report_ghost_check(db, 1, "comment_123", "suspicious", 1, 1)
    # Second suspicious (cross check)
    campaign = db.get(Campaign, 1)
    campaign.ghost_check_status = "suspicious"
    db.commit()
    result = report_ghost_check(db, 1, "comment_123", "suspicious", 2, 2)
    assert result == GHOST_SUSPICIOUS
    # Recheck task scheduled
    tasks = db.query(Task).filter(Task.task_type == "ghost_check").all()
    assert len(tasks) == 2  # cross_check + recheck
