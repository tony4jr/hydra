# PR-8d — 프리셋 라이브러리 (전역 + 5 기본 시드)

**위험**: ★★★ (DB 마이그레이션 + 신규 모델)
**예상**: 5h
**의존**: PR-8c (Brand 톤 컬럼 — 자동 입힘 의존)

---

## 목표

프리셋 = **댓글 트리 양식**. 전역 라이브러리 (브랜드 독립). 신규 가입 시 5 기본 시드. 사용 중인 타겟 명시.

브랜드 톤·금지어·자주 쓰는 표현은 프리셋이 자동 입힘 — 운영자는 프리셋 자체엔 톤 박지 않아도 됨.

---

## 페이지: /presets

```
프리셋 라이브러리                  [+ 새 프리셋]

┌──────────────┬──────────────┬──────────────┐
│ 후기형        │ 공감형        │ 비교형        │
│ 슬롯 3개      │ 슬롯 4개      │ 슬롯 5개      │
│ 사용중: 모렉신 │ 사용중: -    │ 사용중: 모렉신, 천명 │
│ [편집] [복제] │ [편집]       │ [편집]       │
└──────────────┴──────────────┴──────────────┘

┌──────────────┬──────────────┐
│ 정보형        │ 질문형        │
│ 슬롯 2개      │ 슬롯 3개      │
└──────────────┴──────────────┘
```

카드 클릭 → /presets/$id (편집, PR-8e 댓글 트리)

---

## 5 기본 프리셋 시드

신규 가입 시 자동 생성. 운영자가 직접 다듬을 수 있음 (편집 가능).

| 이름 | 슬롯 수 | 컨셉 |
|---|---|---|
| 후기형 | 3 | A=원본 후기, B=A 에 답글 (감사), C=B 에 답글 (재확인) |
| 공감형 | 4 | A=공감 시작, B=A 답글 (자기 경험), C=B 답글 (정보 제공), D=A 답글 (격려) |
| 비교형 | 5 | A=비교 질문, B=A 답글 (옵션1 추천), C=A 답글 (옵션2 추천), D=B 답글 (반박), E=C 답글 (반박) |
| 정보형 | 2 | A=정보 제공, B=A 답글 (감사 + 추가 질문) |
| 질문형 | 3 | A=질문, B=A 답글 (답변 시도), C=A 답글 (다른 시각) |

slot 텍스트 양식은 placeholder (운영자가 편집).

---

## 데이터 모델 (alembic)

### Preset 모델

```python
class Preset(Base):
    __tablename__ = "presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(80), nullable=False)
    description = Column(Text)
    is_global = Column(Boolean, default=True, nullable=False)  # PR-8d 는 모두 True
    is_default = Column(Boolean, default=False, nullable=False)  # 5 기본 시드 표시
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC), nullable=False)

    slots = relationship("CommentTreeSlot", back_populates="preset",
                         cascade="all, delete-orphan")
```

### CommentTreeSlot 모델 (Preset 자식)

```python
class CommentTreeSlot(Base):
    __tablename__ = "comment_tree_slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    preset_id = Column(Integer, ForeignKey("presets.id", ondelete="CASCADE"),
                       nullable=False)
    slot_label = Column(String(4), nullable=False)  # A, B, C, ... (자동 부여)
    reply_to_slot_label = Column(String(4))  # NULL = 메인 댓글, 'A' = A 에 답글
    position = Column(Integer, nullable=False)  # 순서

    # 양식
    text_template = Column(Text)
    length = Column(String(10), default="medium")  # short / medium / long
    emoji = Column(String(10), default="sometimes")  # none / sometimes / often
    ai_variation = Column(Integer, default=50)  # 0~100

    # 좋아요 컨트롤
    like_min = Column(Integer, default=0)
    like_max = Column(Integer, default=0)
    like_distribution = Column(String(10), default="adaptive")
    # adaptive / burst / spread / slow

    preset = relationship("Preset", back_populates="slots")

    __table_args__ = (
        Index("ix_slots_preset", "preset_id"),
        UniqueConstraint("preset_id", "slot_label", name="uq_slots_preset_label"),
    )
```

### Niche.preset_id (FK)

```python
op.add_column('niches', sa.Column(
    'preset_id', sa.Integer(),
    sa.ForeignKey('presets.id', ondelete='SET NULL'), nullable=True
))
op.create_index('idx_niches_preset', 'niches', ['preset_id'])
```

