"""어드민 전용 — 워커 관리 엔드포인트.

- POST /api/admin/workers/enroll : 새 워커용 1회용 enrollment 토큰 + PowerShell 설치 명령 발급

이후 Task 25 에서 카나리/일시정지 등 추가.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hydra.core.enrollment import generate_enrollment_token
from hydra.db import session as _db_session
from hydra.db.models import Task, Worker
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()

VALID_TASK_TYPES = {
    "*",
    "create_account",
    "comment",
    "like",
    "watch_video",
    "warmup",
    "onboarding_verify",
}


class EnrollRequest(BaseModel):
    worker_name: str = Field(..., min_length=1, max_length=64)
    ttl_hours: int = Field(default=24, ge=1, le=24 * 7)
    # Slice 3.2 — role 발급 시점 결정. immutable (재발급 시 변경 거부).
    role: str = Field(default="desktop_worker")
    # admin_agent 발급 시 필수. 가리키는 desktop_worker.id.
    parent_worker_id: Optional[int] = None


class EnrollResponse(BaseModel):
    enrollment_token: str
    install_command: str
    expires_in_hours: int
    role: str = "desktop_worker"
    parent_worker_id: Optional[int] = None


def _validate_enrollment_role_and_parent(
    db, role: str, parent_worker_id: Optional[int], exclude_worker_id: Optional[int] = None,
) -> None:
    """Slice 3.2 — enroll/PATCH role 공통 검증.

    - role: desktop_worker | admin_agent
    - admin_agent: parent_worker_id 필수, 존재 + role == desktop_worker
    - admin_agent : desktop 1:1 강제 (같은 parent 에 admin_agent 2번째 거부)
      exclude_worker_id 는 PATCH 시 자기 자신 제외 (재발급/no-op 허용)
    - desktop_worker: parent_worker_id 비워야
    """
    if role not in ("desktop_worker", "admin_agent"):
        raise HTTPException(400, f"invalid role: {role!r}")
    if role == "admin_agent":
        if parent_worker_id is None:
            raise HTTPException(400, "admin_agent enroll requires parent_worker_id")
        parent = db.get(Worker, parent_worker_id)
        if parent is None:
            raise HTTPException(400, f"parent_worker_id={parent_worker_id} not found")
        if parent.role != "desktop_worker":
            raise HTTPException(
                400,
                f"parent_worker_id={parent_worker_id} role={parent.role}; "
                f"admin_agent parent must be desktop_worker",
            )
        # 1:1 강제 — 같은 desktop 에 다른 admin_agent 이미 있으면 거부.
        # Slice 3.1 의 ambiguous routing 을 발급 단에서 미연에 방지.
        sibling_q = db.query(Worker).filter(
            Worker.role == "admin_agent",
            Worker.parent_worker_id == parent_worker_id,
        )
        if exclude_worker_id is not None:
            sibling_q = sibling_q.filter(Worker.id != exclude_worker_id)
        if sibling_q.first() is not None:
            raise HTTPException(
                409,
                f"desktop_worker {parent_worker_id} already has an admin_agent; "
                "1:1 paired admin_agent enforced",
            )
    else:  # desktop_worker
        if parent_worker_id is not None:
            raise HTTPException(
                400, "desktop_worker enroll must not set parent_worker_id",
            )


class EnrollPairedRequest(BaseModel):
    pc_name: str = Field(..., min_length=1, max_length=48)
    ttl_hours: int = Field(default=24, ge=1, le=24 * 7)


class EnrollPairedResponse(BaseModel):
    desktop: EnrollResponse
    admin_agent: EnrollResponse
    install_command: str  # 두 worker 모두 install 하는 단일 PowerShell


@router.post("/enroll-paired", response_model=EnrollPairedResponse)
def create_enrollment_paired(
    req: EnrollPairedRequest,
    _session: dict = Depends(admin_session),
) -> EnrollPairedResponse:
    """UX A — 한 번 요청으로 desktop_worker + admin_agent 둘 다 enroll.

    워커 PC 한 대 = DB 워커 row 2개 (desktop_worker + admin_agent) 모델을
    UI 1회 작업으로 단순화. 운영자가 PC 이름 1개 입력하면 paired set 발급.

    이름 규칙:
      desktop_worker:    <pc_name>
      admin_agent:       <pc_name>-agent

    desktop_worker 가 먼저 생성되어야 admin_agent parent_worker_id 지정 가능.
    같은 commit 안에서 둘 다 만듦 — 부분 실패 시 rollback.
    """
    pc_name = req.pc_name.strip()
    if not pc_name:
        raise HTTPException(400, "pc_name required")
    desktop_name = pc_name
    agent_name = f"{pc_name}-agent"

    server_url = os.getenv("SERVER_URL", "").rstrip("/")
    if not server_url:
        raise HTTPException(500, "SERVER_URL not configured")

    db = _db_session.SessionLocal()
    try:
        # 둘 다 이미 존재하면 paired set 재발급 (token 회전).
        # 다른 role/parent 면 immutable 검증으로 409 던짐.
        for name, role, parent_id in (
            (desktop_name, "desktop_worker", None),
            # agent 의 parent 는 아래 insert 후 알아냄. 일단 None placeholder
        ):
            _validate_enrollment_role_and_parent(db, role, parent_id)

        # desktop 먼저 enroll (또는 기존 row 검증)
        existing_desktop = db.query(Worker).filter_by(name=desktop_name).first()
        if existing_desktop is not None and existing_desktop.role != "desktop_worker":
            raise HTTPException(
                409,
                f"worker {desktop_name!r} already exists with role={existing_desktop.role}",
            )
        # admin_agent name 도 미리 검증
        existing_agent = db.query(Worker).filter_by(name=agent_name).first()
        if existing_agent is not None:
            if existing_agent.role != "admin_agent":
                raise HTTPException(
                    409,
                    f"worker {agent_name!r} already exists with role={existing_agent.role}",
                )
            # parent 가 향후 결정될 desktop 과 일치하는지 검증은
            # consume 시점 immutable check 가 마지막 안전망.
    finally:
        db.close()

    desktop_token = generate_enrollment_token(
        desktop_name,
        ttl_hours=req.ttl_hours,
        role="desktop_worker",
        parent_worker_id=None,
    )
    # parent_worker_id 가 agent token 에 필요. 그런데 desktop 이 아직 consume
    # 안 됐으면 worker_id 가 없음 → enroll-paired 가 두 단계 흐름이 됨.
    # 운영 시나리오: 워커 PC 가 desktop 먼저 consume → server 가 desktop.id
    # 알면 그제서야 agent token 발급. 이를 단일 호출로 단순화하려면:
    #   1) 서버에서 미리 desktop row 만들고 id 확보 → agent token 에 그 id 박음
    #   2) 워커 PC 가 두 token 으로 두 service 모두 enroll
    # row 미리 생성 — token 만 회전이라 안전.
    db = _db_session.SessionLocal()
    try:
        desktop_row = db.query(Worker).filter_by(name=desktop_name).first()
        if desktop_row is None:
            desktop_row = Worker(
                name=desktop_name,
                role="desktop_worker",
                status="offline",
            )
            db.add(desktop_row)
            db.commit()
            db.refresh(desktop_row)
        desktop_id = desktop_row.id
    finally:
        db.close()

    agent_token = generate_enrollment_token(
        agent_name,
        ttl_hours=req.ttl_hours,
        role="admin_agent",
        parent_worker_id=desktop_id,
    )

    # PowerShell 한 줄로 두 service 모두 설치.
    # setup.ps1 가 -Token + -ServerUrl 받음. role 분기는 setup 안에서
    # token payload role 보고 결정. 두 번 호출.
    install_command = (
        "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; "
        f"iwr -Uri {server_url}/api/workers/setup.ps1 -OutFile setup.ps1; "
        f".\\setup.ps1 -Token '{desktop_token}' -ServerUrl '{server_url}'; "
        f".\\setup.ps1 -Token '{agent_token}' -ServerUrl '{server_url}'"
    )

    return EnrollPairedResponse(
        desktop=EnrollResponse(
            enrollment_token=desktop_token,
            install_command=(
                f".\\setup.ps1 -Token '{desktop_token}' -ServerUrl '{server_url}'"
            ),
            expires_in_hours=req.ttl_hours,
            role="desktop_worker",
            parent_worker_id=None,
        ),
        admin_agent=EnrollResponse(
            enrollment_token=agent_token,
            install_command=(
                f".\\setup.ps1 -Token '{agent_token}' -ServerUrl '{server_url}'"
            ),
            expires_in_hours=req.ttl_hours,
            role="admin_agent",
            parent_worker_id=desktop_id,
        ),
        install_command=install_command,
    )


@router.post("/enroll", response_model=EnrollResponse)
def create_enrollment(
    req: EnrollRequest,
    _session: dict = Depends(admin_session),
) -> EnrollResponse:
    name = req.worker_name.strip()
    if not name:
        raise HTTPException(400, "worker_name required")

    db = _db_session.SessionLocal()
    try:
        _validate_enrollment_role_and_parent(db, req.role, req.parent_worker_id)
        # 같은 name 으로 이미 존재하는 worker 가 다른 role 이면 거부 (immutable)
        existing = db.query(Worker).filter_by(name=name).first()
        if existing is not None:
            if existing.role != req.role:
                raise HTTPException(
                    409,
                    f"worker {name!r} already enrolled as role={existing.role}; "
                    f"role is immutable (cannot re-enroll as {req.role})",
                )
            if existing.parent_worker_id != req.parent_worker_id:
                raise HTTPException(
                    409,
                    f"worker {name!r} already has parent_worker_id="
                    f"{existing.parent_worker_id}; parent is immutable",
                )
    finally:
        db.close()

    token = generate_enrollment_token(
        name,
        ttl_hours=req.ttl_hours,
        role=req.role,
        parent_worker_id=req.parent_worker_id,
    )
    server_url = os.getenv("SERVER_URL", "").rstrip("/")
    if not server_url:
        raise HTTPException(500, "SERVER_URL not configured")

    # 처음 설치하는 PC 는 ExecutionPolicy 가 Restricted 라 .ps1 실행 거부됨 →
    # Process scope 로 Bypass (창 닫으면 원복) 를 명령에 포함시켜 한 줄로 동작.
    install_command = (
        "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; "
        f"iwr -Uri {server_url}/api/workers/setup.ps1 -OutFile setup.ps1; "
        f".\\setup.ps1 -Token '{token}' -ServerUrl '{server_url}'"
    )
    return EnrollResponse(
        enrollment_token=token,
        install_command=install_command,
        expires_in_hours=req.ttl_hours,
        role=req.role,
        parent_worker_id=req.parent_worker_id,
    )


class CurrentTaskInfo(BaseModel):
    id: int
    task_type: str
    started_at: Optional[datetime] = None


class WorkerOut(BaseModel):
    id: int
    name: str
    status: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    current_version: Optional[str] = None
    os_type: Optional[str] = None
    allow_preparation: Optional[bool] = None
    allow_campaign: Optional[bool] = None
    allowed_task_types: list[str] = []
    enrolled_at: Optional[datetime] = None
    current_task: Optional[CurrentTaskInfo] = None  # M2.1-5
    paused_reason: Optional[str] = None  # T7 Circuit Breaker 정보
    consecutive_failures: int = 0
    verbose_mode: bool = False
    # Slice 2.1 — Worker Admin Agent identity 분리.
    role: str = "desktop_worker"
    parent_worker_id: Optional[int] = None
    capabilities: list[str] = []


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """tz-naive datetime 을 UTC 로 가정하고 tz-aware 화. JSON 직렬화 시 +00:00 붙어
    프론트에서 KST 등 사용자 로케일로 정확히 변환됨.

    DB 컬럼이 DateTime (timezone=False) 이라 항상 naive 로 돌아오는데, 우리는
    datetime.now(UTC) 로만 저장하므로 UTC 라고 단언해도 안전.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _worker_to_out(w: Worker, current_task: Optional[Task] = None) -> WorkerOut:
    try:
        types = json.loads(w.allowed_task_types or '["*"]')
        if not isinstance(types, list):
            types = ["*"]
    except json.JSONDecodeError:
        types = ["*"]
    ct = None
    if current_task is not None:
        ct = CurrentTaskInfo(
            id=current_task.id,
            task_type=current_task.task_type,
            started_at=_as_utc(current_task.started_at),
        )
    # Slice 2.1 — capabilities JSON 파싱 (저장은 Text). 잘못된 형식이면 빈 list.
    caps: list[str] = []
    if w.capabilities:
        try:
            parsed = json.loads(w.capabilities)
            if isinstance(parsed, list):
                caps = [str(x) for x in parsed]
        except (json.JSONDecodeError, TypeError):
            caps = []
    return WorkerOut(
        id=w.id, name=w.name, status=w.status,
        last_heartbeat=_as_utc(w.last_heartbeat),
        current_version=w.current_version, os_type=w.os_type,
        allow_preparation=w.allow_preparation, allow_campaign=w.allow_campaign,
        allowed_task_types=[str(t) for t in types],
        enrolled_at=_as_utc(w.enrolled_at),
        current_task=ct,
        paused_reason=w.paused_reason,
        consecutive_failures=w.consecutive_failures or 0,
        verbose_mode=bool(w.verbose_mode),
        role=getattr(w, "role", "desktop_worker") or "desktop_worker",
        parent_worker_id=getattr(w, "parent_worker_id", None),
        capabilities=caps,
    )


