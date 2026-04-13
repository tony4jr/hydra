"""AI comment generation using Claude API.

Spec Part 6 + 1.4:
- Persona-aware comment generation
- Brand rules enforcement (allowed/banned keywords)
- Role-specific tone (seed, witness, agree, etc.)
- Post-generation validation
- Token saving: cache, reuse non-promo comments
"""

import json
import re

import anthropic
from sqlalchemy.orm import Session

from hydra.core.config import settings
from hydra.core.logger import get_logger
from hydra.core.enums import AccountRole
from hydra.db.models import Account, Brand, Video, ActionLog

log = get_logger("content")

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.claude_api_key)
    return _client


# Role descriptions for Claude
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
    """Generate a comment using Claude.

    Args:
        persona: Account's persona dict
        role: Account role for this comment
        brand: Brand info (selling points, rules, etc.)
        video: Target video
        context: Additional context (e.g., conversation so far)
        is_reply: Whether this is a reply to another comment
        parent_comment: The comment being replied to
    """
    client = _get_client()

    # Parse brand data
    allowed = json.loads(brand.allowed_keywords or "[]")
    banned = json.loads(brand.banned_keywords or "[]")
    selling_points = json.loads(brand.selling_points or "[]")
    mention_rules = json.loads(brand.mention_rules or "{}")

    # Build system prompt
    system = f"""당신은 YouTube에 댓글을 남기는 한국인입니다.

[페르소나]
- 나이: {persona.get('age')}세
- 성별: {"여성" if persona.get('gender') == 'female' else "남성"}
- 지역: {persona.get('region', '서울')}
- 직업: {persona.get('occupation', '직장인')}
- 관심사: {', '.join(persona.get('interests', []))}
- 말투: {persona.get('speech_style', '편한 존댓말')}
- 이모지 빈도: {persona.get('emoji_frequency', 'medium')}
- 문장 길이: {persona.get('comment_length', 'medium')}

[역할]
{ROLE_PROMPTS.get(role, '')}

[브랜드 정보 — 자연스럽게 녹여야 함]
- 브랜드: {brand.name}
- 카테고리: {brand.product_category or ''}
- 핵심 메시지: {brand.core_message or ''}
- 셀링포인트: {', '.join(selling_points)}
- 톤 가이드: {brand.tone_guide or '과장 없이 자연스럽게'}

[규칙 — 반드시 지켜야 함]
- 사용 가능 키워드: {', '.join(allowed)}
- 금지 키워드 (절대 사용 금지): {', '.join(banned)}
- 브랜드명 직접 언급: {"가능" if mention_rules.get("brand_direct") else "불가"}
- 성분명만 언급: {"가능" if mention_rules.get("ingredient_only") else "불가"}
- 광고처럼 보이면 안 됨. 진짜 사용자처럼 자연스럽게.
- 댓글만 출력. 설명이나 메타 텍스트 금지."""

    # Build user prompt
    user_msg = f"영상: {video.title}\n"
    if context:
        user_msg += f"\n대화 맥락:\n{context}\n"
    if is_reply and parent_comment:
        user_msg += f"\n이 댓글에 답글:\n\"{parent_comment}\"\n"
    user_msg += "\n위 상황에 맞는 댓글 1개만 작성해주세요."

    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            comment = resp.content[0].text.strip()

            # Strip any wrapping quotes
            comment = comment.strip('"').strip("'")

            # Validate
            issues = validate_comment(comment, banned, brand.name, mention_rules)
            if not issues:
                log.info(f"Generated comment ({role}): {comment[:50]}...")
                return comment

            log.warning(f"Validation failed (attempt {attempt+1}): {issues}")
            # Add hint for retry
            user_msg += f"\n\n⚠️ 이전 시도 문제: {', '.join(issues)}. 수정해서 다시 작성해주세요."

        except anthropic.RateLimitError:
            log.warning("Claude rate limit, waiting 60s")
            import time
            time.sleep(60)
        except Exception as e:
            log.error(f"Comment generation error: {e}")
            if attempt == max_retries - 1:
                raise

    raise RuntimeError(f"Failed to generate valid comment after {max_retries} attempts")


def validate_comment(
    comment: str,
    banned_keywords: list[str],
    brand_name: str,
    mention_rules: dict,
) -> list[str]:
    """Validate a generated comment. Returns list of issues (empty = OK)."""
    issues = []

    # Check banned keywords
    for kw in banned_keywords:
        if kw in comment:
            issues.append(f"금지 키워드 포함: '{kw}'")

    # Check brand mention rules
    if not mention_rules.get("brand_direct") and brand_name in comment:
        issues.append(f"브랜드명 직접 언급 불가: '{brand_name}'")

    # Length check
    if len(comment) > 500:
        issues.append("댓글 500자 초과")
    if len(comment) < 2:
        issues.append("댓글 너무 짧음")

    # Obvious ad patterns
    ad_patterns = [r"구매.*링크", r"할인.*코드", r"지금.*구매", r"클릭.*여기"]
    for pattern in ad_patterns:
        if re.search(pattern, comment):
            issues.append(f"광고 패턴 감지: {pattern}")

    return issues


def generate_non_promo_comment(persona: dict, video_title: str) -> str:
    """Generate a non-promotional comment (minimal AI usage).

    These are generic reactions that don't mention any brand.
    Can be cached and reused.
    """
    client = _get_client()

    system = f"""당신은 YouTube 시청자입니다.
말투: {persona.get('speech_style', '편한 존댓말')}
이모지: {persona.get('emoji_frequency', 'medium')}
문장 길이: {persona.get('comment_length', 'medium')}

영상에 대한 짧고 자연스러운 감상평을 1개만 작성하세요.
브랜드·제품 언급 절대 금지. 순수 감상만."""

    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=150,
        system=system,
        messages=[{"role": "user", "content": f"영상: {video_title}"}],
    )

    return resp.content[0].text.strip().strip('"').strip("'")


def check_duplicate(db: Session, comment: str, account_id: int) -> bool:
    """Check if this exact comment was already posted by this account."""
    existing = (
        db.query(ActionLog)
        .filter(
            ActionLog.account_id == account_id,
            ActionLog.content == comment,
        )
        .first()
    )
    return existing is not None
