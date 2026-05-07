"""PR-B 6-layer system prompt 합성 검증."""
import json

from hydra.ai.agents.slot_agent import _build_slot_system_prompt
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
