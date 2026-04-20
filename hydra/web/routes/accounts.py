"""Account management API."""

import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from hydra.db.session import get_db
from hydra.db.models import Account, ActionLog, CampaignStep, Campaign, ErrorLog, Task
from hydra.core.crypto import encrypt
from hydra.browser.fingerprint_bundle import build_fingerprint_payload
from hydra.core.config import settings
from hydra.browser.adspower import adspower

router = APIRouter()


def auto_queue_create_profile_tasks(db: Session, accounts: list) -> int:
    """Enqueue create_profile tasks for accounts with persona but no active profile.

    Returns number of tasks queued.
    """
    count = 0
    for acc in accounts:
        if acc.adspower_profile_id:
            continue
        if not acc.persona:
            continue
        try:
            persona = json.loads(acc.persona)
        except Exception:
            continue
        device_hint = persona.get("device_hint")
        if not device_hint:
            continue

        fp_payload = build_fingerprint_payload(device_hint)
        name = f"hydra_{acc.id}_{acc.gmail.split('@')[0]}"
        remark_bits = [
            persona.get("name", ""),
            f"{persona.get('age','?')}세",
            persona.get("region", ""),
            persona.get("occupation", ""),
        ]
        remark = " / ".join(b for b in remark_bits if b)

        task = Task(
            account_id=acc.id,
            task_type="create_profile",
            status="pending",
            payload=json.dumps({
                "account_id": acc.id,
                "profile_name": name,
                "group_id": settings.adspower_group_id,
                "remark": remark,
                "device_hint": device_hint,
                "fingerprint_payload": fp_payload,
            }, ensure_ascii=False),
        )
        db.add(task)
        count += 1

    db.commit()
    return count


def compute_quota_report(db: Session) -> dict:
    adspower_count = adspower.get_profile_count()
    linked = db.query(Account).filter(Account.adspower_profile_id.isnot(None)).count()
    quota = settings.adspower_profile_quota
    return {
        "adspower_count": adspower_count,
        "linked_accounts": linked,
        "quota": quota,
        "used_ratio": round(adspower_count / quota, 4) if quota > 0 else 0,
    }


@router.get("/api/adspower-quota")
def adspower_quota(db: Session = Depends(get_db)):
    return compute_quota_report(db)


class ImportRequest(BaseModel):
    path: str
    auto_process: bool = True  # chain persona + profile creation after import


def _auto_process_new_accounts(account_ids: list[int]):
    """Background: assign personas then queue create_profile tasks for new accounts."""
    from hydra.db.session import SessionLocal
    from hydra.ai.agents.persona_agent import batch_assign_personas

    db = SessionLocal()
    try:
        accounts = db.query(Account).filter(Account.id.in_(account_ids)).all()
        batch_assign_personas(db, accounts)
        # refresh to pick up newly written personas
        accounts = db.query(Account).filter(Account.id.in_(account_ids)).all()
        queued = auto_queue_create_profile_tasks(db, accounts)
        return queued
    finally:
        db.close()


