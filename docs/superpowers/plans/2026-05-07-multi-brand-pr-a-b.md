# Multi-Brand Architecture PR-A + PR-B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR-A 데이터 모델(Brand→Product→Niche, NichePresetSelection, intent-based Slot) + PR-B 슬롯 엔진 6-layer system prompt 합성 구현. Spec: [docs/superpowers/specs/2026-05-07-multi-brand-design.md](../specs/2026-05-07-multi-brand-design.md).

**Architecture:** 어제 작성된 슬롯 엔진(Phase A~D, feat/slot-engine 브랜치) 위에 추가 변경. 마이그레이션은 **additive only** (기존 `text_template`/`comment_preset_id` 보존) — PR-F(어제 엔진 prod 배포)와 backward compat. 슬롯 텍스트 생성은 새 6-layer 빌더로 교체, 단 데이터는 신구 공존. PR-C 에서 새 글로벌 프리셋 시드 후 구 9 모렉신 프리셋 deprecate.

**Tech Stack:** Python 3.14, SQLAlchemy 2.x, alembic, FastAPI, pytest, Anthropic SDK.

**Working directory:** `/Users/seominjae/Documents/hydra-slot-engine` (feat/slot-engine 브랜치 위에서 시작 — 엔지니어가 PR 분리 시점에 rebase/split 결정).

**테스트 환경:** `tests/conftest.py`의 `db_session` 픽스처 (sqlite in-memory + `Base.metadata.create_all`). alembic round-trip 은 별도 검증 안 함 — 신규 컬럼이 모델에 정의되면 fixture 가 자동 적용.

---

## File Structure

| 파일 | 역할 | 변경 종류 |
|---|---|---|
| `alembic/versions/u9v0multibrand.py` | 마이그레이션 — 5 테이블 변경 | Create |
| `hydra/db/models.py` | Product, NichePresetSelection, GlobalAdPhraseBlocklist 추가 + Brand/Niche/CommentTreeSlot 컬럼 추가 | Modify |
| `hydra/ai/agents/slot_agent.py` | 6-layer system prompt 빌더로 재작성 | Modify |
| `hydra/services/slot_engine.py` | NichePresetSelection.weight 기반 프리셋 선택 추가 | Modify |
| `hydra/services/campaign_service.py` | Niche 만 받는 새 진입점 | Modify |
| `tests/test_multi_brand_models.py` | 모델 라운드트립 + 관계 검증 | Create |
| `tests/test_slot_agent_composition.py` | 6-layer 합성 + mention 정책 + tone_anchor | Create |
| `tests/test_slot_engine_phase_b.py` | 기존 — NichePresetSelection 분기 추가 테스트 | Modify |

---

## Task 1: Product 모델 + 마이그레이션

**Files:**
- Modify: `hydra/db/models.py` (Product 클래스 추가)
- Create: `alembic/versions/u9v0multibrand.py` (마이그레이션 — Task 1~5 통합)
- Create: `tests/test_multi_brand_models.py`

- [ ] **Step 1: Test 파일 만들고 Product 라운드트립 테스트 작성**

`tests/test_multi_brand_models.py`:

```python
"""PR-A 다중 브랜드 데이터 모델 라운드트립 + 관계 검증."""
import json

from hydra.db.models import (
    Brand, Product, Niche, CommentPreset, CommentTreeSlot,
    NichePresetSelection, GlobalAdPhraseBlocklist,
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

```bash
cd /Users/seominjae/Documents/hydra-slot-engine
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_multi_brand_models.py::test_product_belongs_to_brand -x
```

Expected: ImportError / NameError on `Product`

- [ ] **Step 3: `hydra/db/models.py` 에 Product 모델 추가**

기존 `Brand` 클래스 정의 직후 (line ~310 근방) 추가:

```python
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    product_name = Column(String(120), nullable=False)
    protected_terms = Column(Text)  # JSON list — 표기 lock
    core_keywords = Column(Text)    # JSON list — AI 슬롯 substitution
    description = Column(Text)
    core_message = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC), nullable=False)

    brand = relationship("Brand", back_populates="products")

    __table_args__ = (
        Index("ix_products_brand", "brand_id"),
    )
```

`Brand` 클래스의 relationship 섹션에 추가:

```python
products = relationship("Product", back_populates="brand", cascade="all, delete-orphan")
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_multi_brand_models.py::test_product_belongs_to_brand -x
```

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add hydra/db/models.py tests/test_multi_brand_models.py
git -c commit.gpgsign=false commit -m "feat(model): Product 엔티티 추가 (PR-A Task 1)"
```

---

## Task 2: Slot 컬럼 추가 (intent / tone_anchor / mention_brand / mention_solution)

기존 `text_template` 보존 (backward compat). 신규 컬럼 추가만.

**Files:**
- Modify: `hydra/db/models.py` (CommentTreeSlot 클래스, line ~836 근방)
- Modify: `tests/test_multi_brand_models.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_multi_brand_models.py` 끝에:

