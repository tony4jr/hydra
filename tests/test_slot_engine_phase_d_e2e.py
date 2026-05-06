"""Phase D — E2E DRY-RUN.

시드 스크립트 → 캠페인 생성 (slot_engine 통해) → 텍스트 채우기 (DRY)
끝까지 도는지 검증. 실 Claude API 호출 없음.
"""
import json
from unittest.mock import patch

import pytest

from hydra.db.models import (
    Account, Brand, Campaign, CommentPreset, Niche, Task, Video,
)
from hydra.services.campaign_service import (
    create_campaign_with_tasks, generate_campaign_texts,
)


def _seed_morexin_in_session(db_session):
    """SessionLocal 대신 db_session 픽스처 위에 시드 데이터 직접 박기."""
    # scripts/seed_morexin 의 PRESETS 상수를 가져옴
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "seed_morexin",
        Path(__file__).parent.parent / "scripts" / "seed_morexin.py",
    )
    mod = importlib.util.module_from_spec(spec)
    # SessionLocal 호출 막기 위해 main() 안 부르고 PRESETS 만 가져옴
    spec.loader.exec_module(mod)

    from hydra.db.models import CommentTreeSlot
    brand = Brand(
        name="모렉신",
        product_category="탈모 영양제",
        core_message="머리카락 80%가 케라틴 — 직접 보충이 답",
        tone_guide="과장 없이 자연스럽게",
        selected_presets="[]",
        preset_video_limit=1,
        banned_keywords=json.dumps(["일라스틴", "엘라스틴", "최고", "강추"]),
    )
    db_session.add(brand); db_session.flush()

    niche_map = {}
    for code, name in mod.NICHES:
        n = Niche(name=name, brand_id=brand.id, preset_per_video_limit=1)
        db_session.add(n); db_session.flush()
        niche_map[code] = n

    presets_by_code = {}
    for spec_p in mod.PRESETS:
        p = CommentPreset(
            name=spec_p["name"],
            description=f"[{spec_p['code']}] {spec_p['description']}",
            is_global=False, is_default=False,
        )
        db_session.add(p); db_session.flush()
        for i, slot in enumerate(spec_p["slots"], start=1):
            label, reply_to, same_as, length, emoji, ai_var, lmin, lmax, text = slot
            db_session.add(CommentTreeSlot(
                comment_preset_id=p.id,
                slot_label=label, reply_to_slot_label=reply_to,
                same_account_as_slot_label=same_as,
                position=i,
                text_template=text, length=length, emoji=emoji,
                ai_variation=ai_var, like_min=lmin, like_max=lmax,
                like_distribution="adaptive",
            ))
        niche_map[spec_p["niche_code"]].comment_preset_id = p.id
        presets_by_code[spec_p["code"]] = p
    db_session.commit()
    return brand, niche_map, presets_by_code


def _make_active_accounts(db, n: int):
    for i in range(n):
        db.add(Account(gmail=f"e2e_{i}@t", password="x", status="active",
                       persona=json.dumps({
                           "age": 30 + i, "gender": "여",
                           "region": "서울", "occupation": "직장인",
                           "speech_style": "친근한 존댓말",
                       })))
    db.flush()


def test_seed_creates_9_presets(db_session):
    brand, niches, presets = _seed_morexin_in_session(db_session)
    assert len(presets) == 9
    assert "PRESET-001" in presets
    assert "PRESET-024" in presets
    # PRESET-008 / PRESET-024 에는 D=B 재등장 슬롯 있음
    p008 = presets["PRESET-008"]
    d_slot = next(s for s in p008.slots if s.slot_label == "D")
    assert d_slot.same_account_as_slot_label == "B"


def test_e2e_campaign_with_slot_preset_creates_tasks(db_session):
    """legacy Preset 도 만들고 → CommentPreset id 같이 넘겨서 슬롯 분기 타는지."""
    from hydra.db.models import Preset
    brand, niches, presets = _seed_morexin_in_session(db_session)
    _make_active_accounts(db_session, 6)

    # legacy preset (entry point 가 아직 요구하므로 dummy 1개)
    legacy = Preset(name="dummy", code="dummy",
                    steps=json.dumps([]), is_system=True)
    db_session.add(legacy); db_session.flush()

    # video
    db_session.add(Video(id="v_e2e", url="https://yt/v_e2e",
                         title="산후 V-log", description=""))
    db_session.commit()

    p008 = presets["PRESET-008"]
    camp = create_campaign_with_tasks(
        db=db_session, video_id="v_e2e", brand_id=brand.id,
        preset_code="dummy",
        comment_preset_id=p008.id,
    )

    # comment/reply task 4개 (A/B/C/D), like_boost 다수
    tasks = (db_session.query(Task)
             .filter(Task.campaign_id == camp.id)
             .filter(Task.task_type.in_(("comment", "reply"))).all())
    assert len(tasks) == 4
    by_label = {t.slot_label: t for t in tasks}
    assert by_label["D"].account_id == by_label["B"].account_id
    assert by_label["B"].parent_task_id == by_label["A"].id


def test_e2e_dry_run_text_generation(db_session):
    """DRY-RUN 으로 텍스트 채우면 모든 task 의 payload 에 marker 가 박혀야."""
    from hydra.db.models import Preset
    brand, niches, presets = _seed_morexin_in_session(db_session)
    _make_active_accounts(db_session, 6)
    legacy = Preset(name="dummy", code="dummy",
                    steps=json.dumps([]), is_system=True)
    db_session.add(legacy); db_session.flush()
    db_session.add(Video(id="v_e2e", url="https://yt/v_e2e",
                         title="V-log", description=""))
    db_session.commit()

    p008 = presets["PRESET-008"]
    camp = create_campaign_with_tasks(
        db=db_session, video_id="v_e2e", brand_id=brand.id,
        preset_code="dummy", comment_preset_id=p008.id,
    )

    # generate_campaign_texts → 슬롯 분기 → generate_texts_for_campaign
    # (실 Claude 호출 회피 위해 call_claude 패치)
    fake_calls = []

    def fake_call(*args, **kwargs):
        fake_calls.append(kwargs.get("system", "")[:80])
        return f"[MOCK-{len(fake_calls)}] generated text"

    with patch("hydra.ai.agents.slot_agent.call_claude", side_effect=fake_call):
        results = generate_campaign_texts(db_session, camp.id)

    assert len(results) == 4
    assert all("text" in r for r in results)

    # payload 에 박혔는지
    tasks = (db_session.query(Task)
             .filter(Task.campaign_id == camp.id)
             .filter(Task.task_type.in_(("comment", "reply")))
             .order_by(Task.id).all())
    for t in tasks:
        p = json.loads(t.payload)
        assert p["text"], f"slot {t.slot_label} text empty"
        assert p["ai_pending"] is False
        assert p["ai_generated"] is True
        assert p["text"].startswith("[MOCK-")

    # 4번 호출됨 (A,B,C,D)
    assert len(fake_calls) == 4
