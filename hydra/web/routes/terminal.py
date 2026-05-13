"""Phase 4 Slice 4.1a — Web terminal session lifecycle.

Endpoints:
  admin (admin_session):
    POST   /api/admin/workers/{worker_id}/terminal/open   → {session_id, session_token, command_id}
    POST   /api/admin/terminal/{session_id}/close         → 204
    GET    /api/admin/terminal/{session_id}               → status / metadata

  worker callbacks (X-Worker-Token + session_token):
    POST   /api/workers/terminal/{session_id}/active      → pending → active
    POST   /api/workers/terminal/{session_id}/closed      → closing → closed
    POST   /api/workers/terminal/{session_id}/failed      → pending → failed

Lifecycle:
  pending → active → closing → closed
       └─→ failed (spawn 실패 등)
       └─→ timeout (idle / closing 60s 초과 by batch)

partial unique index 가 같은 worker 의 pending/active/closing 세션 1개만
허용. 409 race-safe.
"""
from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from hydra.db import session as _db_session
from hydra.db.models import TerminalInput, TerminalSession, Worker, WorkerCommand
from hydra.web.routes.admin_auth import admin_session
from hydra.web.routes.worker_api import worker_auth


router = APIRouter()


# Phase 4 Slice 4.1a — closing 상태가 영구 고착되지 않도록 강제 close 시한.
# unique index 가 (worker_id) on (pending,active,closing) 이라 closing 이
# 풀리지 않으면 새 terminal 못 엶. batch 가 60초 초과 closing → closed
# (forced) 로 강제. 4.4 의 timeout 정책과 별개로 4.1a 부터 활성화.
CLOSING_FORCED_TIMEOUT_SEC = 60