```python
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Expected: `TypeError: 'intent' is an invalid keyword argument for CommentTreeSlot`

- [ ] **Step 3: 모델 수정**

`hydra/db/models.py` 의 `CommentTreeSlot` 에 컬럼 추가 (`like_distribution` 다음):

```python
    # PR-A: 의도 설명형 슬롯 (구 text_template 대체)
    intent = Column(Text, nullable=True)            # 의도 설명. 신규 슬롯은 NOT NULL 권장 (앱 레이어 검증)
    tone_anchor = Column(Text, nullable=True)       # JSON list — 톤 참고 예시 1-2개
    mention_brand = Column(Boolean, nullable=False, default=False, server_default=sa.text("false"))
    mention_solution = Column(Boolean, nullable=False, default=False, server_default=sa.text("false"))
```

`hydra/db/models.py` 상단 import 에 `import sqlalchemy as sa` 가 이미 있는지 확인. 없으면 추가.

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_multi_brand_models.py -x
```

Expected: 2 passed.

- [ ] **Step 5: 커밋**

```bash
git add hydra/db/models.py tests/test_multi_brand_models.py
git -c commit.gpgsign=false commit -m "feat(model): Slot intent/tone_anchor/mention_* 컬럼 (PR-A Task 2)"
```

---

## Task 3: NichePresetSelection 모델 (N:M with weight)

**Files:**
- Modify: `hydra/db/models.py`
- Modify: `tests/test_multi_brand_models.py`

- [ ] **Step 1: 테스트 추가**

```python
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Expected: `NameError: name 'NichePresetSelection' is not defined` (또는 `Niche.product_id` 컬럼 없음 — 다음 task)

먼저 `Niche.product_id` 추가 필요 (Task 4 와 swap 가능). 우선 `NichePresetSelection` 만 추가:

- [ ] **Step 3: NichePresetSelection 모델 추가**

`hydra/db/models.py` 의 `CommentPreset` 정의 직후 (line ~819 근방) 추가:

```python
class NichePresetSelection(Base):
    """Niche ↔ CommentPreset N:M with weight + enabled."""
    __tablename__ = "niche_preset_selections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    niche_id = Column(Integer, ForeignKey("niches.id", ondelete="CASCADE"), nullable=False)
    preset_id = Column(Integer, ForeignKey("comment_presets.id", ondelete="CASCADE"), nullable=False)
    weight = Column(Integer, nullable=False, default=10)
    enabled = Column(Boolean, nullable=False, default=True, server_default=sa.text("true"))
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    niche = relationship("Niche")
    preset = relationship("CommentPreset")

    __table_args__ = (
        UniqueConstraint("niche_id", "preset_id", name="uq_niche_preset"),
        Index("ix_nps_niche", "niche_id"),
    )
```

- [ ] **Step 4: 테스트 실행 — Niche.product_id 미정의로 실패 예상**

이 시점에선 fail. Task 4 후 통과.

- [ ] **Step 5: Task 4 와 함께 커밋 (다음)**

---

## Task 4: Niche.product_id FK 추가

**Files:**
- Modify: `hydra/db/models.py` (Niche 클래스)

- [ ] **Step 1: Niche 모델에 product_id 추가**

`hydra/db/models.py` 의 `Niche` 클래스 (line ~141 근방) 에서 `comment_preset_id` 직후:

```python
    # PR-A: Brand → Product → Niche 3-tier
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
```

(nullable=True — 기존 Niche 가 product 없는 상태 허용. 마이그레이션에서 자동 backfill 후 prod 운영자가 수동 정리.)

`Niche` relationship 섹션에 추가:

```python
    product = relationship("Product")
```

- [ ] **Step 2: Task 3 테스트 재실행 → 통과 확인**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_multi_brand_models.py::test_niche_preset_selection_with_weight -x
```

Expected: PASS

- [ ] **Step 3: Task 3+4 묶어서 커밋**

```bash
git add hydra/db/models.py tests/test_multi_brand_models.py
git -c commit.gpgsign=false commit -m "feat(model): NichePresetSelection + Niche.product_id (PR-A Task 3+4)"
```

---

## Task 5: GlobalAdPhraseBlocklist 모델

**Files:**
- Modify: `hydra/db/models.py`
- Modify: `tests/test_multi_brand_models.py`

- [ ] **Step 1: 테스트 추가**

```python
def test_global_ad_phrase_blocklist(db_session):
    db_session.add_all([
        GlobalAdPhraseBlocklist(phrase="구매 링크", added_by_user_id=1),
        GlobalAdPhraseBlocklist(phrase="할인 쿠폰", added_by_user_id=1),
    ])
    db_session.commit()

    rows = db_session.query(GlobalAdPhraseBlocklist).all()
    assert {r.phrase for r in rows} == {"구매 링크", "할인 쿠폰"}
```

- [ ] **Step 2: 테스트 실패 확인**

- [ ] **Step 3: 모델 추가**

`hydra/db/models.py` 끝에:

```python
class GlobalAdPhraseBlocklist(Base):
    """광고 카피 어휘 글로벌 banlist. 운영자가 다중 브랜드 운영하며 누적."""
    __tablename__ = "global_ad_phrase_blocklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phrase = Column(String(120), nullable=False, unique=True)
    added_by_user_id = Column(Integer, nullable=True)
    added_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        Index("ix_global_blocklist_phrase", "phrase"),
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_multi_brand_models.py -x
```

Expected: 4 passed.

- [ ] **Step 5: 커밋**

```bash
git add hydra/db/models.py tests/test_multi_brand_models.py
git -c commit.gpgsign=false commit -m "feat(model): GlobalAdPhraseBlocklist (PR-A Task 5)"
```

