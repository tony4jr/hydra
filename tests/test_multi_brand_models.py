"""PR-A 다중 브랜드 데이터 모델 라운드트립 + 관계 검증."""
import json

from hydra.db.models import (
    Brand, Product,
    # Task 3: Niche, NichePresetSelection
    # Task 5: GlobalAdPhraseBlocklist
    # Task 2: CommentPreset, CommentTreeSlot  (already exist — imported in later task tests)
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
