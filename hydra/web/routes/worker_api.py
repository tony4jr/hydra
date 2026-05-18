"""워커 전용 엔드포인트 — enrollment 토큰 소비 + v2 heartbeat.

Legacy `/api/workers/register`, `/api/workers/heartbeat` (hydra.api.workers) 는 당분간
공존. 신규 워커는 아래 flow 사용:

  1. POST /api/workers/enroll   : enrollment_token → worker_token + shared secrets
  2. POST /api/workers/heartbeat/v2 : X-Worker-Token → {current_version, paused, canary}
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets as _secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, and_

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, Form
from fastapi.responses import PlainTextResponse, Response
from pathlib import Path as _Path
from pydantic import BaseModel, Field

from hydra.core import server_config as scfg
from hydra.core.auth import hash_password, verify_password
from hydra.core.enrollment import verify_enrollment_token
from hydra.db import session as _db_session
from hydra.db.models import Account, AccountEvent, ScreenResolution, Task, Worker, WorkerError, WorkerCommand

router = APIRouter()


_SETUP_PS1 = _Path(__file__).resolve().parents[3] / "setup" / "hydra-worker-setup.ps1"
_INSTALL_BAT = _Path(__file__).resolve().parents[3] / "setup" / "install-worker.bat"
_INSTALL_HYDRA_PS1 = _Path(__file__).resolve().parents[3] / "setup" / "install-hydra.ps1"


def _no_cache_headers(extra: dict | None = None) -> dict:
    """Codex root-cause review: setup script 응답 캐시 차단 + commit hash 노출.

    nginx / browser / proxy 어디서든 옛 파일 캐시 안 되도록.
    """
    import subprocess as _sp
    try:
        head = _sp.run(
            ["git", "-C", str(_INSTALL_HYDRA_PS1.parent.parent), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        commit = head.stdout.strip() if head.returncode == 0 else "unknown"
    except Exception:
        commit = "unknown"
    h = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Hydra-Commit": commit,
    }
    if extra:
        h.update(extra)
    return h


# ──────── Slice 1 follow-up #2: lease hardening 정책 상수/헬퍼 ────────
# 무한 재전달 방지. 한 명령이 N회 lease 시도되고도 ack 못 받으면 failed.
_CMD_ATTEMPT_MAX = 3

# 워커가 ack 직후 self-exit 하는 비멱등 명령 — 만료시 재배달 금지.
# 이미 옛 프로세스가 exit 흐름에 들어갔을 수 있어 두 번째 process 가 또
# git pull / sys.exit 하면 위험.
# Slice 2.4 — desktop_restart 도 추가. agent 가 desktop process 를 stop 후
# start 하는 도중 재배달 받으면 stop-stop 또는 start-start race 위험.
# desktop_start/status/stop 은 idempotent (start: 이미 running 면 no-op,
# stop: 없으면 no-op) 이라 재배달 OK.
#
# Slice 2.5 — desktop_cutover_apply / agent_update_now 도 추가.
# cutover_apply 는 stop+disable+start 다단계라 재배달 시 partial state 위험.
# agent_update_now 는 git reset / pip install 도중 재시작되면 broken state.
_CMD_NON_REDELIVERABLE = frozenset({
    "restart",
    "update_now",
    "desktop_restart",
    "desktop_cutover_apply",
    "agent_update_now",
    # Slice 3.3 — agent_self_restart: ack 후 detached helper 가 nssm restart.
    # ack 전에 죽으면 lease 만료 후 failed (재배달 시 새 NSSM child 가 또
    # restart 시도 → restart loop 위험). 재배달 금지.
    "agent_self_restart",
    # Phase 4 Slice 4.1a — terminal_interrupt: process tree kill 은 비멱등.
    # 재배달 시 이미 죽은 process 다시 kill 시도 → 다른 PID 잡을 위험.
    # terminal_open 은 idempotent (redeliverable) — 같은 session_id 라
    # registry 검사 후 no-op.
    "terminal_interrupt",
})

# Default lease window. shell_exec 만 timeout 기반으로 길게.
_LEASE_DEFAULT_SEC = 60
_LEASE_MIN_SEC = 60
_LEASE_MAX_SEC = 300


def _compute_lease_sec(command: str, payload_obj: dict | None) -> int:
    """명령 별 lease 길이 결정.

    - shell_exec: payload.timeout_sec + 30 (script 가 timeout 까지 돌아도
      lease 만료 안 되도록). min 60, max 300.
    - 그 외: 60 고정.
    """
    if command == "shell_exec":
        raw = (payload_obj or {}).get("timeout_sec", 30)
        try:
            t = int(raw)
        except (TypeError, ValueError):
            t = 30
        return max(_LEASE_MIN_SEC, min(t + 30, _LEASE_MAX_SEC))
    return _LEASE_DEFAULT_SEC


def _append_err(cmd: WorkerCommand, msg: str) -> None:
    """error_message 누적 (heartbeat lease 정책 알림)."""
    if cmd.error_message:
        cmd.error_message = f"{cmd.error_message} | {msg}"
    else:
        cmd.error_message = msg


def _sha256_hex(s: str) -> str:
    """워커 토큰 → SHA-256 hex. 256bit 랜덤 토큰이라 bcrypt 불필요."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@router.get("/setup.ps1")
