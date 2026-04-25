"""T10 재시도 정책 차등 — task_type 별 + 영구 에러 즉시 격리."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hydra.core.orchestrator import (
    PERMANENT_ERROR_PATTERNS, TASK_RETRY_POLICY,
    _is_permanent_error, _max_retries_for, on_task_fail,
)
from hydra.db.models import Account, Base, Task, Worker


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()
    engine.dispose()


def _make(db, task_type: str, retry_count: int = 0,
          error: str | None = None, max_retries: int | None = None) -> int:
    a = Account(gmail=f"{task_type}@x.com", password="enc",
                adspower_profile_id=f"p-{task_type}-{retry_count}", status="active")
    db.add(a); db.commit(); db.refresh(a)
    t = Task(
        account_id=a.id, task_type=task_type, status="failed",
        retry_count=retry_count, max_retries=max_retries,
        error_message=error,
    )
    db.add(t); db.commit(); db.refresh(t)
    return a.id, t.id


def test_max_retries_differs_per_task_type():
    assert _max_retries_for("comment") == 1
    assert _max_retries_for("like") == 3
    assert _max_retries_for("warmup") == 5
    # 알려지지 않은 type → fallback
    assert _max_retries_for("xxx") == 3


def test_permanent_error_pattern_detection():
    assert _is_permanent_error("account suspended permanently")
    assert _is_permanent_error("captcha_persistent: 5x failed")
    assert _is_permanent_error("ProfileLockedElsewhere")
    assert not _is_permanent_error("timeout")
    assert not _is_permanent_error(None)


def test_permanent_error_immediately_suspends_account(db):
    a_id, t_id = _make(db, "comment", retry_count=0, error="account suspended")
    on_task_fail(t_id, db); db.commit()
    assert db.get(Account, a_id).status == "suspended"
    # 재시도 태스크 생성 X
    assert db.query(Task).filter(Task.account_id == a_id, Task.status == "pending").count() == 0


def test_comment_retries_exactly_once(db):
    a_id, t_id = _make(db, "comment", retry_count=0, error="timeout")
    on_task_fail(t_id, db); db.commit()
    # retry_count=1 인 새 태스크 1개
    pending = db.query(Task).filter(Task.account_id == a_id, Task.status == "pending").all()
    assert len(pending) == 1
    assert pending[0].retry_count == 1

    # 두 번째 실패 → 한도 초과로 suspended
    pending[0].status = "failed"; db.commit()
    on_task_fail(pending[0].id, db); db.commit()
    assert db.get(Account, a_id).status == "suspended"


def test_like_retries_three_times(db):
    a_id, _ = _make(db, "like", retry_count=0, error="timeout")
    # 4번 실패 시뮬레이션 — 3번 재시도 후 suspended
    for i in range(4):
        t = db.query(Task).filter(Task.account_id == a_id, Task.status == "failed").order_by(Task.id.desc()).first()
        if t is None:
            t = db.query(Task).filter(Task.account_id == a_id, Task.status == "pending").order_by(Task.id.desc()).first()
            t.status = "failed"; db.commit()
        on_task_fail(t.id, db); db.commit()
        # 다음 시도 setup
        nxt = db.query(Task).filter(Task.account_id == a_id, Task.status == "pending").order_by(Task.id.desc()).first()
        if nxt:
            nxt.error_message = "timeout"
            nxt.status = "failed"; db.commit()

    assert db.get(Account, a_id).status == "suspended"


def test_policy_overrides_task_max_retries_field(db):
    """모델 default=3 으로 항상 값 있어 명시 override 판별 불가 → 정책이 결정."""
    # Task.max_retries=10 으로 만들어도 comment 정책(1) 이 결정
    a_id, t_id = _make(db, "comment", retry_count=0, error="timeout", max_retries=10)
    on_task_fail(t_id, db); db.commit()
    pending = db.query(Task).filter(
        Task.account_id == a_id, Task.status == "pending",
    ).first()
    # 새 retry task 는 max_retries=정책값(1) 으로 생성됨
    assert pending.max_retries == 1
