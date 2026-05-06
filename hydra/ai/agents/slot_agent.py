"""Slot-aware comment generator (Phase C).

CommentTreeSlot 의 text_template / length / emoji / ai_variation / persona 를
이용해 슬롯별 댓글 텍스트 생성. parent_task 의 텍스트를 부모 맥락으로 주입.

기존 content_agent.generate_conversation 과 별개의 진입점.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from hydra.ai.base import get_model
from hydra.ai.harness import call_claude
from hydra.db.models import (
    Account, Brand, Campaign, CommentPreset, CommentTreeSlot, Task, Video,
)


# 길이별 토큰/문장 가이드
LENGTH_GUIDES = {
    "short": ("1~2문장, 30~60자", 80),
    "medium": ("2~3문장, 60~120자", 160),
    "long": ("3~5문장, 120~250자", 280),
}

EMOJI_GUIDES = {
    "none": "이모지/이모티콘 사용 금지.",
    "sometimes": "이모지/ㅠㅠ/ㅎㅎ 같은 표현 1~2개만 자연스럽게.",
    "often": "이모지/ㅠㅠ/ㅎㅎ/!! 같은 표현 3~5개 적극 사용 (감정적인 톤).",
}


def _ai_variation_guide(variation: int) -> str:
    """ai_variation (0~100) → 변주 가이드.

    0   = 템플릿 거의 그대로
    50  = 의미 유지하며 자유 변주
    100 = 템플릿은 방향만 참고, 새로 작성
    """
    if variation <= 25:
        return "참고 템플릿을 거의 그대로 사용하되 어색한 부분만 다듬으세요."
    if variation <= 60:
        return "참고 템플릿의 의미를 유지하되 표현·어순·어휘를 자유롭게 변주하세요."
    return "참고 템플릿은 방향만 참고하고, 같은 의도를 새로운 표현으로 작성하세요."


def _build_slot_system_prompt(
    brand: dict[str, Any], slot: CommentTreeSlot, persona: dict[str, Any] | None
) -> str:
    length_text = LENGTH_GUIDES.get(slot.length, LENGTH_GUIDES["medium"])[0]
    emoji_text = EMOJI_GUIDES.get(slot.emoji, EMOJI_GUIDES["sometimes"])
    variation_text = _ai_variation_guide(slot.ai_variation)

    persona_block = ""
    if persona:
        persona_block = f"""
페르소나:
- {persona.get('age', '?')}세 {persona.get('gender', '?')}
- 지역: {persona.get('region', '서울')}
- 직업: {persona.get('occupation', '직장인')}
- 말투: {persona.get('speech_style', '편한 존댓말')}
이 사람이 실제로 쓰듯 작성하세요.
"""

    template_block = ""
    if slot.text_template:
        template_block = f"""
참고 템플릿:
\"\"\"{slot.text_template}\"\"\"
{variation_text}
"""

    return f"""당신은 YouTube 영상에 댓글을 다는 한국 사용자입니다.
절대 광고처럼 보이면 안 됩니다.

브랜드: {brand.get('name', '')}
제품: {brand.get('product_category', brand.get('product', ''))}
핵심 메시지: {brand.get('core_message', '')}
톤 가이드: {brand.get('tone_guide', '과장 없이 자연스럽게')}