def serve_setup_ps1() -> Response:
    """Windows 워커 설치 스크립트 (legacy).

    UTF-8 BOM 을 prepend — PowerShell 5.1 (Windows 기본) 은 BOM 없으면 cp949 로
    해석해 한글 주석이 깨지며 ParseError 발생.

    Codex root-cause review: no-cache + X-Hydra-Commit 헤더 추가.
    """
    if not _SETUP_PS1.is_file():
        raise HTTPException(500, "setup script missing")
    bom = b"\xef\xbb\xbf"
    return Response(
        bom + _SETUP_PS1.read_bytes(),
        media_type="text/plain; charset=utf-8",
        headers=_no_cache_headers(),
    )


@router.get("/install-hydra.ps1")
def serve_install_hydra_ps1() -> Response:
    """Installer v2 — 단일 진입점 (desktop + admin_agent 한 번에).

    SCRIPT_VERSION placeholder 를 현재 git HEAD 로 치환해서 serve. cache 차단.
    paired enroll endpoint 의 install_command 가 이 URL 사용.
    """
    if not _INSTALL_HYDRA_PS1.is_file():
        raise HTTPException(500, "install-hydra.ps1 missing")
    import subprocess as _sp
    try:
        head = _sp.run(
            ["git", "-C", str(_INSTALL_HYDRA_PS1.parent.parent), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        commit = head.stdout.strip() if head.returncode == 0 else "unknown"
    except Exception:
        commit = "unknown"
    raw = _INSTALL_HYDRA_PS1.read_text(encoding="utf-8")
    body = raw.replace("__HYDRA_COMMIT__", commit)
    bom = b"\xef\xbb\xbf"
    return Response(
        bom + body.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers=_no_cache_headers(),
    )


@router.get("/install-worker.bat")
def serve_install_bat() -> Response:
    """더블클릭 설치 런처 — UAC 자동 + 토큰 GUI 입력창 + setup.ps1 호출.

    cmd.exe 가 LF 만으로는 라인을 잘못 파싱 → CRLF 강제.
    파일 내용은 ASCII 만 사용 (Korean 안내는 PowerShell InputBox 가 처리).
    """
    if not _INSTALL_BAT.is_file():
        raise HTTPException(500, "install bat missing")
    text = _INSTALL_BAT.read_text(encoding="utf-8")
    # LF → CRLF 정규화 (Mac/Linux 에서 작성된 파일이 cmd 에서 깨지지 않도록)
    text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    return Response(
        text.encode("ascii", errors="replace"),
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="install-worker.bat"'},
    )


# ───────────── enroll ─────────────
class EnrollRequest(BaseModel):
    enrollment_token: str
    hostname: str = Field(..., min_length=1, max_length=128)


class EnrollResponse(BaseModel):
    worker_id: int
    worker_token: str
    secrets: dict


@router.post("/enroll", response_model=EnrollResponse)
def enroll(req: EnrollRequest) -> EnrollResponse:
    try:
        data = verify_enrollment_token(req.enrollment_token)
    except Exception:
        raise HTTPException(401, "invalid enrollment token")
    worker_name = data["worker_name"]
    # Slice 3.2 — token payload 에 role/parent 박혀있음. 기본값은 legacy
    # backward compat (이미 발급된 옛 토큰 호환).
    token_role = data.get("role", "desktop_worker")
    token_parent = data.get("parent_worker_id")
    if token_role not in ("desktop_worker", "admin_agent"):
        raise HTTPException(400, f"invalid role in token: {token_role!r}")

    db = _db_session.SessionLocal()
    try:
        # Slice 3.2 — parent re-validation (consume 시점 stale token 방지).
        # 토큰 발급 후 parent worker 가 삭제/role 변경됐을 수 있음.
        if token_role == "admin_agent":
            if token_parent is None:
                raise HTTPException(400, "admin_agent token missing parent_worker_id")
            parent = db.get(Worker, token_parent)
            if parent is None or parent.role != "desktop_worker":
                raise HTTPException(
                    409,
                    f"parent_worker_id={token_parent} invalid at consume "
                    "(deleted or role changed); re-enroll required",
                )

        worker = db.query(Worker).filter_by(name=worker_name).first()
        if worker is None:
            # Slice 3.2 — 1:1 강제: 같은 desktop 에 admin_agent 이미 있으면 거부.
            if token_role == "admin_agent":
                sibling = (
                    db.query(Worker)
                    .filter(
                        Worker.role == "admin_agent",
                        Worker.parent_worker_id == token_parent,
                    )
                    .first()
                )
                if sibling is not None:
                    raise HTTPException(
                        409,
                        f"desktop_worker {token_parent} already has admin_agent "
                        f"(id={sibling.id}); 1:1 enforced",
                    )
            worker = Worker(
                name=worker_name,
                status="offline",
                role=token_role,
                parent_worker_id=token_parent,
            )
            db.add(worker)
            db.flush()
        else:
            # 재발급 — role/parent immutable 검증
            if worker.role != token_role:
                raise HTTPException(
                    409,
                    f"worker {worker_name!r} already has role={worker.role}; "
                    f"role is immutable (cannot re-enroll as {token_role})",
                )
            if worker.parent_worker_id != token_parent:
                raise HTTPException(
                    409,
                    f"worker {worker_name!r} already has parent_worker_id="
                    f"{worker.parent_worker_id}; parent is immutable",
                )

        raw_token = _secrets.token_urlsafe(32)
        worker.token_hash = hash_password(raw_token)  # [LEGACY] 폐기 예정
        worker.token_prefix = raw_token[:8]            # [LEGACY] 폐기 예정
        worker.token_sha256 = _sha256_hex(raw_token)   # [PRIMARY] O(1) auth
        worker.os_type = "windows"
        worker.enrolled_at = datetime.now(UTC)
        db.commit()

        shared = {
            "SERVER_URL": os.getenv("SERVER_URL", ""),
            "DB_CRYPTO_KEY": os.getenv("DB_CRYPTO_KEY") or os.getenv("HYDRA_ENCRYPTION_KEY", ""),
        }
        return EnrollResponse(worker_id=worker.id, worker_token=raw_token, secrets=shared)
    finally:
        db.close()


# ───────────── worker_auth Depends ─────────────
def worker_auth(x_worker_token: str = Header(default="")) -> Worker:
    """워커 토큰 검증 — O(1) SHA-256 조회 우선, 레거시 bcrypt fallback.

    설계 근거: 워커 토큰은 `secrets.token_urlsafe(32)` (256bit 랜덤) 이라
    brute force 불가. bcrypt (slow hash) 는 사람 비밀번호용이지 API 토큰용이 아님.
    SHA-256 + UNIQUE 인덱스면 잘못된 토큰도 DB 0건 = 즉시 401 (bcrypt 순회 없음).
    """
    if not x_worker_token:
        raise HTTPException(401, "missing worker token")
    db = _db_session.SessionLocal()
    try:
        # [FAST PATH] SHA-256 O(1) 조회 — 정상 경로
        token_sha = _sha256_hex(x_worker_token)
        w = db.query(Worker).filter(Worker.token_sha256 == token_sha).first()
        if w is not None:
            db.expunge(w)
            return w

        # [LEGACY] SHA-256 미백필 워커 — 과도기 경로.
        # 최근 7일 heartbeat 있는 워커만 대상. 죽은 테스트 워커가 bad token 마다
        # bcrypt 당하는 것을 방지 (DoS-ish). 신규 워커는 enroll 시 sha256 세팅되므로
        # 이 경로는 pre-migration 워커 전용.
        from datetime import timedelta
        recent_cutoff = datetime.now(UTC) - timedelta(days=7)
        legacy = db.query(Worker).filter(
            Worker.token_hash.isnot(None),
            Worker.token_sha256.is_(None),
            Worker.last_heartbeat.isnot(None),
            Worker.last_heartbeat > recent_cutoff,
        ).all()
        for lw in legacy:
            if verify_password(x_worker_token, lw.token_hash):
                # 재발견 시 sha256 + prefix 백필 (다음 요청부터 fast path)
                lw.token_sha256 = token_sha
                lw.token_prefix = x_worker_token[:8]
                db.commit()
                db.refresh(lw)
                db.expunge(lw)
                return lw

        raise HTTPException(401, "invalid worker token")
    finally:
        db.close()


# ───────────── heartbeat v2 ─────────────
class HeartbeatRequest(BaseModel):
    version: str
    os_type: str = "windows"
    cpu_percent: float = 0.0
    mem_used_mb: int = 0
    disk_free_gb: float = 0.0
    adb_devices: list[str] = []
    adspower_version: str = ""
    playwright_browsers_ok: bool = True
    current_task_id: int | None = None
    time_offset_ms: int = 0
    # Slice 2.1 — Admin Agent redesign 의 optional 필드.
    # 워커가 보내면 서버 DB 의 workers.role / capabilities 갱신.
    # 기존 워커가 안 보내면 None → 서버는 기존 값 유지.
    role: str | None = None  # "desktop_worker" | "admin_agent"
    capabilities: list[str] | None = None


class PendingCommand(BaseModel):
    id: int
    command: str
    payload: dict | None = None


class HeartbeatResponse(BaseModel):
    current_version: str
    paused: bool
    canary_worker_ids: list[int]
    restart_requested: bool = False
    worker_config: dict
    # 워커 전용 비밀 — null 이면 미설정 / 있으면 평문. 워커는 이걸 os.environ 에 주입.
    adspower_api_key: str | None = None
    # 어드민이 발행한 대기 중 명령들 (최대 10개, FIFO)
    pending_commands: list[PendingCommand] = []
    # Verbose 디버그 모드 — True 면 워커가 INFO+ 로그를 /log-tail 로 push.
    verbose_mode: bool = False


# ───────────── error report ─────────────
_ALLOWED_ERROR_KINDS = frozenset({
    "heartbeat_fail", "fetch_fail", "task_fail", "diagnostic",
    "update_fail", "unknown_screen", "other",
})
_DEDUPE_WINDOW_SECONDS = 600  # 10분


class ReportErrorRequest(BaseModel):
    kind: str = Field(..., min_length=1, max_length=32)
    message: str = Field(..., min_length=1, max_length=2000)
    traceback: str | None = None
    context: dict | None = None
    occurred_at: datetime | None = None  # 생략 시 서버 시각


class ReportErrorResponse(BaseModel):
    ok: bool
    deduped: bool = False  # True: 10분 내 중복으로 저장 스킵


@router.post("/report-error", response_model=ReportErrorResponse)
def report_error(
    req: ReportErrorRequest,
    worker: Worker = Depends(worker_auth),
) -> ReportErrorResponse:
    """워커가 발생시킨 에러/진단 리포트 저장.

    dedupe: 같은 (worker_id, kind, message) 가 10분 내에 이미 있으면 저장 스킵.
    """
    kind = req.kind if req.kind in _ALLOWED_ERROR_KINDS else "other"
    occurred_at = req.occurred_at or datetime.now(UTC)
    # occurred_at 이 tz-naive 이면 UTC 로 간주
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)

    db = _db_session.SessionLocal()
    try:
        from datetime import timedelta
        cutoff = datetime.now(UTC) - timedelta(seconds=_DEDUPE_WINDOW_SECONDS)
        dup = (
            db.query(WorkerError)
            .filter(
                WorkerError.worker_id == worker.id,
                WorkerError.kind == kind,
                WorkerError.message == req.message,
                WorkerError.received_at >= cutoff,
            )
            .first()
        )
        if dup is not None:
            return ReportErrorResponse(ok=True, deduped=True)

        ctx_json = json.dumps(req.context, ensure_ascii=False) if req.context else None
        # Phase 1 — mirror of /report-error-with-screenshot mapping for consistency.
        c = req.context or {}
        err = WorkerError(
            worker_id=worker.id,
            kind=kind,
            message=req.message,
            traceback=req.traceback,
            context=ctx_json,
            screen_state=c.get("screen_state"),
            failure_taxonomy=c.get("failure_taxonomy"),
            captured_url=c.get("captured_url"),
            captured_title=c.get("captured_title"),
            occurred_at=occurred_at,
            received_at=datetime.now(UTC),
        )
        db.add(err)
        db.commit()
        return ReportErrorResponse(ok=True, deduped=False)
    finally:
        db.close()


# ───────────── account event (Phase 3.2 timeline) ─────────────
_ALLOWED_EVENT_TYPES = frozenset({
    "task_start", "task_complete", "task_fail",
    "login_success", "login_fail", "unknown_screen", "note", "other",
})


class AccountEventRequest(BaseModel):
    account_id: int
    event_type: str = Field(..., min_length=1, max_length=32)
    message: str = Field(..., min_length=1, max_length=1000)
    task_id: int | None = None
    screen_state: str | None = Field(default=None, max_length=64)
    failure_taxonomy: str | None = Field(default=None, max_length=32)
    context: dict | None = None


class AccountEventResponse(BaseModel):
    ok: bool
    event_id: int


@router.post("/account-event", response_model=AccountEventResponse)
def report_account_event(
    req: AccountEventRequest,
    worker: Worker = Depends(worker_auth),
) -> AccountEventResponse:
    """워커가 계정 timeline 에 1줄 append.

    Ownership 검증 (Codex P1 fix):
      - account_id 가 실제 존재해야 함 (없으면 404)
      - task_id 가 있으면 Task 가 존재하고, Task.worker_id 가 caller 와 일치하고,
        Task.account_id 가 req.account_id 와 일치해야 함 (없거나 불일치 시 403/404)
    이걸로 stale/poisoning 워커가 남의 계정 timeline 을 더럽히지 못함.

    현재 wire 된 호출처: capture_unknown_screen 만 (Phase 3.2 슬라이스). task 라이프사이클
    event(start/complete/fail), login 결과는 후속 PR 에서 worker app/login 에 wire 함.
    """
    ev_type = req.event_type if req.event_type in _ALLOWED_EVENT_TYPES else "other"
    ctx_json = json.dumps(req.context, ensure_ascii=False) if req.context else None
    db = _db_session.SessionLocal()
    try:
        if db.get(Account, req.account_id) is None:
            raise HTTPException(404, f"account {req.account_id} not found")
        if req.task_id is not None:
            task = db.get(Task, req.task_id)
            if task is None:
                raise HTTPException(404, f"task {req.task_id} not found")
            if task.worker_id is not None and task.worker_id != worker.id:
                raise HTTPException(403, f"task {req.task_id} not owned by worker {worker.id}")
            if task.account_id is not None and task.account_id != req.account_id:
                raise HTTPException(
                    400,
                    f"task {req.task_id} account_id ({task.account_id}) != req.account_id ({req.account_id})",
                )
        ev = AccountEvent(
            account_id=req.account_id,
            worker_id=worker.id,
            task_id=req.task_id,
            event_type=ev_type,
            screen_state=req.screen_state,
            failure_taxonomy=req.failure_taxonomy,
            message=req.message,
            context=ctx_json,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        return AccountEventResponse(ok=True, event_id=ev.id)
    finally:
        db.close()


# ───────────── ScreenResolution lookup (Phase 3.3) ─────────────
class ResolutionLookupRequest(BaseModel):
    screen_state: str = Field(..., min_length=1, max_length=64)
    url: str | None = Field(default=None, max_length=2000)
    title: str | None = Field(default=None, max_length=500)
    dom_signature: str | None = Field(default=None, max_length=128)


class ResolutionLookupResponse(BaseModel):
    match: bool
    resolution_id: int | None = None
    resolution_type: str | None = None
    action_config: dict | None = None
    screen_state: str | None = None


@router.post("/resolution-lookup", response_model=ResolutionLookupResponse)
def lookup_resolution(
    req: ResolutionLookupRequest,
    worker: Worker = Depends(worker_auth),
) -> ResolutionLookupResponse:
    """워커가 UNKNOWN_SCREEN 만나기 직전에 호출 — approved=true 인 ScreenResolution
    중 가장 구체적인 매치를 반환. 매치되면 hit_count++ / last_hit_at 갱신.

    매칭 우선순위 (가장 구체적인 것 먼저):
      1. dom_signature 정확 일치
      2. url substring + screen_state 일치
      3. title substring + screen_state 일치
      4. screen_state 단독 일치

    매치 없으면 {match: false}. caller 는 캡처 + 운영자 라벨 큐 진입으로 fallback.
    """
    db = _db_session.SessionLocal()
    try:
        base = db.query(ScreenResolution).filter(ScreenResolution.approved.is_(True))
        match: ScreenResolution | None = None

        # 1) dom_signature 정확 일치
        if req.dom_signature:
            match = base.filter(ScreenResolution.dom_signature == req.dom_signature).first()
        # 2) url substring + screen_state (Codex P1 fix: longer pattern wins
        #    → "/challenge/recaptcha" 가 "/challenge" 보다 우선)
        if match is None and req.url:
            cand = base.filter(
                ScreenResolution.screen_state == req.screen_state,
                ScreenResolution.url_pattern.isnot(None),
            ).all()
            cand.sort(key=lambda r: (-len(r.url_pattern or ""), r.id))
            for r in cand:
                if r.url_pattern and r.url_pattern in req.url:
                    match = r
                    break
        # 3) title substring + screen_state (동일 — 긴 pattern 우선)
        if match is None and req.title:
            cand = base.filter(
                ScreenResolution.screen_state == req.screen_state,
                ScreenResolution.title_pattern.isnot(None),
            ).all()
            cand.sort(key=lambda r: (-len(r.title_pattern or ""), r.id))
            for r in cand:
                if r.title_pattern and r.title_pattern in req.title:
                    match = r
                    break
        # 4) screen_state 단독
        if match is None:
            match = base.filter(
                ScreenResolution.screen_state == req.screen_state,
                ScreenResolution.dom_signature.is_(None),
                ScreenResolution.url_pattern.is_(None),
                ScreenResolution.title_pattern.is_(None),
            ).first()

        if match is None:
            return ResolutionLookupResponse(match=False)

        # hit_count 는 apply 성공 후 별도 ack 엔드포인트가 증가시킴 (Codex P1 fix):
        # lookup-시 증가는 핸들러 미지원/실패 케이스까지 부풀려 metric 신뢰도가 떨어짐.

        action_config = None
        if match.action_config:
            try:
                action_config = json.loads(match.action_config)
            except Exception:
                action_config = None

        return ResolutionLookupResponse(
            match=True,
            resolution_id=match.id,
            resolution_type=match.resolution_type,
            action_config=action_config,
            screen_state=match.screen_state,
        )
    finally:
        db.close()


class ResolutionAppliedRequest(BaseModel):
    resolution_id: int


class ResolutionAppliedResponse(BaseModel):
    ok: bool
    hit_count: int


@router.post("/resolution-applied", response_model=ResolutionAppliedResponse)
def report_resolution_applied(
    req: ResolutionAppliedRequest,
    worker: Worker = Depends(worker_auth),
) -> ResolutionAppliedResponse:
    """Phase 3.3 — apply 성공 ack. hit_count 는 여기서만 증가 (atomic UPDATE)."""
    from sqlalchemy import update as _sa_update
    db = _db_session.SessionLocal()
    try:
        if db.get(ScreenResolution, req.resolution_id) is None:
            raise HTTPException(404, f"resolution {req.resolution_id} not found")
        db.execute(
            _sa_update(ScreenResolution)
            .where(ScreenResolution.id == req.resolution_id)
            .values(
                hit_count=ScreenResolution.hit_count + 1,
                last_hit_at=datetime.now(UTC),
            )
        )
        db.commit()
        r = db.get(ScreenResolution, req.resolution_id)
        return ResolutionAppliedResponse(ok=True, hit_count=r.hit_count or 0)
    finally:
        db.close()


# ───────────── screenshot 업로드 ─────────────
# 실 YouTube 실패 시 육안 디버깅용. /var/www/hydra/screenshots/ 에 저장.
# 7일 후 cron 자동 삭제. 어드민 전용 조회 엔드포인트로 서빙.
_SCREENSHOT_MAX_BYTES = 4 * 1024 * 1024  # 4MB
_ALLOWED_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp"})


def _screenshot_dir() -> _Path:
    """요청 시점 평가 — 테스트가 env 로 오버라이드 가능."""
    return _Path(os.getenv("HYDRA_SCREENSHOT_DIR", "/var/www/hydra/screenshots"))


@router.post("/report-error-with-screenshot", response_model=ReportErrorResponse)
async def report_error_with_screenshot(
    kind: str = Form(...),
    message: str = Form(...),
    screenshot: UploadFile = File(...),
    traceback: str | None = Form(default=None),
    context: str | None = Form(default=None),  # JSON string
    worker: Worker = Depends(worker_auth),
) -> ReportErrorResponse:
    """에러 + 스크린샷 통합 업로드 (multipart).

    dedupe: JSON 전용 report-error 와 동일 (worker, kind, message, 10분 창).
    """
    k = kind if kind in _ALLOWED_ERROR_KINDS else "other"

    # 파일 검증
    filename = screenshot.filename or "screenshot.png"
    ext = _Path(filename).suffix.lower()
    if ext not in _ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"unsupported extension: {ext}")

    # 본문 크기 체크 (스트리밍 읽으면서)
    content = await screenshot.read(_SCREENSHOT_MAX_BYTES + 1)
    if len(content) > _SCREENSHOT_MAX_BYTES:
        raise HTTPException(413, f"screenshot too large (>{_SCREENSHOT_MAX_BYTES} bytes)")
    if not content:
        raise HTTPException(400, "empty screenshot")

    # 저장 경로: YYYY-MM-DD/<worker_id>-<ts>-<rand>.<ext>
    now = datetime.now(UTC)
    base_dir = _screenshot_dir()
    day_dir = base_dir / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    rand = _secrets.token_urlsafe(6)
    rel_path = f"{now.strftime('%Y-%m-%d')}/{worker.id}-{int(now.timestamp())}-{rand}{ext}"
    abs_path = base_dir / rel_path
    abs_path.write_bytes(content)

    # DB 저장 + dedupe
    from datetime import timedelta
    db = _db_session.SessionLocal()
    try:
        cutoff = datetime.now(UTC) - timedelta(seconds=_DEDUPE_WINDOW_SECONDS)
        dup = (
            db.query(WorkerError)
            .filter(
                WorkerError.worker_id == worker.id,
                WorkerError.kind == k,
                WorkerError.message == message,
                WorkerError.received_at >= cutoff,
            )
            .first()
        )
        if dup is not None:
            # dedupe 되어도 스크린샷 URL 만 업데이트 (최신 에러 화면)
            dup.screenshot_url = rel_path
            db.commit()
            return ReportErrorResponse(ok=True, deduped=True)

        ctx_dict = None
        if context:
            try:
                ctx_dict = json.loads(context)
            except Exception:
                ctx_dict = {"_raw": context[:500]}

        # Phase 1 — context dict 의 UNKNOWN_SCREEN 필드를 first-class 컬럼으로 매핑.
        # 기존 context JSON 도 그대로 보존 (backward compat).
        screen_state = ctx_dict.get("screen_state") if ctx_dict else None
        failure_taxonomy = ctx_dict.get("failure_taxonomy") if ctx_dict else None
        captured_url = ctx_dict.get("captured_url") if ctx_dict else None
        captured_title = ctx_dict.get("captured_title") if ctx_dict else None

        err = WorkerError(
            worker_id=worker.id,
            kind=k,
            message=message[:2000],
            traceback=traceback,
            context=json.dumps(ctx_dict, ensure_ascii=False) if ctx_dict else None,
            screenshot_url=rel_path,
            screen_state=screen_state,
            failure_taxonomy=failure_taxonomy,
            captured_url=captured_url,
            captured_title=captured_title,
            occurred_at=now,
            received_at=now,
        )
        db.add(err)
        db.commit()
        return ReportErrorResponse(ok=True, deduped=False)
    finally:
        db.close()


# ───────────── 명령 ack ─────────────
class CommandAckRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=16)  # done | failed
    result: str | None = None
    error_message: str | None = None


