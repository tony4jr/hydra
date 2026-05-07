"""Phase C — 슬롯 기반 AI 텍스트 생성.

generate_comment_for_task / generate_texts_for_campaign 의
프롬프트 구성 + parent 맥락 주입 + payload 갱신 검증.
"""
import json
from unittest.mock import patch

import pytest

from hydra.ai.agents.slot_agent import (
    _build_slot_system_prompt,
    _build_slot_user_message,
    generate_comment_for_task,
    generate_texts_for_campaign,
    _validator,
)
from hydra.db.models import (
    Account, Brand, Campaign, CommentPreset, CommentTreeSlot, Task, Video,
)
from hydra.services.slot_engine import create_campaign_with_slot_tasks


def _make_seed(db):
    """공통 시드: 브랜드 + 5계정 + F5 프리셋 + 캠페인."""
    brand = Brand(
        name="모렉신",
        product_category="탈모 영양제",
        core_message="머리카락 80%가 케라틴 — 직접 보충",
        tone_guide="과장 없이 실사용 후기",
        banned_keywords=json.dumps(["일라스틴", "최고", "강추"]),
    )
    db.add(brand); db.flush()

    accts = []
    for i in range(5):
        a = Account(gmail=f"a{i}@t", password="x", status="active",
                    persona=json.dumps({
                        "age": 30 + i, "gender": "여",
                        "region": "서울", "occupation": "직장인",
                        "speech_style": "친근한 존댓말",
                    }))
        db.add(a); accts.append(a)
    db.flush()

    p = CommentPreset(name="F5", is_global=False)
    db.add(p); db.flush()
    db.add_all([
        CommentTreeSlot(
            comment_preset_id=p.id, slot_label="A", position=1,
            text_template="산후 5개월인데 머리 너무 빠져요 ㅠㅠ",
            length="medium", emoji="sometimes",
            ai_variation=50, like_min=0, like_max=0,
            like_distribution="adaptive",
        ),
        CommentTreeSlot(
            comment_preset_id=p.id, slot_label="B", reply_to_slot_label="A", position=2,
            text_template="저도 그시기에 케라틴 영양제로 좋아졌어요",
            length="medium", emoji="sometimes",
            ai_variation=50, like_min=0, like_max=0,
            like_distribution="adaptive",
        ),
        CommentTreeSlot(
            comment_preset_id=p.id, slot_label="C", reply_to_slot_label="B", position=3,
            text_template="@B 어떤거 드세요?",
            length="short", emoji="often",
            ai_variation=30, like_min=0, like_max=0,
            like_distribution="adaptive",
        ),
        CommentTreeSlot(
            comment_preset_id=p.id, slot_label="D", reply_to_slot_label="C", position=4,
            text_template="@C 모렉신이라고 검색해보세요",
            length="medium", emoji="sometimes",
            ai_variation=50, like_min=0, like_max=0,
            like_distribution="adaptive",
            same_account_as_slot_label="B",
        ),
    ])
    db.commit(); db.refresh(p)

    video = Video(id="v_test", url="https://youtube.com/v/v_test",
                  title="산후 100일 머리관리", description="산후탈모 V-log")
    db.add(video); db.flush()

    campaign = Campaign(brand_id=brand.id, status="planning",
                        scenario="test", comment_preset_id=p.id, video_id="v_test")
    db.add(campaign); db.flush()

    create_campaign_with_slot_tasks(
        db, campaign=campaign, comment_preset=p, video_id="v_test",
    )
    db.commit()
    return brand, p, campaign


def test_system_prompt_contains_slot_metadata():
    # Updated to new 6-layer keyword-arg signature (PR-B Task 7)
    brand = {"name": "모렉신", "product_category": "탈모 영양제",
             "core_message": "케라틴", "tone_guide": "자연스럽게"}
    slot = CommentTreeSlot(
        slot_label="B", position=2,
        intent="[서브·정보형] 케라틴 정보 제공",
        mention_brand=True, mention_solution=True,
        length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0,
        like_distribution="adaptive",
    )
    persona = {"age": 33, "gender": "여", "region": "부산",
               "occupation": "직장인", "speech_style": "편한 존댓말"}
    sys = _build_slot_system_prompt(
        slot=slot,
        brand=brand,
        product={"product_name": "모렉신", "protected_terms": ["모렉신"], "core_keywords": ["케라틴"]},
        niche={"target_audience": "탈모 여성", "mention_intensity": 60},
        persona=persona,
        global_blocklist=[],
    )
    assert "모렉신" in sys
    assert "케라틴" in sys
    assert "33세" in sys


