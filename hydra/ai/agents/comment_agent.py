"""Promotional comment generation agent (Sonnet).

Generates brand-aware comments that follow persona, role, and brand rules.
"""

import json

from hydra.ai.base import get_model, log
from hydra.ai.harness import call_claude, load_prompt
from hydra.ai.evaluator import validate_comment
from hydra.ai.few_shot import get_examples
from hydra.core.enums import AccountRole
from hydra.db.models import Brand, Video

ROLE_PROMPTS = {
    AccountRole.SEED: "첫 댓글을 남기는 역할. 화두를 던지고, 경험이나 고민을 자연스럽게 공유.",
    AccountRole.ASKER: "질문하는 역할. '뭐 드세요?', '효과 있어요?' 같은 자연스러운 질문.",
    AccountRole.WITNESS: "직접 경험한 사람. '저도 써봤는데 좋았어요' 같은 증언.",
    AccountRole.AGREE: "짧게 동의하는 역할. '맞아요', '저도요', '인정' 같은 짧은 반응.",
    AccountRole.CURIOUS: "관심을 보이는 역할. '오 진짜요?', '나도 해볼까' 같은 호기심.",
    AccountRole.INFO: "정보를 공유하는 역할. 성분, 원리 등 지식 기반 댓글.",
    AccountRole.FAN: "열렬한 팬. '인생템 ㅠㅠ', '진짜 최고' 같은 감정적 반응.",
    AccountRole.QA: "다른 사람 질문에 답변해주는 역할. 도움이 되는 답글.",
}


def generate_comment(
    persona: dict,
    role: AccountRole,
    brand: Brand,
    video: Video,
    context: str = "",
    is_reply: bool = False,
    parent_comment: str = "",
    max_retries: int = 3,
) -> str:
    """Generate a promotional comment using Claude.

    Args:
        persona: Account's persona dict.
        role: Account role for this comment.
        brand: Brand info (selling points, rules, etc.).
        video: Target video.
        context: Additional context (e.g., conversation so far).
        is_reply: Whether this is a reply to another comment.
        parent_comment: The comment being replied to.
        max_retries: Number of retry attempts.
    """
    allowed = json.loads(brand.allowed_keywords or "[]")
    banned = json.loads(brand.banned_keywords or "[]")
    selling_points = json.loads(brand.selling_points or "[]")
    mention_rules = json.loads(brand.mention_rules or "{}")

    # Few-shot examples
    examples = get_examples(role)
    examples_text = "\n".join(f"- {ex}" for ex in examples) if examples else "(없음)"

    system = load_prompt(
        "comment_system",
        age=persona.get("age"),
        gender_display="여성" if persona.get("gender") == "female" else "남성",
        region=persona.get("region", "서울"),
        occupation=persona.get("occupation", "직장인"),
        interests=", ".join(persona.get("interests", [])),
        speech_style=persona.get("speech_style", "편한 존댓말"),
        emoji_frequency=persona.get("emoji_frequency", "medium"),
        comment_length=persona.get("comment_length", "medium"),
        role_description=ROLE_PROMPTS.get(role, ""),
        few_shot_examples=examples_text,
        brand_name=brand.name,
        product_category=brand.product_category or "",
        core_message=brand.core_message or "",
        selling_points=", ".join(selling_points),
        tone_guide=brand.tone_guide or "과장 없이 자연스럽게",
        allowed_keywords=", ".join(allowed),
        banned_keywords=", ".join(banned),
        brand_direct="가능" if mention_rules.get("brand_direct") else "불가",
        ingredient_only="가능" if mention_rules.get("ingredient_only") else "불가",
    )

    user_msg = f"영상: {video.title}\n"
    if context:
        user_msg += f"\n대화 맥락:\n{context}\n"
    if is_reply and parent_comment:
        user_msg += f'\n이 댓글에 답글:\n"{parent_comment}"\n'
    user_msg += "\n위 상황에 맞는 댓글 1개만 작성해주세요."

    def _validator(text: str) -> list[str]:
        return validate_comment(text, banned, brand.name, mention_rules)

    def _retry_hint(issues: list[str]) -> str:
        return f"⚠️ 이전 시도 문제: {', '.join(issues)}. 수정해서 다시 작성해주세요."

    comment = call_claude(
        model=get_model("comment"),
        system=system,
        user_message=user_msg,
        max_tokens=300,
        max_retries=max_retries,
        validator=_validator,
        retry_hint_fn=_retry_hint,
    )
    log.info(f"Generated comment ({role}): {comment[:50]}...")
    return comment
