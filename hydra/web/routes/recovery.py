"""Recovery email pool management API."""

import csv
import io

from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from hydra.accounts import recovery_pool
from hydra.core.crypto import decrypt, encrypt
from hydra.core.logger import get_logger
from hydra.db.models import RecoveryEmail
from hydra.db.session import SessionLocal, get_db
from hydra.infra.imap_reader import test_imap_login, detect_imap_host

log = get_logger("web.recovery")

router = APIRouter()


# ─── CRUD ───

class RecoveryCreate(BaseModel):
    email: str
    password: str
    imap_host: str | None = None
    imap_port: int = 993
    notes: str | None = None


@router.post("/api/create")
def create_one(data: RecoveryCreate, db: Session = Depends(get_db)):
    rec = recovery_pool.add_email(
        db, data.email, data.password,
        imap_host=data.imap_host, imap_port=data.imap_port, notes=data.notes,
    )
    return {"ok": True, "id": rec.id, "imap_host": rec.imap_host}


@router.get("/api/list")
def list_all(db: Session = Depends(get_db)):
    rows = db.query(RecoveryEmail).order_by(RecoveryEmail.id).all()
    return [
        {
            "id": r.id,
            "email": r.email,
            "imap_host": r.imap_host,
            "imap_port": r.imap_port,
            "used_by_account_id": r.used_by_account_id,
            "used_at": r.used_at.isoformat() if r.used_at else None,
            "disabled": r.disabled,
            "last_error": r.last_error,
            "notes": r.notes,
        }
        for r in rows
    ]


@router.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    return recovery_pool.pool_stats(db)


@router.post("/api/{rec_id}/toggle-disable")
def toggle_disable(rec_id: int, db: Session = Depends(get_db)):
    rec = db.query(RecoveryEmail).get(rec_id)
    if not rec:
        return {"error": "not found"}
    rec.disabled = not rec.disabled
    db.commit()
    return {"ok": True, "disabled": rec.disabled}


@router.post("/api/{rec_id}/release")
def release_one(rec_id: int, db: Session = Depends(get_db)):
    """Release a recovery email so it can be claimed again."""
    recovery_pool.release(db, rec_id)
    return {"ok": True}


# ─── CSV 업로드 ───

@router.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Accept CSV with columns: email,password,imap_host?,imap_port?,notes?"""
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))

    rows = []
    for row in reader:
        # Normalize keys (strip + lowercase)
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        rows.append(clean)

    result = recovery_pool.bulk_add(db, rows)
    return {"ok": True, **result}


# ─── IMAP 로그인 테스트 ───

class TestLoginRequest(BaseModel):
    rec_id: int


async def _test_task(rec_id: int):
    db = SessionLocal()
    try:
        rec = db.query(RecoveryEmail).get(rec_id)
        if not rec:
            return
        ok, err = await test_imap_login(
            rec.email, decrypt(rec.password),
            host=rec.imap_host, port=rec.imap_port or 993,
        )
        if ok:
            rec.last_error = None
        else:
            rec.last_error = err[:500]
            log.warning(f"IMAP login failed for {rec.email}: {err}")
        db.commit()
    finally:
        db.close()


@router.post("/api/test-login")
async def test_login(req: TestLoginRequest, bg: BackgroundTasks):
    bg.add_task(_test_task, req.rec_id)
    return {"ok": True, "rec_id": req.rec_id, "note": "running in background; refresh list to see result"}


# ─── 전체 IMAP 테스트 ───

async def _test_all_task():
    db = SessionLocal()
    try:
        recs = db.query(RecoveryEmail).filter(RecoveryEmail.disabled == False).all()  # noqa: E712
        for rec in recs:
            ok, err = await test_imap_login(
                rec.email, decrypt(rec.password),
                host=rec.imap_host, port=rec.imap_port or 993,
            )
            if ok:
                rec.last_error = None
            else:
                rec.last_error = err[:500]
            db.commit()
    finally:
        db.close()


@router.post("/api/test-all")
async def test_all(bg: BackgroundTasks):
    bg.add_task(_test_all_task)
    return {"ok": True, "note": "testing all non-disabled emails in background"}
