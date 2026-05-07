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
    Niche, Product, GlobalAdPhraseBlocklist,
)


# 길이별 토큰/문장 가이드 (한국어 토큰 비효율 보정 — 자/토큰 ≈ 0.3)
LENGTH_GUIDES = {
    "short": ("1~2문장, 30~60자", 200),
    "medium": ("2~3문장, 60~120자", 400),
    "long": ("3~5문장, 120~250자", 700),
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


def _detect_protected_terms(template: str | None, brand_name: str) -> list[str]:
    """템플릿에 등장하는 brand_name 키워드 추출. 글로벌 하드코딩 안 함."""
    out = []
    if brand_name:
        out.append(brand_name)
    # 운영자가 등록한 KNOWN_TYPO_PATTERNS 의 canonical (시작은 빈 dict)
    for canonical in KNOWN_TYPO_PATTERNS.keys():
        if canonical not in out:
            out.append(canonical)
    return out


def _build_slot_system_prompt(
    *,
    slot: CommentTreeSlot,
    brand: dict[str, Any],
    product: dict[str, Any] | None,
    niche: dict[str, Any],
    persona: dict[str, Any] | None,
    global_blocklist: list[str],
) -> str:
    """6-layer system prompt 합성.

    Layers:
      1. Global (Slot.intent / tone_anchor / length / emoji / mention 정책 / blocklist)
      2. Brand (tone_guide, banned, company_protected_terms)
      3. Product (product_name, protected_terms, core_keywords) — mention 허용 시만
      4. Niche (target_audience, mention_intensity, voice_override)
      5. Persona
      6. Conversation — _build_slot_user_message 에서 user message 로 따로
    """
    parts: list[str] = ["당신은 YouTube 영상에 댓글을 다는 한국 사용자입니다.",
                        "절대 광고처럼 보이면 안 됩니다."]

    # ── Layer 1: Global (slot 의도 + 정책) ──
    parts.append(f"\n[슬롯 의도]\n{slot.intent or '(미지정)'}")

    tone_anchor_list: list[str] = []
    if slot.tone_anchor:
        try:
            tone_anchor_list = json.loads(slot.tone_anchor)
        except (json.JSONDecodeError, TypeError):
            tone_anchor_list = []
    if tone_anchor_list:
        anchor_lines = "\n".join(f"  - {a}" for a in tone_anchor_list)
        parts.append(
            f"\n[톤 참고 — 변주 시드 X, 어휘 그대로 베끼지 말 것]\n{anchor_lines}"
        )

    length_text = LENGTH_GUIDES.get(slot.length, LENGTH_GUIDES["medium"])[0]
    emoji_text = EMOJI_GUIDES.get(slot.emoji, EMOJI_GUIDES["sometimes"])
    parts.append(f"\n길이 가이드: {length_text}")
    parts.append(f"이모지 가이드: {emoji_text}")

    mention_lines = []
    if not slot.mention_brand:
        mention_lines.append("- 브랜드명 직접 언급 절대 금지.")
    if not slot.mention_solution:
        mention_lines.append("- 솔루션 카테고리/성분 노출 금지.")
    if slot.mention_brand:
        mention_lines.append("- 브랜드명 자연스럽게 1회 노출 (강조 X).")
    if slot.mention_solution:
        mention_lines.append("- 솔루션 카테고리/성분 자연스럽게 언급 OK.")
    if mention_lines:
        parts.append("\n[노출 정책]\n" + "\n".join(mention_lines))

    if global_blocklist:
        bl_lines = ", ".join(f"'{p}'" for p in global_blocklist[:30])
        parts.append(f"\n[광고 카피 금지 어휘]\n{bl_lines}")

    # ── Layer 2: Brand ──
    parts.append(f"\n[브랜드]\n- 회사: {brand.get('name', '')}")
    if brand.get("tone_guide"):
        parts.append(f"- 톤 가이드: {brand['tone_guide']}")
    brand_banned = brand.get("banned_keywords") or []
    if brand_banned:
        parts.append(f"- 회사 banned: {', '.join(brand_banned)}")
    company_protected = brand.get("company_protected_terms") or []
    if company_protected:
        parts.append(f"- 회사 표기 lock: {', '.join(company_protected)}")

    # ── Layer 3: Product (mention 허용 시만) ──
    if product and (slot.mention_brand or slot.mention_solution):
        parts.append(f"\n[제품]")
        if slot.mention_brand:
            parts.append(f"- 제품명: {product.get('product_name', '')}")
            protected = product.get("protected_terms") or []
            if protected:
                parts.append(f"- 표기 lock (절대 변형 금지): {', '.join(protected)}")
        if slot.mention_solution:
            core_kw = product.get("core_keywords") or []
            if core_kw:
                parts.append(f"- 솔루션 키워드 (의도 substitution 후보): {', '.join(core_kw)}")

    # ── Layer 4: Niche ──
    parts.append(f"\n[타겟 니치]")
    if niche.get("target_audience"):
        parts.append(f"- 타겟: {niche['target_audience']}")
    intensity = niche.get("mention_intensity", 40)
    parts.append(
        f"- 노출 강도: {intensity}/100 "
        f"({'공감/정보 톤 우선' if intensity < 50 else '직접 추천 톤 허용' if intensity > 70 else '균형'})"
    )
    if niche.get("voice_override"):
        parts.append(f"- 니치 톤 추가: {niche['voice_override']}")

    # ── Layer 5: Persona ──
    if persona:
        parts.append(
            f"\n[페르소나 — 이 사람이 실제로 쓰듯]\n"
            f"- {persona.get('age', '?')}세 {persona.get('gender', '?')}\n"
            f"- 지역: {persona.get('region', '서울')}\n"
            f"- 직업: {persona.get('occupation', '직장인')}\n"
            f"- 말투: {persona.get('speech_style', '편한 존댓말')}"
        )

    parts.append(
        "\n[출력 규칙]\n"
        "- 한국어로 작성\n"
        "- 광고 패턴 금지 (구매 링크/할인/지금 구매)\n"
        "- 같은 표현 반복 금지\n"
        "- 댓글만 출력. 설명/따옴표/메타텍스트 없이."
    )

    return "\n".join(parts)


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


# 글로벌 typo 패턴 dict — 비어있음. Product.protected_terms 또는 운영자 추가로 채움.
# 형식: {canonical: [variant1, variant2, ...]}
KNOWN_TYPO_PATTERNS: dict[str, list[str]] = {}


def _check_protected_spelling(
    text: str,
    template: str | None,
    brand_name: str,
    *,
    extra_protected_terms: list[str] | None = None,
) -> list[str]:
    """보호 표기 검증.

    1. 결과물에 알려진 오타 변형이 있으면 → issue
    2. 템플릿이 보호 표기를 포함하는데 결과물에 없으면 → issue
    """
    issues = []
    template_text = template or ""

    # 알려진 오타 검출 (KNOWN_TYPO_PATTERNS 는 비어있음 — 운영자 등록 시 누적)
    for canonical, typos in KNOWN_TYPO_PATTERNS.items():
        for typo in typos:
            if typo in text:
                issues.append(f"오타 변형 '{typo}' (정답: '{canonical}')")

    # 템플릿이 정답 표기를 포함하면 결과물도 포함해야
    for canonical in KNOWN_TYPO_PATTERNS.keys():
        if canonical in template_text and canonical not in text:
            already_typo = any(t in text for t in KNOWN_TYPO_PATTERNS[canonical])
            if not already_typo:
                issues.append(f"템플릿이 '{canonical}' 포함하는데 결과물에 누락")

    # 브랜드명 자체
    if brand_name and brand_name not in KNOWN_TYPO_PATTERNS and brand_name in template_text:
        if brand_name not in text:
            issues.append(f"템플릿의 브랜드명 '{brand_name}' 누락")

    # extra_protected_terms (e.g., Product.protected_terms 에서 넘겨받음) — text에 변형 패턴이 있는지는 체크 안 함 (운영자가 typo seed 안 넣었으니 모름).
    # 단, 템플릿에 이런 term이 있으면 결과물에도 있어야:
    if extra_protected_terms and template_text:
        for term in extra_protected_terms:
            if term and term in template_text and term not in text:
                issues.append(f"템플릿의 보호 표기 '{term}' 누락")

    return issues


def _validator(
    text: str,
    banned_keywords: list[str],
    *,
    slot_mention_brand: bool,
    slot_mention_solution: bool,
    brand_name: str,
    protected_terms: list[str],
    core_keywords: list[str],
    global_blocklist: list[str],
) -> list[str]:
    """슬롯·브랜드·니치 정책을 통합 검증."""
    issues: list[str] = []

    if len(text) < 2:
        issues.append("too short")
    if len(text) > 500:
        issues.append("over 500 chars")

    # banned (brand-level)
    text_lower = text.lower()
    for kw in banned_keywords:
        if kw and kw.lower() in text_lower:
            issues.append(f"banned keyword: {kw}")

    # 광고 패턴 (하드코딩 — 항상)
    ad_phrases = ["구매 링크", "할인 코드", "지금 구매", "클릭 여기", "꼭 써보세요"]
    for ph in ad_phrases:
        if ph in text:
            issues.append(f"ad pattern: {ph}")

    # 글로벌 blocklist
    for ph in global_blocklist:
        if ph and ph in text:
            issues.append(f"global blocklist phrase: {ph}")

    # 알려진 오타 (autocorrect 와 같이)
    issues.extend(_check_protected_spelling(
        text, None, brand_name,
        extra_protected_terms=protected_terms,  # Product.protected_terms 그대로
    ))

    # mention_brand 정책
    if not slot_mention_brand and brand_name and brand_name in text:
        issues.append(f"슬롯 mention_brand=False 인데 브랜드명 '{brand_name}' 노출")

    # mention_solution 정책 (core_keywords 또는 추가 protected_terms 노출 차단)
    if not slot_mention_solution:
        # protected_terms 중 brand_name 이 아닌 (성분명) — 예: 체성케라틴
        for term in protected_terms:
            if term and term != brand_name and term in text:
                issues.append(f"슬롯 mention_solution=False 인데 솔루션 '{term}' 노출")
                break
        else:
            for kw in core_keywords:
                if kw and kw in text:
                    issues.append(f"슬롯 mention_solution=False 인데 성분 키워드 '{kw}' 노출")
                    break

    return issues


def _autocorrect_typos(text: str) -> tuple[str, list[str]]:
    """최후 안전망: validator retry 다 실패해도 출력 직전 자동 교정.

    Returns:
        (corrected_text, fixes_applied)
    """
    fixes = []
    out = text
    for canonical, typos in KNOWN_TYPO_PATTERNS.items():
        for typo in typos:
            if typo in out:
                out = out.replace(typo, canonical)
                fixes.append(f"{typo}→{canonical}")
    return out, fixes


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

    # Niche / Product 정보 합성
    niche_dict: dict[str, Any] = {}
    product_dict: dict[str, Any] | None = None
    if campaign and campaign.brand_id:
        niche_obj = None
        if hasattr(campaign, 'niche_id') and campaign.niche_id:
            niche_obj = db.get(Niche, campaign.niche_id)
        if niche_obj:
            niche_dict = {
                "target_audience": niche_obj.target_audience or "",
                "mention_intensity": getattr(niche_obj, "mention_intensity", 40),
                "voice_override": getattr(niche_obj, "voice_override", None),
            }
            if niche_obj.product_id:
                p_obj = db.get(Product, niche_obj.product_id)
                if p_obj:
                    product_dict = {
                        "product_name": p_obj.product_name or "",
                        "protected_terms": json.loads(p_obj.protected_terms or "[]"),
                        "core_keywords": json.loads(p_obj.core_keywords or "[]"),
                    }

    # global blocklist
    blocklist_rows = db.query(GlobalAdPhraseBlocklist).all()
    global_blocklist = [r.phrase for r in blocklist_rows]

    system = _build_slot_system_prompt(
        slot=slot,
        brand=brand_dict,
        product=product_dict,
        niche=niche_dict,
        persona=persona,
        global_blocklist=global_blocklist,
    )
    user = _build_slot_user_message(video_dict, slot, parent_text, sibling_texts)

    if dry_run:
        return (
            f"[DRY-RUN] slot={slot.slot_label} "
            f"parent={'Y' if parent_text else 'N'} "
            f"len={slot.length} emoji={slot.emoji} ai_var={slot.ai_variation}"
        )

    template_text = slot.intent or ""  # 더 이상 text_template 안 씀
    brand_name = brand_dict.get("name", "")
    product_protected = product_dict.get("protected_terms", []) if product_dict else []
    product_core = product_dict.get("core_keywords", []) if product_dict else []

    text = call_claude(
        model=get_model("comment"),
        system=system,
        user_message=user,
        max_tokens=LENGTH_GUIDES.get(slot.length, LENGTH_GUIDES["medium"])[1],
        validator=lambda t: _validator(
            t, banned,
            slot_mention_brand=slot.mention_brand,
            slot_mention_solution=slot.mention_solution,
            brand_name=brand_name,
            protected_terms=product_protected,
            core_keywords=product_core,
            global_blocklist=global_blocklist,
        ),
        max_retries=4,
    )

    # 최후 안전망 — retry 모두 통과해도 자동 교정 한 번 더
    text, fixes = _autocorrect_typos(text)
    if fixes:
        from hydra.ai.base import log
        log.warning(
            f"[slot_agent] task={task.id} slot={slot.slot_label} "
            f"autocorrected typos: {fixes}"
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
