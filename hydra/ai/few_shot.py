"""Few-shot examples management for comment generation quality."""

from hydra.core.enums import AccountRole

# Role-specific example comments for few-shot prompting.
# Keyed by AccountRole → list of example comments.
ROLE_EXAMPLES: dict[AccountRole, list[str]] = {
    AccountRole.SEED: [
        "요즘 머리 빠지는 거 너무 스트레스인데 혹시 뭐 좋은 거 아시는 분..?",
        "저 이거 고민 되는데 써보신 분 계세요?",
    ],
    AccountRole.ASKER: [
        "이거 실제로 효과 있어요?? 후기 궁금해요",
        "혹시 어디서 사셨어요?",
    ],
    AccountRole.WITNESS: [
        "저도 3개월 먹어봤는데 확실히 달라진 느낌이에요",
        "처음엔 반신반의했는데 써보니까 괜찮더라고요",
    ],
    AccountRole.AGREE: [
        "맞아요 ㅋㅋ 인정",
        "ㅇㅇ 저도요",
        "완전 공감",
    ],
    AccountRole.CURIOUS: [
        "오 진짜요?? 나도 한번 해볼까",
        "헐 이런 게 있었어?",
    ],
    AccountRole.INFO: [
        "이건 비오틴 성분이 들어있어서 효과가 있는 거예요",
        "원래 이 성분은 FDA 인증받은 거라 안전해요",
    ],
    AccountRole.FAN: [
        "인생템 찾았다 ㅠㅠ 진짜 최고",
        "이건 진짜 안 쓰면 손해임",
    ],
    AccountRole.QA: [
        "그건 보통 2~3주 정도면 효과 보신다고 하더라고요",
        "아마 공식몰에서 사시면 될 거예요!",
    ],
}


def get_examples(role: AccountRole, count: int = 2) -> list[str]:
    """Get few-shot examples for a role."""
    examples = ROLE_EXAMPLES.get(role, [])
    return examples[:count]
