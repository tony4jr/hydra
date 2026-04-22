"""AuditLog 모델 기본 동작 검증."""
import json
from datetime import datetime, UTC

from hydra.db.models import AuditLog, User


def test_create_audit_log_minimal(db_session):
    """user/target 없어도 action 만으로 기록 가능 (시스템 액션)."""
    log = AuditLog(action="system_boot")
    db_session.add(log)
    db_session.commit()
    assert log.id is not None
    assert log.timestamp is not None


def test_audit_log_with_user_fk(db_session):
    u = User(email="auditor@hydra.local", password_hash="h", role="admin")
    db_session.add(u)
    db_session.commit()

    log = AuditLog(
        user_id=u.id,
        action="deploy",
        target_type="system",
        target_id=None,
        metadata_json=json.dumps({"version": "v1.2.3"}),
        ip_address="203.0.113.1",
        user_agent="Mozilla/5.0",
    )
    db_session.add(log)
    db_session.commit()

    loaded = db_session.query(AuditLog).filter_by(id=log.id).first()
    assert loaded.user_id == u.id
    assert loaded.action == "deploy"
    assert json.loads(loaded.metadata_json)["version"] == "v1.2.3"


def test_audit_log_ipv6_address(db_session):
    """IPv6 주소 최대 45자 저장 가능해야."""
    log = AuditLog(
        action="login",
        ip_address="2001:0db8:85a3:0000:0000:8a2e:0370:7334",
    )
    db_session.add(log)
    db_session.commit()
    assert len(log.ip_address) == 39


def test_audit_log_filter_by_action_and_user(db_session):
    """인덱스 활용 쿼리 동작 (user_id+timestamp, action+timestamp)."""
    for i in range(3):
        db_session.add(AuditLog(user_id=1, action="deploy"))
    for i in range(2):
        db_session.add(AuditLog(user_id=1, action="pause"))
    db_session.commit()

    deploy_count = db_session.query(AuditLog).filter_by(user_id=1, action="deploy").count()
    pause_count = db_session.query(AuditLog).filter_by(user_id=1, action="pause").count()
    assert deploy_count == 3
    assert pause_count == 2
