"""T19 퍼널 단계별 comment_agent 톤 가이드."""
from hydra.ai.agents.comment_agent import FUNNEL_STAGE_GUIDES


def test_all_4_funnel_stages_defined():
    """인지/고려/전환/리텐션 4단계 모두 가이드 정의됨."""
    expected = {"awareness", "consideration", "conversion", "retention"}
    assert set(FUNNEL_STAGE_GUIDES.keys()) == expected


def test_awareness_emphasizes_no_direct_brand():
    """인지 단계는 브랜드 직접 언급 금지 명시."""
    g = FUNNEL_STAGE_GUIDES["awareness"]
    assert "직접 언급 금지" in g or "직접 언급 X" in g


def test_consideration_uses_indirect_mention():
    """고려 단계는 우회 멘션 패턴 명시."""
    g = FUNNEL_STAGE_GUIDES["consideration"]
    assert "우회" in g or "성분" in g


def test_retention_uses_long_term_user_tone():
    """리텐션은 장기 사용자 톤."""
    g = FUNNEL_STAGE_GUIDES["retention"]
    assert "1년" in g or "장기" in g or "재" in g


def test_invalid_funnel_stage_silently_ignored():
    """알려지지 않은 stage 는 dict 에 없음 → caller 에서 무시."""
    assert "garbage" not in FUNNEL_STAGE_GUIDES
