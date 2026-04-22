"""User 모델 기본 동작 검증."""
import pytest
from sqlalchemy.exc import IntegrityError

from hydra.db.models import User


def test_create_user_with_default_role(db_session):
    u = User(email="test1@hydra.local", password_hash="hash1")
    db_session.add(u)
    db_session.commit()
    loaded = db_session.query(User).filter_by(email="test1@hydra.local").first()
    assert loaded.role == "operator"  # server_default


def test_create_admin_user(db_session):
    u = User(email="admin@hydra.local", password_hash="hash_admin", role="admin")
    db_session.add(u)
    db_session.commit()
    loaded = db_session.query(User).filter_by(email="admin@hydra.local").first()
    assert loaded.role == "admin"


def test_email_unique_constraint(db_session):
    db_session.add(User(email="dup@hydra.local", password_hash="h1"))
    db_session.commit()

    db_session.add(User(email="dup@hydra.local", password_hash="h2"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_created_at_auto_set(db_session):
    u = User(email="t_created@hydra.local", password_hash="h")
    db_session.add(u)
    db_session.commit()
    loaded = db_session.query(User).filter_by(email="t_created@hydra.local").first()
    assert loaded.created_at is not None
    assert loaded.last_login_at is None
