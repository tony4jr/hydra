# M1 Golden Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 운영자가 `/accounts` 등록 폼에서 계정 1개를 넣으면 자동으로 온보딩 → 워밍업(3 step 축소) → active → 스텁 캠페인의 comment/like 태스크까지 워커가 수동 개입 없이 완주하는 파이프라인 확립.

**Architecture:** 서버 사이드 상태 전이 엔진을 신설 (hook + scheduler 백업). 기존 `worker/executor.py` 의 단계별 핸들러는 재활용하되 v2 API + `AccountSnapshot` 페이로드로만 동작하도록 재배선. 새 DB 스키마 없음.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy (PG on VPS, sqlite in-memory for tests) / Alembic (no new migration) / TanStack Router + shadcn/ui / pytest + TestClient

**참조 Spec:** [`../specs/2026-04-23-m1-golden-path-design.md`](../specs/2026-04-23-m1-golden-path-design.md)

---

## File Structure

### 신규 서버 모듈
- `hydra/core/orchestrator.py` — 상태 전이 + 다음 태스크 enqueue + 실패/suspend + sweep
- `hydra/core/campaign_stub.py` — active 계정에 하드코딩 프리셋 적용
- `hydra/web/routes/admin_accounts.py` — `POST /api/admin/accounts/register`

### 서버 수정
- `hydra/web/routes/tasks_api.py` — complete/fail 훅 추가
- `hydra/services/background.py` — 30초 tick 에 sweep/scan
- `hydra/web/app.py` — `/api/generate-comment` 을 admin 에서 worker 로 재마운트

### 워커 수정
- `worker/client.py` — heartbeat/fetch/complete/fail 을 v2 경로로
- `worker/app.py` — heartbeat 응답 반응 + `_current_task_id`
- `worker/executor.py` — `SessionLocal` 제거, `AccountSnapshot` 사용

### 프론트
- `frontend/src/features/accounts/account-register-dialog.tsx` — 수동 등록 폼
- `frontend/src/features/accounts/index.tsx` (또는 기존 페이지) — 버튼 추가

### 테스트
- `tests/test_orchestrator.py`
- `tests/test_campaign_stub.py`
- `tests/test_admin_accounts_register.py`
- `tests/test_m1_e2e_integration.py` — 가짜 워커로 end-to-end 루프

---

## 진행 방침

- 각 task 후 바로 commit
- TDD — 실패 테스트 먼저, 최소 구현, 통과
- 기존 318+ pytest 회귀 보호 (매 커밋 후 `pytest -q` 간단 확인)
- 이 플랜의 태스크 번호는 **M1-N** (Phase 1 플랜과 혼동 방지)

---

## Task M1-1: Orchestrator 기본 구조 + registered → warmup(1)

**Files:**
- Create: `hydra/core/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_orchestrator.py`:
```python
"""Task M1-1~M1-5: 상태 전이 엔진."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hydra.core.orchestrator import on_task_complete
from hydra.db.models import Account, Base, Task


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = S()
    yield s
    s.close()
    engine.dispose()


def test_onboarding_complete_promotes_to_warmup_day1(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="registered",
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="onboarding_verify",
        status="done", completed_at=datetime.now(UTC),
    )
    session.add(t)
    session.flush()

    on_task_complete(t.id, session)

    session.refresh(acc)
    assert acc.status == "warmup"
    assert acc.warmup_day == 1
    assert acc.onboard_completed_at is not None

    # 다음 태스크 (warmup) 가 큐에 있어야 함
    queued = session.query(Task).filter_by(
        account_id=acc.id, task_type="warmup", status="pending",
    ).first()
    assert queued is not None
```

- [ ] **Step 2: 실행 → FAIL**

```bash
.venv/bin/pytest tests/test_orchestrator.py::test_onboarding_complete_promotes_to_warmup_day1 -v
```
Expected: `ImportError: cannot import name 'on_task_complete'`

- [ ] **Step 3: 최소 구현**

`hydra/core/orchestrator.py`:
```python
"""M1 상태 전이 엔진 (Task M1-1~M1-5).

task 완료/실패 시 account 상태를 전이시키고 다음 단계 태스크를 큐에 넣는다.
같은 세션에서 호출되어 하나의 트랜잭션으로 원자성 보장.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from hydra.db.models import Account, Task


def on_task_complete(task_id: int, session: Session) -> None:
    """task가 done 으로 커밋되기 직전에 호출. 같은 세션 공유."""
    task = session.get(Task, task_id)
    if task is None or task.account_id is None:
        return
    account = session.get(Account, task.account_id)
    if account is None:
        return

    if task.task_type == "onboarding_verify" and account.status == "registered":
        account.status = "warmup"
        account.warmup_day = 1
        account.onboard_completed_at = datetime.now(UTC)
        session.add(Task(
            account_id=account.id,
            task_type="warmup",
            status="pending",
            priority="normal",
        ))
```

- [ ] **Step 4: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_orchestrator.py::test_onboarding_complete_promotes_to_warmup_day1 -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/core/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): M1-1 registered → warmup(day1) 전이"
```

---

## Task M1-2: warmup day 진행 + 졸업

**Files:**
- Modify: `hydra/core/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_orchestrator.py` 끝에 추가:
```python
def test_warmup_day1_complete_advances_to_day2(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=1,
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="warmup",
        status="done", completed_at=datetime.now(UTC),
    )
    session.add(t)
    session.flush()

    on_task_complete(t.id, session)

    session.refresh(acc)
    assert acc.warmup_day == 2
    assert acc.status == "warmup"
    nxt = session.query(Task).filter_by(
        account_id=acc.id, task_type="warmup", status="pending",
    ).first()
    assert nxt is not None


def test_warmup_day3_complete_promotes_to_active(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=3,
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="warmup",
        status="done", completed_at=datetime.now(UTC),
    )
    session.add(t)
    session.flush()

    on_task_complete(t.id, session)

    session.refresh(acc)
    assert acc.status == "active"
    assert acc.warmup_day == 4
    # 졸업 후엔 자동 warmup task 더 안 생김 (campaign_stub 담당)
    pending_warmup = session.query(Task).filter_by(
        account_id=acc.id, task_type="warmup", status="pending",
    ).count()
    assert pending_warmup == 0
```

- [ ] **Step 2: 실행 → FAIL**

```bash
.venv/bin/pytest tests/test_orchestrator.py -v -k "warmup"
```

- [ ] **Step 3: orchestrator 확장**

`hydra/core/orchestrator.py` 의 `on_task_complete` 본문에 추가:
```python
    if task.task_type == "warmup" and account.status == "warmup":
        if account.warmup_day < 3:
            account.warmup_day += 1
            session.add(Task(
                account_id=account.id,
                task_type="warmup",
                status="pending",
                priority="normal",
            ))
        else:
            # day 3 → active 졸업
            account.warmup_day = 4
            account.status = "active"
