"""Phase B — 슬롯 트리 → Task 변환.

create_campaign_with_slot_tasks() + same_account_as 강제 + parent_task 체인.
"""
import json
import pytest

from hydra.db.models import (
    Account, Brand, Campaign, CommentPreset, CommentTreeSlot,
)
from hydra.services.slot_engine import (
    SlotEngineError, create_campaign_with_slot_tasks,
)


def _make_active_accounts(db, n: int) -> list[Account]:
    accts = []
    for i in range(n):
        a = Account(gmail=f"a{i}@t", password="x", status="active")
        db.add(a)
        accts.append(a)
    db.flush()
    return accts


def _make_campaign(db, brand_id: int) -> Campaign:
    c = Campaign(brand_id=brand_id, status="planning", scenario="test")
    db.add(c); db.flush()
    return c


def _make_preset_f5(db) -> CommentPreset:
    """F5 흐름: A → B → C(asks B) → D(=B 답) — 4 슬롯."""
    p = CommentPreset(name="F5", is_global=False, is_default=False)
    db.add(p); db.flush()
    slots = [
        ("A", None, None, 1, 5, 10),
        ("B", "A", None, 2, 8, 15),
        ("C", "B", None, 3, 3, 6),
        ("D", "C", "B", 4, 4, 8),  # ← D 는 B 와 같은 계정
    ]
    for label, reply_to, same_as, pos, lmin, lmax in slots:
        db.add(CommentTreeSlot(
            comment_preset_id=p.id,
            slot_label=label, reply_to_slot_label=reply_to,
            position=pos,
            text_template=f"text-{label}", length="medium", emoji="sometimes",
            ai_variation=50, like_min=lmin, like_max=lmax,
            like_distribution="adaptive",
            same_account_as_slot_label=same_as,
        ))
    db.commit()
    db.refresh(p)
    return p


def test_slot_tree_creates_correct_task_count(db_session):
    brand = Brand(name="b", selected_presets="[]"); db_session.add(brand); db_session.flush()
    _make_active_accounts(db_session, 5)
    p = _make_preset_f5(db_session)
    c = _make_campaign(db_session, brand.id)

    tasks = create_campaign_with_slot_tasks(
        db_session, campaign=c, comment_preset=p, video_id="v123",
    )
    db_session.commit()

    comment_tasks = [t for t in tasks if t.task_type in ("comment", "reply")]
    like_tasks = [t for t in tasks if t.task_type == "like_boost"]

    # 4 댓글/답글 + like_boost (각 슬롯 like_min~max 사이 N개)
    assert len(comment_tasks) == 4
    assert all(t.slot_label in ("A", "B", "C", "D") for t in comment_tasks)
    assert len(like_tasks) >= 4 * 3  # 최소 like_min 합계 (5+8+3+4=20) 이상


def test_d_slot_uses_same_account_as_b(db_session):
    """F5 흐름: D 슬롯의 account_id == B 슬롯의 account_id."""
    brand = Brand(name="b", selected_presets="[]"); db_session.add(brand); db_session.flush()
    _make_active_accounts(db_session, 5)
    p = _make_preset_f5(db_session)
    c = _make_campaign(db_session, brand.id)

    tasks = create_campaign_with_slot_tasks(
        db_session, campaign=c, comment_preset=p, video_id="v123",
    )
    db_session.commit()

    by_label = {t.slot_label: t for t in tasks if t.slot_label}
    assert by_label["D"].account_id == by_label["B"].account_id
    # A, B, C 는 모두 다른 계정
    assert len({by_label["A"].account_id,
                by_label["B"].account_id,
                by_label["C"].account_id}) == 3


def test_parent_task_id_chain_matches_reply_to(db_session):
    """parent_task_id 가 reply_to_slot_label 의 task 와 매칭."""
    brand = Brand(name="b", selected_presets="[]"); db_session.add(brand); db_session.flush()
    _make_active_accounts(db_session, 5)
    p = _make_preset_f5(db_session)
    c = _make_campaign(db_session, brand.id)

    tasks = create_campaign_with_slot_tasks(
        db_session, campaign=c, comment_preset=p, video_id="v123",
    )
    db_session.commit()

    by_label = {t.slot_label: t for t in tasks
                if t.task_type in ("comment", "reply")}
    assert by_label["A"].parent_task_id is None
    assert by_label["B"].parent_task_id == by_label["A"].id
    assert by_label["C"].parent_task_id == by_label["B"].id
    assert by_label["D"].parent_task_id == by_label["C"].id


