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
from hydra.db.models import Account
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


def create_adspower_profile(db: Session, account: Account) -> str:
    """Create AdsPower browser profile for account."""
    name = f"hydra_{account.id}_{account.gmail.split('@')[0]}"

    for attempt in range(3):
        try:
            profile_id = adspower.create_profile(name)
            account.adspower_profile_id = profile_id
            db.commit()
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
    """Check and graduate accounts that completed warmup period."""
    now = datetime.now(timezone.utc)
    ready = (
        db.query(Account)
        .filter(
            Account.status == AccountStatus.WARMUP,
            Account.warmup_end_date <= now,
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