```

- [ ] **Step 4: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_orchestrator.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/core/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): M1-2 warmup day 진행 + active 졸업"
```

---

## Task M1-3: Task 실패 → retry_count / suspended

**Files:**
- Modify: `hydra/core/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_orchestrator.py`:
```python
from hydra.core.orchestrator import on_task_fail


def test_task_fail_below_threshold_re_enqueues(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=1,
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="warmup",
        status="failed", retry_count=1, max_retries=3,
    )
    session.add(t)
    session.flush()

    on_task_fail(t.id, session)

    session.refresh(acc)
    assert acc.status == "warmup"  # 유지
    nxt = session.query(Task).filter_by(
        account_id=acc.id, task_type="warmup", status="pending",
    ).first()
    assert nxt is not None
    assert nxt.retry_count == 2  # 증가된 값으로 새 태스크


def test_task_fail_at_max_retries_suspends_account(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=1,
    )
    session.add(acc)
    session.flush()
    t = Task(
        account_id=acc.id, task_type="warmup",
        status="failed", retry_count=3, max_retries=3,
    )
    session.add(t)
    session.flush()

    on_task_fail(t.id, session)

    session.refresh(acc)
    assert acc.status == "suspended"
    # 재시도 안 함
    pending = session.query(Task).filter_by(
        account_id=acc.id, status="pending",
    ).count()
    assert pending == 0
```

- [ ] **Step 2: 실행 → FAIL**

```bash
.venv/bin/pytest tests/test_orchestrator.py -v -k "fail"
```

- [ ] **Step 3: on_task_fail 구현**

`hydra/core/orchestrator.py` 끝에 추가:
```python
def on_task_fail(task_id: int, session: Session) -> None:
    """task가 failed 로 커밋되기 직전 호출. 같은 세션 공유."""
    task = session.get(Task, task_id)
    if task is None or task.account_id is None:
        return
    account = session.get(Account, task.account_id)
    if account is None:
        return

    if task.retry_count >= (task.max_retries or 3):
        account.status = "suspended"
        return

    # 재시도: 같은 task_type 으로 새 태스크 (retry_count + 1)
    session.add(Task(
        account_id=account.id,
        task_type=task.task_type,
        status="pending",
        priority=task.priority,
        retry_count=task.retry_count + 1,
        max_retries=task.max_retries,
    ))
```

- [ ] **Step 4: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_orchestrator.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/core/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): M1-3 task 실패 retry + suspend"
```

---

## Task M1-4: sweep_stuck_accounts (백업 스케줄러 감지)

**Files:**
- Modify: `hydra/core/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_orchestrator.py`:
```python
from hydra.core.orchestrator import sweep_stuck_accounts


def test_sweep_detects_warmup_without_pending_task_and_reenqueues(session):
    """warmup 중인데 pending 태스크가 없으면 재enqueue."""
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=2,
    )
    session.add(acc)
    session.commit()

    count = sweep_stuck_accounts(session)
    assert count == 1

    nxt = session.query(Task).filter_by(
        account_id=acc.id, task_type="warmup", status="pending",
    ).first()
    assert nxt is not None


def test_sweep_ignores_accounts_with_pending_task(session):
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="warmup", warmup_day=1,
    )
    session.add(acc)
    session.flush()
    session.add(Task(
        account_id=acc.id, task_type="warmup", status="pending",
    ))
    session.commit()

    count = sweep_stuck_accounts(session)
    assert count == 0


def test_sweep_ignores_active_and_suspended(session):
    session.add_all([
        Account(gmail="a@x.com", password="x", adspower_profile_id="p1",
                status="active", warmup_day=4),
        Account(gmail="b@x.com", password="x", adspower_profile_id="p2",
                status="suspended"),
        Account(gmail="c@x.com", password="x", adspower_profile_id="p3",
                status="retired"),
    ])
    session.commit()

    assert sweep_stuck_accounts(session) == 0
```

- [ ] **Step 2: 실행 → FAIL**

```bash
.venv/bin/pytest tests/test_orchestrator.py -v -k "sweep"
```

- [ ] **Step 3: 구현**

`hydra/core/orchestrator.py` 끝에 추가:
```python
_ACTIVE_STATUSES = ("registered", "warmup")


def sweep_stuck_accounts(session: Session) -> int:
    """진행 중인 account 중 next task 가 없는 것 감지 + 재enqueue.

    Returns: 복구한 account 수.
    """
    candidates = (
        session.query(Account)
        .filter(Account.status.in_(_ACTIVE_STATUSES))
        .all()
    )
    recovered = 0
    for acc in candidates:
        has_pending = (
            session.query(Task)
            .filter_by(account_id=acc.id, status="pending")
            .first()
            is not None
        )
        has_running = (
            session.query(Task)
            .filter_by(account_id=acc.id, status="running")
            .first()
            is not None
        )
        if has_pending or has_running:
            continue
        # 현재 상태에 맞는 태스크 재생성
        if acc.status == "registered":
            tt = "onboarding_verify"
        else:  # warmup
            tt = "warmup"
        session.add(Task(
            account_id=acc.id, task_type=tt,
            status="pending", priority="normal",
        ))
        recovered += 1
    if recovered:
        session.commit()
    return recovered
```

- [ ] **Step 4: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_orchestrator.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/core/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): M1-4 sweep_stuck_accounts 누수 복구"
```

---

## Task M1-5: campaign_stub — active 계정에 프리셋 적용

**Files:**
- Create: `hydra/core/campaign_stub.py`
- Test: `tests/test_campaign_stub.py`

- [ ] **Step 1: 실패 테스트**

`tests/test_campaign_stub.py`:
```python
"""Task M1-5: 스텁 캠페인 — active 계정에 comment/like 태스크 1회씩 생성."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hydra.core.campaign_stub import scan_active_accounts
from hydra.db.models import Account, Base, Task


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    s = S()
    yield s
    s.close()
    engine.dispose()


def test_scan_generates_comment_and_like_for_active(session, monkeypatch):
    monkeypatch.setenv("M1_TEST_VIDEO_ID", "dQw4w9WgXcQ")
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="active", warmup_day=4,
    )
    session.add(acc)
    session.commit()

    count = scan_active_accounts(session)
    assert count == 1

    tasks = session.query(Task).filter_by(account_id=acc.id).all()
    types = sorted(t.task_type for t in tasks)
    assert types == ["comment", "like"]


def test_scan_skips_account_already_processed(session, monkeypatch):
    monkeypatch.setenv("M1_TEST_VIDEO_ID", "dQw4w9WgXcQ")
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="active", warmup_day=4,
    )
    session.add(acc)
    session.flush()
    # 이미 comment/like 태스크가 있다면 (status 무관) skip
    session.add(Task(account_id=acc.id, task_type="comment", status="done"))
    session.commit()

    assert scan_active_accounts(session) == 0


def test_scan_skips_non_active(session, monkeypatch):
    monkeypatch.setenv("M1_TEST_VIDEO_ID", "dQw4w9WgXcQ")
    session.add_all([
        Account(gmail="a@x.com", password="x", adspower_profile_id="p1",
                status="warmup", warmup_day=2),
        Account(gmail="b@x.com", password="x", adspower_profile_id="p2",
                status="suspended"),
    ])
    session.commit()

    assert scan_active_accounts(session) == 0


def test_scan_raises_without_video_id(session, monkeypatch):
    monkeypatch.delenv("M1_TEST_VIDEO_ID", raising=False)
    acc = Account(
        gmail="a@x.com", password="x",
        adspower_profile_id="p1", status="active", warmup_day=4,
    )
    session.add(acc)
    session.commit()

    # 영상 ID 없으면 skip (에러 대신 0 반환)
    assert scan_active_accounts(session) == 0
```