@router.get("/", response_model=list[WorkerOut])
def list_workers(_session: dict = Depends(admin_session)) -> list[WorkerOut]:
    db = _db_session.SessionLocal()
    try:
        workers = db.query(Worker).order_by(Worker.id).all()
        result = []
        for w in workers:
            running = (
                db.query(Task)
                .filter(Task.worker_id == w.id, Task.status == "running")
                .first()
            )
            result.append(_worker_to_out(w, running))
        return result
    finally:
        db.close()


class WorkerPatch(BaseModel):
    allowed_task_types: Optional[list[str]] = None
    allow_preparation: Optional[bool] = None
    allow_campaign: Optional[bool] = None
    status: Optional[str] = None  # online|offline|paused
    adspower_api_key: Optional[str] = None  # 평문 입력, 서버에서 Fernet 암호화 저장
                                            # 빈 문자열 "" 은 제거 의미
    verbose_mode: Optional[bool] = None  # INFO+ 로그 push 토글


@router.patch("/{worker_id}", response_model=WorkerOut)
def update_worker(
    worker_id: int,
    req: WorkerPatch,
    _session: dict = Depends(admin_session),
) -> WorkerOut:
    db = _db_session.SessionLocal()
    try:
        w = db.get(Worker, worker_id)
        if w is None:
            raise HTTPException(404, "worker not found")

        if req.allowed_task_types is not None:
            types = list(req.allowed_task_types)
            unknown = [t for t in types if t not in VALID_TASK_TYPES]
            if unknown:
                raise HTTPException(
                    400, f"unknown task_type(s): {unknown}. "
                    f"allowed: {sorted(VALID_TASK_TYPES)}",
                )
            # wildcard 는 단독
            if "*" in types:
                types = ["*"]
            w.allowed_task_types = json.dumps(types)

        if req.allow_preparation is not None:
            w.allow_preparation = bool(req.allow_preparation)
        if req.allow_campaign is not None:
            w.allow_campaign = bool(req.allow_campaign)
        # 양쪽 OFF 가드 — 워커가 어떤 task 도 못 받게 되는 상태 방지.
        # 명시적으로 둘 다 False 로 두려면 status='paused' 사용 권장.
        if w.allow_preparation is False and w.allow_campaign is False:
            raise HTTPException(
                400,
                "워커 역할이 양쪽 모두 OFF 입니다. 최소 하나는 ON 이어야 task 를 받을 수 있습니다. "
                "전체 정지가 필요하면 status='paused' 를 사용하세요."
            )
        if req.status is not None:
            if req.status not in ("online", "offline", "paused"):
                raise HTTPException(400, f"invalid status: {req.status}")
            w.status = req.status
        if req.adspower_api_key is not None:
            from hydra.core import crypto
            if req.adspower_api_key == "":
                w.adspower_api_key_enc = None
            else:
                w.adspower_api_key_enc = crypto.encrypt(req.adspower_api_key)
        if req.verbose_mode is not None:
            w.verbose_mode = bool(req.verbose_mode)

        db.commit()
        db.refresh(w)
        running = (
            db.query(Task)
            .filter(Task.worker_id == w.id, Task.status == "running")
            .first()
        )
        return _worker_to_out(w, running)
    finally:
        db.close()


