"""Task M1-6 + M2.2: 어드민 계정 등록 / 복구 import.

- register: 신규 계정 (status=registered, onboarding_verify task enqueue)
- import-recovered: 이미 활성 상태인 복구 계정 bulk insert (status=active, task 생성 X)
"""
from __future__ import annotations

from datetime import UTC, datetime

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


class RecoveredAccount(BaseModel):
    gmail: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)
    adspower_profile_id: str = Field(..., min_length=1)
    recovery_email: str | None = None
    phone_number: str | None = None
    youtube_channel_id: str | None = None
    notes: str | None = None


class ImportRecoveredRequest(BaseModel):
    accounts: list[RecoveredAccount]


class ImportRecoveredResult(BaseModel):
    imported: list[int]  # 새로 생성된 account_id 들
    skipped: list[dict]  # {"gmail": ..., "reason": ...}


@router.post("/import-recovered", response_model=ImportRecoveredResult)
def import_recovered_accounts(
    req: ImportRecoveredRequest,
    _session: dict = Depends(admin_session),
) -> ImportRecoveredResult:
    """DB 손실 후 복구된 계정들을 bulk insert.

    - status=active, warmup_day=4, onboard_completed_at=now (이미 온보딩/워밍업 완료 가정)
    - 온보딩 태스크 생성 X
    - gmail 또는 adspower_profile_id 중복 시 해당 row 는 skip (전체 실패 X)

    M1 파이프라인 진입점과 별개 — 복구 전용. 향후 실 자동 생성도 이 경로 재사용 가능.
    """
    db = _db_session.SessionLocal()
    try:
        imported: list[int] = []
        skipped: list[dict] = []
        now = datetime.now(UTC)

        for r in req.accounts:
            if db.query(Account).filter_by(gmail=r.gmail).first():
                skipped.append({"gmail": r.gmail, "reason": "gmail_exists"})
                continue
            if db.query(Account).filter_by(
                adspower_profile_id=r.adspower_profile_id
            ).first():
                skipped.append({
                    "gmail": r.gmail,
                    "reason": "profile_id_exists",
                    "profile_id": r.adspower_profile_id,
                })
                continue

            acc = Account(
                gmail=r.gmail,
                password=crypto.encrypt(r.password),
                adspower_profile_id=r.adspower_profile_id,
                recovery_email=r.recovery_email,
                phone_number=r.phone_number,
                youtube_channel_id=r.youtube_channel_id,
                notes=r.notes,
                status="active",
                warmup_day=4,
                onboard_completed_at=now,
            )
            db.add(acc)
            db.flush()
            imported.append(acc.id)

        db.commit()
        return ImportRecoveredResult(imported=imported, skipped=skipped)
    finally:
        db.close()