@router.post("/api/import")
def import_csv(
    data: ImportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    from hydra.accounts.manager import import_from_csv
    try:
        count = import_from_csv(db, data.path)
    except FileNotFoundError:
        return {"ok": False, "message": "파일을 찾을 수 없습니다"}
    except Exception as e:
        return {"ok": False, "message": str(e)}

    if not count:
        return {"ok": True, "message": "0개 계정 가져오기 완료", "auto_processing": False}

    # Grab IDs of accounts still in "registered" with no persona/profile — the
    # most recently imported ones. Using created_at descending narrows to this
    # batch without needing import_from_csv to return IDs.
    recent_ids = [
        a.id for a in (
            db.query(Account)
            .filter(Account.persona.is_(None), Account.adspower_profile_id.is_(None))
            .order_by(Account.id.desc())
            .limit(count)
            .all()
        )
    ]

    if data.auto_process and recent_ids:
        background_tasks.add_task(_auto_process_new_accounts, recent_ids)
        return {
            "ok": True,
            "message": f"{count}개 계정 가져오기 완료. 페르소나 배정 + 프로필 생성 태스크 큐잉을 백그라운드에서 진행합니다.",
            "auto_processing": True,
            "queued_account_ids": recent_ids,
        }

    return {
        "ok": True,
        "message": f"{count}개 계정 가져오기 완료 (auto_process=false, 수동 단계 필요)",
        "auto_processing": False,
    }


@router.get("/api/list")
def list_accounts(
    status: str | None = None,
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Account)
    if status:
        query = query.filter(Account.status == status)
    total = query.count()
    accounts = query.order_by(Account.id).offset((page - 1) * size).limit(size).all()

    # Batch compute success rates for listed accounts
    account_ids = [a.id for a in accounts]
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    step_stats = {}
    if account_ids:
        rows = (
            db.query(
                CampaignStep.account_id,
                func.count().label("total"),
                func.sum(case((CampaignStep.status == "done", 1), else_=0)).label("done"),
            )
            .filter(
                CampaignStep.account_id.in_(account_ids),
                CampaignStep.scheduled_at >= thirty_days_ago,
            )
            .group_by(CampaignStep.account_id)
            .all()
        )
        for row in rows:
            t = row.total or 0
            d = int(row.done or 0)
            step_stats[row.account_id] = round(d / t * 100, 1) if t > 0 else 0.0

    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": a.id,
                "gmail": a.gmail,
                "status": a.status,
                "warmup_group": a.warmup_group,
                "warmup_day": a.warmup_day or 0,
                "warmup_start_date": str(a.warmup_start_date) if a.warmup_start_date else None,
                "warmup_end_date": str(a.warmup_end_date) if a.warmup_end_date else None,
                "onboard_completed_at": str(a.onboard_completed_at) if a.onboard_completed_at else None,
                "ghost_count": a.ghost_count or 0,
                "success_rate": step_stats.get(a.id, 0.0),
                "adspower_profile_id": a.adspower_profile_id,
                "youtube_channel_id": a.youtube_channel_id,
                "has_persona": a.persona is not None,
                "has_cookies": a.cookies is not None,
                "has_totp": bool(a.totp_secret),
                "identity_challenge_until": str(a.identity_challenge_until) if a.identity_challenge_until else None,
                "identity_challenge_count": a.identity_challenge_count or 0,
                "last_active_at": str(a.last_active_at) if a.last_active_at else None,
                "created_at": str(a.created_at),
            }
            for a in accounts
        ],
    }


@router.get("/api/stats")
def account_stats(db: Session = Depends(get_db)):
    """Summary stats for accounts page."""
    stats = {}
    for row in db.query(Account.status, func.count()).group_by(Account.status).all():
        stats[row[0]] = row[1]
    return stats


@router.get("/api/health-summary")
def health_summary(db: Session = Depends(get_db)):
    """Quick health overview for all active accounts."""
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    accounts = db.query(Account).filter(Account.status.in_(["active", "warmup", "cooldown"])).all()

    results = []
    for a in accounts:
        step_stats = (
            db.query(
                func.count().label("total"),
                func.sum(case((CampaignStep.status == "done", 1), else_=0)).label("done"),
            )
            .filter(
                CampaignStep.account_id == a.id,
                CampaignStep.scheduled_at >= thirty_days_ago,
            )
            .first()
        )
        total = step_stats.total or 0
        done = int(step_stats.done or 0)

        results.append({
            "id": a.id,
            "gmail": a.gmail,
            "status": a.status,
            "success_rate": round(done / total * 100, 1) if total > 0 else 0.0,
            "ghost_count": a.ghost_count or 0,
            "last_active_at": str(a.last_active_at) if a.last_active_at else None,
        })

    return {"accounts": results}


@router.get("/api/csv-template")
def csv_template():
    """Return CSV template content."""
    return {
        "headers": ["gmail", "password", "recovery_email", "phone_number", "totp_secret"],
        "required": ["gmail", "password"],
        "optional": ["recovery_email", "phone_number", "totp_secret"],
        "example": "user@gmail.com,MyP@ss123,recovery@gmail.com,+821012345678,JBSWY3DPEHPK3PXP",
    }


@router.get("/api/devices")
def list_devices():
    """List connected ADB devices."""
    import subprocess
    try:
        result = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n")[1:]
        devices = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                device_id = parts[0]
                status = parts[1]
                model = ""
                for p in parts[2:]:
                    if p.startswith("model:"):
                        model = p.split(":")[1]
                devices.append({"device_id": device_id, "status": status, "model": model})
        return {"devices": devices}
    except Exception as e:
        return {"devices": [], "error": str(e)}