class RolePatch(BaseModel):
    role: str
    parent_worker_id: Optional[int] = None


@router.patch("/{worker_id}/role", response_model=WorkerOut)
def update_worker_role(
    worker_id: int,
    req: RolePatch,
    _session: dict = Depends(admin_session),
) -> WorkerOut:
    """Slice 3.2 — role 변경 admin-only endpoint.

    role 은 enroll 시점 immutable. 운영상 PC 용도 전환이 필요한 경우만 이
    endpoint 로 변경. heartbeat 차단 (Slice 3.2) 이후 유일한 정식 경로.

    부수 효과: 변경 시 pending/leased 상태이고 target_role mismatch 인
    WorkerCommand 를 즉시 failed + role_mismatch_after_role_change 로 닫음
    (heartbeat lease 까지 미루면 운영자 혼란).
    """
    from hydra.db.models import WorkerCommand
    db = _db_session.SessionLocal()
    try:
        w = db.get(Worker, worker_id)
        if w is None:
            raise HTTPException(404, "worker not found")

        _validate_enrollment_role_and_parent(
            db, req.role, req.parent_worker_id, exclude_worker_id=w.id,
        )

        # Slice 3.2 follow-up (Codex) — child invariant 보호:
        # 이 worker 가 desktop_worker 였고 PATCH 로 admin_agent 가 되려는데
        # 이 worker 를 parent 로 가리키는 child admin_agent 가 이미 있으면
        # child.parent.role 가 admin_agent 가 되어 invariant 위반. 거부.
        if req.role == "admin_agent" and w.role == "desktop_worker":
            child = (
                db.query(Worker)
                .filter(
                    Worker.role == "admin_agent",
                    Worker.parent_worker_id == w.id,
                )
                .first()
            )
            if child is not None:
                raise HTTPException(
                    409,
                    f"worker {w.id} is parent of admin_agent {child.id}; "
                    "cannot change role to admin_agent (child invariant)",
                )

        # no-op (같은 role + parent) 은 그냥 통과
        if w.role == req.role and w.parent_worker_id == req.parent_worker_id:
            running = (
                db.query(Task).filter(Task.worker_id == w.id, Task.status == "running").first()
            )
            return _worker_to_out(w, running)

        w.role = req.role
        w.parent_worker_id = req.parent_worker_id

        # pending/leased 중 target_role 박혔고 mismatch 인 것 정리.
        now = datetime.now(UTC)
        affected = (
            db.query(WorkerCommand)
            .filter(
                WorkerCommand.worker_id == w.id,
                WorkerCommand.status.in_(["pending", "leased"]),
                WorkerCommand.target_role.isnot(None),
                WorkerCommand.target_role != w.role,
            )
            .all()
        )
        for c in affected:
            c.status = "failed"
            c.completed_at = now
            c.lease_expires_at = None
            msg = (
                f"role_mismatch_after_role_change:"
                f"target={c.target_role},new_role={w.role}"
            )
            c.error_message = (c.error_message + " | " + msg) if c.error_message else msg

        db.commit()
        db.refresh(w)
        running = (
            db.query(Task).filter(Task.worker_id == w.id, Task.status == "running").first()
        )
        return _worker_to_out(w, running)
    finally:
        db.close()