@router.post("/command/{cmd_id}/ack")
def ack_command(
    cmd_id: int,
    req: CommandAckRequest,
    worker: Worker = Depends(worker_auth),
) -> dict:
    """워커가 명령 실행 결과 보고."""
    if req.status not in ("done", "failed"):
        raise HTTPException(400, f"invalid status: {req.status}")
    db = _db_session.SessionLocal()
    try:
        cmd = db.get(WorkerCommand, cmd_id)
        if cmd is None:
            raise HTTPException(404, "command not found")
        if cmd.worker_id != worker.id:
            raise HTTPException(403, "command not owned by this worker")
        # Slice 1: lease 해제. ack 가 final state 라 더 이상 재배달 안 함.
        cmd.status = req.status
        cmd.completed_at = datetime.now(UTC)
        cmd.lease_expires_at = None
        if cmd.started_at is None and cmd.delivered_at is not None:
            cmd.started_at = cmd.delivered_at
        cmd.result = req.result
        cmd.error_message = req.error_message
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.post("/heartbeat/v2", response_model=HeartbeatResponse)
def heartbeat_v2(
    req: HeartbeatRequest,
    worker: Worker = Depends(worker_auth),
) -> HeartbeatResponse:
    db = _db_session.SessionLocal()
    try:
        w = db.get(Worker, worker.id)
        w.last_heartbeat = datetime.now(UTC)
        w.current_version = req.version
        # 어드민이 수동으로 일시정지(paused) 한 경우엔 status 유지 — 재개 누를 때까지 sticky.
        # offline → online 복귀만 자동 처리.
        if w.status != "paused":
            w.status = "online"
        w.health_snapshot = json.dumps(req.model_dump(), ensure_ascii=False)

        # PR-Preflight: 워커가 ADB device 보고했고 ip_config 비어있으면 자동 세팅.
        # 사용자가 워커 PC 안 만져도 서버가 자동으로 첫 device ID 박음.
        if req.adb_devices and not w.ip_config:
            w.ip_config = json.dumps(
                {"adb_device_id": req.adb_devices[0]},
                ensure_ascii=False,
            )

        # Slice 3.2 — role immutability. heartbeat 는 role 변경 절대 불가.
        # 토큰 발급 시점에 결정된 role 만 valid; 운영상 변경은 PATCH /role 만.
        # invalid role 은 400 (악성/실수 워커 빨리 감지), valid role 은 silent
        # ignore (워커가 옛 코드로 role 보내도 호환).
        if req.role is not None and req.role not in ("desktop_worker", "admin_agent"):
            raise HTTPException(400, f"invalid role: {req.role}")
        # capabilities 는 mutable — 워커 PC 환경 변화 (NSSM 설치 등) 반영.
        if req.capabilities is not None:
            w.capabilities = json.dumps(req.capabilities, ensure_ascii=False)

        db.commit()

        ads_key: str | None = None
        if w.adspower_api_key_enc:
            try:
                from hydra.core import crypto
                ads_key = crypto.decrypt(w.adspower_api_key_enc)
            except Exception:
                ads_key = None

        # Slice 1 follow-up #2 — lease hardening:
        #   1) Postgres atomic lease pickup (FOR UPDATE SKIP LOCKED)
        #   2) per-command lease_sec (shell_exec = timeout+30, others = 60)
        #   3) attempt_count 상한 (ATTEMPT_MAX) — 초과시 failed
        #   4) non-redeliverable command (restart/update_now) 만료시 재배달 금지 → failed
        # SQLite 테스트 환경은 with_for_update 비호환 → fallback (단일 connection 이라 race 없음).
        now = datetime.now(UTC)

        base_q = (
            db.query(WorkerCommand)
            .filter(
                WorkerCommand.worker_id == w.id,
                or_(
                    WorkerCommand.status == "pending",
                    and_(
                        WorkerCommand.status == "leased",
                        WorkerCommand.lease_expires_at.isnot(None),
                        WorkerCommand.lease_expires_at < now,
                    ),
                ),
            )
            .order_by(WorkerCommand.issued_at)
            .limit(10)
        )
        dialect_name = db.bind.dialect.name if db.bind is not None else ""
        if dialect_name == "postgresql":
            # 다른 동시 heartbeat (또는 admin transaction) 가 같은 row 잠그면
            # SKIP LOCKED 로 그 row 건너뜀 → 중복 lease/배달 차단.
            base_q = base_q.with_for_update(skip_locked=True)
        candidates = base_q.all()

        pending: list[PendingCommand] = []
        for c in candidates:
            is_redelivery = (c.status == "leased")  # 만료된 leased → 재배달 시도
            next_attempt = (c.attempt_count or 0) + 1

            # 상한 초과 → failed (재시도 무한 반복 방지)
            if next_attempt > _CMD_ATTEMPT_MAX:
                # 관측 일관성: 메시지의 N 을 마지막으로 기록된 attempt_count 와 동일하게.
                # next_attempt (=ATTEMPT_MAX+1) 는 시도하지 않은 횟수라 헷갈림 방지.
                c.status = "failed"
                c.completed_at = now
                c.lease_expires_at = None
                _append_err(
                    c,
                    f"attempt_limit_exceeded:max={_CMD_ATTEMPT_MAX}"
                    f",last_attempt={c.attempt_count or 0}",
                )
                continue

            # restart / update_now 같이 워커가 ack 직후 self-exit 하는 비멱등 명령은
            # 만료 후 다시 보내면 곤란 (이미 옛 워커가 exit 시도 중일 수 있음).
            if is_redelivery and c.command in _CMD_NON_REDELIVERABLE:
                c.status = "failed"
                c.completed_at = now
                c.lease_expires_at = None
                _append_err(c, "non_redeliverable_after_lease_expiry")
                continue

            # Phase 3 Slice 3.1 — target_role 가 박혀있고 현재 worker.role 와
            # 다르면 invariant 위반 (발행 시점 auto-route 이후 role 가 바뀐 경우 등).
            # 같은 worker 에 재배달하지 않고 failed + role_mismatch.
            if c.target_role is not None and c.target_role != w.role:
                c.status = "failed"
                c.completed_at = now
                c.lease_expires_at = None
                _append_err(
                    c,
                    f"role_mismatch:target={c.target_role},actual={w.role}",
                )
                continue

            # payload parse — lease_sec 계산용
            payload_dict = None
            if c.payload:
                try:
                    payload_dict = json.loads(c.payload)
                except Exception:
                    payload_dict = None

            lease_sec = _compute_lease_sec(c.command, payload_dict)
            c.attempt_count = next_attempt
            c.status = "leased"
            c.delivered_at = c.delivered_at or now
            c.lease_expires_at = now + timedelta(seconds=lease_sec)
            pending.append(PendingCommand(id=c.id, command=c.command, payload=payload_dict))

        if candidates:
            db.commit()

        return HeartbeatResponse(
            current_version=scfg.get_current_version(session=db) or "",
            paused=scfg.is_paused(session=db),
            canary_worker_ids=scfg.get_canary_worker_ids(session=db),
            worker_config={
                "poll_interval_sec": 15,
                "max_concurrent_tasks": 1,
                "drain_timeout_minutes": 15,
            },
            adspower_api_key=ads_key,
            pending_commands=pending,
            verbose_mode=bool(w.verbose_mode),
        )
    finally:
        db.close()


