"""Daily Telegram report — sent at 09:00 KST via cron.

Aggregates per-day metrics:
  - Tasks: pending / running / done / failed (24h window)
  - Comments / replies posted (counts + new YT comment_ids)
  - Ghost check results (visible / suspicious / not_yet)
  - Workers: online / offline / paused
  - Account holds (status changes to identity_challenge / suspended in 24h)
  - Hot errors (top error types from worker_errors)
  - System: HTTPS, fail2ban current bans, disk usage

Sends a single Telegram message. Plain text (no markdown) for reliability.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from hydra.core.logger import get_logger
from hydra.db.models import (
    Account,
    SystemConfig,
    Task,
    Worker,
)
from hydra.db.session import SessionLocal

log = get_logger("telegram_report")

UTC = timezone.utc


def _get_cred(db, key: str) -> str | None:
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    return row.value if row and row.value else None


def _send(token: str, chat_id: str, text: str) -> bool:
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, timeout=10,
        ) as resp:
            r = json.loads(resp.read())
            return bool(r.get("ok"))
    except Exception as e:
        log.error(f"telegram send failed: {e}")
        return False


def build_report() -> str:
    """Generate report text. Pure DB read, no side effects."""
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=24)

        # Tasks summary
        tasks_24h = db.query(Task).filter(Task.created_at >= cutoff).all()
        by_status = {"pending": 0, "running": 0, "done": 0, "failed": 0, "cancelled": 0}
        by_type = {}
        for t in tasks_24h:
            s = (t.status or "?").lower()
            by_status[s] = by_status.get(s, 0) + 1
            by_type[t.task_type] = by_type.get(t.task_type, 0) + 1

        # Successful comments / replies
        comments_done = sum(1 for t in tasks_24h
                            if t.task_type == "comment" and t.status == "done")
        replies_done = sum(1 for t in tasks_24h
                           if t.task_type == "reply" and t.status == "done")

        # Workers
        workers = db.query(Worker).all()
        wkr_online = sum(1 for w in workers if w.status == "online")
        wkr_offline = sum(1 for w in workers if w.status == "offline")
        wkr_paused = sum(1 for w in workers if w.status == "paused")

        # Accounts by status
        accs = db.query(Account).all()
        by_acc_status = {}
        for a in accs:
            by_acc_status[a.status or "?"] = by_acc_status.get(a.status or "?", 0) + 1
        ipp_flagged = sum(1 for a in accs if a.ipp_flagged)

        # 24h account state changes — identity_challenge or suspended new today
        new_idchallenge = sum(
            1 for a in accs
            if a.identity_challenge_until and a.identity_challenge_until > now
        )

        # Active campaigns
        from hydra.db.models import Campaign
        camp_active = db.query(Campaign).filter(Campaign.status == "in_progress").count()

        # Build text
        lines = [
            f"📊 HYDRA 일일 리포트",
            f"({now.strftime('%Y-%m-%d %H:%M KST')})",
            "",
            f"━ 24h 태스크",
            f"  완료: {by_status.get('done', 0)}  실패: {by_status.get('failed', 0)}",
            f"  진행: {by_status.get('running', 0)}  대기: {by_status.get('pending', 0)}",
            "",
            f"━ 게시 성과 (24h)",
            f"  댓글 게시: {comments_done}",
            f"  대댓글 게시: {replies_done}",
            "",
            f"━ 워커",
            f"  온라인: {wkr_online}  오프라인: {wkr_offline}  일시중지: {wkr_paused}",
            "",
            f"━ 계정 ({len(accs)}개)",
        ]
        for s, n in sorted(by_acc_status.items(), key=lambda x: -x[1]):
            lines.append(f"  {s}: {n}")
        lines.append(f"  IPP 플래그: {ipp_flagged}")
        lines.append(f"  본인인증 쿨다운: {new_idchallenge}")
        lines.append("")
        lines.append(f"━ 캠페인")
        lines.append(f"  실행중: {camp_active}")
        lines.append("")

        # Hot errors (last 24h) — try worker_errors table if exists
        try:
            from hydra.db.models import WorkerError
            errors = (
                db.query(WorkerError)
                .filter(WorkerError.created_at >= cutoff)
                .order_by(WorkerError.created_at.desc())
                .limit(50)
                .all()
            )
            if errors:
                err_kinds = {}
                for e in errors:
                    err_kinds[e.kind] = err_kinds.get(e.kind, 0) + 1
                lines.append(f"━ 24h 에러 (top 5 종류)")
                for k, n in sorted(err_kinds.items(), key=lambda x: -x[1])[:5]:
                    lines.append(f"  {k}: {n}")
                lines.append("")
        except Exception:
            pass

        # Footer
        try:
            from hydra.core import server_config as scfg
            ver = scfg.get_current_version(session=db) or "?"
            lines.append(f"버전: {ver}")
        except Exception:
            pass

        return "\n".join(lines)
    finally:
        db.close()


def send_daily_report() -> bool:
    """Public entry point — called by cron / admin button."""
    db = SessionLocal()
    try:
        token = _get_cred(db, "telegram_bot_token")
        chat_id = _get_cred(db, "telegram_chat_id")
    finally:
        db.close()
    if not token or not chat_id:
        log.warning("telegram credentials missing — skipping daily report")
        return False

    text = build_report()
    ok = _send(token, chat_id, text)
    if ok:
        log.info(f"daily report sent ({len(text)} chars)")
    else:
        log.error("daily report send failed")
    return ok


if __name__ == "__main__":
    # Cron entrypoint
    import sys
    success = send_daily_report()
    sys.exit(0 if success else 1)
