"""Task M1-6: 어드민 수동 계정 등록.

향후 실제 계정 자동 생성 로직이 들어오면 동일 파이프라인 트리거를 위해
같은 함수를 내부 호출하도록 설계.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hydra.core import crypto
from hydra.db import session as _db_session
from hydra.db.models import Account, Task
from hydra.web.routes.admin_auth import admin_session

router = APIRouter()


class AccountRegisterRequest(BaseModel):
    gmail: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)
    adspower_profile_id: str = Field(..., min_length=1)
    recovery_email: str | None = None
    phone_number: str | None = None


@router.post("/register")
def register_account(
    req: AccountRegisterRequest,
    _session: dict = Depends(admin_session),
) -> dict:
    db = _db_session.SessionLocal()
    try:
        if db.query(Account).filter_by(gmail=req.gmail).first():
            raise HTTPException(409, f"gmail already exists: {req.gmail}")
        if db.query(Account).filter_by(
            adspower_profile_id=req.adspower_profile_id
        ).first():
            raise HTTPException(
                409, f"adspower_profile_id in use: {req.adspower_profile_id}",
            )

        acc = Account(
            gmail=req.gmail,
            password=crypto.encrypt(req.password),
            adspower_profile_id=req.adspower_profile_id,
            recovery_email=req.recovery_email,
            phone_number=req.phone_number,
            status="registered",
        )
        db.add(acc)
        db.flush()

        db.add(Task(
            account_id=acc.id,
            task_type="onboarding_verify",
            status="pending",
        ))
        db.commit()
        return {"account_id": acc.id, "status": acc.status}
    finally:
        db.close()