# ───────────── log tail (verbose 모드 일상 활동 push) ─────────────

class LogTailEntry(BaseModel):
    occurred_at: datetime
    level: str = Field(..., min_length=1, max_length=16)
    logger_name: str | None = Field(None, max_length=128)
    message: str = Field(..., min_length=1, max_length=2000)


class LogTailRequest(BaseModel):
    entries: list[LogTailEntry] = Field(..., max_length=200)


@router.post("/log-tail")
def report_log_tail(
    req: LogTailRequest,
    worker: Worker = Depends(worker_auth),
) -> dict:
    """워커 → 서버 INFO+ 활동 로그 batch push (verbose_mode 켜진 워커만).

    verbose_mode 가 OFF 인데 들어오면 무시 (저장 X). 개별 행은 최대 2000자.
    """
    from hydra.db.models import WorkerLogTail
    db = _db_session.SessionLocal()
    try:
        w = db.get(Worker, worker.id)
        if not w or not w.verbose_mode:
            return {"ok": True, "stored": 0, "verbose_off": True}

        now = datetime.now(UTC)
        stored = 0
        for e in req.entries:
            occurred = e.occurred_at
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=UTC)
            db.add(WorkerLogTail(
                worker_id=w.id,
                occurred_at=occurred,
                received_at=now,
                level=e.level.upper()[:16],
                logger_name=(e.logger_name or "")[:128] or None,
                message=e.message[:2000],
            ))
            stored += 1
        db.commit()
        return {"ok": True, "stored": stored}
    finally:
        db.close()