---

## Task 6: alembic 마이그레이션 (Task 1~5 통합)

prod 적용용. 모든 컬럼 추가, 데이터 백필, downgrade 정의.

**Files:**
- Create: `alembic/versions/u9v0multibrand.py`

- [ ] **Step 1: 직전 alembic head 확인**

```bash
cat alembic/versions/s7t8slot_engine.py | head -20
```

Expected: revision = `s7t8slotengine`, down_revision = `r5s6wlogtail`

- [ ] **Step 2: 새 마이그레이션 파일 생성**

`alembic/versions/u9v0multibrand.py`:

```python
"""multi-brand: Product, NichePresetSelection, Slot intent/tone/mention, GlobalAdPhraseBlocklist

Revision ID: u9v0multibrand
Revises: s7t8slotengine
Create Date: 2026-05-07

PR-A — Brand → Product → Niche 3-tier + 의도 설명형 슬롯 + 광고 어휘 blocklist.
Additive only — 기존 text_template / Niche.comment_preset_id 보존.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'u9v0multibrand'
down_revision: Union[str, Sequence[str], None] = 's7t8slotengine'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) products 테이블
    op.create_table(
        'products',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer, sa.ForeignKey('brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_name', sa.String(120), nullable=False),
        sa.Column('protected_terms', sa.Text),
        sa.Column('core_keywords', sa.Text),
        sa.Column('description', sa.Text),
        sa.Column('core_message', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_products_brand', 'products', ['brand_id'])

    # 2) Niche.product_id
    op.add_column(
        'niches',
        sa.Column('product_id', sa.Integer, sa.ForeignKey('products.id', ondelete='SET NULL'), nullable=True),
    )

    # 3) Slot 컬럼 추가
    op.add_column('comment_tree_slots',
                  sa.Column('intent', sa.Text, nullable=True))
    op.add_column('comment_tree_slots',
                  sa.Column('tone_anchor', sa.Text, nullable=True))
    op.add_column('comment_tree_slots',
                  sa.Column('mention_brand', sa.Boolean, nullable=False, server_default=sa.text('false')))
    op.add_column('comment_tree_slots',
                  sa.Column('mention_solution', sa.Boolean, nullable=False, server_default=sa.text('false')))

    # 4) niche_preset_selections 테이블
    op.create_table(
        'niche_preset_selections',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('niche_id', sa.Integer, sa.ForeignKey('niches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('preset_id', sa.Integer, sa.ForeignKey('comment_presets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('weight', sa.Integer, nullable=False, server_default='10'),
        sa.Column('enabled', sa.Boolean, nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint('niche_id', 'preset_id', name='uq_niche_preset'),
    )
    op.create_index('ix_nps_niche', 'niche_preset_selections', ['niche_id'])

    # 5) global_ad_phrase_blocklist
    op.create_table(
        'global_ad_phrase_blocklist',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('phrase', sa.String(120), nullable=False, unique=True),
        sa.Column('added_by_user_id', sa.Integer, nullable=True),
        sa.Column('added_at', sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_global_blocklist_phrase', 'global_ad_phrase_blocklist', ['phrase'])

    # 6) 데이터 백필 — 기존 Brand 마다 Product 1개 자동 생성
    # (운영 데이터 보호: brand.product_name 존재하는 행만)
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO products (brand_id, product_name, core_keywords, description, core_message,
                              created_at, updated_at)
        SELECT id,
               COALESCE(product_name, name),
               COALESCE(allowed_keywords, '[]'),
               '', COALESCE(core_message, ''),
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM brands
        WHERE NOT EXISTS (SELECT 1 FROM products p WHERE p.brand_id = brands.id)
    """))

    # 7) Niche.product_id 백필 — 같은 brand_id 의 첫 product 로 매핑
    conn.execute(sa.text("""
        UPDATE niches
        SET product_id = (
            SELECT MIN(p.id) FROM products p WHERE p.brand_id = niches.brand_id
        )
        WHERE product_id IS NULL AND brand_id IS NOT NULL
    """))

    # 8) Niche.comment_preset_id 가 있던 행 → NichePresetSelection 으로 이전
    conn.execute(sa.text("""
        INSERT INTO niche_preset_selections (niche_id, preset_id, weight, enabled, created_at)
        SELECT id, comment_preset_id, 100, 1, CURRENT_TIMESTAMP
        FROM niches
        WHERE comment_preset_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM niche_preset_selections nps
            WHERE nps.niche_id = niches.id AND nps.preset_id = niches.comment_preset_id
        )
    """))


def downgrade() -> None:
    op.drop_index('ix_global_blocklist_phrase', table_name='global_ad_phrase_blocklist')
    op.drop_table('global_ad_phrase_blocklist')

    op.drop_index('ix_nps_niche', table_name='niche_preset_selections')
    op.drop_table('niche_preset_selections')

    op.drop_column('comment_tree_slots', 'mention_solution')
    op.drop_column('comment_tree_slots', 'mention_brand')
    op.drop_column('comment_tree_slots', 'tone_anchor')
    op.drop_column('comment_tree_slots', 'intent')

    op.drop_column('niches', 'product_id')

    op.drop_index('ix_products_brand', table_name='products')
    op.drop_table('products')
```

