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


class EnrollResponse(BaseModel):
    enrollment_token: str
    install_command: str
    expires_in_hours: int


@router.post("/enroll", response_model=EnrollResponse)
def create_enrollment(
    req: EnrollRequest,
    _session: dict = Depends(admin_session),
) -> EnrollResponse:
    name = req.worker_name.strip()
    if not name:
        raise HTTPException(400, "worker_name required")

    token = generate_enrollment_token(name, ttl_hours=req.ttl_hours)
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
        AccountProfileHistory, ExecutionLog,
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
})


# Slice 1 — shell_exec 가드 상한. 운영자가 보내는 script 의 크기/실행 시간/출력량 제한.
SHELL_MAX_SCRIPT_LEN = 8000          # 8KB
SHELL_MAX_TIMEOUT_SEC = 120          # 2분
SHELL_DEFAULT_TIMEOUT_SEC = 30
SHELL_ALLOWED_SHELLS = frozenset({"powershell", "sh"})


class CommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=64)
    payload: Optional[dict] = None


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


@router.post("/{worker_id}/command", response_model=CommandOut)
def issue_command(
    worker_id: int,
    req: CommandRequest,
    session: dict = Depends(admin_session),
) -> CommandOut:
    """어드민이 워커에 명령 발행 — heartbeat 응답으로 전달됨."""
    if req.command not in ALLOWED_COMMANDS:
        raise HTTPException(400, f"unknown command: {req.command}. allowed: {sorted(ALLOWED_COMMANDS)}")
    from hydra.db.models import WorkerCommand
    db = _db_session.SessionLocal()
    try:
        if db.get(Worker, worker_id) is None:
            raise HTTPException(404, "worker not found")
        cmd = WorkerCommand(
            worker_id=worker_id,
            command=req.command,
            payload=json.dumps(req.payload, ensure_ascii=False) if req.payload else None,
            status="pending",
            issued_by=session.get("user_id"),
            issued_at=datetime.now(UTC),
        )
        db.add(cmd)
        db.commit()
        db.refresh(cmd)
        return CommandOut(
            id=cmd.id, worker_id=cmd.worker_id, command=cmd.command,
            payload=req.payload, status=cmd.status,
            issued_at=cmd.issued_at.isoformat(),
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
    if req.shell not in SHELL_ALLOWED_SHELLS:
        raise HTTPException(
            400, f"shell must be one of {sorted(SHELL_ALLOWED_SHELLS)}, got {req.shell!r}",
        )
    if len(req.script) > SHELL_MAX_SCRIPT_LEN:
        raise HTTPException(
            400, f"script length {len(req.script)} exceeds limit {SHELL_MAX_SCRIPT_LEN}",
        )
    if not (1 <= req.timeout_sec <= SHELL_MAX_TIMEOUT_SEC):
        raise HTTPException(
            400, f"timeout_sec must be 1..{SHELL_MAX_TIMEOUT_SEC}, got {req.timeout_sec}",
        )

    from hydra.db.models import WorkerCommand
    payload = {
        "shell": req.shell,
        "script": req.script,
        "timeout_sec": req.timeout_sec,
    }
    db = _db_session.SessionLocal()
    try:
        if db.get(Worker, worker_id) is None:
            raise HTTPException(404, "worker not found")
        cmd = WorkerCommand(
            worker_id=worker_id,
            command="shell_exec",
            payload=json.dumps(payload, ensure_ascii=False),
            status="pending",
            issued_by=session.get("user_id"),
            issued_at=datetime.now(UTC),
        )
        db.add(cmd)
        db.commit()
        db.refresh(cmd)
        return CommandOut(
            id=cmd.id, worker_id=cmd.worker_id, command=cmd.command,
            payload=payload, status=cmd.status,
            issued_at=cmd.issued_at.isoformat(),
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
