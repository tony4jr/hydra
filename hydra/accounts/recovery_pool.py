"""Recovery email pool management.

Each Google signup needs a recovery email. We pre-load a pool of real
emails (Naver, Daum, Gmail, etc.) with IMAP credentials so HYDRA can
retrieve Google's verification codes automatically.

Lifecycle:
  disabled=False, used_by_account_id=NULL  →  available
  claim_for_account(account_id)            →  marks used_by + used_at
  release_on_failure()                     →  clears used_by so it can retry
  mark_burned()                            →  disabled=True (manual intervention)
"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from hydra.core.crypto import encrypt, decrypt
from hydra.core.logger import get_logger
from hydra.db.models import RecoveryEmail
from hydra.infra.imap_reader import detect_imap_host

log = get_logger("recovery_pool")


class RecoveryPoolExhausted(RuntimeError):
    """Raised when no available recovery emails remain."""


def add_email(db: Session, email: str, password: str,
              imap_host: str | None = None, imap_port: int = 993,
              notes: str | None = None) -> RecoveryEmail:
    """Add a new recovery email to the pool. Password is encrypted."""
    host = imap_host or detect_imap_host(email)
    rec = RecoveryEmail(
        email=email.strip().lower(),
        password=encrypt(password),
        imap_host=host,
        imap_port=imap_port,
        notes=notes,
    )
    db.add(rec)
    db.commit()
    log.info(f"Added recovery email: {rec.email} (host={rec.imap_host})")
    return rec


def bulk_add(db: Session, rows: list[dict]) -> dict:
    """Bulk import from CSV-shaped dicts.

    Each row: {email, password, imap_host?, imap_port?, notes?}
    Returns {added, skipped_duplicates, errors}.
    """
    added = 0
    skipped = 0
    errors: list[str] = []

    for row in rows:
        email = (row.get("email") or "").strip().lower()
        pw = (row.get("password") or "").strip()
        if not email or not pw:
            errors.append(f"missing email or password: {row}")
            continue

        existing = db.query(RecoveryEmail).filter(RecoveryEmail.email == email).first()
        if existing:
            skipped += 1
            continue

        try:
            host = (row.get("imap_host") or "").strip() or detect_imap_host(email)
            port = int(row.get("imap_port") or 993)
            db.add(RecoveryEmail(
                email=email,
                password=encrypt(pw),
                imap_host=host,
                imap_port=port,
                notes=(row.get("notes") or "").strip() or None,
            ))
            added += 1
        except Exception as e:
            errors.append(f"{email}: {e}")

    db.commit()
    log.info(f"Recovery pool bulk add: +{added}, skipped={skipped}, errors={len(errors)}")
    return {"added": added, "skipped_duplicates": skipped, "errors": errors}


def claim_for_account(db: Session, account_id: int) -> RecoveryEmail | None:
    """Pick an available recovery email and reserve it for this account.

    Returns None if the pool is empty — caller should abort signup.
    """
    rec = (
        db.query(RecoveryEmail)
        .filter(
            RecoveryEmail.disabled == False,  # noqa: E712
            RecoveryEmail.used_by_account_id.is_(None),
        )
        .order_by(RecoveryEmail.id)
        .with_for_update(nowait=True, skip_locked=True) if db.bind.dialect.name == "postgresql"
        else db.query(RecoveryEmail).filter(
            RecoveryEmail.disabled == False,  # noqa: E712
            RecoveryEmail.used_by_account_id.is_(None),
        ).order_by(RecoveryEmail.id)
    ).first()

    if not rec:
        return None

    rec.used_by_account_id = account_id
    rec.used_at = datetime.now(timezone.utc)
    db.commit()
    log.info(f"Claimed recovery email #{rec.id} ({rec.email}) for account {account_id}")
    return rec


def release(db: Session, recovery_id: int):
    """Release a claimed recovery (signup aborted before consumption)."""
    rec = db.query(RecoveryEmail).get(recovery_id)
    if not rec:
        return
    rec.used_by_account_id = None
    rec.used_at = None
    db.commit()
    log.info(f"Released recovery email #{rec.id} ({rec.email})")


def mark_burned(db: Session, recovery_id: int, reason: str = ""):
    """Disable a recovery email (credentials invalid, blacklisted, etc.)."""
    rec = db.query(RecoveryEmail).get(recovery_id)
    if not rec:
        return
    rec.disabled = True
    rec.last_error = reason[:500]
    db.commit()
    log.warning(f"Burned recovery email #{rec.id} ({rec.email}): {reason}")


def get_credentials(rec: RecoveryEmail) -> tuple[str, str, str, int]:
    """Return (email, password_plain, host, port)."""
    return (rec.email, decrypt(rec.password), rec.imap_host or "", rec.imap_port or 993)


def pool_stats(db: Session) -> dict:
    """Return summary stats for the pool."""
    from sqlalchemy import func, case
    total = db.query(func.count(RecoveryEmail.id)).scalar()
    available = db.query(func.count(RecoveryEmail.id)).filter(
        RecoveryEmail.disabled == False,  # noqa: E712
        RecoveryEmail.used_by_account_id.is_(None),
    ).scalar()
    used = db.query(func.count(RecoveryEmail.id)).filter(
        RecoveryEmail.used_by_account_id.isnot(None),
    ).scalar()
    disabled = db.query(func.count(RecoveryEmail.id)).filter(
        RecoveryEmail.disabled == True,  # noqa: E712
    ).scalar()
    return {
        "total": total or 0,
        "available": available or 0,
        "used": used or 0,
        "disabled": disabled or 0,
    }