- [ ] **Step 3: 마이그레이션 파일 syntax 체크 (alembic 명령으로 head 확인)**

```bash
# 직접 alembic 실행은 prod-mirror DB 손대니까 안 함. 대신 import 테스트:
/Users/seominjae/Documents/hydra/.venv/bin/python -c "
import sys
sys.path.insert(0, '/Users/seominjae/Documents/hydra-slot-engine')
from alembic.config import Config
cfg = Config('alembic.ini')
from alembic.script import ScriptDirectory
sd = ScriptDirectory.from_config(cfg)
for rev in sd.walk_revisions('base', 'heads'):
    if rev.revision == 'u9v0multibrand':
        print(f'OK: {rev.revision} (down: {rev.down_revision})')
        break
else:
    print('NOT FOUND')
"
```

Expected: `OK: u9v0multibrand (down: s7t8slotengine)`

- [ ] **Step 4: 모델 테스트 회귀 확인**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_multi_brand_models.py tests/test_slot_engine_phase_a.py tests/test_slot_engine_phase_b.py tests/test_slot_engine_phase_c.py -q
```

Expected: 모두 PASS (회귀 0).

- [ ] **Step 5: 커밋**

```bash
git add alembic/versions/u9v0multibrand.py
git -c commit.gpgsign=false commit -m "feat(alembic): u9v0multibrand — PR-A 통합 마이그레이션 (Task 6)"
```

---

## Task 7: 6-layer system prompt 빌더 (slot_agent.py 재작성)

**Files:**
- Modify: `hydra/ai/agents/slot_agent.py` (`_build_slot_system_prompt`)
- Create: `tests/test_slot_agent_composition.py`

- [ ] **Step 1: 6-layer 합성 테스트 작성**

`tests/test_slot_agent_composition.py`:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인 (signature mismatch)**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_slot_agent_composition.py::test_all_six_layers_present_in_system_prompt -x
```

Expected: TypeError on `_build_slot_system_prompt(...)` 시그니처 불일치.

- [ ] **Step 3: `_build_slot_system_prompt` 재작성**

`hydra/ai/agents/slot_agent.py` 의 `_build_slot_system_prompt` 함수 전체 교체:

```python
def _build_slot_system_prompt(
    *,
    slot: CommentTreeSlot,
    brand: dict[str, Any],
    product: dict[str, Any] | None,
    niche: dict[str, Any],
    persona: dict[str, Any] | None,
    global_blocklist: list[str],
) -> str:
    """6-layer system prompt 합성.

    Layers:
      1. Global (Slot.intent / tone_anchor / length / emoji / mention 정책 / blocklist)
      2. Brand (tone_guide, banned, company_protected_terms)
      3. Product (product_name, protected_terms, core_keywords) — mention 허용 시만
      4. Niche (target_audience, mention_intensity, voice_override)
      5. Persona
      6. Conversation — _build_slot_user_message 에서 user message 로 따로
    """
    parts: list[str] = ["당신은 YouTube 영상에 댓글을 다는 한국 사용자입니다.",
                        "절대 광고처럼 보이면 안 됩니다."]

    # ── Layer 1: Global (slot 의도 + 정책) ──
    parts.append(f"\n[슬롯 의도]\n{slot.intent or '(미지정)'}")

    tone_anchor_list: list[str] = []
    if slot.tone_anchor:
        try:
            tone_anchor_list = json.loads(slot.tone_anchor)
        except (json.JSONDecodeError, TypeError):
            tone_anchor_list = []
    if tone_anchor_list:
        anchor_lines = "\n".join(f"  - {a}" for a in tone_anchor_list)
        parts.append(
            f"\n[톤 참고 — 변주 시드 X, 어휘 그대로 베끼지 말 것]\n{anchor_lines}"
        )

    length_text = LENGTH_GUIDES.get(slot.length, LENGTH_GUIDES["medium"])[0]
    emoji_text = EMOJI_GUIDES.get(slot.emoji, EMOJI_GUIDES["sometimes"])
    parts.append(f"\n길이 가이드: {length_text}")
    parts.append(f"이모지 가이드: {emoji_text}")

    mention_lines = []
    if not slot.mention_brand:
        mention_lines.append("- 브랜드명 직접 언급 절대 금지.")
    if not slot.mention_solution:
        mention_lines.append("- 솔루션 카테고리/성분 노출 금지.")
    if slot.mention_brand:
        mention_lines.append("- 브랜드명 자연스럽게 1회 노출 (강조 X).")
    if slot.mention_solution:
        mention_lines.append("- 솔루션 카테고리/성분 자연스럽게 언급 OK.")
    if mention_lines:
        parts.append("\n[노출 정책]\n" + "\n".join(mention_lines))

    if global_blocklist:
        bl_lines = ", ".join(f"'{p}'" for p in global_blocklist[:30])
        parts.append(f"\n[광고 카피 금지 어휘]\n{bl_lines}")

    # ── Layer 2: Brand ──
    parts.append(f"\n[브랜드]\n- 회사: {brand.get('name', '')}")
    if brand.get("tone_guide"):
        parts.append(f"- 톤 가이드: {brand['tone_guide']}")
    brand_banned = brand.get("banned_keywords") or []
    if brand_banned:
        parts.append(f"- 회사 banned: {', '.join(brand_banned)}")
    company_protected = brand.get("company_protected_terms") or []
    if company_protected:
        parts.append(f"- 회사 표기 lock: {', '.join(company_protected)}")

    # ── Layer 3: Product (mention 허용 시만) ──
    if product and (slot.mention_brand or slot.mention_solution):
        parts.append(f"\n[제품]")
        if slot.mention_brand:
            parts.append(f"- 제품명: {product.get('product_name', '')}")
            protected = product.get("protected_terms") or []
            if protected:
                parts.append(f"- 표기 lock (절대 변형 금지): {', '.join(protected)}")
        if slot.mention_solution:
            core_kw = product.get("core_keywords") or []
            if core_kw:
                parts.append(f"- 솔루션 키워드 (의도 substitution 후보): {', '.join(core_kw)}")

    # ── Layer 4: Niche ──
    parts.append(f"\n[타겟 니치]")
    if niche.get("target_audience"):
        parts.append(f"- 타겟: {niche['target_audience']}")
    intensity = niche.get("mention_intensity", 40)
    parts.append(
        f"- 노출 강도: {intensity}/100 "
        f"({'공감/정보 톤 우선' if intensity < 50 else '직접 추천 톤 허용' if intensity > 70 else '균형'})"
    )
    if niche.get("voice_override"):
        parts.append(f"- 니치 톤 추가: {niche['voice_override']}")

    # ── Layer 5: Persona ──
    if persona:
        parts.append(
            f"\n[페르소나 — 이 사람이 실제로 쓰듯]\n"
            f"- {persona.get('age', '?')}세 {persona.get('gender', '?')}\n"
            f"- 지역: {persona.get('region', '서울')}\n"
            f"- 직업: {persona.get('occupation', '직장인')}\n"
            f"- 말투: {persona.get('speech_style', '편한 존댓말')}"
        )

    parts.append(
        "\n[출력 규칙]\n"
        "- 한국어로 작성\n"
        "- 광고 패턴 금지 (구매 링크/할인/지금 구매)\n"
        "- 같은 표현 반복 금지\n"
        "- 댓글만 출력. 설명/따옴표/메타텍스트 없이."
    )

    return "\n".join(parts)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_slot_agent_composition.py::test_all_six_layers_present_in_system_prompt -x
```

