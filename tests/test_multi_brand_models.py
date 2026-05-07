"""PR-A 다중 브랜드 데이터 모델 라운드트립 + 관계 검증."""
import json

from hydra.db.models import (
    Brand, Product,
    CommentPreset, CommentTreeSlot,
    Niche, NichePresetSelection,
    # Task 5: GlobalAdPhraseBlocklist
)


def test_product_belongs_to_brand(db_session):
    brand = Brand(name="OO헬스", category="영양제", selected_presets="[]")
    db_session.add(brand); db_session.flush()

    product = Product(
        brand_id=brand.id,
        product_name="모렉신",
        protected_terms=json.dumps(["모렉신", "체성케라틴"], ensure_ascii=False),
        core_keywords=json.dumps(["체성케라틴", "케라틴", "모근 단백질"], ensure_ascii=False),
        description="탈모 영양제",
        core_message="머리카락 80%가 케라틴 — 직접 보충",
    )
    db_session.add(product); db_session.commit()

    refetched = db_session.query(Product).filter_by(product_name="모렉신").first()
    assert refetched.brand_id == brand.id
    assert "체성케라틴" in json.loads(refetched.protected_terms)
    assert refetched.brand.name == "OO헬스"


def test_slot_has_intent_and_mention_policy(db_session):
    p = CommentPreset(name="F5 demo", is_global=True, is_default=False)
    db_session.add(p); db_session.flush()

    slot = CommentTreeSlot(
        comment_preset_id=p.id, slot_label="A", position=1,
        intent="[메인·고민형] 영상 주제에 공감, 본인 입장에서 자연 토로. 제품 언급 X.",
        tone_anchor=json.dumps([
            "와 진짜 공감... 저도 그런 고민 있어요 ㅠㅠ",
            "ㅠㅠ 저도 똑같아요"
        ], ensure_ascii=False),
        mention_brand=False,
        mention_solution=False,
        length="medium", emoji="sometimes",
        ai_variation=80,
        like_min=0, like_max=10, like_distribution="adaptive",
    )
    db_session.add(slot); db_session.commit()

    refetched = db_session.query(CommentTreeSlot).filter_by(slot_label="A").first()
    assert refetched.intent.startswith("[메인·고민형]")
    assert "와 진짜 공감" in json.loads(refetched.tone_anchor)[0]
    assert refetched.mention_brand is False
    assert refetched.mention_solution is False


def test_niche_preset_selection_with_weight(db_session):
    brand = Brand(name="b", selected_presets="[]"); db_session.add(brand); db_session.flush()
    product = Product(brand_id=brand.id, product_name="p")
    db_session.add(product); db_session.flush()
    niche = Niche(name="산후맘", brand_id=brand.id, product_id=product.id,
                  preset_per_video_limit=1)
    db_session.add(niche); db_session.flush()

    p1 = CommentPreset(name="F5", is_global=True); db_session.add(p1)
    p2 = CommentPreset(name="F4", is_global=True); db_session.add(p2)
    db_session.flush()

    db_session.add_all([
        NichePresetSelection(niche_id=niche.id, preset_id=p1.id, weight=70, enabled=True),
        NichePresetSelection(niche_id=niche.id, preset_id=p2.id, weight=30, enabled=True),
    ])
    db_session.commit()

    selections = (db_session.query(NichePresetSelection)
                  .filter_by(niche_id=niche.id).all())
    assert len(selections) == 2
    weights = {s.preset_id: s.weight for s in selections}
    assert weights[p1.id] == 70
    assert weights[p2.id] == 30
