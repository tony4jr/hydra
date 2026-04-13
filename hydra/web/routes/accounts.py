"""Account management API."""

import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from hydra.db.session import get_db
from hydra.db.models import Account, ActionLog

router = APIRouter()


class ImportRequest(BaseModel):
    path: str


@router.post("/api/import")
def import_csv(data: ImportRequest, db: Session = Depends(get_db)):
    from hydra.accounts.manager import import_from_csv
    try:
        count = import_from_csv(db, data.path)
        return {"ok": True, "message": f"{count}개 계정 가져오기 완료"}
    except FileNotFoundError:
        return {"ok": False, "message": "파일을 찾을 수 없습니다"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


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

    return {
        "total": total,
        "page": page,
        "items": [
            {
                "id": a.id,
                "gmail": a.gmail,
                "status": a.status,
                "warmup_group": a.warmup_group,
                "warmup_end_date": str(a.warmup_end_date) if a.warmup_end_date else None,
                "ghost_count": a.ghost_count,
                "adspower_profile_id": a.adspower_profile_id,
                "has_persona": a.persona is not None,
                "has_cookies": a.cookies is not None,
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
        "warmup_end_date": str(account.warmup_end_date) if account.warmup_end_date else None,
        "ghost_count": account.ghost_count,
        "persona": account.persona,
        "adspower_profile_id": account.adspower_profile_id,
        "has_cookies": account.cookies is not None,
        "notes": account.notes,
        "created_at": str(account.created_at),
        "last_active_at": str(account.last_active_at) if account.last_active_at else None,
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
    from hydra.accounts.persona import assign_persona
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
    from hydra.accounts.persona import batch_assign_personas
    accounts = db.query(Account).filter(Account.persona.is_(None)).all()
    batch_assign_personas(db, accounts)
    return {"ok": True, "count": len(accounts)}


@router.get("/api/csv-template")
def csv_template():
    """Return CSV template content."""
    return {
        "headers": ["gmail", "password", "recovery_email", "phone_number", "totp_secret"],
        "required": ["gmail", "password"],
        "optional": ["recovery_email", "phone_number", "totp_secret"],
        "example": "user@gmail.com,MyP@ss123,recovery@gmail.com,+821012345678,JBSWY3DPEHPK3PXP",
    }
