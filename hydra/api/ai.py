"""AI 댓글 생성 API — Worker에서 요청 시 content_agent 호출."""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from hydra.db.session import get_db
from hydra.db.models import Brand, Preset, Video, Worker
from hydra.web.routes.worker_api import worker_auth

router = APIRouter(prefix="/api", tags=["ai"])


@router.post("/generate-comment")
def generate_comment(
    body: dict,
    _worker: Worker = Depends(worker_auth),
    db: Session = Depends(get_db),
):
    """Worker에서 요청 시 AI 댓글 생성. worker_auth 로 보호."""
    from hydra.ai.agents.content_agent import generate_conversation

    video_id = body.get("video_id", "")
    brand_id = body.get("brand_id")
    preset_code = body.get("preset_code", "A")
    step_number = body.get("step_number", 1)

    # 영상 정보
    video = db.get(Video, video_id) if video_id else None
    video_dict = (
        {"title": video.title or "", "description": video.description or "", "url": video.url or ""}
        if video
        else {"title": "", "description": "", "url": ""}
    )

    # 브랜드 정보
    brand = db.get(Brand, brand_id) if brand_id else None
    brand_dict: dict = {}
    if brand:
        brand_dict = {
            "name": brand.name,
            "product": brand.product_category or "",
            "core_message": brand.core_message or "",
            "tone_guide": brand.tone_guide or "",
            "banned_keywords": brand.banned_keywords or "[]",
            "promo_keywords": brand.promo_keywords or "[]",
        }

    # 프리셋
    preset = db.query(Preset).filter(Preset.code == preset_code).first()
    steps = json.loads(preset.steps) if preset else [
        {"step_number": 1, "role": "seed", "type": "comment", "tone": "자연스러운"}
    ]

    # 해당 스텝만 추출
    target_steps = [s for s in steps if s["step_number"] == step_number] or steps[:1]

    # 페르소나
    persona = body.get("persona")

    try:
        results = generate_conversation(
            brand=brand_dict,
            preset_steps=target_steps,
            video=video_dict,
            personas=[persona] if persona else None,
        )
        if results:
            return {"text": results[0]["text"]}
    except Exception as e:
        return {"text": "", "error": str(e)}

    return {"text": ""}
