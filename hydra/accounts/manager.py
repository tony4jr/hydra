"""Account lifecycle manager — state machine.

Spec Part 2:
registered → profile_set → warmup → active → (cooldown/retired)

CSV import, warmup group assignment, status transitions.
"""

import csv
import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from hydra.core.config import settings
from hydra.core.logger import get_logger
from hydra.core import crypto
from hydra.core.enums import AccountStatus, WarmupGroup, WARMUP_DAYS
from hydra.db.models import Account, AccountProfileHistory
from hydra.browser.adspower import adspower
from hydra.infra import telegram

log = get_logger("accounts")


def import_from_csv(db: Session, csv_path: str | Path) -> int:
    """Import accounts from CSV.

    Required: gmail, password
    Optional: recovery_email, phone_number, totp_secret
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    count = 0
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gmail = row.get("gmail", "").strip()
            if not gmail:
                continue

            # Skip duplicate
            if db.query(Account).filter(Account.gmail == gmail).first():
                log.warning(f"Skipping duplicate: {gmail}")
                continue

            # Auto-assign warmup group
            group = random.choice(list(WarmupGroup))

            account = Account(
                gmail=gmail,
                password=crypto.encrypt(row.get("password", "").strip()),
                recovery_email=row.get("recovery_email", "").strip() or None,
                phone_number=row.get("phone_number", "").strip() or None,
                totp_secret=crypto.encrypt(row.get("totp_secret", "").strip()) if row.get("totp_secret", "").strip() else None,
                warmup_group=group,
                status=AccountStatus.REGISTERED,
            )
            db.add(account)
            count += 1

    db.commit()
    log.info(f"Imported {count} accounts from {path.name}")
    return count


def record_profile_creation(
    db: Session,
    account: Account,
    *,
    profile_id: str,
    worker_id: int | None,
    fingerprint_snapshot: dict,
    device_hint: str,
    created_source: str = "auto",
) -> AccountProfileHistory:
    """Atomically link an AdsPower profile to an account and record history.

    Raises:
        ValueError: if the account already has an active profile.
    """
    if account.adspower_profile_id:
        raise ValueError(
            f"Account {account.id} ({account.gmail}) already has an active profile: "
            f"{account.adspower_profile_id}"
        )

    account.adspower_profile_id = profile_id
    account.status = AccountStatus.PROFILE_SET

    history = AccountProfileHistory(
        account_id=account.id,
        worker_id=worker_id,
        adspower_profile_id=profile_id,
        fingerprint_snapshot=json.dumps(fingerprint_snapshot, ensure_ascii=False),
        created_source=created_source,
        device_hint=device_hint,
    )
    db.add(history)
    db.commit()
    log.info(f"Profile {profile_id} linked to {account.gmail} (source={created_source})")
    return history


def retire_profile_record(db: Session, account: Account, reason: str):
    """Mark the account's active profile as retired. Idempotent."""
    if not account.adspower_profile_id:
        return
    active = (
        db.query(AccountProfileHistory)
        .filter_by(account_id=account.id, retired_at=None)
        .first()
    )
    if active:
        active.retired_at = datetime.now(timezone.utc)
        active.retire_reason = reason
    account.adspower_profile_id = None
    db.commit()
    log.info(f"Profile retired for {account.gmail} (reason={reason})")


def create_adspower_profile(
    db: Session,
    account: Account,
    *,
    fingerprint_config: dict | None = None,
    device_hint: str = "windows_heavy",
) -> str:
    """Server-side convenience: create profile synchronously on Worker-less setups.

    In production, prefer queueing a `create_profile` task so a Worker handles
    the AdsPower API call (Worker has the local AdsPower instance).
    """
    from hydra.browser.fingerprint_bundle import build_fingerprint_payload
    name = f"hydra_{account.id}_{account.gmail.split('@')[0]}"
    if fingerprint_config is None:
        fingerprint_config = build_fingerprint_payload(device_hint)

    for attempt in range(3):
        try:
            profile_id = adspower.create_profile(
                name=name,
                group_id=settings.adspower_group_id,
                fingerprint_config=fingerprint_config,
            )
            record_profile_creation(
                db, account,
                profile_id=profile_id, worker_id=None,
                fingerprint_snapshot=fingerprint_config,
                device_hint=device_hint,
            )
            return profile_id
        except Exception as e:
            log.warning(f"AdsPower profile creation attempt {attempt+1} failed: {e}")
            if attempt == 2:
                telegram.warning(f"AdsPower 프로필 생성 실패: {account.gmail}")
                raise


