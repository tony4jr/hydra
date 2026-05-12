"""PR-D-lite: IpLog DB I/O 실패 시 silent fallback.

워커 로컬 SQLite 에 accounts row 가 없어서 IpLog FK 위반 시 IP rotation 자체는 정상 진행.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_check_ip_available_db_error_returns_false():
    """DB 쿼리 실패 → False (rotate 강제)."""
    from hydra.infra.ip import check_ip_available
    db = MagicMock()
    db.query.side_effect = RuntimeError("simulated db error")
    assert check_ip_available(db, "1.2.3.4", account_id=42) is False


def test_log_ip_usage_db_error_returns_none():
    """DB INSERT 실패 → None, rollback 호출."""
    from hydra.infra.ip import log_ip_usage
    db = MagicMock()
    db.commit.side_effect = RuntimeError("FK violation")
    result = log_ip_usage(db, account_id=42, ip_address="1.2.3.4", device_id="DEV")
    assert result is None
    db.rollback.assert_called_once()


def test_log_ip_usage_success_returns_record():
    """정상 시 IpLog 객체 반환."""
    from hydra.infra.ip import log_ip_usage
    db = MagicMock()
    result = log_ip_usage(db, account_id=42, ip_address="1.2.3.4", device_id="DEV")
    assert result is not None
    db.commit.assert_called_once()


def test_check_ip_available_no_conflict_returns_true():
    """정상 DB 쿼리 + conflict 없음 → True."""
    from hydra.infra.ip import check_ip_available
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # no conflict
    assert check_ip_available(db, "1.2.3.4", account_id=42) is True