- [ ] **Step 2: 실행 → FAIL**

```bash
.venv/bin/pytest tests/test_campaign_stub.py -v
```

- [ ] **Step 3: 구현**

`hydra/core/campaign_stub.py`:
```python
"""M1 Task M1-5: 스텁 캠페인.

env M1_TEST_VIDEO_ID 에 설정된 영상 1개에 대해,
active 상태이지만 아직 처리 안 된 계정에 comment/like 태스크 1회씩 생성.
"""
from __future__ import annotations

import json
import os

from sqlalchemy.orm import Session

from hydra.db.models import Account, Task


def _target_video_id() -> str | None:
    return os.getenv("M1_TEST_VIDEO_ID", "").strip() or None


def scan_active_accounts(session: Session) -> int:
    """active 계정 중 이번 스텁 캠페인 미처리 건 대상으로 comment/like 태스크 생성.

    Returns: 처리한 account 수.
    """
    video_id = _target_video_id()
    if not video_id:
        return 0

    actives = (
        session.query(Account)
        .filter(Account.status == "active")
        .all()
    )
    processed = 0
    for acc in actives:
        existing = (
            session.query(Task)
            .filter(
                Task.account_id == acc.id,
                Task.task_type.in_(("comment", "like")),
            )
            .first()
        )
        if existing is not None:
            continue  # 이미 한 번 처리됨

        payload_base = {"video_id": video_id, "m1_stub": True}
        session.add_all([
            Task(
                account_id=acc.id,
                task_type="comment",
                status="pending",
                priority="normal",
                payload=json.dumps({**payload_base, "ai_generated": True}),
            ),
            Task(
                account_id=acc.id,
                task_type="like",
                status="pending",
                priority="normal",
                payload=json.dumps(payload_base),
            ),
        ])
        processed += 1
    if processed:
        session.commit()
    return processed
```

- [ ] **Step 4: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_campaign_stub.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/core/campaign_stub.py tests/test_campaign_stub.py
git commit -m "feat(campaign-stub): M1-5 active 계정에 프리셋 comment/like 태스크"
```

---

## Task M1-6: `/api/admin/accounts/register` 엔드포인트

**Files:**
- Create: `hydra/web/routes/admin_accounts.py`
- Modify: `hydra/web/app.py` (router 등록)
- Test: `tests/test_admin_accounts_register.py`

- [ ] **Step 1: 실패 테스트**

`tests/test_admin_accounts_register.py`:
```python
"""Task M1-6: POST /api/admin/accounts/register."""
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import Account, Base, Task


@pytest.fixture
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    token = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {"client": client, "token": token, "session": TestSession}
    engine.dispose()


def _hdr(env):
    return {"Authorization": f"Bearer {env['token']}"}


def test_register_requires_auth(env):
    r = env["client"].post("/api/admin/accounts/register", json={
        "gmail": "a@x.com", "password": "p", "adspower_profile_id": "p1",
    })
    assert r.status_code == 401