Expected: PASS

- [ ] **Step 5: 기존 호출처 업데이트 — `generate_comment_for_task`**

`hydra/ai/agents/slot_agent.py` 의 `generate_comment_for_task` 안에서 `_build_slot_system_prompt(brand_dict, slot, persona)` 호출하던 곳을 새 시그니처로:

```python
    # Niche / Product 정보 합성
    niche_dict = {}
    product_dict = None
    if campaign and campaign.brand_id:
        # campaign 에 niche_id 가 있으면 그쪽, 없으면 brand 만
        niche_obj = None
        if hasattr(campaign, 'niche_id') and campaign.niche_id:
            niche_obj = db.get(Niche, campaign.niche_id)
        if niche_obj:
            niche_dict = {
                "target_audience": niche_obj.target_audience or "",
                "mention_intensity": getattr(niche_obj, "mention_intensity", 40),
                "voice_override": getattr(niche_obj, "voice_override", None),
            }
            if niche_obj.product_id:
                p_obj = db.get(Product, niche_obj.product_id)
                if p_obj:
                    product_dict = {
                        "product_name": p_obj.product_name or "",
                        "protected_terms": json.loads(p_obj.protected_terms or "[]"),
                        "core_keywords": json.loads(p_obj.core_keywords or "[]"),
                    }

    # global blocklist
    blocklist_rows = db.query(GlobalAdPhraseBlocklist).all()
    global_blocklist = [r.phrase for r in blocklist_rows]

    system = _build_slot_system_prompt(
        slot=slot,
        brand=brand_dict,
        product=product_dict,
        niche=niche_dict,
        persona=persona,
        global_blocklist=global_blocklist,
    )
```

`hydra/ai/agents/slot_agent.py` 상단 import 에 추가:

```python
from hydra.db.models import (
    Account, Brand, Campaign, CommentPreset, CommentTreeSlot, Task, Video,
    Niche, Product, GlobalAdPhraseBlocklist,
)
```