⚠️ 기존 codebase 의 다른 `Preset` 클래스 (있다면) 와 충돌 확인 필요. 없으면 신설, 있으면 spec 부정합 정리 PR 먼저.

### 5 시드 INSERT (alembic)

마이그레이션 안 INSERT (운영자가 삭제 가능):

```sql
INSERT INTO presets (name, description, is_global, is_default) VALUES
  ('후기형', '제품 사용 후기 + 감사 + 재확인 (3슬롯)', TRUE, TRUE),
  ('공감형', '공감 + 경험 공유 + 정보 + 격려 (4슬롯)', TRUE, TRUE),
  ('비교형', '비교 질문 + 옵션 추천 + 반박 (5슬롯)', TRUE, TRUE),
  ('정보형', '정보 제공 + 감사 + 추가 질문 (2슬롯)', TRUE, TRUE),
  ('질문형', '질문 + 답변 + 다른 시각 (3슬롯)', TRUE, TRUE);

-- 슬롯은 운영자가 편집할 placeholder, 양식은 빈 문자열 또는 sample
INSERT INTO comment_tree_slots (preset_id, slot_label, reply_to_slot_label, position, text_template) VALUES
  ((SELECT id FROM presets WHERE name='후기형'), 'A', NULL, 1, '<후기 본문>'),
  ((SELECT id FROM presets WHERE name='후기형'), 'B', 'A', 2, '감사합니다 :)'),
  ((SELECT id FROM presets WHERE name='후기형'), 'C', 'B', 3, '저도 한번 써볼게요'),
  -- 공감형 4 슬롯, 비교형 5, 정보형 2, 질문형 3
  ...;
```

---

## 백엔드

`GET /api/admin/presets/list` — 모든 프리셋 + 사용 중인 niche 카운트
`POST /api/admin/presets` — 신규 (운영자 직접)
`POST /api/admin/presets/{id}/clone` — 복제
`GET /api/admin/presets/{id}` — 상세 + 슬롯 list
`PATCH /api/admin/presets/{id}` — 이름/설명
`DELETE /api/admin/presets/{id}` — soft delete (is_default 시드는 삭제 X, 409)

슬롯 CRUD 는 PR-8e 에서.

---

## 변경 파일

| 파일 | 변경 |
|---|---|
| `alembic/versions/XX_preset_library.py` | **신규** — Preset/CommentTreeSlot + 5 시드 + Niche.preset_id |
| `hydra/db/models.py` | Preset, CommentTreeSlot 추가, Niche.preset_id |
| `hydra/web/routes/presets.py` | **신규** (또는 기존 보강) |
| `hydra/web/app.py` | router |
| `frontend/src/features/presets/index.tsx` | **신규** 라이브러리 페이지 |
| `frontend/src/features/presets/[id].tsx` | placeholder, PR-8e 에서 콘텐츠 |
| `frontend/src/types/preset.ts` | **신규** |
| `frontend/src/hooks/use-presets.ts` | **신규** |
| `frontend/src/routes/_authenticated/presets/index.tsx` | **신규** |
| `frontend/src/routes/_authenticated/presets/$presetId.tsx` | **신규** |

---

## 격리 dry-run + 안전 검증

- accounts 9 row count = 0 변동
- presets 5 시드 INSERT 확인
- comment_tree_slots 슬롯 17개 (3+4+5+2+3) INSERT 확인
- niches.preset_id = NULL (default, 모든 row)
- downgrade → presets 테이블 / niches.preset_id 제거 → 재upgrade

---

## 자율 결정 영역

- A. 시드 슬롯 텍스트 양식 (placeholder 만 또는 한국어 sample)
- B. is_default 시드 삭제 정책 (현재: 409, 운영자 요청 시 force=true 옵션 추가 가능)
- C. Niche → Preset 1:1 vs N:1 (지금 spec 은 Niche.preset_id 단일 — N:1 즉 한 프리셋이 여러 타겟에서 사용 가능, 하지만 한 타겟엔 한 프리셋. PR-8e/8g 에서 캠페인 단위로 다른 프리셋 사용 시 별도 모델 필요)
- D. 기존 codebase 에 `Preset` 동명 클래스 있으면 분기점 — spec 정리 PR

---

## Out of scope

- 슬롯 편집 UI (PR-8e)
- AI 톤 자동 입힘 실제 구현 (PR-8d 는 schema 만, 적용은 댓글 생성 워커)
- 프리셋 marketplace / sharing (별도)