@router.delete("/{worker_id}")
def delete_worker(
    worker_id: int,
    _session: dict = Depends(admin_session),
):
    """워커 삭제. 실행 중인 태스크가 있으면 거부.

    같이 삭제: WorkerCommand, WorkerError, ProfileLock (운영 산출물/ephemeral).
    NULL 로 보존: Task, AccountProfileHistory, ExecutionLog (historical).
    """
    from hydra.db.models import (
        WorkerCommand, WorkerError, ProfileLock,
        AccountProfileHistory, ExecutionLog, IpLog, WorkerLogTail,
        TerminalSession,
    )
    db = _db_session.SessionLocal()
    try:
        w = db.get(Worker, worker_id)
        if w is None:
            raise HTTPException(404, "worker not found")

        running = (
            db.query(Task)
            .filter(Task.worker_id == worker_id, Task.status == "running")
            .first()
        )
        if running is not None:
            raise HTTPException(
                409,
                f"실행 중인 태스크(id={running.id}, type={running.task_type})가 있습니다. "
                "완료 또는 실패 처리 후 다시 시도하세요.",
            )

        worker_name = w.name

        # 이력 보존 — worker_id NULL
        db.query(Task).filter(Task.worker_id == worker_id).update(
            {Task.worker_id: None}, synchronize_session=False,
        )
        db.query(AccountProfileHistory).filter(
            AccountProfileHistory.worker_id == worker_id
        ).update({AccountProfileHistory.worker_id: None}, synchronize_session=False)
        db.query(ExecutionLog).filter(ExecutionLog.worker_id == worker_id).update(
            {ExecutionLog.worker_id: None}, synchronize_session=False,
        )
        # Codex 5/12 P2 follow-up — IpLog.worker_id 도 NULL 처리. FK 의
        # ondelete=SET NULL 과 중복이지만 application 단계에서도 명시 — 둘
        # 중 하나만 작동해도 worker 삭제가 끊기지 않게 안전망.
        db.query(IpLog).filter(IpLog.worker_id == worker_id).update(
            {IpLog.worker_id: None}, synchronize_session=False,
        )
        # 운영 산출물 / ephemeral lock 은 함께 삭제
        db.query(WorkerCommand).filter(WorkerCommand.worker_id == worker_id).delete(
            synchronize_session=False,
        )
        db.query(WorkerError).filter(WorkerError.worker_id == worker_id).delete(
            synchronize_session=False,
        )
        db.query(ProfileLock).filter(ProfileLock.worker_id == worker_id).delete(
            synchronize_session=False,
        )
        # Codex P2 post-review — WorkerLogTail (단기 verbose 디버그 log) 도
        # ephemeral 한 데이터라 worker 와 함께 삭제. nullable=False FK 라
        # 그대로 두면 worker 삭제 FK 위반.
        db.query(WorkerLogTail).filter(WorkerLogTail.worker_id == worker_id).delete(
            synchronize_session=False,
        )

        # Phase 4 follow-up — paired admin_agent 의 parent_worker_id FK 가
        # RESTRICT (no ondelete) 라 desktop 삭제 시 FK 위반. paired admin_agent
        # 가 있으면 같이 삭제 (1:1 정책상 desktop 죽으면 agent 도 의미 없음).
        paired_agents = (
            db.query(Worker)
            .filter(Worker.parent_worker_id == worker_id, Worker.role == "admin_agent")
            .all()
        )
        for agent in paired_agents:
            # admin_agent 의 child terminal_sessions cascade
            db.query(TerminalSession).filter(
                TerminalSession.worker_id == agent.id
            ).delete(synchronize_session=False)
            db.query(WorkerCommand).filter(WorkerCommand.worker_id == agent.id).delete(
                synchronize_session=False,
            )
            db.query(WorkerError).filter(WorkerError.worker_id == agent.id).delete(
                synchronize_session=False,
            )
            db.query(WorkerLogTail).filter(WorkerLogTail.worker_id == agent.id).delete(
                synchronize_session=False,
            )
            db.delete(agent)

        # Phase 4 — 본인 워커의 terminal_sessions 도 cascade
        db.query(TerminalSession).filter(
            TerminalSession.worker_id == worker_id
        ).delete(synchronize_session=False)

        db.delete(w)
        db.commit()
        return {"ok": True, "deleted_worker_id": worker_id, "name": worker_name}
    finally:
        db.close()


