"""Phase A — slot engine 데이터 레이어.

CommentTreeSlot.same_account_as_slot_label + Task.slot_id/slot_label/parent_task_id
모델 라운드트립 검증.
"""
from hydra.db.models import (
    Account, Brand, Campaign, CommentPreset, CommentTreeSlot, Task
)


def test_slot_same_account_field_persists(db_session):
    p = CommentPreset(name="F5 demo", is_global=False, is_default=False)
    db_session.add(p)
    db_session.flush()

    db_session.add(CommentTreeSlot(
        comment_preset_id=p.id, slot_label="A", position=1,
        text_template="A", length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0, like_distribution="adaptive",
    ))
    db_session.add(CommentTreeSlot(
        comment_preset_id=p.id, slot_label="B", reply_to_slot_label="A", position=2,
        text_template="B", length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0, like_distribution="adaptive",
    ))
    db_session.add(CommentTreeSlot(
        comment_preset_id=p.id, slot_label="D", reply_to_slot_label="C", position=4,
        text_template="D", length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0, like_distribution="adaptive",
        same_account_as_slot_label="B",  # ← 핵심: D = B 같은 계정
    ))
    db_session.commit()

    d_slot = (
        db_session.query(CommentTreeSlot)
        .filter_by(comment_preset_id=p.id, slot_label="D")
        .first()
    )
    assert d_slot.same_account_as_slot_label == "B"


def test_task_slot_link_persists(db_session):
    """slot_id, slot_label, parent_task_id 라운드트립 + 답글 체인."""
    brand = Brand(name="t", selected_presets="[]")
    db_session.add(brand); db_session.flush()
    campaign = Campaign(brand_id=brand.id, status="planning", scenario="test")
    db_session.add(campaign); db_session.flush()

    p = CommentPreset(name="x", is_global=False, is_default=False)
    db_session.add(p); db_session.flush()
    slot_a = CommentTreeSlot(
        comment_preset_id=p.id, slot_label="A", position=1,
        text_template="", length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0, like_distribution="adaptive",
    )
    slot_b = CommentTreeSlot(
        comment_preset_id=p.id, slot_label="B", reply_to_slot_label="A", position=2,
        text_template="", length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0, like_distribution="adaptive",
    )
    db_session.add_all([slot_a, slot_b]); db_session.flush()

    acct = Account(gmail="u1@test", password="x")
    db_session.add(acct); db_session.flush()

    task_a = Task(
        campaign_id=campaign.id, account_id=acct.id, task_type="comment",
        status="pending", slot_id=slot_a.id, slot_label="A",
    )
    db_session.add(task_a); db_session.flush()

    task_b = Task(
        campaign_id=campaign.id, account_id=acct.id, task_type="reply",
        status="pending", slot_id=slot_b.id, slot_label="B",
        parent_task_id=task_a.id,
    )
    db_session.add(task_b); db_session.flush()
    db_session.commit()

    refetched = db_session.query(Task).filter_by(slot_label="B").first()
    assert refetched.slot_id == slot_b.id
    assert refetched.parent_task_id == task_a.id
    # relationship
    assert refetched.parent_task.slot_label == "A"
    assert refetched.slot.slot_label == "B"


def test_slot_label_unique_within_preset_still_enforced(db_session):
    """기존 UNIQUE(preset_id, slot_label) 제약 유지 — 재등장은 다른 라벨로만."""
    import sqlalchemy.exc as sae

    p = CommentPreset(name="y", is_global=False, is_default=False)
    db_session.add(p); db_session.flush()
    db_session.add(CommentTreeSlot(
        comment_preset_id=p.id, slot_label="A", position=1,
        text_template="", length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0, like_distribution="adaptive",
    ))
    db_session.commit()

    db_session.add(CommentTreeSlot(
        comment_preset_id=p.id, slot_label="A", position=2,
        text_template="", length="medium", emoji="sometimes",
        ai_variation=50, like_min=0, like_max=0, like_distribution="adaptive",
    ))
    try:
        db_session.commit()
    except sae.IntegrityError:
        db_session.rollback()
        return
    raise AssertionError("expected IntegrityError on duplicate slot_label")