def test_user_message_includes_parent_context():
    slot = CommentTreeSlot(
        slot_label="B", reply_to_slot_label="A", position=2,
        text_template="", length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0,
        like_distribution="adaptive",
    )
    user = _build_slot_user_message(
        {"title": "산후 V-log"}, slot,
        parent_text="머리 너무 빠져요 ㅠㅠ",
        sibling_texts=[],
    )
    assert "산후 V-log" in user
    assert "머리 너무 빠져요" in user
    assert "답글" in user


def test_user_message_for_main_slot_has_no_parent():
    slot = CommentTreeSlot(
        slot_label="A", reply_to_slot_label=None, position=1,
        text_template="", length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0,
        like_distribution="adaptive",
    )
    user = _build_slot_user_message({"title": "v"}, slot, None, [])
    assert "메인 댓글" in user
    assert "답글" not in user


def test_validator_catches_banned_and_ad_patterns():
    # Updated to new explicit-parameter signature (PR-B Task 8)
    _kw = dict(slot_mention_brand=True, slot_mention_solution=True,
               brand_name="모렉신", protected_terms=[], core_keywords=[],
               global_blocklist=[])
    # OK
    assert _validator("케라틴 영양제 좋네요", ["일라스틴"], **_kw) == []
    # banned
    issues = _validator("일라스틴 좋아요", ["일라스틴"], **_kw)
    assert any("일라스틴" in i for i in issues)
    # ad pattern
    issues2 = _validator("지금 구매하세요!!", [], **_kw)
    assert any("ad pattern" in i for i in issues2)
    # too short
    assert any("too short" in i for i in _validator("a", [], **_kw))


def test_validator_catches_brand_typos():
    # 모렙신 → 모렉신 오타
    # Updated to new explicit-parameter signature (PR-B Task 8); template arg removed
    issues = _validator(
        "모렙신 추천드려요", banned_keywords=[],
        slot_mention_brand=True, slot_mention_solution=True,
        brand_name="모렉신", protected_terms=[], core_keywords=[],
        global_blocklist=[],
    )
    assert any("모렙신" in i for i in issues)


def test_validator_catches_keratin_typos():
    # Updated to new explicit-parameter signature (PR-B Task 8); template arg removed
    issues = _validator(
        "체성캐라틴이 들어있어요", banned_keywords=[],
        slot_mention_brand=True, slot_mention_solution=True,
        brand_name="모렉신", protected_terms=[], core_keywords=[],
        global_blocklist=[],
    )
    assert any("체성캐라틴" in i for i in issues)


@pytest.mark.skip(
    reason=(
        "PR-B Task 8: template-mirroring 로직이 새 _validator 에서 제거됨. "
        "브랜드명 노출 제어는 이제 slot_mention_brand 플래그로만 결정됨 "
        "(test_slot_agent_composition.py 의 Task 8 테스트로 커버)."
    )
)
def test_validator_template_brand_mention_required_when_template_has_it():
    # 템플릿에 모렉신 있는데 결과에 없음 → issue
    issues = _validator(
        "그냥 영양제 먹고 좋아졌어요", banned_keywords=[],
        template="모렉신 먹고 좋아졌어요", brand_name="모렉신",
    )
    assert any("누락" in i for i in issues)


@pytest.mark.skip(
    reason=(
        "PR-B Task 8: template-mirroring 로직이 새 _validator 에서 제거됨. "
        "메인 슬롯 브랜드명 차단은 이제 slot_mention_brand=False 로 제어됨 "
        "(test_slot_agent_composition.py::test_validator_blocks_brand_mention_when_slot_forbids 로 커버)."
    )
)
def test_validator_blocks_brand_mention_when_template_has_none():
    # 템플릿에 모렉신 없는데 결과에 있음 → issue (메인 슬롯 광고티)
    issues = _validator(
        "모렉신 진짜 좋아요", banned_keywords=[],
        template="머리 너무 빠져요 ㅠㅠ", brand_name="모렉신",
    )
    assert any("미러링 위반" in i for i in issues)


@pytest.mark.skip(
    reason=(
        "PR-B Task 8: template-mirroring 로직이 새 _validator 에서 제거됨. "
        "브랜드명 허용은 이제 slot_mention_brand=True 로 제어됨 "
        "(test_slot_agent_composition.py::test_validator_passes_when_slot_allows_mention 로 커버)."
    )
)
def test_validator_passes_when_template_mirrored():
    issues = _validator(
        "모렉신이라고 한번 검색해보세요", banned_keywords=[],
        template="모렉신이라고 검색해보세요", brand_name="모렉신",
    )
    assert issues == []


def test_autocorrect_replaces_known_typos():
    from hydra.ai.agents.slot_agent import _autocorrect_typos
    fixed, fixes = _autocorrect_typos("모렙신 체성캐라틴 좋아요")
    assert "모렉신" in fixed
    assert "체성케라틴" in fixed
    assert "모렙신" not in fixed
    assert "체성캐라틴" not in fixed
    assert len(fixes) == 2


