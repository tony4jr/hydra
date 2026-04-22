"""hydra.core.server_config 테스트.

SystemConfig 테이블(key-value)을 singleton row 처럼 다루는 헬퍼들.
기존 SystemConfig 에 server_config.* 접두 키로 저장.
"""
import pytest

from hydra.core import server_config as sc
from hydra.db.models import SystemConfig


def test_get_current_version_returns_default_when_unset(db_session):
    # SystemConfig 에 current_version key 없을 때
    assert sc.get_current_version(session=db_session) == "v0"


def test_set_and_get_current_version(db_session):
    sc.set_current_version("v1.2.3", session=db_session)
    db_session.commit()
    assert sc.get_current_version(session=db_session) == "v1.2.3"


def test_set_current_version_overwrites_existing(db_session):
    sc.set_current_version("v1", session=db_session)
    db_session.commit()
    sc.set_current_version("v2", session=db_session)
    db_session.commit()
    assert sc.get_current_version(session=db_session) == "v2"

    # 여러 row 생기지 않고 한 개만 유지
    rows = db_session.query(SystemConfig).filter_by(key="server_config.current_version").all()
    assert len(rows) == 1


def test_is_paused_default_false(db_session):
    assert sc.is_paused(session=db_session) is False


def test_set_paused_true_then_read(db_session):
    sc.set_paused(True, session=db_session)
    db_session.commit()
    assert sc.is_paused(session=db_session) is True
    sc.set_paused(False, session=db_session)
    db_session.commit()
    assert sc.is_paused(session=db_session) is False


def test_canary_worker_ids_default_empty(db_session):
    assert sc.get_canary_worker_ids(session=db_session) == []


def test_set_and_get_canary_worker_ids(db_session):
    sc.set_canary_worker_ids([1, 3, 7], session=db_session)
    db_session.commit()
    assert sc.get_canary_worker_ids(session=db_session) == [1, 3, 7]


def test_set_canary_rejects_non_int_list(db_session):
    with pytest.raises((TypeError, ValueError)):
        sc.set_canary_worker_ids("not a list", session=db_session)