# ───────────── sync (account + worker rows) ─────────────

@router.get("/sync")
def sync_data(worker: Worker = Depends(worker_auth)) -> dict:
    """Return all Account + Worker rows for local DB sync.

    Worker pulls this on startup so ensure_safe_ip can find rows in its local
    SQLite. Sensitive credential columns (password, totp_secret) are still
    Fernet-encrypted as stored in the DB — worker has the same encryption key.
    """
    db = _db_session.SessionLocal()
    try:
        from hydra.db.models import Account
        accs = []
        for a in db.query(Account).all():
            accs.append({c.name: getattr(a, c.name) for c in a.__table__.columns})
        wkrs = []
        for w in db.query(Worker).all():
            wkrs.append({c.name: getattr(w, c.name) for c in w.__table__.columns})

        # Coerce datetimes to ISO strings (FastAPI default JSON encoder handles this,
        # but being explicit avoids surprises with naive datetimes from SQLite)
        def _ser(rows):
            out = []
            for r in rows:
                d = {}
                for k, v in r.items():
                    if isinstance(v, datetime):
                        d[k] = v.isoformat()
                    else:
                        d[k] = v
                out.append(d)
            return out

        return {"accounts": _ser(accs), "workers": _ser(wkrs)}
    finally:
        db.close()