def test_register_creates_account_and_enqueues_onboarding(env):
    r = env["client"].post(
        "/api/admin/accounts/register",
        headers=_hdr(env),
        json={
            "gmail": "new@x.com",
            "password": "Plain!Pass123",
            "adspower_profile_id": "prof-new",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] >= 1

    db = env["session"]()
    acc = db.get(Account, body["account_id"])
    assert acc.gmail == "new@x.com"
    assert acc.status == "registered"
    # 평문 비밀번호가 그대로 DB 에 저장되면 안 됨 — 암호화 확인
    assert acc.password != "Plain!Pass123"

    tasks = db.query(Task).filter_by(account_id=acc.id).all()
    assert len(tasks) == 1
    assert tasks[0].task_type == "onboarding_verify"
    assert tasks[0].status == "pending"
    db.close()


def test_register_duplicate_gmail_409(env):
    env["client"].post(
        "/api/admin/accounts/register",
        headers=_hdr(env),
        json={"gmail": "dup@x.com", "password": "p", "adspower_profile_id": "p1"},
    )
    r = env["client"].post(
        "/api/admin/accounts/register",
        headers=_hdr(env),
        json={"gmail": "dup@x.com", "password": "p2", "adspower_profile_id": "p2"},
    )
    assert r.status_code == 409
```

- [ ] **Step 2: 실행 → FAIL**

```bash
.venv/bin/pytest tests/test_admin_accounts_register.py -v
```

- [ ] **Step 3: admin_accounts 라우터 생성**

`hydra/web/routes/admin_accounts.py`:
```python
"""Task M1-6: 어드민 수동 계정 등록.

향후 실제 계정 자동 생성 로직이 들어오면 동일 파이프라인 트리거를 위해
같은 함수를 내부 호출하도록 설계.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hydra.core import crypto
from hydra.db import session as _db_session
from hydra.db.models import Account, Task
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()


class AccountRegisterRequest(BaseModel):
    gmail: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)
    adspower_profile_id: str = Field(..., min_length=1)
    recovery_email: str | None = None
    phone_number: str | None = None


@router.post("/register")
def register_account(
    req: AccountRegisterRequest,
    _session: dict = Depends(admin_session),
) -> dict:
    db = _db_session.SessionLocal()
    try:
        if db.query(Account).filter_by(gmail=req.gmail).first():
            raise HTTPException(409, f"gmail already exists: {req.gmail}")
        if db.query(Account).filter_by(
            adspower_profile_id=req.adspower_profile_id
        ).first():
            raise HTTPException(
                409, f"adspower_profile_id in use: {req.adspower_profile_id}",
            )

        acc = Account(
            gmail=req.gmail,
            password=crypto.encrypt(req.password),
            adspower_profile_id=req.adspower_profile_id,
            recovery_email=req.recovery_email,
            phone_number=req.phone_number,
            status="registered",
        )
        db.add(acc)
        db.flush()

        db.add(Task(
            account_id=acc.id,
            task_type="onboarding_verify",
            status="pending",
            priority="normal",
        ))
        db.commit()
        return {"account_id": acc.id, "status": acc.status}
    finally:
        db.close()
```

- [ ] **Step 4: app.py 에 라우터 등록**

`hydra/web/app.py` 의 admin_audit 라우터 등록 줄 **바로 다음** 에 추가:
```python
from hydra.web.routes import admin_accounts  # 상단 import 에 추가 필요

app.include_router(admin_accounts.router, prefix="/api/admin/accounts",
                   tags=["admin-accounts"], dependencies=_ADMIN_DEPS)
```

상단 import 블록 수정:
```python
from hydra.web.routes import (
    admin_auth, admin_workers, admin_avatars, admin_deploy, admin_audit,
    admin_accounts,
    avatar_serving, worker_api, tasks_api,
)
```

- [ ] **Step 5: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_admin_accounts_register.py -v
```

- [ ] **Step 6: Commit**

```bash
git add hydra/web/routes/admin_accounts.py hydra/web/app.py \
        tests/test_admin_accounts_register.py
git commit -m "feat(admin): M1-6 POST /api/admin/accounts/register + onboarding enqueue"
```

---

## Task M1-7: tasks_api complete/fail 에 orchestrator 훅 삽입

**Files:**
- Modify: `hydra/web/routes/tasks_api.py`
- Modify: `tests/test_tasks_v2.py` (회귀 보호)
- Test: 새 통합 케이스는 Task M1-12 에서 다룸

- [ ] **Step 1: 수정**

`hydra/web/routes/tasks_api.py` 의 `complete` 함수 — `db.commit()` **직전**에 훅 추가:

기존 코드:
```python
        t.status = "done"
        t.completed_at = datetime.now(UTC)
        t.result = req.result
        _release_lock(db, t.id)
        db.commit()
```

변경:
```python
        t.status = "done"
        t.completed_at = datetime.now(UTC)
        t.result = req.result
        _release_lock(db, t.id)
        # M1-7: 상태 전이 훅 — 같은 트랜잭션에서
        from hydra.core.orchestrator import on_task_complete
        on_task_complete(t.id, db)
        db.commit()
```

`fail` 함수 — `db.commit()` 직전:

기존:
```python
        t.status = "failed"
        t.completed_at = datetime.now(UTC)
        t.error_message = req.error
        _release_lock(db, t.id)
        db.commit()
```

변경:
```python
        t.status = "failed"
        t.completed_at = datetime.now(UTC)
        t.error_message = req.error
        _release_lock(db, t.id)
        # M1-7: 실패 전이 훅
        from hydra.core.orchestrator import on_task_fail
        on_task_fail(t.id, db)
        db.commit()
```

- [ ] **Step 2: 회귀 실행**

기존 tests/test_tasks_v2.py 가 전부 통과해야 함:
```bash
.venv/bin/pytest tests/test_tasks_v2.py -v
```
Expected: all PASS (훅이 기존 동작 안 깸 — pending 태스크 없는 account 면 no-op)

- [ ] **Step 3: 통합 테스트 추가**

`tests/test_tasks_v2.py` 에 추가:
```python
def test_complete_onboarding_auto_enqueues_warmup(env):
    """M1-7: complete 훅이 orchestrator 전이 유발."""
    from hydra.db.models import Account, Task
    from datetime import UTC, datetime

    # 기존 pending account 지우고 새 시나리오 셋업
    db = env["session"]()
    db.query(Task).delete()
    db.query(Account).delete()
    acc = Account(
        gmail="onb@x.com", password="x",
        adspower_profile_id="p-onb", status="registered",
    )
    db.add(acc); db.flush()
    db.add(Task(
        account_id=acc.id, task_type="onboarding_verify",
        status="pending", priority="normal",
    ))
    db.commit()
    acc_id = acc.id
    db.close()

    # 워커가 fetch 해서 running 으로 만들기
    fetch_resp = env["client"].post(
        "/api/tasks/v2/fetch",
        headers={"X-Worker-Token": env["worker_token"]},
    )
    fetched = fetch_resp.json()["tasks"][0]
    tid = fetched["id"]

    # complete 호출
    r = env["client"].post(
        "/api/tasks/v2/complete",
        headers={"X-Worker-Token": env["worker_token"]},
        json={"task_id": tid},
    )
    assert r.status_code == 200

    # orchestrator 훅 동작 확인
    db = env["session"]()
    acc = db.get(Account, acc_id)
    assert acc.status == "warmup"
    assert acc.warmup_day == 1
    warmup_task = db.query(Task).filter_by(
        account_id=acc_id, task_type="warmup", status="pending",
    ).first()
    assert warmup_task is not None
    db.close()
```

- [ ] **Step 4: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_tasks_v2.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/web/routes/tasks_api.py tests/test_tasks_v2.py
git commit -m "feat(tasks-api): M1-7 complete/fail 에 orchestrator 훅 삽입"
```

---

## Task M1-8: background scheduler 에 sweep/scan 연동

**Files:**
- Modify: `hydra/services/background.py`
- Test: `tests/test_m1_background_tick.py`

- [ ] **Step 1: 기존 scheduler 구조 확인**

```bash
cat hydra/services/background.py | head -60
```
(기존 스케줄러가 어떤 방식 — loop + sleep? APScheduler? — 인지 맞춰 통합)

- [ ] **Step 2: 실패 테스트 작성**

`tests/test_m1_background_tick.py`:
```python
"""Task M1-8: background scheduler 가 orchestrator.sweep + campaign_stub.scan 호출."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import Account, Base, Task
from hydra.services.background import m1_tick


@pytest.fixture
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)
    monkeypatch.setenv("M1_TEST_VIDEO_ID", "dQw4w9WgXcQ")
    yield TestSession
    engine.dispose()


def test_tick_sweeps_and_scans(env):
    # 1) stuck warmup account (sweep 대상)
    # 2) active account 이번 스텁 미처리 (scan 대상)
    s = env()
    stuck = Account(
        gmail="stuck@x.com", password="x", adspower_profile_id="p1",
        status="warmup", warmup_day=2,
    )
    active = Account(
        gmail="act@x.com", password="x", adspower_profile_id="p2",
        status="active", warmup_day=4,
    )
    s.add_all([stuck, active])
    s.commit()
    stuck_id = stuck.id
    active_id = active.id
    s.close()

    result = m1_tick()
    assert result["swept"] == 1
    assert result["scanned"] == 1

    s = env()
    # stuck 에 warmup 태스크 생겼어야
    assert s.query(Task).filter_by(
        account_id=stuck_id, task_type="warmup", status="pending",
    ).count() == 1
    # active 에 comment + like 태스크
    assert s.query(Task).filter_by(
        account_id=active_id, task_type="comment",
    ).count() == 1
    assert s.query(Task).filter_by(
        account_id=active_id, task_type="like",
    ).count() == 1
    s.close()
