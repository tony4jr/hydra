"""고스트 감지 3단계 — 자연 감지 → 교차 검증 → 시간차 재확인."""
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session
from hydra.db.models import Campaign, Account, Task
import json

# 고스트 상태
GHOST_PENDING = "pending"
GHOST_SUSPICIOUS = "suspicious"
GHOST_CONFIRMED = "ghost"
GHOST_VISIBLE = "visible"


def report_ghost_check(
    db: Session,
    campaign_id: int,
    comment_id: str,
    result: str,
    checked_by_account_id: int,
    checked_by_worker_id: int,
) -> str:
    """고스트 체크 결과 보고. 3단계 판정.

    Returns: 최종 판정 (visible, suspicious, ghost)
    """
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        return "error"

    current_status = campaign.ghost_check_status or GHOST_PENDING

    if result == "visible":
        # 보임 → 정상
        campaign.ghost_check_status = GHOST_VISIBLE
        campaign.ghost_checked_at = datetime.now(UTC)
        campaign.ghost_checked_by = checked_by_account_id
        db.commit()
        return GHOST_VISIBLE

    if result == "suspicious":
        if current_status == GHOST_PENDING:
            # 1단계: 처음 의심 → suspicious로 변경, 교차 검증 예약
            campaign.ghost_check_status = GHOST_SUSPICIOUS
            campaign.ghost_checked_at = datetime.now(UTC)
            campaign.ghost_checked_by = checked_by_account_id

            # 교차 검증 태스크 생성 (다른 계정, 다른 워커)
            _schedule_cross_check(db, campaign, comment_id, checked_by_account_id, checked_by_worker_id)
            db.commit()
            return GHOST_SUSPICIOUS

        elif current_status == GHOST_SUSPICIOUS:
            # 2단계: 교차 검증에서도 의심 → 24시간 후 재확인 예약
            _schedule_recheck(db, campaign, comment_id)
            db.commit()
            return GHOST_SUSPICIOUS

        elif current_status == "recheck_pending":
            # 3단계: 24시간 후에도 안 보임 → 고스트 확정
            campaign.ghost_check_status = GHOST_CONFIRMED
            campaign.ghost_checked_at = datetime.now(UTC)
            _handle_ghost_confirmed(db, campaign)
            db.commit()
            return GHOST_CONFIRMED

    return current_status


def _schedule_cross_check(db, campaign, comment_id, exclude_account_id, exclude_worker_id):
    """교차 검증 태스크 — 다른 계정, 다른 워커로."""
    task = Task(
        campaign_id=campaign.id,
        task_type="ghost_check",
        priority="high",
        status="pending",
        payload=json.dumps({
            "video_id": campaign.video_id,
            "youtube_comment_id": comment_id,
            "check_stage": "cross_check",
            "exclude_account_id": exclude_account_id,
            "exclude_worker_id": exclude_worker_id,
        }),
        scheduled_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db.add(task)


def _schedule_recheck(db, campaign, comment_id):
    """24시간 후 재확인 태스크."""
    campaign.ghost_check_status = "recheck_pending"
    task = Task(
        campaign_id=campaign.id,
        task_type="ghost_check",
        priority="normal",
        status="pending",
        payload=json.dumps({
            "video_id": campaign.video_id,
            "youtube_comment_id": comment_id,
            "check_stage": "recheck",
        }),
        scheduled_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db.add(task)


def _handle_ghost_confirmed(db, campaign):
    """고스트 확정 처리 — 시드 계정 쿨다운."""
    from hydra.db.models import CampaignStep
    seed_step = db.query(CampaignStep).filter(
        CampaignStep.campaign_id == campaign.id,
        CampaignStep.step_number == 1,
    ).first()
    if seed_step and seed_step.account_id:
        account = db.get(Account, seed_step.account_id)
        if account:
            account.status = "cooldown"
            account.ghost_count = (account.ghost_count or 0) + 1