def transition(db: Session, account: Account, new_status: AccountStatus, reason: str = ""):
    """Change account status with logging."""
    old = account.status
    account.status = new_status

    if new_status == AccountStatus.WARMUP:
        days = WARMUP_DAYS.get(account.warmup_group, 7)
        account.warmup_start_date = datetime.now(timezone.utc)
        account.warmup_end_date = datetime.now(timezone.utc) + timedelta(days=days)
        if not account.warmup_day:
            account.warmup_day = 1

    elif new_status == AccountStatus.ACTIVE:
        account.last_active_at = datetime.now(timezone.utc)
        telegram.info(f"계정 웜업 졸업: {account.gmail}")

    elif new_status == AccountStatus.COOLDOWN:
        account.ghost_count += 1
        telegram.warning(f"Ghost 감지 ({account.ghost_count}회): {account.gmail}")

    elif new_status == AccountStatus.RETIRED:
        account.retired_at = datetime.now(timezone.utc)
        account.retired_reason = reason
        telegram.warning(f"계정 폐기: {account.gmail} — {reason}")

    elif new_status == AccountStatus.SUSPENDED:
        account.retired_at = datetime.now(timezone.utc)
        account.retired_reason = "suspended"
        account.status = AccountStatus.RETIRED
        telegram.urgent(f"계정 정지 감지: {account.gmail}")

    db.commit()
    log.info(f"Account {account.gmail}: {old} → {new_status} ({reason})")


def check_warmup_graduation(db: Session) -> list[Account]:
    """Check and graduate accounts that completed warmup period.

    스텝 기반: warmup_day > 3 이면 졸업. 날짜 기반 조건 제거 — 스케줄러 지연/
    일시정지 등으로 달력일 계산이 틀어지는 것을 방지.
    """
    ready = (
        db.query(Account)
        .filter(
            Account.status == AccountStatus.WARMUP,
            Account.warmup_day > 3,
        )
        .all()
    )

    graduated = []
    for account in ready:
        transition(db, account, AccountStatus.ACTIVE, "warmup completed")
        graduated.append(account)

    if graduated:
        log.info(f"Graduated {len(graduated)} accounts from warmup")

    return graduated


def check_cooldown_recovery(db: Session) -> list[Account]:
    """Check and recover accounts from ghost cooldown."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ghost_cooldown_days)
    ready = (
        db.query(Account)
        .filter(
            Account.status == AccountStatus.COOLDOWN,
            Account.last_active_at <= cutoff,
        )
        .all()
    )

    recovered = []
    for account in ready:
        if account.ghost_count >= 2:
            transition(db, account, AccountStatus.RETIRED, "ghost 2회 누적")
        else:
            transition(db, account, AccountStatus.ACTIVE, "cooldown recovery")
            recovered.append(account)

    return recovered


def handle_ghost(db: Session, account: Account):
    """Handle ghost detection for an account."""
    if account.ghost_count >= 1:
        # Second ghost → retire
        transition(db, account, AccountStatus.RETIRED, "ghost 2회")
    else:
        # First ghost → cooldown
        transition(db, account, AccountStatus.COOLDOWN, "ghost detected")


def get_available_accounts(
    db: Session,
    role: str | None = None,
    exclude_ids: list[int] | None = None,
) -> list[Account]:
    """Get active accounts available for work."""
    query = db.query(Account).filter(Account.status == AccountStatus.ACTIVE)

    if role and role != "any":
        query = query.filter(
            (Account.role_preference == role) | (Account.role_preference == "any") | (Account.role_preference.is_(None))
        )

    if exclude_ids:
        query = query.filter(Account.id.notin_(exclude_ids))

    return query.all()


def get_account_stats(db: Session) -> dict:
    """Get summary of account statuses."""
    accounts = db.query(Account).all()
    stats = {}
    for a in accounts:
        stats[a.status] = stats.get(a.status, 0) + 1
    stats["total"] = len(accounts)
    return stats


def queue_channel_creation(db: Session, account: Account):
    """Queue YouTube channel creation task for an account.

    The actual creation happens during the next browser session:
    1. Open YouTube in account's browser profile
    2. Click "Create a channel"
    3. Fill in name from persona
    4. Confirm

    This just marks the account as needing channel creation.
    """
    if account.youtube_channel_id:
        return

    account.notes = json.dumps({
        **(json.loads(account.notes) if account.notes and account.notes.startswith("{") else {}),
        "pending_channel_creation": True,
    }, ensure_ascii=False)
    db.commit()
    log.info(f"Queued channel creation for {account.gmail}")
