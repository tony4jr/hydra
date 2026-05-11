"""PR-Kill: Suspend guard — 사고 급증 시 자동 캠페인 fetch 중지 안전망.

설계:
- 슬라이딩 윈도우 카운터 (5분 기본)로 4개 시그널 모니터링:
    1. account_suspended_recent_count
    2. phase_timeout_recent_count
    3. task_failed_recent_count
    4. fail_rate (recent fails / recent attempts)
- 임계 초과 시 server_config.paused = True 자동 토글 + telegram alert + reason 기록
- kill switch 발동 후엔 사람이 수동으로 set_paused(False) 해야 풀림 (auto-recover 안 함 — 의도적 보수)

운영자 가시성:
- SystemConfig "server_config.kill_switch_reason" — 마지막 발동 사유 + 시각
- /api/admin/system/kill-switch GET → 현재 상태 + 최근 시그널
- /api/admin/system/kill-switch DELETE → 수동 reset (set_paused(False) + reason 클리어)

호출 지점:
- on_task_fail (orchestrator) → suspend/phase_timeout 카운터 증가 시 evaluate()
- v2/fetch 진입 직전 → server_config.paused 이미 체크 중이라 추가 호출 불필요

회귀 방지:
- 이미 paused=True 면 evaluate skip (이중 발동 방지)
- 카운터는 메모리 X — DB 쿼리 기반 (멀티-프로세스 안전)
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, UTC, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from hydra.core import server_config as scfg
from hydra.core.logger import get_logger
from hydra.db import session as _db_session
from hydra.db.models import Account, SystemConfig, Task, WorkerError

log = get_logger("suspend_guard")


# Tunable thresholds — 코드 상수 + env override.
# 5분 윈도우 내 발동 조건. 모두 OR — 어느 하나라도 초과하면 kill switch.
DEFAULT_WINDOW_MINUTES = 5
DEFAULT_THRESHOLDS = {
    "account_suspended_in_window": 3,    # 5분 내 계정 3개 정지
    "phase_timeout_in_window": 10,        # 5분 내 phase_timeout 10건
    "task_failed_in_window": 20,          # 5분 내 task fail 20건
    "fail_rate_pct": 50.0,                # 5분 fail rate 50% 이상 (최소 attempts 5)
    "min_attempts_for_rate": 5,           # rate 계산용 최소 시도수 (작은 N 노이즈 방지)
}


def _load_thresholds() -> dict:
    """env override 우선 적용."""
    import os
    out = dict(DEFAULT_THRESHOLDS)
    for k in out:
        ev = os.getenv(f"HYDRA_KILL_{k.upper()}")
        if ev is None:
            continue
        try:
            out[k] = type(out[k])(ev)
        except (ValueError, TypeError):
            log.warning(f"invalid env override HYDRA_KILL_{k.upper()}={ev}, using default")
    return out


def _window_start(now: datetime, minutes: int) -> datetime:
    return now - timedelta(minutes=minutes)


@dataclass
class GuardSignal:
    account_suspended: int
    phase_timeout: int
    task_failed: int
    task_attempts: int
    fail_rate_pct: float


def collect_signals(session: Session, *, window_minutes: int = DEFAULT_WINDOW_MINUTES) -> GuardSignal:
    """현재 윈도우의 4개 시그널 측정.

    완성/실패 task 시각은 completed_at; account 정지 시각은 last_active_at 우회 — 정확한
    suspended_at 컬럼이 없어서 retired_at 도 함께 본다.
    """
    now = datetime.now(UTC)
    start = _window_start(now, window_minutes)
    # tz-naive DB row 가정 (prod Postgres 도 timestamp without time zone)
    start_naive = start.replace(tzinfo=None)

    # Account: status='suspended' + last_active_at >= start (정지된 직후 last_active 갱신 패턴 가정)
    # 보다 명확한 transition 추적을 위해선 별도 audit 테이블이 필요하지만, 현 모델 한도 내에선
    # status='suspended' 신규 진입 카운트가 어렵다. fallback: 윈도우 내 last_active_at + suspended.
    # 보수적으로 잘못된 정지가 트리거되지 않게, "suspended" 상태이며 last_active_at 이 윈도우 안.
    acct_suspended = (
        session.query(Account)
        .filter(Account.status == "suspended")
        .filter(Account.last_active_at >= start_naive)
        .count()
    )

    # WorkerError.kind='phase_timeout' (PR-E 도입 후 생성)
    phase_timeout = (
        session.query(WorkerError)
        .filter(WorkerError.kind == "phase_timeout")
        .filter(WorkerError.received_at >= start_naive)
        .count()
    )

    # Task: status='failed' 윈도우 안.
    task_failed = (
        session.query(Task)
        .filter(Task.status == "failed")
        .filter(Task.completed_at >= start_naive)
        .count()
    )
    # 시도수 = 윈도우 안에서 완료/실패한 모든 task.
    task_attempts = (
        session.query(Task)
        .filter(Task.status.in_(["done", "failed"]))
        .filter(Task.completed_at >= start_naive)
        .count()
    )
    fail_rate = (task_failed / task_attempts * 100.0) if task_attempts else 0.0

    return GuardSignal(
        account_suspended=acct_suspended,
        phase_timeout=phase_timeout,
        task_failed=task_failed,
        task_attempts=task_attempts,
        fail_rate_pct=fail_rate,
    )


def _exceeds(signal: GuardSignal, thresholds: dict) -> Optional[str]:
    """초과 사유 첫 매치 — None 이면 안전.

    PR-Kill v2: `>=` 비교로 의도된 임계 정확히 발동.
    (이전 `>` 는 "3건"이 4건부터 발동되는 의미상 어긋남 — Codex 검토에서 발견.)
    """
    if signal.account_suspended >= thresholds["account_suspended_in_window"]:
        return (
            f"account_suspended in window: {signal.account_suspended} "
            f">= {thresholds['account_suspended_in_window']}"
        )
    if signal.phase_timeout >= thresholds["phase_timeout_in_window"]:
        return (
            f"phase_timeout in window: {signal.phase_timeout} "
            f">= {thresholds['phase_timeout_in_window']}"
        )
    if signal.task_failed >= thresholds["task_failed_in_window"]:
        return (
            f"task_failed in window: {signal.task_failed} "
            f">= {thresholds['task_failed_in_window']}"
        )
    if (
        signal.task_attempts >= thresholds["min_attempts_for_rate"]
        and signal.fail_rate_pct >= thresholds["fail_rate_pct"]
    ):
        return (
            f"fail_rate {signal.fail_rate_pct:.1f}% >= {thresholds['fail_rate_pct']}% "
            f"(attempts={signal.task_attempts})"
        )
    return None


_KEY_KILL_REASON = "server_config.kill_switch_reason"


def get_kill_reason(*, session: Optional[Session] = None) -> Optional[str]:
    owned = session is None
    s = session or scfg.SessionLocal()
    try:
        row = s.query(SystemConfig).filter_by(key=_KEY_KILL_REASON).first()
        return row.value if row else None
    finally:
        if owned:
            s.close()


def set_kill_reason(reason: Optional[str], *, session: Optional[Session] = None) -> None:
    owned = session is None
    s = session or scfg.SessionLocal()
    try:
        row = s.query(SystemConfig).filter_by(key=_KEY_KILL_REASON).first()
        if reason is None:
            if row:
                s.delete(row)
        else:
            if row:
                row.value = reason
            else:
                s.add(SystemConfig(key=_KEY_KILL_REASON, value=reason))
        if owned:
            s.commit()
    finally:
        if owned:
            s.close()


def evaluate(
    *,
    session: Optional[Session] = None,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    thresholds: Optional[dict] = None,
    notify: bool = True,
) -> Optional[str]:
    """현재 시그널 평가. 임계 초과 시 paused=True + reason 기록.

    Returns:
        trip reason (str) — 발동된 경우.
        None — 안전.

    호출 패턴:
    - orchestrator.on_task_fail 마지막에 evaluate() 호출.
    - 이미 paused=True 면 skip (이중 발동 방지).
    """
    owned = session is None
    s = session or scfg.SessionLocal()
    try:
        if scfg.is_paused(session=s):
            return None  # 이미 paused — 이중 발동 방지

        thr = thresholds or _load_thresholds()
        signal = collect_signals(s, window_minutes=window_minutes)
        reason = _exceeds(signal, thr)
        if reason is None:
            return None

        # Kill switch — paused True + reason 기록 + telegram
        scfg.set_paused(True, session=s)
        full_reason = (
            f"{reason} | signals={asdict(signal)} | window={window_minutes}min "
            f"| at {datetime.now(UTC).isoformat()}"
        )
        set_kill_reason(full_reason, session=s)
        if owned:
            s.commit()
        log.critical(f"KILL SWITCH TRIPPED: {full_reason}")
        if notify:
            try:
                from hydra.infra import telegram
                telegram.urgent(
                    f"🛑 HYDRA Kill Switch 발동\n\n"
                    f"<b>사유:</b> {reason}\n"
                    f"<b>시그널:</b>\n"
                    f"  계정정지 {signal.account_suspended}건, "
                    f"phase_timeout {signal.phase_timeout}건, "
                    f"task_fail {signal.task_failed}/{signal.task_attempts} "
                    f"({signal.fail_rate_pct:.1f}%)\n"
                    f"<b>윈도우:</b> {window_minutes}분\n\n"
                    f"수동 reset: admin/system/kill-switch DELETE"
                )
            except Exception as e:
                log.warning(f"telegram alert failed: {e}")
        return reason
    finally:
        if owned:
            s.close()


def reset(*, session: Optional[Session] = None) -> None:
    """수동 reset — paused=False + reason 클리어. 운영자 호출용."""
    owned = session is None
    s = session or scfg.SessionLocal()
    try:
        scfg.set_paused(False, session=s)
        set_kill_reason(None, session=s)
        if owned:
            s.commit()
        log.info("kill switch reset")
    finally:
        if owned:
            s.close()
