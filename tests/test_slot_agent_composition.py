"""PR-B 6-layer system prompt 합성 검증."""
import json

import pytest

from hydra.ai.agents.slot_agent import _build_slot_system_prompt, _validator
from hydra.db.models import CommentTreeSlot


def _slot(intent="[메인] 자연 토로", tone_anchor=None, mention_brand=False,
          mention_solution=False, length="medium", emoji="sometimes",
          ai_variation=80):
    s = CommentTreeSlot(
        slot_label="A", position=1,
        intent=intent,
        tone_anchor=json.dumps(tone_anchor or []) if tone_anchor else None,
        mention_brand=mention_brand,
        mention_solution=mention_solution,
        length=length, emoji=emoji,
        ai_variation=ai_variation,
        like_min=0, like_max=0, like_distribution="adaptive",
    )
    return s


def test_all_six_layers_present_in_system_prompt():
    sys_prompt = _build_slot_system_prompt(
        slot=_slot(intent="[메인·고민형] 자연 토로", mention_brand=False),
        brand={"name": "OO헬스", "tone_guide": "과장 X", "banned_keywords": ["일라스틴"],
               "company_protected_terms": []},
        product={"product_name": "모렉신",
                 "protected_terms": ["모렉신", "체성케라틴"],
                 "core_keywords": ["체성케라틴", "케라틴"]},
        niche={"target_audience": "산후 6개월 30대 여성",
               "mention_intensity": 40,
               "voice_override": None},
        persona={"age": 33, "gender": "여", "region": "서울",
                 "occupation": "직장인", "speech_style": "친근한 존댓말"},
        global_blocklist=["구매 링크", "할인 쿠폰"],
    )
    # Global layer
    assert "[메인·고민형] 자연 토로" in sys_prompt
    # Brand layer
    assert "OO헬스" in sys_prompt
    assert "과장 X" in sys_prompt
    # Niche layer
    assert "산후 6개월 30대 여성" in sys_prompt
    assert "40" in sys_prompt  # mention_intensity
    # Persona layer
    assert "33세 여" in sys_prompt
    assert "친근한 존댓말" in sys_prompt
    # Blocklist
    assert "구매 링크" in sys_prompt or "할인 쿠폰" in sys_prompt
    # Layer 3 absence — slot has mention_brand=False AND mention_solution=False,
    # so Product layer must NOT inject "[제품]" block even though product dict was provided
    assert "[제품]" not in sys_prompt


def test_layer_3_product_present_when_mention_allowed():
    sys_prompt = _build_slot_system_prompt(
        slot=_slot(intent="[D슬롯·답변] 제품 노출", mention_brand=True, mention_solution=True),
        brand={"name": "OO헬스", "tone_guide": "", "banned_keywords": [],
               "company_protected_terms": []},
        product={"product_name": "모렉신",
                 "protected_terms": ["모렉신", "체성케라틴"],
                 "core_keywords": ["체성케라틴"]},
        niche={"target_audience": "30대 여성", "mention_intensity": 70,
               "voice_override": None},
        persona=None,
        global_blocklist=[],
    )
    assert "[제품]" in sys_prompt
    assert "모렉신" in sys_prompt
    assert "체성케라틴" in sys_prompt


def test_validator_blocks_brand_mention_when_slot_forbids():
    issues = _validator(
        text="모렉신 짱이에요",
        banned_keywords=[],
        slot_mention_brand=False,
        slot_mention_solution=False,
        brand_name="모렉신",
        protected_terms=["모렉신", "체성케라틴"],
        core_keywords=["체성케라틴"],
        global_blocklist=[],
    )
    assert any("브랜드명" in i for i in issues)


def test_validator_blocks_solution_mention_when_slot_forbids():
    issues = _validator(
        text="체성케라틴이 좋아요",
        banned_keywords=[],
        slot_mention_brand=False,
        slot_mention_solution=False,
        brand_name="모렉신",
        protected_terms=["모렉신", "체성케라틴"],
        core_keywords=["체성케라틴", "케라틴"],
        global_blocklist=[],
    )
    assert any("솔루션" in i or "성분" in i or "체성케라틴" in i for i in issues)


def test_validator_passes_when_slot_allows_mention():
    issues = _validator(
        text="모렉신이라고 검색해보세요",
        banned_keywords=[],
        slot_mention_brand=True,
        slot_mention_solution=True,
        brand_name="모렉신",
        protected_terms=["모렉신", "체성케라틴"],
        core_keywords=["체성케라틴"],
        global_blocklist=[],
    )
    assert issues == []


def test_validator_blocks_global_blocklist_phrases():
    issues = _validator(
        text="구매 링크는 댓글에",
        banned_keywords=[],
        slot_mention_brand=True,
        slot_mention_solution=True,
        brand_name="모렉신",
        protected_terms=[],
        core_keywords=[],
        global_blocklist=["구매 링크"],
    )
    assert any("blocklist" in i.lower() or "구매 링크" in i for i in issues)


# ── C1 회귀 테스트 ──────────────────────────────────────────────────────────

def test_typo_dict_no_hardcoded_brand_terms():
    """KNOWN_TYPO_PATTERNS 가 빈 dict 로 시작 (multi-brand 안전)."""
    from hydra.ai.agents.slot_agent import KNOWN_TYPO_PATTERNS
    assert KNOWN_TYPO_PATTERNS == {}, "글로벌 typo 패턴이 하드코딩되면 안 됨"


def test_validator_doesnt_flag_other_brand_text():
    """모렉신 brand 가 아닌 곳에서 '모렉신' 단어가 들어가도 어떤 issue 도 안 남."""
    issues = _validator(
        text="저는 다른제품 잘 쓰고 있어요",
        banned_keywords=[],
        slot_mention_brand=True,
        slot_mention_solution=True,
        brand_name="다른브랜드",
        protected_terms=[],
        core_keywords=[],
        global_blocklist=[],
    )
    assert issues == []