# ───────────── worker errors listing ─────────────
class WorkerErrorOut(BaseModel):
    id: int
    worker_id: int
    worker_name: str
    kind: str
    message: str
    traceback: Optional[str] = None
    context: Optional[dict] = None
    screenshot_url: Optional[str] = None  # 상대경로 (예: 2026-04-25/5-1777.png)
    occurred_at: str
    received_at: str


@router.get("/errors")
def list_worker_errors(
    _session: dict = Depends(admin_session),
    worker_id: Optional[int] = None,
    kind: Optional[str] = None,
    limit: int = 200,
) -> list[WorkerErrorOut]:
    """워커 에러 로그 조회 (최신순).

    필터: worker_id, kind. limit 최대 1000.
    """
    from hydra.db.models import WorkerError
    limit = max(1, min(limit, 1000))

    db = _db_session.SessionLocal()
    try:
        q = db.query(WorkerError, Worker).join(Worker, WorkerError.worker_id == Worker.id)
        if worker_id is not None:
            q = q.filter(WorkerError.worker_id == worker_id)
        if kind:
            q = q.filter(WorkerError.kind == kind)
        q = q.order_by(WorkerError.received_at.desc()).limit(limit)

        out = []
        for err, worker in q.all():
            ctx = None
            if err.context:
                try:
                    ctx = json.loads(err.context)
                except Exception:
                    ctx = {"_raw": err.context}
            out.append(WorkerErrorOut(
                id=err.id,
                worker_id=err.worker_id,
                worker_name=worker.name,
                kind=err.kind,
                message=err.message,
                traceback=err.traceback,
                context=ctx,
                screenshot_url=err.screenshot_url,
                occurred_at=err.occurred_at.isoformat(),
                received_at=err.received_at.isoformat(),
            ))
        return out
    finally:
        db.close()


# ───────────── screenshot 서빙 (admin 인증 필수) ─────────────
@router.get("/errors/screenshot/{path:path}")
def get_error_screenshot(path: str, _session: dict = Depends(admin_session)):
    """worker_errors.screenshot_url 로 저장된 상대경로 이미지 서빙.

    관리자 JWT 필수. path traversal 방지 위해 .. / 절대경로 거부.
    """
    from fastapi.responses import FileResponse
    from pathlib import Path as _P
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "invalid path")
    base = _P(os.getenv("HYDRA_SCREENSHOT_DIR", "/var/www/hydra/screenshots"))
    abs_path = (base / path).resolve()
    # 경로 이탈 재확인
    if not str(abs_path).startswith(str(base.resolve())):
        raise HTTPException(400, "path escape")
    if not abs_path.is_file():
        raise HTTPException(404, "screenshot not found")
    return FileResponse(abs_path)


# ───────────── 원격 명령 시스템 ─────────────
ALLOWED_COMMANDS = frozenset({
    "restart", "update_now", "run_diag", "retry_task", "screenshot_now",
    "stop_all_browsers", "refresh_fingerprint", "update_adspower_patch",
    "ensure_schema",  # PR-AutoSchema — 워커에 schema 재보장 명령. result ack 로 보고.
    "shell_exec",     # Slice 1: 원격 PowerShell 단발 실행 — payload {shell, script, timeout_sec}.
    # Slice 2.4: admin agent → desktop worker process 관리.
    # admin_agent role worker 가 받음. server routing 은 여전히 worker_id 단일이라
    # 운영자가 admin_agent worker_id 로 발행해야 함 (admin UI 에서 직접 또는
    # convenience endpoint 후속).
    "desktop_status",
    "desktop_start",
    "desktop_stop",
    "desktop_restart",
    # Slice 2.5: cutover (legacy HydraWorker Task Scheduler disable + desktop
    # restart) + agent-owned update. worker.commands.execute_command 에서
    # HYDRA_PROCESS_ROLE=admin_agent guard 검증.
    "desktop_cutover_status",
    "desktop_cutover_apply",
    "agent_update_now",
    # Slice 3.3 — admin agent self-restart (ack-then-spawn detached helper).
    "agent_self_restart",
    # Phase 4 Slice 4.1a — web terminal lifecycle commands (admin_agent only).
    "terminal_open",
    "terminal_close",
    "terminal_interrupt",
})


