import json
import re
import random
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import Session
from hydra.db.models import Brand, Campaign, Task, Preset, Video


def create_campaign_with_tasks(
    db: Session,
    video_id: str,
    brand_id: int,
    preset_code: str,
    campaign_type: str = "scenario",
    comment_mode: str = "ai_auto",
) -> Campaign:
    """캠페인 생성 + 프리셋 기반 태스크 자동 분해."""
    preset = db.query(Preset).filter(Preset.code == preset_code).first()
    if not preset:
        raise ValueError(f"Preset '{preset_code}' not found")

    campaign = Campaign(
        video_id=video_id,
        brand_id=brand_id,
        scenario=preset_code,
        campaign_type=campaign_type,
        comment_mode=comment_mode,
        preset_id=preset.id,
        status="planning",
    )
    db.add(campaign)
    db.flush()

    steps = json.loads(preset.steps)
    base_time = datetime.now(UTC)

    for step in steps:
        delay_min = step.get("delay_min", 0)
        delay_max = step.get("delay_max", 0)
        delay = random.uniform(delay_min, delay_max) if delay_max > 0 else 0
        scheduled_at = base_time + timedelta(minutes=delay)

        task = Task(
            campaign_id=campaign.id,
            task_type=step["type"],
            priority="normal",
            status="pending",
            payload=json.dumps({
                "step_number": step["step_number"],
                "role": step["role"],
                "tone": step.get("tone", ""),
                "target": step.get("target", "main"),
                "video_id": video_id,
                "brand_id": brand_id,
                "preset_code": preset_code,
            }, ensure_ascii=False),
            scheduled_at=scheduled_at,
        )
        db.add(task)

        like_count = step.get("like_count", 0)
        if like_count > 0:
            like_delay = delay + random.uniform(2, 8)
            for i in range(like_count):
                like_scheduled = base_time + timedelta(
                    minutes=like_delay + random.uniform(0.25, 1.5) * i
                )
                like_task = Task(
                    campaign_id=campaign.id,
                    task_type="like_boost",
                    priority="low",
                    status="pending",
                    payload=json.dumps({
                        "target_step": step["step_number"],
                        "video_id": video_id,
                    }, ensure_ascii=False),
                    scheduled_at=like_scheduled,
                )
                db.add(like_task)

    campaign.status = "in_progress"
    db.commit()
    db.refresh(campaign)
    return campaign


def create_direct_campaign(
    db: Session,
    video_urls: list[str],
    actions: dict,
) -> list[Campaign]:
    """다이렉트 캠페인: URL 여러 개 + 작업 선택."""
    campaigns = []
    for url in video_urls:
        video_id = extract_video_id(url)
        if not video_id:
            continue

        campaign = Campaign(
            video_id=video_id,
            brand_id=actions.get("brand_id", 1),
            scenario=actions.get("scenario", "direct"),
            campaign_type="direct",
            comment_mode=actions.get("comment_mode", "manual"),
            status="in_progress",
        )
        db.add(campaign)
        db.flush()

        base_time = datetime.now(UTC)

        like_count = actions.get("like_count", 0)
        for i in range(like_count):
            task = Task(
                campaign_id=campaign.id,
                task_type="like",
                priority="normal",
                status="pending",
                payload=json.dumps({"video_id": video_id}, ensure_ascii=False),
                scheduled_at=base_time + timedelta(seconds=random.uniform(15, 90) * i),
            )
            db.add(task)

        comments = actions.get("comments", [])
        for j, comment in enumerate(comments):
            task = Task(
                campaign_id=campaign.id,
                task_type="comment",
                priority="normal",
                status="pending",
                payload=json.dumps({
                    "video_id": video_id,
                    "text": comment.get("text", ""),
                    "mode": comment.get("mode", "manual"),
                }, ensure_ascii=False),
                scheduled_at=base_time + timedelta(minutes=random.uniform(3, 15) * j),
            )
            db.add(task)

        if actions.get("subscribe", False):
            task = Task(
                campaign_id=campaign.id,
                task_type="subscribe",
                priority="low",
                status="pending",
                payload=json.dumps({"video_id": video_id}, ensure_ascii=False),
                scheduled_at=base_time,
            )
            db.add(task)

        db.commit()
        campaigns.append(campaign)

    return campaigns


def extract_video_id(url: str) -> str | None:
    """YouTube URL에서 video ID 추출."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def generate_campaign_texts(
    db: Session,
    campaign_id: int,
) -> list[dict]:
    """캠페인의 태스크에 AI 생성 텍스트를 채움.

    캠페인의 프리셋 + 브랜드 + 영상 정보로 content_agent 호출,
    결과를 각 태스크의 payload에 text 필드로 추가.
    """
    campaign = db.get(Campaign, campaign_id)
    if not campaign or not campaign.preset_id:
        return []

    preset = db.get(Preset, campaign.preset_id)
    if not preset:
        return []

    # 브랜드 정보 구성
    brand_obj = db.get(Brand, campaign.brand_id) if campaign.brand_id else None
    brand_dict = {}
    if brand_obj:
        brand_dict = {
            "name": brand_obj.name,
            "product": brand_obj.product_category or "",
            "core_message": brand_obj.core_message or "",
            "keywords": [],
            "tone_guide": brand_obj.tone_guide or "자연스러운 말투",
            "banned_keywords": brand_obj.banned_keywords or "[]",
        }

    # 영상 정보
    video_obj = db.get(Video, campaign.video_id) if campaign.video_id else None
    video_dict = {}
    if video_obj:
        video_dict = {
            "title": video_obj.title or "",
            "description": video_obj.description or "",
            "url": video_obj.url or "",
        }

    # 프리셋 스텝
    steps = json.loads(preset.steps)

    # AI 생성 호출
    try:
        from hydra.ai.agents.content_agent import generate_conversation
        results = generate_conversation(
            brand=brand_dict,
            preset_steps=steps,
            video=video_dict,
        )
    except Exception as e:
        print(f"AI generation failed: {e}")
        return []

    # 태스크에 텍스트 채우기
    comment_tasks = db.query(Task).filter(
        Task.campaign_id == campaign_id,
        Task.task_type.in_(["comment", "reply"]),
    ).order_by(Task.created_at).all()

    for task, result in zip(comment_tasks, results):
        payload = json.loads(task.payload or "{}")
        payload["text"] = result["text"]
        payload["ai_generated"] = True
        task.payload = json.dumps(payload, ensure_ascii=False)

    db.commit()
    return results