- [ ] **Step 6: 기존 phase C 테스트 회귀 확인**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_slot_engine_phase_c.py -q
```

기존 phase C 테스트는 구 시그니처로 작성됨. 깨질 가능성 큼. 깨진 테스트는 새 시그니처로 업데이트:
- `test_system_prompt_contains_slot_metadata`: 시그니처 keyword args 로 변경
- `test_user_message_includes_parent_context`: 변경 없음 (user message 빌더는 그대로)
- 이외 깨지는 테스트는 일단 skip 또는 업데이트

Expected after update: PASS.

- [ ] **Step 7: 커밋**

```bash
git add hydra/ai/agents/slot_agent.py tests/test_slot_agent_composition.py tests/test_slot_engine_phase_c.py
git -c commit.gpgsign=false commit -m "feat(slot_agent): 6-layer system prompt 합성 (PR-B Task 7)"
```

---

## Task 8: mention 정책 validator

**Files:**
- Modify: `hydra/ai/agents/slot_agent.py` (`_validator`)
- Modify: `tests/test_slot_agent_composition.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_slot_agent_composition.py` 에:

```python
from hydra.ai.agents.slot_agent import _validator


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
```

- [ ] **Step 2: 테스트 실패 확인 (시그니처 불일치)**

- [ ] **Step 3: `_validator` 재작성**

`hydra/ai/agents/slot_agent.py` 의 `_validator` 교체:

```python
def _validator(
    text: str,
    banned_keywords: list[str],
    *,
    slot_mention_brand: bool,
    slot_mention_solution: bool,
    brand_name: str,
    protected_terms: list[str],
    core_keywords: list[str],
    global_blocklist: list[str],
) -> list[str]:
    """슬롯·브랜드·니치 정책을 통합 검증."""
    issues: list[str] = []

    if len(text) < 2:
        issues.append("too short")
    if len(text) > 500:
        issues.append("over 500 chars")

    # banned (brand-level)
    text_lower = text.lower()
    for kw in banned_keywords:
        if kw and kw.lower() in text_lower:
            issues.append(f"banned keyword: {kw}")

    # 광고 패턴 (하드코딩 — 항상)
    ad_phrases = ["구매 링크", "할인 코드", "지금 구매", "클릭 여기", "꼭 써보세요"]
    for ph in ad_phrases:
        if ph in text:
            issues.append(f"ad pattern: {ph}")

    # 글로벌 blocklist
    for ph in global_blocklist:
        if ph and ph in text:
            issues.append(f"global blocklist phrase: {ph}")

    # 알려진 오타 (autocorrect 와 같이)
    issues.extend(_check_protected_spelling(text, None, brand_name))

    # mention_brand 정책
    if not slot_mention_brand and brand_name and brand_name in text:
        issues.append(f"슬롯 mention_brand=False 인데 브랜드명 '{brand_name}' 노출")

    # mention_solution 정책 (core_keywords 또는 추가 protected_terms 노출 차단)
    if not slot_mention_solution:
        # protected_terms 중 brand_name 이 아닌 (성분명) — 예: 체성케라틴
        for term in protected_terms:
            if term and term != brand_name and term in text:
                issues.append(f"슬롯 mention_solution=False 인데 솔루션 '{term}' 노출")
                break
        else:
            for kw in core_keywords:
                if kw and kw in text:
                    issues.append(f"슬롯 mention_solution=False 인데 성분 키워드 '{kw}' 노출")
                    break

    return issues
```

`generate_comment_for_task` 안의 `_validator` 호출 업데이트:

```python
    template_text = slot.intent or ""  # 더 이상 text_template 안 씀
    brand_name = brand_dict.get("name", "")
    product_protected = product_dict.get("protected_terms", []) if product_dict else []
    product_core = product_dict.get("core_keywords", []) if product_dict else []

    text = call_claude(
        model=get_model("comment"),
        system=system,
        user_message=user,
        max_tokens=LENGTH_GUIDES.get(slot.length, LENGTH_GUIDES["medium"])[1],
        validator=lambda t: _validator(
            t, banned,
            slot_mention_brand=slot.mention_brand,
            slot_mention_solution=slot.mention_solution,
            brand_name=brand_name,
            protected_terms=product_protected,
            core_keywords=product_core,
            global_blocklist=global_blocklist,
        ),
        max_retries=4,
    )
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_slot_agent_composition.py -q
```

Expected: 5 passed.

- [ ] **Step 5: phase C 회귀 확인 후 커밋**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_slot_engine_phase_c.py -q
```

Phase C 테스트가 옛 `_validator(text, banned, template, brand)` 시그니처로 작성됐다면 업데이트 필요. 새 시그니처에 맞춰 keyword args 추가.

```bash
git add hydra/ai/agents/slot_agent.py tests/test_slot_agent_composition.py tests/test_slot_engine_phase_c.py
git -c commit.gpgsign=false commit -m "feat(slot_agent): mention 정책 validator (PR-B Task 8)"
```

---

## Task 9: NichePresetSelection.weight 기반 캠페인 enqueue

**Files:**
- Modify: `hydra/services/slot_engine.py` (`create_campaign_with_slot_tasks` 진입점 위에 새 함수)
- Modify: `tests/test_slot_engine_phase_b.py`

- [ ] **Step 1: 테스트 추가**

`tests/test_slot_engine_phase_b.py` 끝에:

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Expected: `ImportError: cannot import name 'pick_preset_for_niche'`

- [ ] **Step 3: 함수 추가**

`hydra/services/slot_engine.py` 끝에:

```python
def pick_preset_for_niche(db: Session, niche_id: int) -> CommentPreset:
    """Niche 의 NichePresetSelection 가중치 따라 프리셋 1개 랜덤 선택.

    Raises:
        SlotEngineError: enabled selection 이 없을 때.
    """
    from hydra.db.models import NichePresetSelection
    selections = (
        db.query(NichePresetSelection)
        .filter(NichePresetSelection.niche_id == niche_id)
        .filter(NichePresetSelection.enabled.is_(True))
        .all()
    )
    if not selections:
        raise SlotEngineError(f"no enabled preset for niche {niche_id}")
    weights = [s.weight for s in selections]
    if sum(weights) <= 0:
        raise SlotEngineError(f"all preset weights are zero for niche {niche_id}")
    picked = random.choices(selections, weights=weights, k=1)[0]
    preset = db.get(CommentPreset, picked.preset_id)
    if preset is None:
        raise SlotEngineError(f"preset {picked.preset_id} not found")
    return preset
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_slot_engine_phase_b.py -q
```