# Phase 3 Slice 3.1 — command policy map. admin_agent runtime 전용 명령을
# 발행 시점에 자동 라우팅 + heartbeat lease 시 role 검증.
# desktop_worker 전용은 현재 없음 (모든 task automation 은 envelope 로 분배).
_CMD_REQUIRED_ROLE: dict[str, str] = {
    "desktop_status": "admin_agent",
    "desktop_start": "admin_agent",
    "desktop_stop": "admin_agent",
    "desktop_restart": "admin_agent",
    "desktop_cutover_status": "admin_agent",
    "desktop_cutover_apply": "admin_agent",
    "agent_update_now": "admin_agent",
    "agent_self_restart": "admin_agent",
    # Phase 4 Slice 4.1a — web terminal admin_agent 전용.
    "terminal_open": "admin_agent",
    "terminal_close": "admin_agent",
    "terminal_interrupt": "admin_agent",
}


def _resolve_command_target(
    db, worker_id: int, command: str, override: Optional[str],
) -> tuple[Worker, Optional[str]]:
    """발행 시점 auto-route + target_role 결정.

    1) 명령에 required_role 이 있고 worker.role 가 다르면 paired worker 로 rewrite.
       paired 매칭: admin_agent.parent_worker_id == desktop_worker.id.
       - desktop_worker 에 admin_only 명령 → 이 desktop 을 가리키는 admin_agent 들 검색
         · 0개 → 409 no paired
         · 2개 이상 → 409 ambiguous (비결정적 routing 금지)
         · 1개 → rewrite
       - admin_agent 에 desktop_only 명령 → parent_worker_id 가 가리키는 desktop
    2) override (req.target_role) 있으면 우선. invalid value 또는 resolved
       worker.role 와 mismatch 면 400.
    3) 일반 명령 (정책 없음, override 없음) 은 target_role=NULL 박음 — role 변경
       에 면역이며 UI 가 routing 표시 안 함 (Codex Slice 3.1 review 권고).
    """
    worker = db.get(Worker, worker_id)
    if worker is None:
        raise HTTPException(404, "worker not found")

    required = _CMD_REQUIRED_ROLE.get(command)

    if override is not None and override not in ("desktop_worker", "admin_agent"):
        raise HTTPException(400, f"invalid target_role: {override}")

    # admin-only 명령을 잘못된 role 에 발행한 경우 auto-route
    if required and worker.role != required:
        if required == "admin_agent" and worker.role == "desktop_worker":
            candidates = (
                db.query(Worker)
                .filter(
                    Worker.role == "admin_agent",
                    Worker.parent_worker_id == worker.id,
                )
                .all()
            )
            if len(candidates) == 0:
                raise HTTPException(
                    409,
                    f"no paired admin_agent for worker_id={worker_id} "
                    f"(role={worker.role}); command {command} requires admin_agent",
                )
            if len(candidates) > 1:
                raise HTTPException(
                    409,
                    f"ambiguous paired admin_agent for worker_id={worker_id} "
                    f"({len(candidates)} candidates); operator must issue directly",
                )
            worker = candidates[0]
        elif required == "desktop_worker" and worker.role == "admin_agent":
            paired = None
            if worker.parent_worker_id is not None:
                p = db.get(Worker, worker.parent_worker_id)
                if p is not None and p.role == "desktop_worker":
                    paired = p
            if paired is None:
                raise HTTPException(
                    409,
                    f"no paired desktop_worker for worker_id={worker_id} "
                    f"(role={worker.role}); command {command} requires desktop_worker",
                )
            worker = paired
        else:
            raise HTTPException(
                409,
                f"cannot auto-route {command} (required={required}) from "
                f"worker_id={worker_id} role={worker.role}",
            )

    # override 가 있으면 최종 worker.role 와 다시 검증
    if override is not None and worker.role != override:
        raise HTTPException(
            400,
            f"target_role={override} mismatches resolved worker role {worker.role}",
        )

    # final_target 결정:
    #  - override 있으면 그것
    #  - required 있으면 그것 (auto-route 후라 worker.role == required 보장)
    #  - 둘 다 없으면 NULL (일반 명령은 routing 정책 비대상)
    final_target = override if override is not None else required
    return worker, final_target


# Slice 1 — shell_exec 가드 상한. 운영자가 보내는 script 의 크기/실행 시간/출력량 제한.
SHELL_MAX_SCRIPT_LEN = 8000          # 8KB
SHELL_MAX_TIMEOUT_SEC = 120          # 2분
SHELL_DEFAULT_TIMEOUT_SEC = 30
SHELL_ALLOWED_SHELLS = frozenset({"powershell", "sh"})


def _validate_shell_exec_payload(payload: Optional[dict]) -> dict:
    """shell_exec payload 검증 + 정규화. dict 반환.

    Slice 1 follow-up — generic /command 와 convenience /shell 양쪽 모두 같은
    가드를 적용하기 위한 helper. /shell 에서만 가드하던 게 generic 우회 가능.

    raises HTTPException(400) on:
      - payload not dict / missing 'script'
      - script empty 또는 8000 자 초과
      - shell 화이트리스트 밖 (default 'powershell')
      - timeout_sec 1..120 밖 (default 30)
    """
    if not isinstance(payload, dict):
        raise HTTPException(400, "shell_exec: payload must be an object with 'script'")

    script = payload.get("script")
    if not isinstance(script, str) or not script:
        raise HTTPException(400, "shell_exec: 'script' must be a non-empty string")
    if len(script) > SHELL_MAX_SCRIPT_LEN:
        raise HTTPException(
            400, f"shell_exec: script length {len(script)} exceeds limit {SHELL_MAX_SCRIPT_LEN}",
        )

    shell = payload.get("shell", "powershell")
    if shell not in SHELL_ALLOWED_SHELLS:
        raise HTTPException(
            400, f"shell_exec: shell must be one of {sorted(SHELL_ALLOWED_SHELLS)}, got {shell!r}",
        )

    timeout_sec = payload.get("timeout_sec", SHELL_DEFAULT_TIMEOUT_SEC)
    try:
        timeout_sec = int(timeout_sec)
    except (TypeError, ValueError):
        raise HTTPException(400, "shell_exec: timeout_sec must be an integer")
    if not (1 <= timeout_sec <= SHELL_MAX_TIMEOUT_SEC):
        raise HTTPException(
            400, f"shell_exec: timeout_sec must be 1..{SHELL_MAX_TIMEOUT_SEC}, got {timeout_sec}",
        )

    return {"shell": shell, "script": script, "timeout_sec": timeout_sec}


class CommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=64)
    payload: Optional[dict] = None
    # Phase 3 — 운영자가 명시적으로 대상 role 지정. 없으면 _CMD_REQUIRED_ROLE
    # 또는 대상 worker.role 로 자동 결정.
    target_role: Optional[str] = None


class CommandOut(BaseModel):
    id: int
    worker_id: int
    command: str
    payload: Optional[dict] = None
    status: str
    issued_at: str
    delivered_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error_message: Optional[str] = None
    # Phase 3 — 명령에 박힌 target_role. heartbeat lease 시 worker.role 검증용.
    target_role: Optional[str] = None
    # Phase 3 — auto-route 발생 시 원래 발행 worker_id (감사 용).
    requested_worker_id: Optional[int] = None


@router.post("/{worker_id}/command", response_model=CommandOut)
def issue_command(
    worker_id: int,
    req: CommandRequest,
    session: dict = Depends(admin_session),
) -> CommandOut:
    """어드민이 워커에 명령 발행 — heartbeat 응답으로 전달됨.

    Slice 1 follow-up — shell_exec 발행 시 generic 경로도 /shell convenience
    endpoint 와 동일한 validation + 정규화. payload bypass 차단.
    """
    if req.command not in ALLOWED_COMMANDS:
        raise HTTPException(400, f"unknown command: {req.command}. allowed: {sorted(ALLOWED_COMMANDS)}")

    payload = req.payload
    if req.command == "shell_exec":
        payload = _validate_shell_exec_payload(payload)

    from hydra.db.models import WorkerCommand
    db = _db_session.SessionLocal()
    try:
        # Phase 3 Slice 3.1 — 발행 시점 auto-route + target_role 결정.
        worker, target_role = _resolve_command_target(
            db, worker_id, req.command, req.target_role,
        )
        cmd = WorkerCommand(
            worker_id=worker.id,
            command=req.command,
            payload=json.dumps(payload, ensure_ascii=False) if payload else None,
            status="pending",
            issued_by=session.get("user_id"),
            issued_at=datetime.now(UTC),
            target_role=target_role,
        )
        db.add(cmd)
        db.commit()
        db.refresh(cmd)
        return CommandOut(
            id=cmd.id, worker_id=cmd.worker_id, command=cmd.command,
            payload=payload, status=cmd.status,
            issued_at=cmd.issued_at.isoformat(),
            target_role=cmd.target_role,
            requested_worker_id=(worker_id if worker.id != worker_id else None),
        )
    finally:
        db.close()


# Slice 1 — 원격 PowerShell 단발 실행 convenience endpoint.
# 내부적으로 WorkerCommand(command="shell_exec") 발행. 결과는 기존 /commands list 에서 확인.
class ShellExecRequest(BaseModel):
    script: str = Field(..., min_length=1)
    shell: str = "powershell"
    timeout_sec: int = SHELL_DEFAULT_TIMEOUT_SEC


@router.post("/{worker_id}/shell", response_model=CommandOut)
def issue_shell(
    worker_id: int,
    req: ShellExecRequest,
    session: dict = Depends(admin_session),
) -> CommandOut:
    """원격 워커 PC 에 단발 PowerShell 명령 실행. 결과는 command result 로 조회.

    Slice 1 — Worker Admin Agent redesign. 운영자가 워커 PC 에 물리 접근 없이
    진단/복구 가능하도록 만드는 첫 채널. ALLOWED_COMMANDS 의 일반 발행 경로
    대비 script 길이/timeout/shell 화이트리스트 가드 추가.
    """
    # Slice 1 follow-up — generic /command 경로와 같은 _validate_shell_exec_payload
    # helper 로 검증. 두 경로 모두 동일한 가드 적용 보장.
    payload = _validate_shell_exec_payload({
        "shell": req.shell,
        "script": req.script,
        "timeout_sec": req.timeout_sec,
    })

    from hydra.db.models import WorkerCommand
    db = _db_session.SessionLocal()
    try:
        # Phase 3 Slice 3.1 — generic /command 와 동일하게 _resolve_command_target
        # 거침. shell_exec 는 _CMD_REQUIRED_ROLE 에 없어서 target_role=NULL
        # 박힘 (일반 명령 정책). /shell convenience 경로가 정책 우회하지
        # 않도록 보장 (Codex review 권고).
        worker, target_role = _resolve_command_target(
            db, worker_id, "shell_exec", None,
        )
        cmd = WorkerCommand(
            worker_id=worker.id,
            command="shell_exec",
            payload=json.dumps(payload, ensure_ascii=False),
            status="pending",
            issued_by=session.get("user_id"),
            issued_at=datetime.now(UTC),
            target_role=target_role,
        )
        db.add(cmd)
        db.commit()
        db.refresh(cmd)
        return CommandOut(
            id=cmd.id, worker_id=cmd.worker_id, command=cmd.command,
            payload=payload, status=cmd.status,
            issued_at=cmd.issued_at.isoformat(),
            target_role=cmd.target_role,
            requested_worker_id=(worker_id if worker.id != worker_id else None),
        )
    finally:
        db.close()


