"""content_agent 단위 테스트 (Claude API 호출 없이)."""
from hydra.ai.agents.content_agent import (
    _select_model,
    _build_system_prompt,
    _build_user_message,
    _validate_comment,
    PROMO_ROLES,
    CASUAL_ROLES,
)


def test_select_model_promo():
    for role in PROMO_ROLES:
        model = _select_model(role)
        assert "sonnet" in model.lower() or model  # Sonnet 계열


def test_select_model_casual():
    for role in CASUAL_ROLES:
        model = _select_model(role)
        assert model  # Haiku 계열


def test_build_system_prompt():
    brand = {"name": "트리코라", "product": "탈모영양제", "core_message": "식물성 케라틴", "tone_guide": "자연스러운 후기"}
    prompt = _build_system_prompt(brand, "seed", "교육형")
    assert "트리코라" in prompt
    assert "교육형" in prompt
    assert "광고" in prompt  # 광고 금지 규칙 포함


def test_build_user_message_with_context():
    video = {"title": "탈모 예방법", "description": "탈모에 대해 알아봅시다"}
    step = {"step_number": 2, "type": "reply", "target": "step_1", "tone": "질문", "role": "asker"}
    context = [{"step_number": 1, "role": "seed", "text": "머리카락 구성성분을 먹어야해요", "type": "comment"}]
    msg = _build_user_message(video, step, context, None, None)
    assert "탈모 예방법" in msg
    assert "머리카락 구성성분" in msg
    assert "질문" in msg


def test_validate_comment_pass():
    brand = {"banned_keywords": []}
    assert _validate_comment("저도 이거 먹고 있는데 좋아요", brand) == []


def test_validate_comment_too_short():
    brand = {"banned_keywords": []}
    issues = _validate_comment("", brand)
    assert len(issues) > 0


def test_validate_comment_banned_keyword():
    brand = {"banned_keywords": ["경쟁사제품"]}
    issues = _validate_comment("경쟁사제품보다 나아요", brand)
    assert len(issues) > 0


def test_validate_comment_ad_phrase():
    brand = {"banned_keywords": []}
    issues = _validate_comment("이거 강력 추천합니다", brand)
    assert len(issues) > 0