Expected: 모두 PASS (기존 7 + 신규 2 = 9 passed).

- [ ] **Step 5: 커밋**

```bash
git add hydra/services/slot_engine.py tests/test_slot_engine_phase_b.py
git -c commit.gpgsign=false commit -m "feat(slot_engine): NichePresetSelection.weight 기반 프리셋 선택 (PR-B Task 9)"
```

---

## Task 10: campaign_service 새 진입점 (Niche 만 받음)

**Files:**
- Modify: `hydra/services/campaign_service.py`
- Modify: `tests/test_slot_engine_phase_d_e2e.py` (또는 신규 테스트)

- [ ] **Step 1: 테스트 추가**

`tests/test_slot_engine_phase_d_e2e.py` 끝에:

```python
def test_create_campaign_for_niche_uses_weighted_preset(db_session):
    """Niche 입력만으로 캠페인 enqueue — 가중치 따라 프리셋 자동 선택."""
    from hydra.services.campaign_service import create_campaign_for_niche
    from hydra.db.models import (
        Brand, Product, Niche, Account, Video, CommentPreset, CommentTreeSlot,
        NichePresetSelection, Task,
    )
    import json

    brand = Brand(name="OO헬스", category="영양제", selected_presets="[]")
    db_session.add(brand); db_session.flush()
    product = Product(brand_id=brand.id, product_name="모렉신",
                      protected_terms=json.dumps(["모렉신"]),
                      core_keywords=json.dumps(["체성케라틴"]))
    db_session.add(product); db_session.flush()
    niche = Niche(name="산후맘", brand_id=brand.id, product_id=product.id,
                  target_audience="30대 산후맘", preset_per_video_limit=1)
    db_session.add(niche); db_session.flush()

    # 활성 계정 5개
    for i in range(5):
        db_session.add(Account(gmail=f"e2e_{i}@t", password="x", status="active",
                               persona=json.dumps({"age": 30+i, "gender": "여",
                                                   "region": "서울", "occupation": "직장인",
                                                   "speech_style": "친근한 존댓말"})))
    db_session.flush()

    # 글로벌 프리셋 1개 (의도 설명형)
    p = CommentPreset(name="F4 트렌", is_global=True)
    db_session.add(p); db_session.flush()
    db_session.add_all([
        CommentTreeSlot(comment_preset_id=p.id, slot_label="A", position=1,
                        intent="[메인·고민] 자연 토로", mention_brand=False,
                        mention_solution=False, length="medium", emoji="sometimes",
                        ai_variation=80, like_min=0, like_max=5, like_distribution="adaptive"),
        CommentTreeSlot(comment_preset_id=p.id, slot_label="B", reply_to_slot_label="A",
                        position=2, intent="[증언] 본인 경험", mention_brand=False,
                        mention_solution=True, length="medium", emoji="sometimes",
                        ai_variation=80, like_min=0, like_max=5, like_distribution="adaptive"),
    ])
    db_session.add(NichePresetSelection(niche_id=niche.id, preset_id=p.id,
                                        weight=100, enabled=True))

    db_session.add(Video(id="v_test", url="https://yt/v_test", title="산후 V-log"))
    db_session.commit()

    campaign = create_campaign_for_niche(
        db=db_session, niche_id=niche.id, video_id="v_test",
    )
    db_session.commit()

    tasks = (db_session.query(Task)
             .filter(Task.campaign_id == campaign.id)
             .filter(Task.task_type.in_(("comment", "reply"))).all())
    assert len(tasks) == 2
    by_label = {t.slot_label: t for t in tasks}
    assert by_label["B"].parent_task_id == by_label["A"].id
```

- [ ] **Step 2: 테스트 실패 확인**

Expected: `ImportError: cannot import name 'create_campaign_for_niche'`

- [ ] **Step 3: 함수 추가**

`hydra/services/campaign_service.py` 끝에:

```python
def create_campaign_for_niche(
    db: Session,
    *,
    niche_id: int,
    video_id: str,
) -> Campaign:
    """새 multi-brand 흐름 진입점 — Niche 만 받아 자동으로 product/brand/preset 결정.

    1. Niche 검증
    2. NichePresetSelection.weight 따라 글로벌 프리셋 선택
    3. Campaign row 생성
    4. slot_engine 호출 → Task 트리 생성
    """
    from hydra.db.models import Niche
    from hydra.services.slot_engine import (
        create_campaign_with_slot_tasks, pick_preset_for_niche,
    )

    niche = db.get(Niche, niche_id)
    if niche is None:
        raise ValueError(f"Niche {niche_id} not found")

    preset = pick_preset_for_niche(db, niche_id)

    campaign = Campaign(
        video_id=video_id,
        brand_id=niche.brand_id,
        niche_id=niche_id,
        scenario=preset.name,
        campaign_type="scenario",
        comment_mode="ai_auto",
        comment_preset_id=preset.id,
        status="planning",
    )
    db.add(campaign); db.flush()

    create_campaign_with_slot_tasks(
        db, campaign=campaign, comment_preset=preset, video_id=video_id,
    )
    campaign.status = "in_progress"
    db.commit()
    db.refresh(campaign)
    return campaign
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_slot_engine_phase_d_e2e.py -q
```