```

- [ ] **Step 3: 실행 → FAIL**

```bash
.venv/bin/pytest tests/test_m1_background_tick.py -v
```

- [ ] **Step 4: background.py 에 m1_tick 추가**

`hydra/services/background.py` 끝에 추가 (기존 코드는 그대로):
```python
def m1_tick() -> dict:
    """M1-8: orchestrator.sweep_stuck_accounts + campaign_stub.scan_active_accounts.

    기존 scheduler 의 주기 tick 에서 호출. 독립 함수라 테스트 용이.
    """
    from hydra.core.orchestrator import sweep_stuck_accounts
    from hydra.core.campaign_stub import scan_active_accounts
    from hydra.db import session as _s

    db = _s.SessionLocal()
    try:
        swept = sweep_stuck_accounts(db)
        scanned = scan_active_accounts(db)
        return {"swept": swept, "scanned": scanned}
    finally:
        db.close()
```

기존 `scheduler.start()` 루프 안에 30초마다 `m1_tick()` 호출 추가 — 기존 코드 구조 보고 적절한 위치에 끼워 넣기. 가이드:
- 기존에 `while not stopped: ... await asyncio.sleep(N)` 형태면 동일 루프에 추가.
- `m1_tick()` 은 동기 함수이므로 비동기 컨텍스트에서 `asyncio.to_thread(m1_tick)` 로 감싸서 호출.

예시:
```python
# scheduler.start() 루프 안
import time
_last_m1_tick = 0.0
while not self._stopped:
    now = time.time()
    if now - _last_m1_tick >= 30:
        try:
            await asyncio.to_thread(m1_tick)
        except Exception as e:
            log.exception("m1_tick failed: %s", e)
        _last_m1_tick = now
    await asyncio.sleep(1)
```

- [ ] **Step 5: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_m1_background_tick.py -v
```

- [ ] **Step 6: Commit**

```bash
git add hydra/services/background.py tests/test_m1_background_tick.py
git commit -m "feat(scheduler): M1-8 m1_tick (sweep + campaign scan) 30초 주기"
```

---

## Task M1-9: AI 엔드포인트 `/api/generate-comment` 을 worker_auth 로 재마운트

**Files:**
- Modify: `hydra/api/ai.py`
- Modify: `hydra/web/app.py`
- Test: `tests/test_ai_worker_auth.py`

- [ ] **Step 1: 현재 구조 확인**

```bash
grep -n "generate-comment\|router\s*=\|Depends" hydra/api/ai.py | head -20
```

- [ ] **Step 2: 실패 테스트**

`tests/test_ai_worker_auth.py`:
```python
"""M1-9: /api/generate-comment 이 admin_session 이 아닌 worker_auth 로 작동."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.core.enrollment import generate_enrollment_token
from hydra.db.models import Base


@pytest.fixture
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)
    monkeypatch.setenv("ENROLLMENT_SECRET", "test-enroll-12345")
    monkeypatch.setenv("SERVER_URL", "https://test.example.com")

    from hydra.web.app import app
    client = TestClient(app)
    et = generate_enrollment_token("wk", ttl_hours=1)
    wt = client.post(
        "/api/workers/enroll",
        json={"enrollment_token": et, "hostname": "wk"},
    ).json()["worker_token"]
    yield {"client": client, "wt": wt}
    engine.dispose()


def test_generate_comment_requires_worker_token(env):
    r = env["client"].post("/api/generate-comment", json={"video_id": "x"})
    assert r.status_code == 401


def test_generate_comment_accepts_worker_token(env):
    # 실 AI 호출은 외부이므로 200 or 500 가능, 핵심은 401 아닌 것
    r = env["client"].post(
        "/api/generate-comment",
        headers={"X-Worker-Token": env["wt"]},
        json={"video_id": "x"},
    )
    assert r.status_code != 401


def test_generate_comment_rejects_admin_jwt(env):
    """과거 admin 세션 뒤에 있었던 흔적이 없도록 — admin JWT 로는 이제 통과 안 됨."""
    from datetime import UTC, datetime, timedelta
    import jwt as _jwt
    import os
    os.environ["JWT_SECRET"] = "test-jwt-secret"
    now = datetime.now(UTC)
    token = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret", algorithm="HS256",
    )
    r = env["client"].post(
        "/api/generate-comment",
        headers={"Authorization": f"Bearer {token}"},
        json={"video_id": "x"},
    )
    assert r.status_code == 401
```

- [ ] **Step 3: 실행 → FAIL** (현재는 admin_session 이라 admin JWT 가 통과)

```bash
.venv/bin/pytest tests/test_ai_worker_auth.py -v
```

- [ ] **Step 4: ai.py 에 worker_auth Depends 추가**

`hydra/api/ai.py` — `generate-comment` 라우트 핸들러 시그니처에 추가:
```python
from hydra.web.routes.worker_api import worker_auth
from hydra.db.models import Worker

@router.post("/generate-comment")
def generate_comment(
    body: ...,
    _worker: Worker = Depends(worker_auth),
    ...
):
    ...
```

- [ ] **Step 5: app.py 에서 ai_router 의 admin 의존성 제거**

`hydra/web/app.py`:
```python
# Before: app.include_router(ai_router, dependencies=_ADMIN_DEPS)
# After:
app.include_router(ai_router)  # 개별 라우트가 worker_auth 로 보호
```

- [ ] **Step 6: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_ai_worker_auth.py -v
```

- [ ] **Step 7: Commit**

```bash
git add hydra/api/ai.py hydra/web/app.py tests/test_ai_worker_auth.py
git commit -m "security: M1-9 /api/generate-comment 을 worker_auth 로 보호 (admin 제거)"
```

---

## Task M1-10: worker/client.py v2 API 전환

**Files:**
- Modify: `worker/client.py`
- Modify: `tests/test_worker_client.py`

- [ ] **Step 1: 기존 client 확인**

```bash
cat worker/client.py
```
(현재 어떤 경로 쓰는지 — `/api/workers/heartbeat` `/api/tasks/fetch` 등 — 확인)

- [ ] **Step 2: 테스트 수정**

`tests/test_worker_client.py` 에 추가 (기존 테스트는 유지하되 신규 v2 케이스 별도 추가):
```python
def test_client_heartbeat_calls_v2_endpoint(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt-123")
    from worker.config import WorkerConfig
    import worker.config as cfg_module
    import worker.client as client_module
    new_cfg = WorkerConfig()
    monkeypatch.setattr(cfg_module, "config", new_cfg)
    monkeypatch.setattr(client_module, "config", new_cfg)
    from worker.client import ServerClient

    calls = []

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "current_version": "v1", "paused": False,
                "canary_worker_ids": [], "restart_requested": False,
                "worker_config": {"poll_interval_sec": 15},
            }
        def raise_for_status(self):
            pass

    class FakeHttp:
        def post(self, url, **kw):
            calls.append(url)
            return FakeResp()
        def close(self):
            pass

    client = ServerClient()
    client.http = FakeHttp()
    result = client.heartbeat()

    assert any("/api/workers/heartbeat/v2" in u for u in calls)
    assert result["current_version"] == "v1"
    client.close()


