"""ExecutionLog 모델 기본 동작 검증."""
import json
from datetime import datetime, UTC

from hydra.db.models import ExecutionLog


def test_create_execution_log_minimal(db_session):
    """task/worker/account 전부 NULL 로도 생성 가능 (부트스트랩/초기 로그용)."""
    log = ExecutionLog(
        timestamp=datetime.now(UTC),
        level="INFO",
        message="startup ok",
    )
    db_session.add(log)
    db_session.commit()
    assert log.id is not None


def test_create_execution_log_with_context_and_screenshot(db_session):
    log = ExecutionLog(
        task_id=None, worker_id=None, account_id=None,
        timestamp=datetime.now(UTC),
        level="ERROR",
        message="goal apply failed",
        context=json.dumps({"goal": "channel_profile", "url": "https://..."}),
        screenshot_url="https://example/shot.png",
    )
    db_session.add(log)
    db_session.commit()
    loaded = db_session.query(ExecutionLog).filter_by(id=log.id).first()
    parsed_ctx = json.loads(loaded.context)
    assert parsed_ctx["goal"] == "channel_profile"
    assert loaded.screenshot_url.endswith("shot.png")


def test_execution_log_levels(db_session):
    for lv in ("DEBUG", "INFO", "WARN", "ERROR"):
        db_session.add(ExecutionLog(
            timestamp=datetime.now(UTC), level=lv, message=f"{lv} msg"
        ))
    db_session.commit()
    cnt_error = db_session.query(ExecutionLog).filter_by(level="ERROR").count()
    assert cnt_error == 1


def test_execution_log_indexes_exist(db_session):
    """worker_id+timestamp 컬럼 인덱스 필터 쿼리 동작 확인."""
    now = datetime.now(UTC)
    for i in range(5):
        db_session.add(ExecutionLog(
            worker_id=1, timestamp=now, level="INFO", message=f"test{i}"
        ))
    db_session.commit()
    rows = db_session.query(ExecutionLog).filter_by(worker_id=1).all()
    assert len(rows) == 5
