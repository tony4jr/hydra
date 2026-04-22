"""ProfileLock — task_id 필드 + 동시 실행 방지 unique partial index."""
import pytest
from datetime import datetime, UTC
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from hydra.db.models import ProfileLock, Account, Worker


def _ensure_unique_partial_index(db_session):
    """conftest 가 Base.metadata.create_all 로 테이블만 만들어서 마이그레이션의
    raw SQL partial index 가 없음. 테스트에서만 직접 생성."""
    db_session.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_profile_locks_active "
        "ON profile_locks (account_id) WHERE released_at IS NULL"
    ))
    db_session.commit()


def _make_account_worker(db_session, gmail="a@test.local", worker_name="w1"):
    acct = Account(gmail=gmail, password="pwd", status="warmup",
                    adspower_profile_id=f"prof-{gmail}")
    worker = Worker(name=worker_name, token_hash="hash_test")
    db_session.add_all([acct, worker])
    db_session.commit()
    return acct, worker


def test_create_lock_with_task_id(db_session):
    acct, worker = _make_account_worker(db_session)
    lock = ProfileLock(
        account_id=acct.id,
        worker_id=worker.id,
        task_id=None,
        adspower_profile_id=acct.adspower_profile_id,
    )
    db_session.add(lock); db_session.commit()
    assert lock.id is not None
    assert lock.released_at is None


def test_second_active_lock_on_same_account_raises(db_session):
    """같은 account 에 released_at IS NULL 인 lock 2개 시도 → UNIQUE 위반."""
    _ensure_unique_partial_index(db_session)
    acct, worker = _make_account_worker(db_session)
    db_session.add(ProfileLock(
        account_id=acct.id, worker_id=worker.id,
        adspower_profile_id=acct.adspower_profile_id,
    ))
    db_session.commit()

    # 두 번째 lock
    db_session.add(ProfileLock(
        account_id=acct.id, worker_id=worker.id,
        adspower_profile_id=acct.adspower_profile_id,
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_released_lock_allows_new_active_lock(db_session):
    """첫 lock 이 released 상태면 같은 account 에 새 active lock 생성 가능."""
    acct, worker = _make_account_worker(db_session)
    first = ProfileLock(
        account_id=acct.id, worker_id=worker.id,
        adspower_profile_id=acct.adspower_profile_id,
        released_at=datetime.now(UTC),   # 즉시 released
    )
    db_session.add(first); db_session.commit()

    second = ProfileLock(
        account_id=acct.id, worker_id=worker.id,
        adspower_profile_id=acct.adspower_profile_id,
    )
    db_session.add(second); db_session.commit()
    assert second.id is not None
    assert second.id != first.id


def test_different_accounts_can_hold_active_locks_simultaneously(db_session):
    """다른 account 면 동시 active lock OK."""
    a1, w = _make_account_worker(db_session, gmail="a1@test.local", worker_name="w-multi")
    a2 = Account(gmail="a2@test.local", password="p", status="warmup",
                 adspower_profile_id="prof-a2")
    db_session.add(a2); db_session.commit()

    db_session.add_all([
        ProfileLock(account_id=a1.id, worker_id=w.id, adspower_profile_id=a1.adspower_profile_id),
        ProfileLock(account_id=a2.id, worker_id=w.id, adspower_profile_id=a2.adspower_profile_id),
    ])
    db_session.commit()  # 에러 없어야 함