def test_client_fetch_tasks_calls_v2_endpoint(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt-123")
    from worker.config import WorkerConfig
    import worker.config as cfg_module
    import worker.client as client_module
    new_cfg = WorkerConfig()
    monkeypatch.setattr(cfg_module, "config", new_cfg)
    monkeypatch.setattr(client_module, "config", new_cfg)
    from worker.client import ServerClient

    calls = []
    class FakeResp:
        status_code = 200
        def json(self): return {"tasks": []}
        def raise_for_status(self): pass
    class FakeHttp:
        def post(self, url, **kw):
            calls.append(url); return FakeResp()
        def close(self): pass

    c = ServerClient(); c.http = FakeHttp()
    c.fetch_tasks()
    assert any("/api/tasks/v2/fetch" in u for u in calls)
    c.close()
```

- [ ] **Step 3: 실행 → FAIL**

```bash
.venv/bin/pytest tests/test_worker_client.py -v
```

- [ ] **Step 4: client.py 수정**

`worker/client.py` 의 관련 메서드들을 v2 경로로 변경. 기존 패턴 유지하면서:
- `heartbeat()` → `POST {base}/api/workers/heartbeat/v2` · body = `{version, os_type, ...}` · 응답 dict 반환
- `fetch_tasks()` → `POST {base}/api/tasks/v2/fetch` · 헤더 `X-Worker-Token` · 응답 `{"tasks": [...]}`
- `complete_task(task_id, result)` → `POST {base}/api/tasks/v2/complete` · body `{task_id, result}`
- `fail_task(task_id, error)` → `POST {base}/api/tasks/v2/fail` · body `{task_id, error}`
- `account_created_upload(task_id, payload)` → `POST {base}/api/tasks/v2/{task_id}/result/account-created`

예시 heartbeat:
```python
def heartbeat(self) -> dict:
    resp = self.http.post(
        f"{self.base_url}/api/workers/heartbeat/v2",
        headers=self.headers,
        json={
            "version": config.worker_version,
            "os_type": "darwin",  # 플랫폼 감지 기능 이미 있으면 사용
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
```

(enroll 플로우는 별도 — Task M1-15 에서 다룸)

- [ ] **Step 5: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_worker_client.py -v
```

- [ ] **Step 6: Commit**

```bash
git add worker/client.py tests/test_worker_client.py
git commit -m "refactor(worker-client): M1-10 heartbeat/fetch/complete/fail v2 API 전환"
```

---

## Task M1-11: worker/app.py heartbeat 응답 반응 + `_current_task_id`

**Files:**
- Modify: `worker/app.py`
- Modify: `tests/test_worker_client.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_worker_client.py` 끝에:
```python
def test_worker_app_skips_fetch_when_paused(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt")
    from worker.config import WorkerConfig
    import worker.config as cfg_mod
    import worker.client as cli_mod
    import worker.app as app_mod
    new_cfg = WorkerConfig()
    for m in (cfg_mod, cli_mod, app_mod):
        monkeypatch.setattr(m, "config", new_cfg)
    from worker.app import WorkerApp

    app = WorkerApp()

    fetch_calls = []

    class FakeClient:
        def heartbeat(self):
            return {"paused": True, "current_version": "v1"}
        def fetch_tasks(self):
            fetch_calls.append(1)
            return []
        def close(self): pass

    app.client = FakeClient()
    import asyncio
    asyncio.get_event_loop().run_until_complete(app._async_tick())

    # paused=True 이므로 fetch 호출되지 않아야
    assert fetch_calls == []


def test_worker_app_tracks_current_task_id(monkeypatch):
    monkeypatch.setenv("HYDRA_SERVER_URL", "http://mock:8000")
    monkeypatch.setenv("HYDRA_WORKER_TOKEN", "wt")
    from worker.config import WorkerConfig
    import worker.config as cfg_mod, worker.client as cli_mod, worker.app as app_mod
    new_cfg = WorkerConfig()
    for m in (cfg_mod, cli_mod, app_mod):
        monkeypatch.setattr(m, "config", new_cfg)
    from worker.app import WorkerApp

    app = WorkerApp()
    assert getattr(app, "_current_task_id", None) is None
```

- [ ] **Step 2: 실행 → FAIL**

```bash
.venv/bin/pytest tests/test_worker_client.py -v -k "paused or current_task"
```

- [ ] **Step 3: app.py 수정**

`worker/app.py` 의 `_async_tick` 함수 안에 heartbeat 응답 반응 추가. 기존 로직에 맞춰:
```python
async def _async_tick(self):
    try:
        hb = self.client.heartbeat()
    except Exception as e:
        print(f"[Worker] heartbeat failed: {e}")
        return

    # M1-11: paused 시 fetch 스킵
    if hb.get("paused"):
        return

    # M1-11: current_version 감지 → updater
    from worker.updater import maybe_update
    is_idle = getattr(self, "_current_task_id", None) is None
    maybe_update(
        server_version=hb.get("current_version", ""),
        local_version=config.worker_version,
        is_idle=is_idle,
    )

    # 기존 fetch + execute 로직 이어짐
    ...
```

`_execute_session` (또는 실행 지점) 에서:
```python
self._current_task_id = task["id"]
try:
    await self.executor.execute(task)
finally:
    self._current_task_id = None
```

WorkerApp `__init__` 에 `self._current_task_id = None` 초기화 추가.

- [ ] **Step 4: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_worker_client.py -v
```

- [ ] **Step 5: Commit**

```bash
git add worker/app.py tests/test_worker_client.py
git commit -m "feat(worker-app): M1-11 heartbeat 반응 (paused/version) + _current_task_id"
```

---

## Task M1-12: worker/executor.py SessionLocal 제거 + AccountSnapshot 사용

**Files:**
- Modify: `worker/executor.py`
- Modify/Add: `tests/test_executor_snapshot.py`

- [ ] **Step 1: 현재 SessionLocal 사용 지점 찾기**

```bash
grep -n "SessionLocal\|hydra.db" worker/executor.py
```
(출력: 240, 515, 516, 518, 532, 533, 534 근처 — 모두 Account 조회 용도)

- [ ] **Step 2: 실패 테스트**

`tests/test_executor_snapshot.py`:
```python
"""Task M1-12: executor 가 AccountSnapshot 만으로 작동."""
import inspect


def test_executor_source_does_not_import_sessionlocal():
    """M1-12: worker/executor.py 에서 SessionLocal import 완전 제거."""
    import worker.executor as ex
    src = inspect.getsource(ex)
    assert "SessionLocal" not in src, (
        "worker/executor.py 는 AccountSnapshot 페이로드만 사용해야 함."
    )
    assert "from hydra.db.session import" not in src


def test_executor_source_imports_account_snapshot():
    import worker.executor as ex
    src = inspect.getsource(ex)
    assert "AccountSnapshot" in src
```

- [ ] **Step 3: 실행 → FAIL**

```bash
.venv/bin/pytest tests/test_executor_snapshot.py -v
```

- [ ] **Step 4: executor.py 리팩터**

`worker/executor.py`:

상단 import 수정:
```python
# 삭제:
# from hydra.db.session import SessionLocal
# from hydra.db.models import Account

# 추가:
from worker.account_snapshot import AccountSnapshot
```

각 핸들러 함수에서 `db = SessionLocal(); acct = db.get(Account, task["account_id"])` 블록을:
```python
snap = AccountSnapshot.from_payload(task)
```
로 대체. `acct.gmail`, `acct.password`, `acct.persona`, `acct.adspower_profile_id` 등의 속성 접근은 snap 이 동일 이름을 제공하므로 그대로 유지.

`acct.totp_secret` 의 복호화 호출 (`crypto.decrypt(acct.totp_secret)`) 이 있다면 삭제하고 `snap.totp_secret` 를 직접 사용 (이미 평문).

AI 호출 부분의 HTTP 헤더 추가:
```python
resp = httpx.post(
    f"{config.server_url}/api/generate-comment",
    headers={"X-Worker-Token": config.worker_token},
    json=payload,
    timeout=30,
)
```
(이미 있으면 스킵)

- [ ] **Step 5: 실행 → PASS**

```bash
.venv/bin/pytest tests/test_executor_snapshot.py -v
```

- [ ] **Step 6: 회귀 체크**

```bash
.venv/bin/pytest tests/ -q --ignore=tests/test_language_setup.py
```
전부 PASS 확인.

- [ ] **Step 7: Commit**

```bash
git add worker/executor.py tests/test_executor_snapshot.py
git commit -m "refactor(worker-executor): M1-12 SessionLocal 제거 + AccountSnapshot 사용"
```

---

## Task M1-13: 프론트 계정 등록 다이얼로그

**Files:**
- Create: `frontend/src/features/accounts/account-register-dialog.tsx`
- Modify: 기존 accounts 페이지에 버튼 연결

- [ ] **Step 1: 기존 accounts 페이지 위치 확인**

```bash
ls frontend/src/features/accounts/ frontend/src/routes/_authenticated/accounts/
```

- [ ] **Step 2: 다이얼로그 컴포넌트 생성**

`frontend/src/features/accounts/account-register-dialog.tsx`:
```tsx
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogDescription,
  DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { fetchApi } from '@/lib/api'
import { toast } from 'sonner'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: () => void
}

export function AccountRegisterDialog({ open, onOpenChange, onCreated }: Props) {
  const [gmail, setGmail] = useState('')
  const [password, setPassword] = useState('')
  const [profileId, setProfileId] = useState('')
  const [recovery, setRecovery] = useState('')
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!gmail.trim() || !password || !profileId.trim()) {
      toast.error('필수 항목을 모두 입력하세요')
      return
    }
    setBusy(true)
    try {
      await fetchApi<{ account_id: number }>(
        '/api/admin/accounts/register',
        {
          method: 'POST',
          body: JSON.stringify({
            gmail: gmail.trim(),
            password,
            adspower_profile_id: profileId.trim(),
            recovery_email: recovery.trim() || null,
            phone_number: phone.trim() || null,
          }),
        },
      )
      toast.success('등록됨 · 온보딩 태스크 자동 생성')
      onCreated?.()
      onOpenChange(false)
      setGmail(''); setPassword(''); setProfileId('')
      setRecovery(''); setPhone('')
    } catch (e) {
      toast.error((e as Error).message || '등록 실패')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>계정 등록</DialogTitle>
          <DialogDescription>
            등록 즉시 온보딩 단계로 자동 진행됩니다 (M1).
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-3'>
          <div>
            <Label>Gmail *</Label>
            <Input value={gmail} onChange={(e) => setGmail(e.target.value)} autoFocus />
          </div>
          <div>
            <Label>비밀번호 *</Label>
            <Input type='password' value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div>
            <Label>AdsPower Profile ID *</Label>
            <Input value={profileId}
                   onChange={(e) => setProfileId(e.target.value)}
                   placeholder='k1xxx' />
          </div>
          <div>
            <Label>복구 이메일</Label>
            <Input value={recovery}
                   onChange={(e) => setRecovery(e.target.value)} />
          </div>
          <div>
            <Label>전화번호</Label>
            <Input value={phone}
                   onChange={(e) => setPhone(e.target.value)}
                   placeholder='+82...' />
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline'
                  onClick={() => onOpenChange(false)}
                  disabled={busy}>취소</Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? '등록중…' : '등록'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 3: 기존 accounts 페이지에 버튼 + 상태 연결**

`frontend/src/features/accounts/index.tsx` (또는 해당 파일) 상단 import:
```tsx
import { useState } from 'react'
import { AccountRegisterDialog } from './account-register-dialog'
import { Button } from '@/components/ui/button'
import { Plus } from 'lucide-react'
```

컴포넌트 안에 상태 + 버튼:
```tsx
const [regOpen, setRegOpen] = useState(false)

// 헤더 영역에:
<Button onClick={() => setRegOpen(true)}>
  <Plus className='mr-1 h-4 w-4' /> 계정 등록
</Button>

// 컴포넌트 반환 JSX 끝에:
<AccountRegisterDialog
  open={regOpen}
  onOpenChange={setRegOpen}
  onCreated={() => { /* 목록 새로고침 — 기존 로드 함수 호출 */ }}
/>
```

- [ ] **Step 4: 빌드 확인**

```bash
cd frontend && npm run build
```
Expected: `✓ built in ...`

- [ ] **Step 5: Commit**

```bash
cd /Users/seominjae/Documents/hydra
git add frontend/src/features/accounts/ frontend/src/routeTree.gen.ts
git commit -m "feat(ui): M1-13 계정 등록 다이얼로그 + 버튼"
```

---

## Task M1-14: 전체 회귀 + VPS 배포

**Files:**
- 코드 변경 없음. 검증 + 배포.

- [ ] **Step 1: 전체 pytest**

```bash
.venv/bin/pytest tests/ -q --ignore=tests/test_language_setup.py
```
Expected: 380+ tests, 0 fail.

- [ ] **Step 2: 프론트 빌드**

```bash
cd frontend && npm run build
```
Expected: success.

- [ ] **Step 3: 배포 (어드민 UI 버튼 or API)**

```bash
cd /Users/seominjae/Documents/hydra
# 이미 main 에 push 되어있다면:
TOKEN=$(curl -s -X POST https://hydra-prod.duckdns.org/api/admin/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"email":"admin@hydra.local","password":"'"$ADMIN_PASSWORD"'"}' \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')
curl -X POST -H "Authorization: Bearer $TOKEN" \
    https://hydra-prod.duckdns.org/api/admin/deploy
```
20초 후:
```bash
curl -H "Authorization: Bearer $TOKEN" \
    https://hydra-prod.duckdns.org/api/admin/server-config | python3 -m json.tool
```
`current_version` 이 최신 git hash 로 업데이트됐는지 확인.

- [ ] **Step 4: e2e_check.sh 재실행**

```bash
HYDRA_URL=https://hydra-prod.duckdns.org \
ADMIN_EMAIL=admin@hydra.local \
ADMIN_PASSWORD="$ADMIN_PASSWORD" \
bash scripts/e2e_check.sh
```
Expected: PASS 14/14.

- [ ] **Step 5: Commit (필요 시)**

배포 로그가 남아있으면 문서 업데이트 후 commit. 아니면 skip.

---

## Task M1-15: Mac 로컬 워커 Golden Path E2E

**Files:**
- Create: `scripts/m1_run_mac_worker.sh` (편의 스크립트)
- Modify: `docs/e2e-checklist.md`

- [ ] **Step 1: .env 세팅 확인**

Mac `/Users/seominjae/Documents/hydra/.env` 필요 항목:
```
SERVER_URL=https://hydra-prod.duckdns.org
ENROLLMENT_SECRET=  # VPS .env 와 동일
HYDRA_ENCRYPTION_KEY=inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=
JWT_SECRET=  # VPS 와 동일
M1_TEST_VIDEO_ID=dQw4w9WgXcQ  # 아무 공개 YouTube 영상 ID
```

없는 값은 VPS 에서 복사:
```bash
ssh -i ~/.ssh/hydra_prod deployer@158.247.232.101 'cat /opt/hydra/.env' \
    | grep -E "ENROLLMENT_SECRET|HYDRA_ENCRYPTION_KEY|JWT_SECRET"
```

- [ ] **Step 2: VPS .env 에 M1_TEST_VIDEO_ID 추가**

```bash
ssh -i ~/.ssh/hydra_prod deployer@158.247.232.101 \
    'echo "M1_TEST_VIDEO_ID=dQw4w9WgXcQ" | sudo tee -a /opt/hydra/.env'
sudo systemctl restart hydra-server
```
(M1 전용 — 나중에 실 캠페인 UI 생기면 제거)

- [ ] **Step 3: 워커 실행 스크립트**

`scripts/m1_run_mac_worker.sh`:
```bash
#!/usr/bin/env bash
# M1 Golden Path 로컬 워커 실행 (Mac).
set -euo pipefail

cd "$(dirname "$0")/.."

# 1. enrollment token 받기 (VPS 에서 발급)
ADMIN_TOKEN=$(curl -s -X POST "${SERVER_URL:-https://hydra-prod.duckdns.org}/api/admin/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}" \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')

ENROLL=$(curl -s -X POST "${SERVER_URL:-https://hydra-prod.duckdns.org}/api/admin/workers/enroll" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"worker_name":"mac-m1","ttl_hours":1}' \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["enrollment_token"])')

# 2. enroll 해서 worker_token + secrets 받기
WT=$(curl -s -X POST "${SERVER_URL:-https://hydra-prod.duckdns.org}/api/workers/enroll" \
    -H 'Content-Type: application/json' \
    -d "{\"enrollment_token\":\"$ENROLL\",\"hostname\":\"mac-m1\"}" \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["worker_token"])')

# 3. .env 에 WORKER_TOKEN 주입
grep -v '^WORKER_TOKEN=' .env > .env.tmp && mv .env.tmp .env
echo "WORKER_TOKEN=$WT" >> .env
echo "enrolled: worker_token = ${WT:0:8}..."

# 4. 워커 실행 (foreground — Ctrl+C 로 종료)
echo "run: .venv/bin/python -m worker"
```

실행 권한:
```bash
chmod +x scripts/m1_run_mac_worker.sh
```

- [ ] **Step 4: 로컬 M1 시나리오 실행**

```bash
# 어드민 UI (localhost:5175) 에서 "계정 등록" 눌러 1개 생성
# (또는 API 직접 호출)

# 별도 터미널에서 워커 기동
ADMIN_EMAIL=admin@hydra.local \
ADMIN_PASSWORD='FgcrwvWv!RMYq35IKDPu' \
bash scripts/m1_run_mac_worker.sh
.venv/bin/python -m worker
```

관찰 대상:
- 워커 heartbeat 정상 (15초 간격)
- onboarding_verify 태스크 fetch → execute → complete
- 곧바로 warmup 태스크 3개 연속 진행
- active 전환 후 30초 이내에 comment/like 태스크 생성
- comment + like 완료

실제 YouTube 액션이 일어날 수 있으므로 **테스트 계정/비디오 사용 주의**.

- [ ] **Step 5: 결과 검증**

```bash
# VPS DB 조회 — 최근 생성된 Account + Task
ssh -i ~/.ssh/hydra_prod deployer@158.247.232.101 \
    'sudo -u postgres psql -d hydra_prod -c "
    SELECT id, gmail, status, warmup_day
      FROM accounts ORDER BY id DESC LIMIT 3;
    SELECT id, task_type, status, completed_at
      FROM tasks WHERE account_id = (SELECT MAX(id) FROM accounts)
      ORDER BY id;
    "'
```
기대:
- Account.status = `active`, warmup_day = 4
- Tasks: onboarding_verify, warmup×3, comment, like 모두 `done`

- [ ] **Step 6: docs/e2e-checklist.md 업데이트**

"Worker 실전 연결 후 추가 (Phase 1e 이후)" 섹션을 **M1 완료 기준** 으로 전환 — 항목 체크 표시 +
"M1 Golden Path 검증 완료" 한 줄 기록.

- [ ] **Step 7: Commit**

```bash
git add scripts/m1_run_mac_worker.sh docs/e2e-checklist.md
git commit -m "feat(m1): Mac 로컬 워커 Golden Path E2E 실행 스크립트 + 검증 기록"
```

---

## 완료 기준

1. `pytest -q` GREEN (이 플랜 신규 테스트 포함 ~400+)
2. `scripts/e2e_check.sh` 14 PASS (기존 유지)
3. 어드민 UI 에서 계정 1개 등록 → Mac 로컬 워커가 자동 실행 → Account 상태가
   active 로 전환 + comment/like 태스크 `done` 처리 확인
4. DB 에 suspended / 좀비 / 기타 상태 오염 없음

완료 후 다음 마일스톤(M2):
- 캠페인 생성/관리 UI
- 복수 캠페인 동시 실행 + account 할당
- UI 전면 재설계 (토스 수준)
- 실운영 워밍업 기간 (24h scheduled_at 지연) 전환

---