def test_scheduled_at_ordering(db_session):
    """답글 scheduled_at 은 부모보다 나중."""
    brand = Brand(name="b", selected_presets="[]"); db_session.add(brand); db_session.flush()
    _make_active_accounts(db_session, 5)
    p = _make_preset_f5(db_session)
    c = _make_campaign(db_session, brand.id)

    tasks = create_campaign_with_slot_tasks(
        db_session, campaign=c, comment_preset=p, video_id="v123",
    )
    db_session.commit()

    by_label = {t.slot_label: t for t in tasks
                if t.task_type in ("comment", "reply")}
    assert by_label["B"].scheduled_at > by_label["A"].scheduled_at
    assert by_label["C"].scheduled_at > by_label["B"].scheduled_at
    assert by_label["D"].scheduled_at > by_label["C"].scheduled_at


def test_payload_contains_slot_metadata(db_session):
    brand = Brand(name="b", selected_presets="[]"); db_session.add(brand); db_session.flush()
    _make_active_accounts(db_session, 5)
    p = _make_preset_f5(db_session)
    c = _make_campaign(db_session, brand.id)

    tasks = create_campaign_with_slot_tasks(
        db_session, campaign=c, comment_preset=p, video_id="v_xyz",
    )
    db_session.commit()

    d_task = next(t for t in tasks if t.slot_label == "D")
    payload = json.loads(d_task.payload)
    assert payload["video_id"] == "v_xyz"
    assert payload["preset_id"] == p.id
    assert payload["slot_label"] == "D"
    assert payload["reply_to_slot_label"] == "C"
    assert payload["is_reappear"] is True
    assert payload["ai_pending"] is True


def test_insufficient_accounts_raises(db_session):
    brand = Brand(name="b", selected_presets="[]"); db_session.add(brand); db_session.flush()
    _make_active_accounts(db_session, 2)  # 3 fresh slots needed (A/B/C), D 는 재등장
    p = _make_preset_f5(db_session)
    c = _make_campaign(db_session, brand.id)

    with pytest.raises(SlotEngineError, match="insufficient active accounts"):
        create_campaign_with_slot_tasks(
            db_session, campaign=c, comment_preset=p, video_id="v",
        )


def test_invalid_same_account_label_raises(db_session):
    brand = Brand(name="b", selected_presets="[]"); db_session.add(brand); db_session.flush()
    _make_active_accounts(db_session, 5)

    p = CommentPreset(name="bad", is_global=False, is_default=False)
    db_session.add(p); db_session.flush()
    db_session.add(CommentTreeSlot(
        comment_preset_id=p.id, slot_label="A", position=1,
        text_template="", length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0, like_distribution="adaptive",
        same_account_as_slot_label="X",  # ← 존재 안 함
    ))
    db_session.commit()

    c = _make_campaign(db_session, brand.id)
    with pytest.raises(SlotEngineError, match="not found"):
        create_campaign_with_slot_tasks(
            db_session, campaign=c, comment_preset=p, video_id="v",
        )


def test_pick_preset_for_niche_uses_weight(db_session):
    from hydra.services.slot_engine import pick_preset_for_niche
    from hydra.db.models import (
        Brand, Niche, CommentPreset, NichePresetSelection,
    )
    brand = Brand(name="b", selected_presets="[]"); db_session.add(brand); db_session.flush()
    niche = Niche(name="n", brand_id=brand.id, preset_per_video_limit=1)
    db_session.add(niche); db_session.flush()
    p1 = CommentPreset(name="P1", is_global=True); db_session.add(p1)
    p2 = CommentPreset(name="P2", is_global=True); db_session.add(p2)
    db_session.flush()
    db_session.add_all([
        NichePresetSelection(niche_id=niche.id, preset_id=p1.id, weight=80, enabled=True),
        NichePresetSelection(niche_id=niche.id, preset_id=p2.id, weight=20, enabled=True),
    ])
    db_session.commit()

    counts = {p1.id: 0, p2.id: 0}
    import random; random.seed(42)
    for _ in range(1000):
        picked = pick_preset_for_niche(db_session, niche.id)
        counts[picked.id] += 1
    # 80:20 분포 (±15% 허용)
    ratio = counts[p1.id] / 1000
    assert 0.65 < ratio < 0.95, f"expected ~0.8, got {ratio}"


def test_pick_preset_skips_disabled(db_session):
    from hydra.services.slot_engine import pick_preset_for_niche, SlotEngineError
    from hydra.db.models import Brand, Niche, CommentPreset, NichePresetSelection
    brand = Brand(name="b", selected_presets="[]"); db_session.add(brand); db_session.flush()
    niche = Niche(name="n", brand_id=brand.id, preset_per_video_limit=1)
    db_session.add(niche); db_session.flush()
    p1 = CommentPreset(name="P1", is_global=True); db_session.add(p1)
    db_session.flush()
    db_session.add(NichePresetSelection(niche_id=niche.id, preset_id=p1.id,
                                        weight=10, enabled=False))
    db_session.commit()

    import pytest
    with pytest.raises(SlotEngineError, match="no enabled preset"):
        pick_preset_for_niche(db_session, niche.id)
