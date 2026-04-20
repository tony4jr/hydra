"""like_boost_config.load() 테스트."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hydra.db.models import Base, SystemConfig
from hydra.services.like_boost_config import load, DEFAULTS


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_returns_defaults_when_empty(db):
    cfg = load(db)
    assert cfg == DEFAULTS


def test_reads_stored_values(db):
    db.add_all([
        SystemConfig(key="like_boost.watch_sec_min", value="5"),
        SystemConfig(key="like_boost.watch_sec_max", value="20"),
        SystemConfig(key="like_boost.click_delay_min", value="0.5"),
    ])
    db.commit()
    cfg = load(db)
    assert cfg["like_boost.watch_sec_min"] == 5
    assert cfg["like_boost.watch_sec_max"] == 20
    assert cfg["like_boost.click_delay_min"] == 0.5
    # unset keys fall back
    assert cfg["like_boost.scroll_delay_min"] == DEFAULTS["like_boost.scroll_delay_min"]


def test_negative_values_fall_back_to_default(db):
    db.add(SystemConfig(key="like_boost.watch_sec_min", value="-1"))
    db.commit()
    cfg = load(db)
    assert cfg["like_boost.watch_sec_min"] == DEFAULTS["like_boost.watch_sec_min"]


def test_garbage_values_fall_back(db):
    db.add(SystemConfig(key="like_boost.watch_sec_max", value="abc"))
    db.commit()
    cfg = load(db)
    assert cfg["like_boost.watch_sec_max"] == DEFAULTS["like_boost.watch_sec_max"]


def test_reversed_min_max_restores_pair(db):
    # min > max → pair resets to defaults
    db.add_all([
        SystemConfig(key="like_boost.watch_sec_min", value="50"),
        SystemConfig(key="like_boost.watch_sec_max", value="10"),
    ])
    db.commit()
    cfg = load(db)
    assert cfg["like_boost.watch_sec_min"] == DEFAULTS["like_boost.watch_sec_min"]
    assert cfg["like_boost.watch_sec_max"] == DEFAULTS["like_boost.watch_sec_max"]


def test_empty_string_treated_as_unset(db):
    db.add(SystemConfig(key="like_boost.watch_sec_min", value=""))
    db.commit()
    cfg = load(db)
    assert cfg["like_boost.watch_sec_min"] == DEFAULTS["like_boost.watch_sec_min"]


def test_int_keys_truncate_float_strings(db):
    db.add(SystemConfig(key="like_boost.surrounding_count_min", value="3"))
    db.commit()
    cfg = load(db)
    assert cfg["like_boost.surrounding_count_min"] == 3
    assert isinstance(cfg["like_boost.surrounding_count_min"], int)
