"""자동 캠페인 스케줄러 — 브랜드 주간 목표 기반 캠페인 자동 생성."""
import json
import random
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session
from hydra.db.models import Brand, Campaign, Video, Keyword, Preset
from hydra.services.campaign_service import create_campaign_with_tasks
from hydra.services.video_protection import check_video_campaign_limit


def get_brands_needing_campaigns(db: Session) -> list[dict]:
    """주간 목표가 설정된 브랜드 중 목표 미달인 것들 조회."""
    brands = db.query(Brand).filter(
        Brand.weekly_campaign_target > 0,
        Brand.auto_campaign_enabled == True,
        Brand.status == "active",
    ).all()

    result = []
    week_start = _get_week_start()

    for brand in brands:
        # 이번 주 캠페인 수
        week_campaigns = db.query(Campaign).filter(
            Campaign.brand_id == brand.id,
            Campaign.created_at >= week_start,
            Campaign.status != "cancelled",
        ).count()

        remaining = brand.weekly_campaign_target - week_campaigns
        if remaining > 0:
            result.append({
                "brand_id": brand.id,
                "brand_name": brand.name,
                "target": brand.weekly_campaign_target,
                "completed": week_campaigns,
                "remaining": remaining,
            })

    return result


def auto_create_campaigns(db: Session, max_per_run: int = 5) -> list[Campaign]:
    """자동 캠페인 생성. 주간 목표 미달 브랜드에 대해 캠페인 생성."""
    brands_needing = get_brands_needing_campaigns(db)
    created = []

    for brand_info in brands_needing:
        brand_id = brand_info["brand_id"]
        remaining = brand_info["remaining"]

        # 이번 실행에서 최대 max_per_run개
        to_create = min(remaining, max_per_run)

        # 작업 가능한 영상 찾기
        available_videos = _find_available_videos(db, brand_id, to_create)

        # 브랜드의 선택된 프리셋 사용
        brand = db.get(Brand, brand_id)
        if brand and brand.selected_presets:
            try:
                selected_codes = json.loads(brand.selected_presets)
                presets = db.query(Preset).filter(Preset.code.in_(selected_codes)).all()
            except (json.JSONDecodeError, TypeError):
                presets = db.query(Preset).all()
        else:
            presets = db.query(Preset).all()

        if not presets:
            continue

        for video in available_videos:
            # 영상 보호 규칙 체크
            allowed, _ = check_video_campaign_limit(db, video.id)
            if not allowed:
                continue

            preset = random.choice(presets)
            try:
                campaign = create_campaign_with_tasks(
                    db=db,
                    video_id=video.id,
                    brand_id=brand_id,
                    preset_code=preset.code,
                )
                created.append(campaign)
            except Exception as e:
                print(f"[Scheduler] Failed to create campaign: {e}")
                continue

            if len(created) >= max_per_run:
                break

    return created


def _find_available_videos(db: Session, brand_id: int, limit: int) -> list:
    """작업 우선순위에 따라 영상 선택.
    1순위: 인기 (조회수 높은 순)
    2순위: 신규 (24시간 이내)
    3순위: 최근 (7일 이내)
    4순위: 나머지
    """
    now = datetime.now(UTC)

    keywords = db.query(Keyword).filter(
        Keyword.brand_id == brand_id,
        Keyword.status == "active",
    ).all()
    keyword_ids = [kw.id for kw in keywords]
    if not keyword_ids:
        return []

    base_query = db.query(Video).filter(
        Video.keyword_id.in_(keyword_ids),
        Video.status == "available",
        Video.comments_enabled == True,
    )

    # 1순위: 조회수 높은 순
    popular = base_query.order_by(Video.view_count.desc()).limit(limit * 3).all()

    result = []
    for v in popular:
        if len(result) >= limit:
            break
        allowed, _ = check_video_campaign_limit(db, v.id)
        if allowed:
            result.append(v)

    if len(result) >= limit:
        return result

    # 2순위: 24시간 이내 신규
    new_cutoff = now - timedelta(hours=24)
    new_videos = base_query.filter(Video.published_at >= new_cutoff).order_by(Video.published_at.desc()).limit(limit * 2).all()
    for v in new_videos:
        if len(result) >= limit:
            break
        if v not in result:
            allowed, _ = check_video_campaign_limit(db, v.id)
            if allowed:
                result.append(v)

    if len(result) >= limit:
        return result

    # 3순위: 7일 이내
    recent_cutoff = now - timedelta(days=7)
    recent = base_query.filter(Video.published_at >= recent_cutoff).order_by(Video.published_at.desc()).limit(limit * 2).all()
    for v in recent:
        if len(result) >= limit:
            break
        if v not in result:
            allowed, _ = check_video_campaign_limit(db, v.id)
            if allowed:
                result.append(v)

    if len(result) >= limit:
        return result

    # 4순위: 나머지
    rest = base_query.order_by(Video.collected_at.desc()).limit(limit * 2).all()
    for v in rest:
        if len(result) >= limit:
            break
        if v not in result:
            allowed, _ = check_video_campaign_limit(db, v.id)
            if allowed:
                result.append(v)

    return result


def _get_week_start() -> datetime:
    """이번 주 월요일 00:00 UTC."""
    now = datetime.now(UTC)
    week_start = now - timedelta(days=now.weekday())
    return week_start.replace(hour=0, minute=0, second=0, microsecond=0)