@router.get("/{worker_id}/commands", response_model=list[CommandOut])
def list_commands(
    worker_id: int,
    _session: dict = Depends(admin_session),
    limit: int = 50,
) -> list[CommandOut]:
    """워커의 최근 명령 이력."""
    from hydra.db.models import WorkerCommand
    limit = max(1, min(limit, 500))
    db = _db_session.SessionLocal()
    try:
        rows = (
            db.query(WorkerCommand)
            .filter(WorkerCommand.worker_id == worker_id)
            .order_by(WorkerCommand.issued_at.desc())
            .limit(limit)
            .all()
        )
        out = []
        for c in rows:
            payload = None
            if c.payload:
                try:
                    payload = json.loads(c.payload)
                except Exception:
                    payload = {"_raw": c.payload[:500]}
            out.append(CommandOut(
                id=c.id, worker_id=c.worker_id, command=c.command,
                payload=payload, status=c.status,
                issued_at=c.issued_at.isoformat(),
                delivered_at=c.delivered_at.isoformat() if c.delivered_at else None,
                completed_at=c.completed_at.isoformat() if c.completed_at else None,
                result=c.result, error_message=c.error_message,
                target_role=c.target_role,
            ))
        return out
    finally:
        db.close()


# ───────────── 라이브 로그 (verbose mode 으로 푸시된 INFO+) ─────────────
class LogTailEntryOut(BaseModel):
    id: int
    occurred_at: str
    received_at: str
    level: str
    logger_name: Optional[str] = None
    message: str


@router.get("/{worker_id}/log-tail")
def get_log_tail(
    worker_id: int,
    _session: dict = Depends(admin_session),
    limit: int = 200,
    after_id: Optional[int] = None,
) -> list[LogTailEntryOut]:
    """워커가 verbose_mode 로 푸시한 INFO+ 로그.

    after_id: 폴링 시 이전 마지막 id 보다 큰 것만 (incremental fetch).
    """
    from hydra.db.models import WorkerLogTail
    limit = max(1, min(limit, 1000))
    db = _db_session.SessionLocal()
    try:
        if db.get(Worker, worker_id) is None:
            raise HTTPException(404, "worker not found")
        q = db.query(WorkerLogTail).filter(WorkerLogTail.worker_id == worker_id)
        if after_id is not None:
            q = q.filter(WorkerLogTail.id > after_id)
        rows = q.order_by(WorkerLogTail.id.desc()).limit(limit).all()
        rows = list(reversed(rows))  # 시간 오름차순
        return [
            LogTailEntryOut(
                id=r.id,
                occurred_at=r.occurred_at.isoformat(),
                received_at=r.received_at.isoformat(),
                level=r.level,
                logger_name=r.logger_name,
                message=r.message,
            )
            for r in rows
        ]
    finally:
        db.close()


# ───────────── T8 Exit IP 감시 ─────────────
class IpHistoryEntry(BaseModel):
    account_id: int
    account_gmail: str
    ip_address: str
    device_id: Optional[str] = None
    started_at: str
    ended_at: Optional[str] = None
    duration_sec: Optional[int] = None


class IpConflictEntry(BaseModel):
    ip_address: str
    accounts: list[dict]  # [{account_id, gmail, started_at}]
    conflict_at: str


@router.get("/ip-history")
def ip_history(
    _session: dict = Depends(admin_session),
    hours: int = 24,
    limit: int = 500,
) -> list[IpHistoryEntry]:
    """최근 N시간 (기본 24h) 의 exit IP 사용 이력. 시간 내림차순."""
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from hydra.db.models import Account, IpLog

    limit = max(1, min(limit, 5000))
    cutoff = _dt.now(_tz.utc) - _td(hours=max(1, min(hours, 168)))

    db = _db_session.SessionLocal()
    try:
        rows = (
            db.query(IpLog, Account)
            .join(Account, IpLog.account_id == Account.id)
            .filter(IpLog.started_at >= cutoff)
            .order_by(IpLog.started_at.desc())
            .limit(limit)
            .all()
        )
        out = []
        for log, acc in rows:
            duration = None
            if log.ended_at and log.started_at:
                duration = int((log.ended_at - log.started_at).total_seconds())
            out.append(IpHistoryEntry(
                account_id=acc.id,
                account_gmail=acc.gmail,
                ip_address=log.ip_address,
                device_id=log.device_id,
                started_at=log.started_at.isoformat(),
                ended_at=log.ended_at.isoformat() if log.ended_at else None,
                duration_sec=duration,
            ))
        return out
    finally:
        db.close()


@router.get("/ip-conflicts")
def ip_conflicts(
    _session: dict = Depends(admin_session),
    hours: int = 24,
) -> list[IpConflictEntry]:
    """같은 IP 가 짧은 시간 내 여러 계정에서 사용된 케이스 (안티디텍션 위험).

    윈도우 내 동일 IP × 2+ 계정 → conflict.
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from hydra.db.models import Account, IpLog
    from collections import defaultdict

    cutoff = _dt.now(_tz.utc) - _td(hours=max(1, min(hours, 168)))

    db = _db_session.SessionLocal()
    try:
        rows = (
            db.query(IpLog, Account)
            .join(Account, IpLog.account_id == Account.id)
            .filter(IpLog.started_at >= cutoff)
            .order_by(IpLog.started_at.desc())
            .all()
        )
        by_ip: dict[str, list] = defaultdict(list)
        for log, acc in rows:
            by_ip[log.ip_address].append({
                "account_id": acc.id, "gmail": acc.gmail,
                "started_at": log.started_at.isoformat(),
            })

        conflicts = []
        for ip, uses in by_ip.items():
            unique_accounts = {u["account_id"] for u in uses}
            if len(unique_accounts) > 1:
                conflicts.append(IpConflictEntry(
                    ip_address=ip,
                    accounts=uses,
                    conflict_at=uses[0]["started_at"],
                ))
        return conflicts
    finally:
        db.close()