def test_generate_comment_dry_run_produces_marker(db_session):
    brand, p, camp = _make_seed(db_session)
    tasks = (db_session.query(Task)
             .filter(Task.campaign_id == camp.id, Task.slot_id.isnot(None))
             .order_by(Task.id).all())
    a_task = next(t for t in tasks if t.slot_label == "A")
    text = generate_comment_for_task(db_session, task=a_task, dry_run=True)
    assert "[DRY-RUN]" in text
    assert "slot=A" in text


def test_generate_texts_for_campaign_fills_payload(db_session):
    brand, p, camp = _make_seed(db_session)

    fake_outputs = {
        "A": "산후 100일인데 머리 너무 빠져요 ㅠㅠ 영상 보고 위로받아요",
        "B": "저도 그시기에 케라틴 영양제로 좋아졌어요",
        "C": "어떤거 드세요?? 알려주세요!!",
        "D": "모렉신이라고 한번 검색해보세요 :)",
    }

    def fake_call(*args, **kwargs):
        # system prompt 안에 들어간 슬롯 라벨로 구분
        sys = kwargs.get("system", "")
        for label, out in fake_outputs.items():
            if f"슬롯 라벨: {label}" in sys:
                return out
        # fallback: user message 의 부모 텍스트로 구분
        msg = kwargs.get("user_message", "")
        if "메인 댓글" in msg:
            return fake_outputs["A"]
        if "산후 100일" in msg or "위로" in msg:  # B가 A에 답
            return fake_outputs["B"]
        if "케라틴 영양제로 좋아졌어요" in msg:  # C가 B에 답
            return fake_outputs["C"]
        return fake_outputs["D"]  # D가 C에 답

    with patch("hydra.ai.agents.slot_agent.call_claude", side_effect=fake_call):
        results = generate_texts_for_campaign(db_session, campaign_id=camp.id)

    assert len(results) == 4
    by_label = {r["slot_label"]: r for r in results}
    for label in "ABCD":
        assert by_label[label]["text"]

    # payload 에 text 가 박혔는지
    a_task = (db_session.query(Task)
              .filter(Task.campaign_id == camp.id, Task.slot_label == "A")
              .first())
    payload = json.loads(a_task.payload)
    assert payload["text"]
    assert payload["ai_pending"] is False
    assert payload["ai_generated"] is True


def test_parent_text_passed_to_child(db_session):
    """B 가 생성될 때 A 의 텍스트가 system/user 어딘가에 들어갔는지."""
    brand, p, camp = _make_seed(db_session)

    captured = {"calls": []}

    def fake_call(*args, **kwargs):
        captured["calls"].append({
            "system": kwargs.get("system", ""),
            "user": kwargs.get("user_message", ""),
        })
        # A 는 메인, 나머지는 답글 — 길이 다양화
        return f"댓글-{len(captured['calls'])}"

    with patch("hydra.ai.agents.slot_agent.call_claude", side_effect=fake_call):
        generate_texts_for_campaign(db_session, campaign_id=camp.id)

    # 첫 호출 (A): parent 없음
    assert "부모 댓글" not in captured["calls"][0]["user"]
    # 두 번째 호출 (B): A 의 텍스트가 부모로 들어가야
    assert "댓글-1" in captured["calls"][1]["user"]
    assert "부모 댓글" in captured["calls"][1]["user"]
    # 세 번째 (C): B 의 텍스트가 부모
    assert "댓글-2" in captured["calls"][2]["user"]


def test_d_slot_uses_same_persona_as_b(db_session):
    """D 슬롯은 B 와 같은 account → 같은 persona 가 system 에 들어가야."""
    brand, p, camp = _make_seed(db_session)

    captured_personas = []

    def fake_call(*args, **kwargs):
        sys = kwargs.get("system", "")
        # 페르소나 블록 첫 줄 (- {age}세 {gender}) 추출
        # New format: "[페르소나 — 이 사람이 실제로 쓰듯]" header (PR-B Task 7)
        in_persona = False
        for line in sys.splitlines():
            if "페르소나" in line and ("이 사람이" in line or line.startswith("페르소나:")):
                in_persona = True
                continue
            if in_persona and line.startswith("- ") and "세" in line:
                captured_personas.append(line)
                break
        return "ok"

    with patch("hydra.ai.agents.slot_agent.call_claude", side_effect=fake_call):
        generate_texts_for_campaign(db_session, campaign_id=camp.id)

    # B 와 D 의 페르소나 라인이 같아야 (같은 account_id 라서)
    # 호출 순서: A, B, C, D
    assert captured_personas[1] == captured_personas[3], \
        f"B persona != D persona — same_account_as 미적용. b={captured_personas[1]}, d={captured_personas[3]}"
