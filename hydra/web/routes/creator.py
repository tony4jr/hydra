"""Account creator API — trigger Gmail signup + 2FA + warmup from web UI."""

import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from hydra.accounts.creator import create_account
from hydra.accounts.tfa_setup import setup_totp
from hydra.accounts.warmup_runner import run_warmup_session
from hydra.core.config import settings
from hydra.core.logger import get_logger
from hydra.db.models import Account
from hydra.db.session import SessionLocal, get_db

log = get_logger("web.creator")

router = APIRouter()


class CreateRequest(BaseModel):
    count: int = 1
    device_id: str | None = None  # override settings.adb_device_id


def _resolve_device(device_id: str | None) -> str | None:
    return device_id or settings.adb_device_id or None


async def _create_many(count: int, device_id: str | None):
    """Background job — create N accounts sequentially with delays."""
    db = SessionLocal()
    try:
        for i in range(count):
            log.info(f"Creating account {i+1}/{count}")
            await create_account(db, device_id=device_id)
            # Stagger between signups so we don't look like a script
            await asyncio.sleep(60 + 30 * i)
    finally:
        db.close()


@router.post("/api/create")
async def api_create(req: CreateRequest, bg: BackgroundTasks):
    """Queue N signup attempts in the background."""
    device_id = _resolve_device(req.device_id)
    bg.add_task(_create_many, req.count, device_id)
    return {"ok": True, "queued": req.count, "device_id": device_id or "(none)"}


class TotpRequest(BaseModel):
    account_id: int


async def _setup_totp_task(account_id: int):
    db = SessionLocal()
    try:
        acct = db.query(Account).get(account_id)
        if acct:
            await setup_totp(db, acct)
    finally:
        db.close()


@router.post("/api/setup-totp")
async def api_setup_totp(req: TotpRequest, bg: BackgroundTasks):
    bg.add_task(_setup_totp_task, req.account_id)
    return {"ok": True, "account_id": req.account_id}


class WarmupRequest(BaseModel):
    account_id: int
    device_id: str | None = None


async def _warmup_task(account_id: int, device_id: str | None):
    db = SessionLocal()
    try:
        acct = db.query(Account).get(account_id)
        if acct:
            await run_warmup_session(acct, device_id=device_id)
    finally:
        db.close()


@router.post("/api/warmup")
async def api_warmup(req: WarmupRequest, bg: BackgroundTasks):
    device_id = _resolve_device(req.device_id)
    bg.add_task(_warmup_task, req.account_id, device_id)
    return {"ok": True, "account_id": req.account_id, "device_id": device_id or "(none)"}


@router.get("/api/status")
def api_status(db: Session = Depends(get_db)):
    """Summary of accounts by status."""
    from sqlalchemy import func
    rows = db.query(Account.status, func.count(Account.id)).group_by(Account.status).all()
    return {"by_status": {s: c for s, c in rows}}
