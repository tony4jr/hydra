from hydra.services.auto_scheduler import get_brands_needing_campaigns, _get_week_start
from hydra.db.models import Base, Brand, Campaign, Video, Keyword
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
    # Brand with weekly target
    brand = Brand(name="TestBrand", status="active", weekly_campaign_target=10, auto_campaign_enabled=True)
    session.add(brand)
    session.commit()
    yield session
    session.close()


def test_get_brands_needing_campaigns(db):
    result = get_brands_needing_campaigns(db)
    assert len(result) == 1
    assert result[0]["brand_name"] == "TestBrand"
    assert result[0]["remaining"] == 10


def test_get_brands_no_target(db):
    brand = db.query(Brand).first()
    brand.weekly_campaign_target = 0
    db.commit()
    result = get_brands_needing_campaigns(db)
    assert len(result) == 0


def test_get_brands_auto_disabled(db):
    brand = db.query(Brand).first()
    brand.auto_campaign_enabled = False
    db.commit()
    result = get_brands_needing_campaigns(db)
    assert len(result) == 0


def test_get_week_start():
    ws = _get_week_start()
    assert ws.weekday() == 0  # Monday
    assert ws.hour == 0
    assert ws.minute == 0