Expected: 4 passed (기존 3 + 신규 1).

- [ ] **Step 5: 커밋**

```bash
git add hydra/services/campaign_service.py tests/test_slot_engine_phase_d_e2e.py
git -c commit.gpgsign=false commit -m "feat(campaign_service): create_campaign_for_niche — multi-brand 진입점 (PR-B Task 10)"
```

---

## Task 11: 전체 테스트 회귀 + 정리

- [ ] **Step 1: 모든 슬롯 엔진 테스트 실행**

```bash
cd /Users/seominjae/Documents/hydra-slot-engine
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/test_slot_engine_phase_a.py tests/test_slot_engine_phase_b.py tests/test_slot_engine_phase_c.py tests/test_slot_engine_phase_d_e2e.py tests/test_multi_brand_models.py tests/test_slot_agent_composition.py -q
```

Expected: 모두 PASS. 합계 ~30+ tests.

- [ ] **Step 2: 전체 회귀 (이미 알려진 9 pre-existing 실패 외)**

```bash
/Users/seominjae/Documents/hydra/.venv/bin/python -m pytest tests/ -q --tb=no 2>&1 | tail -5
```

Expected: 신규 회귀 0건. pre-existing 9 failures 그대로.

- [ ] **Step 3: 알려진 이슈 정리 — Task 7 에서 phase C 의 mock 기반 테스트가 깨졌으면 새 시그니처로 정렬**

`tests/test_slot_engine_phase_c.py` 안의 `_build_slot_system_prompt` 호출을 keyword args 로 교정. 만약 `test_d_slot_uses_same_persona_as_b` 같은 테스트가 새 시그니처와 맞지 않으면 `_make_seed` fixture 도 niche/product 설정해서 새 시그니처 충족시키기.

- [ ] **Step 4: PR-A + PR-B 통합 커밋 메시지로 squash 안 함 (개별 커밋 보존)**

git log 확인:

```bash
git log --oneline origin/main..HEAD | head -20
```

Expected: 어제 4커밋 + Task 1~10 커밋 모두 보임.

- [ ] **Step 5: 최종 커밋 (회귀 정리만 했으면)**

```bash
git status -s
git -c commit.gpgsign=false commit -am "chore: PR-A + PR-B 회귀 정리"
```

---

## Self-Review (이 plan 자체 점검)

**Spec coverage:**
- §3.1 GlobalPreset/Slot 새 컬럼 → Task 2 ✓
- §3.1 GlobalAdPhraseBlocklist → Task 5 ✓
- §3.2 Brand 컬럼 정리 → ⚠️ 이 plan 에선 신규 컬럼만 추가. 기존 product_name/product_category 제거는 다음 PR (별도 정리). 마이그레이션 §6 데이터 백필 로 우회.
- §3.2 Product 신설 → Task 1 ✓
- §3.2 Niche.product_id, NichePresetSelection → Task 3+4 ✓
- §3.2 CommentTreeSlot intent/tone_anchor/mention_* → Task 2 ✓
- §4 6-layer 합성 → Task 7 ✓
- §5.3 자동 안전망 mention 정책 validator → Task 8 ✓
- §5.3 niche.mention_intensity 의 system prompt 주입 → Task 7 (intensity 라인 포함) ✓
- §6 다양성 (프리셋 가중치 선택) → Task 9 ✓
- §5.2 캠페인 생성 새 흐름 → Task 10 ✓

**갭 (다른 PR 로 이관)**:
- 기존 Brand 컬럼(product_name, product_category, selling_points 등) 정리 — PR-A2 또는 cleanup PR
- Persona 자동 생성 흐름 (persona_agent 호출) — PR-D (어드민 wizard) 영역
- 어드민 UI — PR-D
- 모니터링 대시보드 — PR-E
- 새 글로벌 프리셋 시드 (10~15개) — PR-C

**Placeholder scan**: 없음. 모든 step 에 실제 코드/명령 명시.

**Type consistency**: `pick_preset_for_niche` 리턴 타입 = `CommentPreset` ✓. `create_campaign_for_niche` 가 호출하는 `create_campaign_with_slot_tasks` 시그니처 동일 ✓. `_build_slot_system_prompt` keyword args 통일 ✓.

**Ambiguity**: Task 7 의 phase C 테스트 정렬 — "깨진 테스트는 일단 skip 또는 업데이트" 라고 적었지만 더 구체적으로 — Task 11 Step 3 에서 명시. 충분.

---

**총 예상 시간**: 6-8 시간 (Task 당 30~45분, TDD 사이클).

**위험**: 
- Task 6 마이그레이션의 backfill SQL — sqlite/postgres 호환성. 위 SQL 은 두 엔진 모두 동작. prod 적용 전 staging 1회 dry-run 권장.
- Task 7 의 phase C 회귀 — 시그니처 변경으로 깨질 수 있음. Task 7 Step 6 + Task 11 Step 3 에서 정렬.

**다음 plan**: PR-C (새 글로벌 프리셋 10~15개 작성) → PR-D (어드민 wizard) → PR-E (캠페인 + 대시보드). 별도 plan 파일.