길이 가이드: {length_text}
이모지 가이드: {emoji_text}
{persona_block}{template_block}
규칙:
- 한국어
- 광고 패턴 금지 (구매 링크/할인/지금 구매/꼭 써보세요)
- 같은 표현 반복 금지
- 댓글만 출력. 설명/따옴표/메타텍스트 없이.
"""


def _build_slot_user_message(
    video: dict[str, Any],
    slot: CommentTreeSlot,
    parent_text: str | None,
    sibling_texts: list[str],
) -> str:
    parts = [f"영상 제목: {video.get('title', '')}"]
    if video.get("description"):
        parts.append(f"영상 설명: {video['description'][:200]}")

    if parent_text:
        parts.append(f"\n부모 댓글 (이 댓글은 그 답글입니다):\n\"{parent_text}\"")

    if sibling_texts:
        sib = "\n".join(f"- {s}" for s in sibling_texts[:3])
        parts.append(f"\n같은 트리에 이미 작성된 댓글 (중복 금지):\n{sib}")

    if slot.reply_to_slot_label is None:
        parts.append("\n→ 메인 댓글을 작성하세요.")
    else:
        parts.append(f"\n→ 위 부모 댓글에 자연스러운 답글을 작성하세요.")

    return "\n".join(parts)


def _resolve_persona(account: Account | None) -> dict[str, Any] | None:
    if account is None or not account.persona:
        return None
    try:
        return json.loads(account.persona)
    except (json.JSONDecodeError, TypeError):
        return None


def _validator(text: str, banned_keywords: list[str]) -> list[str]:
    issues = []
    if len(text) < 2:
        issues.append("too short")
    if len(text) > 500:
        issues.append("over 500 chars")
    text_lower = text.lower()
    for kw in banned_keywords:
        if kw and kw.lower() in text_lower:
            issues.append(f"banned keyword: {kw}")
    ad_phrases = ["구매 링크", "할인 코드", "지금 구매", "클릭 여기", "꼭 써보세요"]
    for ph in ad_phrases:
        if ph in text:
            issues.append(f"ad pattern: {ph}")
    return issues


def generate_comment_for_task(
    db: Session,
    *,
    task: Task,
    dry_run: bool = False,
) -> str:
    """단일 Task (슬롯 기반) 의 댓글 텍스트 생성.

    parent_task 가 있으면 그 텍스트를 맥락으로 주입.
    같은 부모를 공유하는 형제 슬롯들의 기존 텍스트도 중복 회피용으로 전달.
    """
    if task.slot_id is None:
        raise ValueError(f"task {task.id} has no slot_id — not a slot-engine task")

    slot = db.get(CommentTreeSlot, task.slot_id)
    if slot is None:
        raise ValueError(f"slot {task.slot_id} not found")

    campaign = db.get(Campaign, task.campaign_id) if task.campaign_id else None
    brand = db.get(Brand, campaign.brand_id) if (campaign and campaign.brand_id) else None
    payload = json.loads(task.payload or "{}")
    video_id = payload.get("video_id")
    video = db.get(Video, video_id) if video_id else None
    account = db.get(Account, task.account_id) if task.account_id else None

    brand_dict = {
        "name": (brand.name if brand else ""),
        "product_category": (brand.product_category if brand else ""),
        "core_message": (brand.core_message if brand else ""),
        "tone_guide": (brand.tone_guide if brand else "자연스럽게"),
    }
    banned = []
    if brand and brand.banned_keywords:
        try:
            banned = json.loads(brand.banned_keywords)
        except (json.JSONDecodeError, TypeError):
            banned = []

    video_dict = {
        "title": (video.title if video else ""),
        "description": (video.description if video else ""),
    }

    parent_text = None
    if task.parent_task_id:
        parent = db.get(Task, task.parent_task_id)
        if parent and parent.payload:
            try:
                parent_payload = json.loads(parent.payload)
                parent_text = parent_payload.get("text")
            except (json.JSONDecodeError, TypeError):
                pass

    # 형제: 같은 parent_task_id 가진 다른 슬롯 task 들 (이미 텍스트 채워진 것만)
    sibling_texts: list[str] = []
    if task.parent_task_id and task.campaign_id:
        siblings = (
            db.query(Task)
            .filter(Task.parent_task_id == task.parent_task_id)
            .filter(Task.id != task.id)
            .all()
        )
        for s in siblings:
            try:
                sp = json.loads(s.payload or "{}")
                if sp.get("text"):
                    sibling_texts.append(sp["text"])
            except (json.JSONDecodeError, TypeError):
                pass

    persona = _resolve_persona(account)

    system = _build_slot_system_prompt(brand_dict, slot, persona)
    user = _build_slot_user_message(video_dict, slot, parent_text, sibling_texts)

    if dry_run:
        return (
            f"[DRY-RUN] slot={slot.slot_label} "
            f"parent={'Y' if parent_text else 'N'} "
            f"len={slot.length} emoji={slot.emoji} ai_var={slot.ai_variation}"
        )

    text = call_claude(
        model=get_model("comment"),
        system=system,
        user_message=user,
        max_tokens=LENGTH_GUIDES.get(slot.length, LENGTH_GUIDES["medium"])[1],
        validator=lambda t: _validator(t, banned),
    )
    return text


def generate_texts_for_campaign(
    db: Session, *, campaign_id: int, dry_run: bool = False,
) -> list[dict[str, Any]]:
    """슬롯 트리 기반 캠페인의 댓글/답글 task 들에 텍스트 채움.

    슬롯 position 순서대로 처리 (부모 먼저, 자식 나중에).

    Returns:
        [{"task_id": int, "slot_label": str, "text": str}, ...]
    """
    tasks = (
        db.query(Task)
        .filter(Task.campaign_id == campaign_id)
        .filter(Task.task_type.in_(("comment", "reply")))
        .filter(Task.slot_id.isnot(None))
        .order_by(Task.id)  # slot position 순으로 생성됐으니 id 순 == position 순
        .all()
    )
    results = []
    for task in tasks:
        text = generate_comment_for_task(db, task=task, dry_run=dry_run)
        payload = json.loads(task.payload or "{}")
        payload["text"] = text
        payload["ai_pending"] = False
        payload["ai_generated"] = not dry_run
        task.payload = json.dumps(payload, ensure_ascii=False)
        db.flush()
        results.append({
            "task_id": task.id,
            "slot_label": task.slot_label,
            "text": text,
        })
    db.commit()
    return results
