"""Phase 3 — Admin Screen Review API + ScreenResolution 모델 검증."""
from datetime import UTC, datetime
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hydra.db.models import Base, WorkerError, ScreenResolution, Worker


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    # 워커 1개 + UNKNOWN 에러 3개 시드
    w = Worker(id=1, name="pc-01", status="online", current_version="v1",
               last_heartbeat=datetime.now(UTC))
    s.add(w)
    s.flush()
    for i, st in enumerate(("post_password_unknown", "trust_device_prompt", "post_password_unknown")):
        s.add(WorkerError(
            worker_id=1, kind="unknown_screen",
            message=f"UNKNOWN_SCREEN state={st}",
            occurred_at=datetime.now(UTC),
            received_at=datetime.now(UTC),
            screen_state=st, failure_taxonomy="page_variant",
            captured_url=f"https://accounts.google.com/x{i}",
            captured_title=f"Test {i}",
        ))
    s.commit()
    yield s
    s.close()
    engine.dispose()


def test_screen_resolution_model_columns():
    cols = {c.name for c in ScreenResolution.__table__.columns}
    expected = {
        "id", "screen_state", "url_pattern", "title_pattern", "dom_signature",
        "resolution_type", "action_config", "source_error_id", "created_by_user_id",
        "approved", "hit_count", "last_hit_at", "created_at", "notes",
    }
    assert expected.issubset(cols)


def test_worker_error_unknown_screen_filterable(db):
    """worker_errors 에 screen_state/failure_taxonomy 가 정확히 저장."""
    rows = db.query(WorkerError).filter(WorkerError.kind == "unknown_screen").all()
    assert len(rows) == 3
    states = {r.screen_state for r in rows}
    assert "post_password_unknown" in states
    assert "trust_device_prompt" in states


def test_screen_resolution_insert(db):
    """ScreenResolution 직접 insert + query 동작."""
    res = ScreenResolution(
        screen_state="trust_device_prompt",
        resolution_type="auto_click_skip",
        action_config=json.dumps({"selector": "button:has-text('나중에')"}),
        approved=True,
    )
    db.add(res)
    db.commit()
    fetched = db.query(ScreenResolution).first()
    assert fetched.screen_state == "trust_device_prompt"
    assert fetched.approved is True
    assert json.loads(fetched.action_config)["selector"] == "button:has-text('나중에')"


def test_resolution_links_to_source_error(db):
    """source_error_id FK 가 worker_errors.id 와 연결."""
    err = db.query(WorkerError).filter(WorkerError.kind == "unknown_screen").first()
    res = ScreenResolution(
        screen_state="x",
        resolution_type="fail_task",
        source_error_id=err.id,
    )
    db.add(res)
    db.commit()
    fetched = db.query(ScreenResolution).first()
    assert fetched.source_error_id == err.id


def test_valid_resolution_types():
    """API에서 허용하는 5종 타입 검증 (admin_screen_review.py 와 sync)."""
    valid = {
        "auto_click_skip", "auto_enter_code", "escalate_manual",
        "fail_task", "retry_after_cooldown",
    }
    # 임포트 검증 — 모듈이 잘못된 enum 안 만들었는지
    from hydra.web.routes.admin_screen_review import LabelRequest
    # Pydantic 이라 직접 모델 instantiate 만으로 valid_types 검증은 안 됨.
    # 라우터 핸들러에 내장된 valid_types 셋이 우리 의도와 같은지는 핸들러 코드 검증
    import hydra.web.routes.admin_screen_review as mod
    import inspect
    src = inspect.getsource(mod.label_unknown_screen)
    for t in valid:
        assert t in src


def test_admin_screen_review_router_registered():
    """app.py 에 admin_screen_review router 가 include 됐는지."""
    from hydra.web.app import app
    paths = [r.path for r in app.routes]
    # /api/admin/screen-review/list, /label, /resolutions 가 등록되어야
    assert any("/screen-review/list" in p for p in paths)
    assert any("/screen-review/resolutions" in p for p in paths)