@router.post("/api/devices/set-active")
def set_active_device(device_id: str):
    """Set the active device for IP rotation."""
    from hydra.core.scheduler import set_device
    set_device(device_id)
    return {"ok": True, "active_device": device_id}


# --- Path parameter routes below (must be after static routes) ---

@router.get("/api/{account_id}")
def get_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).get(account_id)
    if not account:
        return {"error": "not found"}
    return {
        "id": account.id,
        "gmail": account.gmail,
        "status": account.status,
        "warmup_group": account.warmup_group,
        "warmup_day": account.warmup_day or 0,
        "warmup_start_date": str(account.warmup_start_date) if account.warmup_start_date else None,
        "warmup_end_date": str(account.warmup_end_date) if account.warmup_end_date else None,
        "onboard_completed_at": str(account.onboard_completed_at) if account.onboard_completed_at else None,
        "ghost_count": account.ghost_count,
        "persona": account.persona,
        "adspower_profile_id": account.adspower_profile_id,
        "youtube_channel_id": account.youtube_channel_id,
        "has_cookies": account.cookies is not None,
        "has_totp": bool(account.totp_secret),
        "identity_challenge_until": str(account.identity_challenge_until) if account.identity_challenge_until else None,
        "identity_challenge_count": account.identity_challenge_count or 0,
        "notes": account.notes,
        "created_at": str(account.created_at),
        "last_active_at": str(account.last_active_at) if account.last_active_at else None,
        "daily_comment_limit": account.daily_comment_limit,
        "daily_like_limit": account.daily_like_limit,
        "weekly_comment_limit": account.weekly_comment_limit,
        "weekly_like_limit": account.weekly_like_limit,
    }


@router.post("/api/{account_id}/status")
def update_status(account_id: int, status: str, db: Session = Depends(get_db)):
    from hydra.accounts.manager import transition
    from hydra.core.enums import AccountStatus
    account = db.query(Account).get(account_id)
    if not account:
        return {"error": "not found"}
    transition(db, account, AccountStatus(status), "수동 변경")
    return {"ok": True, "new_status": account.status}


@router.post("/api/{account_id}/create-profile")
def create_adspower_profile(account_id: int, db: Session = Depends(get_db)):
    """Create AdsPower browser profile for account."""
    from hydra.accounts.manager import create_adspower_profile
    account = db.query(Account).get(account_id)
    if not account:
        return {"error": "not found"}
    if account.adspower_profile_id:
        return {"ok": True, "message": "이미 프로필이 있습니다", "profile_id": account.adspower_profile_id}
    try:
        pid = create_adspower_profile(db, account)
        return {"ok": True, "profile_id": pid}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/{account_id}/assign-persona")