def _force_close_stale_closing(db) -> int:
    """closing 상태가 60초 초과면 forced close. heartbeat / admin endpoint 호출
    시 hook 으로 부르거나 별도 batch 가능. Slice 4.1a 는 hook 으로만 호출.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=CLOSING_FORCED_TIMEOUT_SEC)
    rows = (
        db.query(TerminalSession)
        .filter(
            TerminalSession.status == "closing",
            TerminalSession.closing_at.isnot(None),
            TerminalSession.closing_at < cutoff,
        )
        .all()
    )
    now = datetime.now(UTC)
    for s in rows:
        s.status = "closed"
        s.closed_at = now
        prev = s.error_message or ""
        msg = "force_closed_after_closing_timeout"
        s.error_message = (prev + " | " + msg) if prev else msg
    return len(rows)


class TerminalOpenRequest(BaseModel):
    shell: str = Field(default="powershell")


class TerminalOpenResponse(BaseModel):
    session_id: int
    session_token: str
    command_id: int
    worker_id: int
    requested_worker_id: Optional[int] = None
    status: str


class TerminalInfo(BaseModel):
    session_id: int
    worker_id: int
    opened_by: Optional[int] = None
    opened_at: str
    last_activity_at: str
    closing_at: Optional[str] = None
    closed_at: Optional[str] = None
    status: str
    shell: str
    error_message: Optional[str] = None


def _to_info(s: TerminalSession) -> TerminalInfo:
    def _iso(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat()
    return TerminalInfo(
        session_id=s.id, worker_id=s.worker_id,
        opened_by=s.opened_by,
        opened_at=_iso(s.opened_at),
        last_activity_at=_iso(s.last_activity_at),
        closing_at=_iso(s.closing_at), closed_at=_iso(s.closed_at),
        status=s.status, shell=s.shell, error_message=s.error_message,
    )


@router.post(
    "/admin/workers/{worker_id}/terminal/open",
    response_model=TerminalOpenResponse,
)
def open_terminal(
    worker_id: int,
    req: TerminalOpenRequest,
    session: dict = Depends(admin_session),
) -> TerminalOpenResponse:
    """관리자 터미널 세션 열기. target_role=admin_agent 자동 라우팅.

    409: 같은 worker 에 pending/active/closing 세션 이미 있음 (partial unique).
    400: shell 화이트리스트 밖.
    """
    if req.shell not in ("powershell", "sh"):
        raise HTTPException(400, f"invalid shell: {req.shell!r}")

    from hydra.web.routes.admin_workers import _resolve_command_target

    db = _db_session.SessionLocal()
    try:
        # admin_agent 로 자동 라우팅. desktop_worker 발행 시 paired admin_agent
        # 로 rewrite (Slice 3.1). paired 없으면 409.
        worker, target_role = _resolve_command_target(
            db, worker_id, "terminal_open", None,
        )
        # 강제 close 청소 — 같은 worker 의 closing 60초 초과 정리해야
        # partial unique 가 막지 않게.
        _force_close_stale_closing(db)

        session_token = secrets.token_urlsafe(32)
        ts = TerminalSession(
            worker_id=worker.id,
            opened_by=session.get("user_id"),
            opened_at=datetime.now(UTC),
            last_activity_at=datetime.now(UTC),
            status="pending",
            shell=req.shell,
            session_token=session_token,
        )
        db.add(ts)
        try:
            db.flush()  # unique index 즉시 평가
        except IntegrityError:
            # partial unique 위반 → 이미 active/pending/closing 세션 있음
            db.rollback()
            raise HTTPException(
                409,
                f"worker {worker.id} already has an open terminal session",
            )

        payload = {
            "session_id": ts.id,
            "session_token": session_token,
            "shell": req.shell,
        }
        cmd = WorkerCommand(
            worker_id=worker.id,
            command="terminal_open",
            payload=json.dumps(payload, ensure_ascii=False),
            status="pending",
            issued_by=session.get("user_id"),
            issued_at=datetime.now(UTC),
            target_role=target_role,
        )
        db.add(cmd)
        db.commit()
        db.refresh(ts); db.refresh(cmd)
        return TerminalOpenResponse(
            session_id=ts.id,
            session_token=session_token,
            command_id=cmd.id,
            worker_id=worker.id,
            requested_worker_id=(worker_id if worker.id != worker_id else None),
            status=ts.status,
        )
    finally:
        db.close()


@router.post("/admin/terminal/{session_id}/close")
def close_terminal(
    session_id: int,
    session: dict = Depends(admin_session),
) -> dict:
    """admin close 요청 — 2-phase. status=closing 마킹 + worker 에 close command.
    실제 closed 는 worker 가 process 종료 후 /closed POST.
    """
    db = _db_session.SessionLocal()
    try:
        ts = db.get(TerminalSession, session_id)
        if ts is None:
            raise HTTPException(404, "terminal session not found")
        # 종료 상태 또는 이미 closing 인 경우 idempotent noop — 중복 명령
        # 발행 방지 (Codex Slice 4.1a review 권고).
        if ts.status in ("closed", "timeout", "failed", "closing"):
            return {"ok": True, "status": ts.status, "noop": True}
        ts.status = "closing"
        ts.closing_at = datetime.now(UTC)
        ts.last_activity_at = datetime.now(UTC)
        # Slice 4.1b — worker dispatcher 가 session_token 도 필요로 함
        # (callback POST 인증 + registry 조회). payload 에 같이 박음.
        cmd = WorkerCommand(
            worker_id=ts.worker_id,
            command="terminal_close",
            payload=json.dumps(
                {"session_id": ts.id, "session_token": ts.session_token},
                ensure_ascii=False,
            ),
            status="pending",
            issued_by=session.get("user_id"),
            issued_at=datetime.now(UTC),
            target_role="admin_agent",
        )
        db.add(cmd)
        db.commit()
        return {"ok": True, "status": ts.status, "command_id": cmd.id}
    finally:
        db.close()


@router.get("/admin/terminal/{session_id}", response_model=TerminalInfo)
def get_terminal_info(
    session_id: int,
    _session: dict = Depends(admin_session),
) -> TerminalInfo:
    db = _db_session.SessionLocal()
    try:
        ts = db.get(TerminalSession, session_id)
        if ts is None:
            raise HTTPException(404, "terminal session not found")
        return _to_info(ts)
    finally:
        db.close()


# ─────────────── Worker callbacks ───────────────
# X-Worker-Token + session.worker_id 일치 + X-Terminal-Session-Token 3중 검증.

def _verify_worker_session(
    db, session_id: int, worker: Worker, session_token: str,
) -> TerminalSession:
    ts = db.get(TerminalSession, session_id)
    if ts is None:
        raise HTTPException(404, "terminal session not found")
    if ts.worker_id != worker.id:
        raise HTTPException(403, "session not owned by this worker")
    if not session_token or not secrets.compare_digest(ts.session_token, session_token):
        raise HTTPException(403, "invalid session_token")
    return ts


@router.post("/workers/terminal/{session_id}/active")
def worker_mark_active(
    session_id: int,
    worker: Worker = Depends(worker_auth),
    x_terminal_session_token: str = Header(default=""),
) -> dict:
    """워커가 shell process spawn 후 호출. pending → active."""
    db = _db_session.SessionLocal()
    try:
        ts = _verify_worker_session(db, session_id, worker, x_terminal_session_token)
        if ts.status == "active":
            return {"ok": True, "status": ts.status, "noop": True}
        if ts.status != "pending":
            raise HTTPException(
                409, f"terminal not pending (status={ts.status})",
            )
        ts.status = "active"
        ts.last_activity_at = datetime.now(UTC)
        db.commit()
        return {"ok": True, "status": ts.status}
    finally:
        db.close()


@router.post("/workers/terminal/{session_id}/closed")
def worker_mark_closed(
    session_id: int,
    worker: Worker = Depends(worker_auth),
    x_terminal_session_token: str = Header(default=""),
) -> dict:
    """워커가 shell process 종료 확인 후 호출. closing → closed.
    active 에서 직접 받아도 OK (워커 자체 crash 후 detect 등)."""
    db = _db_session.SessionLocal()
    try:
        ts = _verify_worker_session(db, session_id, worker, x_terminal_session_token)
        if ts.status == "closed":
            return {"ok": True, "status": ts.status, "noop": True}
        ts.status = "closed"
        ts.closed_at = datetime.now(UTC)
        ts.last_activity_at = datetime.now(UTC)
        db.commit()
        return {"ok": True, "status": ts.status}
    finally:
        db.close()


# ─────────────── Phase 4 Slice 4.2a — input queue ───────────────

INPUT_MAX_BYTES = 8 * 1024  # 8KB per single input


class TerminalInputRequest(BaseModel):
    data: str


class TerminalInputOut(BaseModel):
    id: int
    seq: int
    data: str
    byte_size: int
    produced_at: str


def _iso_or_none(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


@router.post("/admin/terminal/{session_id}/input")
def admin_post_input(
    session_id: int,
    req: TerminalInputRequest,
    _session: dict = Depends(admin_session),
) -> dict:
    """admin UI 에서 stdin 데이터 발행. active 세션만 허용. data 8KB 상한."""
    data = req.data
    if not isinstance(data, str):
        raise HTTPException(400, "data must be string")
    byte_size = len(data.encode("utf-8"))
    if byte_size == 0:
        raise HTTPException(400, "data cannot be empty")
    if byte_size > INPUT_MAX_BYTES:
        raise HTTPException(400, f"input exceeds {INPUT_MAX_BYTES} bytes")

    # Codex Slice 4.2a blocker fix: seq race 회피.
    # max(seq)+1 lock 없이 계산하면 동시 /input 시 같은 seq → unique violation.
    # IntegrityError retry 로 안전. retry 횟수 제한 (무한 loop 방지).
    MAX_SEQ_RETRY = 5
    db = _db_session.SessionLocal()
    try:
        for attempt in range(MAX_SEQ_RETRY):
            ts = db.get(TerminalSession, session_id)
            if ts is None:
                raise HTTPException(404, "terminal session not found")
            if ts.status != "active":
                raise HTTPException(
                    409, f"input only valid on active session (status={ts.status})",
                )

            # seq: 같은 session 안에서 max+1
            prev_max = (
                db.query(TerminalInput)
                .filter(TerminalInput.session_id == session_id)
                .order_by(TerminalInput.seq.desc())
                .first()
            )
            next_seq = (prev_max.seq + 1) if prev_max is not None else 1

            ti = TerminalInput(
                session_id=session_id, seq=next_seq, data=data,
                byte_size=byte_size, produced_at=datetime.now(UTC),
            )
            db.add(ti)
            ts.last_activity_at = datetime.now(UTC)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                if attempt == MAX_SEQ_RETRY - 1:
                    raise HTTPException(
                        500, "input seq race could not be resolved after retries",
                    )
                # 다음 iteration 으로 retry
                continue
            db.refresh(ti)
            return {"ok": True, "id": ti.id, "seq": ti.seq, "byte_size": byte_size}
    finally:
        db.close()


@router.get("/workers/terminal/{session_id}/inputs")
def worker_get_inputs(
    session_id: int,
    after_seq: int = 0,
    worker: Worker = Depends(worker_auth),
    x_terminal_session_token: str = Header(default=""),
) -> dict:
    """워커 short-poll. after_seq 이후 input list 반환 (최대 100건)."""
    db = _db_session.SessionLocal()
    try:
        ts = _verify_worker_session(db, session_id, worker, x_terminal_session_token)
        rows = (
            db.query(TerminalInput)
            .filter(
                TerminalInput.session_id == session_id,
                TerminalInput.seq > after_seq,
            )
            .order_by(TerminalInput.seq.asc())
            .limit(100)
            .all()
        )
        items = [
            {
                "id": r.id, "seq": r.seq, "data": r.data,
                "byte_size": r.byte_size,
                "produced_at": _iso_or_none(r.produced_at),
            }
            for r in rows
        ]
        return {"ok": True, "inputs": items, "status": ts.status}
    finally:
        db.close()


@router.post("/workers/terminal/{session_id}/input-consumed")
def worker_report_consumed(
    session_id: int,
    consumed_seq: int = 0,
    worker: Worker = Depends(worker_auth),
    x_terminal_session_token: str = Header(default=""),
) -> dict:
    """워커가 어디까지 stdin write 완료했는지 보고. consumed_seq 이하 row 의
    consumed_at 마킹 + last_activity_at 갱신.
    """
    db = _db_session.SessionLocal()
    try:
        ts = _verify_worker_session(db, session_id, worker, x_terminal_session_token)
        now = datetime.now(UTC)
        updated = (
            db.query(TerminalInput)
            .filter(
                TerminalInput.session_id == session_id,
                TerminalInput.seq <= consumed_seq,
                TerminalInput.consumed_at.is_(None),
            )
            .update({TerminalInput.consumed_at: now}, synchronize_session=False)
        )
        ts.last_activity_at = now
        db.commit()
        return {"ok": True, "updated": updated}
    finally:
        db.close()


@router.post("/workers/terminal/{session_id}/failed")
def worker_mark_failed(
    session_id: int,
    worker: Worker = Depends(worker_auth),
    x_terminal_session_token: str = Header(default=""),
    error: str = "",
) -> dict:
    """워커가 shell spawn 실패 등 즉시 fail 보고.

    pending → failed 만 허용 (Codex Slice 4.1a review blocker).
    active/closing/closed/timeout/failed 에 늦은 /failed 콜백이 와서 덮어쓰는
    것 금지 — 그러면 partial unique 가 풀려 새 terminal 가 열리는데 실제
    shell process 는 살아 있을 위험.
    """
    db = _db_session.SessionLocal()
    try:
        ts = _verify_worker_session(db, session_id, worker, x_terminal_session_token)
        if ts.status == "failed":
            return {"ok": True, "status": ts.status, "noop": True}
        if ts.status != "pending":
            raise HTTPException(
                409,
                f"terminal /failed only valid from pending (current status={ts.status})",
            )
        ts.status = "failed"
        ts.closed_at = datetime.now(UTC)
        ts.last_activity_at = datetime.now(UTC)
        if error:
            ts.error_message = (
                (ts.error_message + " | " + error) if ts.error_message else error
            )
        db.commit()
        return {"ok": True, "status": ts.status}
    finally:
        db.close()