def assign_persona(account_id: int, db: Session = Depends(get_db)):
    """Generate and assign persona using Claude."""
    from hydra.ai.agents.persona_agent import assign_persona
    account = db.query(Account).get(account_id)
    if not account:
        return {"error": "not found"}
    try:
        assign_persona(db, account)
        return {"ok": True, "persona": json.loads(account.persona)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/batch/create-profiles")
def batch_create_profiles(db: Session = Depends(get_db)):
    """Create AdsPower profiles for all accounts that don't have one."""
    from hydra.accounts.manager import create_adspower_profile
    accounts = db.query(Account).filter(Account.adspower_profile_id.is_(None)).all()
    results = {"success": 0, "failed": 0}
    for account in accounts:
        try:
            create_adspower_profile(db, account)
            results["success"] += 1
        except Exception:
            results["failed"] += 1
    return results


@router.post("/api/batch/assign-personas")
def batch_assign_personas(db: Session = Depends(get_db)):
    """Assign personas to all accounts that don't have one."""
    from hydra.ai.agents.persona_agent import batch_assign_personas
    accounts = db.query(Account).filter(Account.persona.is_(None)).all()
    batch_assign_personas(db, accounts)
    return {"ok": True, "count": len(accounts)}


@router.post("/api/batch/auto-queue-profiles")
def batch_auto_queue_profiles(db: Session = Depends(get_db)):
    """Queue create_profile tasks for any account that has a persona but no profile yet."""
    accounts = (
        db.query(Account)
        .filter(Account.persona.isnot(None),
                Account.adspower_profile_id.is_(None))
        .all()
    )
    n = auto_queue_create_profile_tasks(db, accounts)
    return {"ok": True, "queued": n, "total_candidates": len(accounts)}


@router.get("/api/{account_id}/metrics")
def account_metrics(account_id: int, db: Session = Depends(get_db)):
    """Per-account operational metrics: success rate, ghost, captcha, stability."""
    account = db.query(Account).get(account_id)
    if not account:
        return {"error": "not found"}

    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago = now - timedelta(days=7)

    # --- Success rate (30d) ---
    steps = (
        db.query(
            func.count().label("total"),
            func.sum(case((CampaignStep.status == "done", 1), else_=0)).label("done"),
            func.sum(case((CampaignStep.status == "failed", 1), else_=0)).label("failed"),
        )
        .filter(
            CampaignStep.account_id == account_id,
            CampaignStep.scheduled_at >= thirty_days_ago,
        )
        .first()
    )
    total_steps = steps.total or 0
    done_steps = int(steps.done or 0)
    failed_steps = int(steps.failed or 0)
    success_rate = round(done_steps / total_steps * 100, 1) if total_steps > 0 else 0.0

    # --- Ghost count ---
    ghost_count = account.ghost_count or 0

    # --- Captcha / error stats (30d) ---
    captcha_errors = (
        db.query(func.count())
        .filter(
            ErrorLog.account_id == account_id,
            ErrorLog.source == "youtube",
            ErrorLog.message.like("%captcha%"),
            ErrorLog.created_at >= thirty_days_ago,
        )
        .scalar()
    )
    total_errors = (
        db.query(func.count())
        .filter(
            ErrorLog.account_id == account_id,
            ErrorLog.created_at >= thirty_days_ago,
        )
        .scalar()
    )

    # --- Stability score (0~100) ---
    # Factors: success_rate (40%), ghost penalty (20%), error rate (20%), activity recency (20%)
    stability = 0.0

    # Success component (40pts)
    stability += success_rate * 0.4

    # Ghost penalty (20pts): 0 ghost = 20, 1 = 10, 2+ = 0
    ghost_score = max(0, 20 - ghost_count * 10)
    stability += ghost_score

    # Error rate (20pts)
    action_count = (
        db.query(func.count())
        .filter(ActionLog.account_id == account_id, ActionLog.created_at >= thirty_days_ago)
        .scalar()
    ) or 1
    error_rate = total_errors / action_count
    stability += max(0, 20 - error_rate * 100)

    # Activity recency (20pts)
    if account.last_active_at:
        days_inactive = (now - account.last_active_at).days
        stability += max(0, 20 - days_inactive * 2)
    # else: 0 pts

    stability = round(min(100, max(0, stability)), 1)

    # --- Activity summary (7d) ---
    recent_actions = (
        db.query(ActionLog.action_type, func.count())
        .filter(ActionLog.account_id == account_id, ActionLog.created_at >= seven_days_ago)
        .group_by(ActionLog.action_type)
        .all()
    )

    return {
        "account_id": account_id,
        "status": account.status,
        "success_rate": success_rate,
        "total_steps_30d": total_steps,
        "done_steps_30d": done_steps,
        "failed_steps_30d": failed_steps,
        "ghost_count": ghost_count,
        "captcha_errors_30d": captcha_errors,
        "total_errors_30d": total_errors,
        "stability_score": stability,
        "last_active_at": str(account.last_active_at) if account.last_active_at else None,
        "recent_activity_7d": {row[0]: row[1] for row in recent_actions},
    }


@router.get("/api/{account_id}/history")
def account_history(
    account_id: int,
    page: int = 1,
    size: int = 50,
    action_type: str | None = None,
    db: Session = Depends(get_db),
):
    """Per-account activity history with comment links."""
    account = db.query(Account).get(account_id)
    if not account:
        return {"error": "not found"}

    query = db.query(ActionLog).filter(ActionLog.account_id == account_id)
    if action_type:
        query = query.filter(ActionLog.action_type == action_type)

    total = query.count()
    logs = query.order_by(ActionLog.created_at.desc()).offset((page - 1) * size).limit(size).all()

    items = []
    for al in logs:
        item = {
            "id": al.id,
            "action_type": al.action_type,
            "is_promo": al.is_promo,
            "content": al.content[:100] if al.content else None,
            "video_id": al.video_id,
            "campaign_id": al.campaign_id,
            "youtube_comment_id": al.youtube_comment_id,
            "ip_address": al.ip_address,
            "duration_sec": al.duration_sec,
            "status": al.status,
            "created_at": str(al.created_at),
        }

        # Build YouTube comment link if we have both video_id and comment_id
        if al.video_id and al.youtube_comment_id:
            item["comment_url"] = (
                f"https://www.youtube.com/watch?v={al.video_id}"
                f"&lc={al.youtube_comment_id}"
            )
        else:
            item["comment_url"] = None

        items.append(item)

    return {"total": total, "page": page, "items": items}


# --- #8: Account Info Change + Channel Creation ---

class AccountUpdateInput(BaseModel):
    gmail: str | None = None
    password: str | None = None
    recovery_email: str | None = None
    phone_number: str | None = None
    notes: str | None = None
    daily_comment_limit: int | None = None
    daily_like_limit: int | None = None
    weekly_comment_limit: int | None = None
    weekly_like_limit: int | None = None


def _apply_limit_updates(account: Account, data: AccountUpdateInput) -> list[str]:
    """Validate and apply 4 limit fields. Returns list of invalid field names."""
    invalid = []
    if data.daily_comment_limit is not None:
        if data.daily_comment_limit < 0:
            invalid.append("daily_comment_limit")
        else:
            account.daily_comment_limit = data.daily_comment_limit
    if data.daily_like_limit is not None:
        if data.daily_like_limit < 0:
            invalid.append("daily_like_limit")
        else:
            account.daily_like_limit = data.daily_like_limit
    if data.weekly_comment_limit is not None:
        if data.weekly_comment_limit < 0:
            invalid.append("weekly_comment_limit")
        else:
            account.weekly_comment_limit = data.weekly_comment_limit
    if data.weekly_like_limit is not None:
        if data.weekly_like_limit < 0:
            invalid.append("weekly_like_limit")
        else:
            account.weekly_like_limit = data.weekly_like_limit
    return invalid


@router.post("/api/{account_id}/update")
def update_account(account_id: int, data: AccountUpdateInput, db: Session = Depends(get_db)):
    """Update account information."""
    account = db.query(Account).get(account_id)
    if not account:
        return {"error": "not found"}

    if data.gmail is not None:
        account.gmail = data.gmail
    if data.password:
        account.password = encrypt(data.password)
    if data.recovery_email is not None:
        account.recovery_email = data.recovery_email
    if data.phone_number is not None:
        account.phone_number = data.phone_number
    if data.notes is not None:
        account.notes = data.notes

    invalid = _apply_limit_updates(account, data)
    if invalid:
        return {"error": "invalid_limits", "fields": invalid}

    db.commit()
    return {"ok": True, "id": account.id}


class BulkLimitsInput(BaseModel):
    account_ids: list[int]
    daily_comment_limit: int | None = None
    daily_like_limit: int | None = None
    weekly_comment_limit: int | None = None
    weekly_like_limit: int | None = None


@router.post("/api/bulk-update-limits")
def bulk_update_limits(data: BulkLimitsInput, db: Session = Depends(get_db)):
    """일괄 한도 변경. 지정된 필드만 갱신, None 필드는 유지."""
    if not data.account_ids:
        return {"error": "no_accounts"}

    # 검증: 음수 금지
    for field in ("daily_comment_limit", "daily_like_limit",
                  "weekly_comment_limit", "weekly_like_limit"):
        v = getattr(data, field)
        if v is not None and v < 0:
            return {"error": "invalid_limits", "fields": [field]}

    accounts = db.query(Account).filter(Account.id.in_(data.account_ids)).all()
    updated = 0
    for account in accounts:
        if data.daily_comment_limit is not None:
            account.daily_comment_limit = data.daily_comment_limit
        if data.daily_like_limit is not None:
            account.daily_like_limit = data.daily_like_limit
        if data.weekly_comment_limit is not None:
            account.weekly_comment_limit = data.weekly_comment_limit
        if data.weekly_like_limit is not None:
            account.weekly_like_limit = data.weekly_like_limit
        updated += 1
    db.commit()
    return {"ok": True, "updated": updated}


@router.post("/api/{account_id}/create-channel")
def create_youtube_channel(account_id: int, db: Session = Depends(get_db)):
    """Trigger YouTube channel creation automation for account."""
    account = db.query(Account).get(account_id)
    if not account:
        return {"error": "not found"}
    if account.youtube_channel_id:
        return {"ok": True, "message": "이미 채널이 있습니다", "channel_id": account.youtube_channel_id}

    # Queue the channel creation task
    from hydra.accounts.manager import queue_channel_creation
    try:
        queue_channel_creation(db, account)
        return {"ok": True, "message": "채널 생성 대기열에 추가됨"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# --- #22: Batch Account Setup ---

class BatchSetupInput(BaseModel):
    account_ids: list[int] | None = None
    status_filter: str | None = "registered"
    actions: list[str]  # ["create_profile", "assign_persona", "create_channel"]
    limit: int = 200


@router.post("/api/batch/setup")
def batch_setup(data: BatchSetupInput, db: Session = Depends(get_db)):
    """Batch setup accounts: create profiles, assign personas, create channels."""
    query = db.query(Account)
    if data.account_ids:
        query = query.filter(Account.id.in_(data.account_ids))
    elif data.status_filter:
        query = query.filter(Account.status == data.status_filter)

    accounts = query.limit(data.limit).all()
    results = {"total": len(accounts), "actions": {}}

    for action in data.actions:
        success = 0
        failed = 0

        if action == "create_profile":
            from hydra.accounts.manager import create_adspower_profile
            for a in accounts:
                if a.adspower_profile_id:
                    continue
                try:
                    create_adspower_profile(db, a)
                    success += 1
                except Exception:
                    failed += 1

        elif action == "assign_persona":
            from hydra.ai.agents.persona_agent import assign_persona
            for a in accounts:
                if a.persona:
                    continue
                try:
                    assign_persona(db, a)
                    success += 1
                except Exception:
                    failed += 1

        elif action == "create_channel":
            from hydra.accounts.manager import queue_channel_creation
            for a in accounts:
                if a.youtube_channel_id:
                    continue
                try:
                    queue_channel_creation(db, a)
                    success += 1
                except Exception:
                    failed += 1

        results["actions"][action] = {"success": success, "failed": failed}

    return results


# ─── 본인 인증(identity challenge) 관리 ─────────────────────────────

@router.post("/api/{account_id}/identity-challenge/unlock")
def identity_challenge_unlock(account_id: int, db: Session = Depends(get_db)):
    """쿨다운 강제 해제. 이전 준비 상태(warmup/registered)로 복원."""
    acct = db.get(Account, account_id)
    if not acct:
        return {"error": "not found"}
    acct.identity_challenge_until = None
    if acct.status == "identity_challenge":
        acct.status = "warmup" if acct.onboard_completed_at else "registered"
    db.commit()
    return {"ok": True, "status": acct.status, "count": acct.identity_challenge_count or 0}


@router.post("/api/{account_id}/identity-challenge/ban")
def identity_challenge_ban(account_id: int, db: Session = Depends(get_db)):
    """본인 인증 반복 실패 계정을 영구 suspended 처리."""
    acct = db.get(Account, account_id)
    if not acct:
        return {"error": "not found"}
    acct.status = "suspended"
    acct.retired_at = datetime.now(timezone.utc)
    acct.retired_reason = f"identity_challenge repeated (count={acct.identity_challenge_count or 0})"
    db.commit()
    return {"ok": True, "status": acct.status}


@router.get("/api/identity-challenge/stats")
def identity_challenge_stats(db: Session = Depends(get_db)):
    """본인 인증 쿨다운 현황 + 해제 예정."""
    now = datetime.now(timezone.utc)
    rows = db.query(Account).filter(Account.identity_challenge_count > 0).all()
    items = []
    for a in rows:
        until = a.identity_challenge_until
        items.append({
            "id": a.id,
            "gmail": a.gmail,
            "status": a.status,
            "count": a.identity_challenge_count or 0,
            "until": str(until) if until else None,
            "remaining_seconds": max(0, int((until - now).total_seconds())) if until else 0,
            "active_cooldown": bool(until and until > now),
        })
    items.sort(key=lambda x: (-x["active_cooldown"], -x["count"]))
    return {
        "total": len(items),
        "active_cooldown": sum(1 for i in items if i["active_cooldown"]),
        "items": items,
    }


# ─── 온보딩 / 상태 / 채널 ────────────────────────────────────────

@router.post("/api/{account_id}/onboard/retry")
def onboard_retry(account_id: int, db: Session = Depends(get_db)):
    """실패/부분 완료 계정 온보딩 재시도 태스크 enqueue."""
    from hydra.db.models import Task
    import json as _json
    acct = db.get(Account, account_id)
    if not acct:
        return {"error": "not found"}
    from hydra.core import crypto
    payload = {
        "email": acct.gmail,
        "password": crypto.decrypt(acct.password) if acct.password else None,
        "recovery_email": acct.recovery_email,
        "persona": _json.loads(acct.persona) if acct.persona else None,
    }
    task = Task(
        task_type="onboard",
        account_id=acct.id,
        status="pending",
        priority="high",
        payload=_json.dumps(payload, ensure_ascii=False),
        created_at=datetime.now(timezone.utc),
    )
    db.add(task)
    db.commit()
    return {"ok": True, "task_id": task.id}


@router.get("/api/{account_id}/onboard/actions")
def onboard_actions(account_id: int, db: Session = Depends(get_db)):
    """계정의 최근 onboard Task 실행 결과(result JSON의 actions 필드) 반환."""
    from hydra.db.models import Task
    import json as _json
    tasks = (
        db.query(Task)
        .filter(Task.account_id == account_id, Task.task_type == "onboard")
        .order_by(Task.created_at.desc())
        .limit(5)
        .all()
    )
    rows = []
    for t in tasks:
        result = None
        if t.result:
            try:
                result = _json.loads(t.result)
            except Exception:
                result = {"raw": t.result}
        rows.append({
            "task_id": t.id,
            "status": t.status,
            "created_at": str(t.created_at),
            "completed_at": str(t.completed_at) if t.completed_at else None,
            "error": t.error_message,
            "actions": (result or {}).get("actions", []) if isinstance(result, dict) else [],
            "critical_failures": (result or {}).get("critical_failures", []) if isinstance(result, dict) else [],
            "ok": (result or {}).get("ok") if isinstance(result, dict) else None,
        })
    return {"items": rows}


@router.get("/api/{account_id}/channel/verify")
async def channel_verify(account_id: int, db: Session = Depends(get_db)):
    """YT 공개 페이지에서 채널명 읽어 DB 값과 비교 — 라이브 검증. 쿠키/로그인 불요."""
    import httpx
    import re
    acct = db.get(Account, account_id)
    if not acct:
        return {"error": "not found"}
    if not acct.youtube_channel_id:
        return {"error": "channel_id missing"}
    url = f"https://www.youtube.com/channel/{acct.youtube_channel_id}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            r = await c.get(url, headers={"Accept-Language": "ko"})
            html = r.text
    except Exception as e:
        return {"error": f"fetch failed: {e}"}
    # og:title 에 채널명 있음
    m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    live_name = m.group(1) if m else None
    persona = json.loads(acct.persona) if acct.persona else {}
    expected = (persona.get("channel_plan") or {}).get("title")
    return {
        "channel_id": acct.youtube_channel_id,
        "live_name": live_name,
        "expected_name": expected,
        "match": bool(live_name and expected and live_name.strip() == expected.strip()),
    }


# ─── 모니터링: 아바타 인벤토리 / IP 로그 ────────────────────────

@router.get("/api/avatars/inventory")
def avatars_inventory():
    """페르소나 아바타 파일 풀 현황 — 토픽별 개수, 빈 폴더 경고."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent.parent.parent / "data" / "avatars"
    topics = {}
    warnings = []
    if not root.exists():
        return {"root": str(root), "topics": {}, "warnings": ["avatars root missing"]}
    for kind_dir in root.iterdir():
        if not kind_dir.is_dir():
            continue
        for sub in kind_dir.iterdir():
            if not sub.is_dir():
                continue
            files = [p for p in sub.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
            key = f"{kind_dir.name}/{sub.name}"
            topics[key] = len(files)
            if len(files) == 0:
                warnings.append(f"{key}: empty")
            elif len(files) < 10:
                warnings.append(f"{key}: low ({len(files)})")
    return {"root": str(root), "topics": topics, "warnings": warnings}


@router.get("/api/{account_id}/ip-log")
def account_ip_log(account_id: int, limit: int = 30, db: Session = Depends(get_db)):
    """계정의 최근 IP 사용 기록. ip_logs 테이블 기반."""
    from hydra.db.models import IpLog
    rows = (
        db.query(IpLog)
        .filter(IpLog.account_id == account_id)
        .order_by(IpLog.started_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "ip": r.ip_address,
                "device_id": r.device_id,
                "started_at": str(r.started_at),
                "ended_at": str(r.ended_at) if r.ended_at else None,
            }
            for r in rows
        ]
    }
