# PR-3 — Niche 모델 신설 + 마이그레이션

## 목표

Brand 1계층 구조를 Brand → Niche 2계층으로 확장합니다. 운영 중인 시스템에 무중단으로 적용하며, 기존 데이터는 1:1로 자동 마이그레이션됩니다.

이 PR은 데이터 모델 변경이라 가장 위험합니다. **반드시 staging에서 prod 데이터 dump로 dry-run 후 진행하세요.**

---

## 의존성

- 선행 PR: PR-1 (용어 헬퍼)
- 후속 PR: PR-4 (시장 페이지가 이 모델 사용)

---

## 범위

### In
- DB 마이그레이션 (3단계: 추가 → 백필 → NOT NULL)
- `Niche` 테이블 신설
- `Brand` 테이블에서 niche-specific 필드 제거 (단, deprecate만, 실제 삭제는 다음 메이저 버전)
- `Niche` CRUD API
- 기존 `Brand` API의 호환성 유지 (deprecation 헤더 추가)
- 자동 마이그레이션: 기존 Brand 1개당 Niche 1개 자동 생성, 같은 데이터로 채움

### Out
- 시장 상세 페이지 UI (PR-4)
- Tag 모델 (PR-6)
- 기존 Brand 컬럼 실제 삭제 (다음 메이저)

---

## DB 변경 (Alembic)

### 마이그레이션 파일 1: `add_niche_table.py`

```python
"""add niche table

Revision ID: <auto>
Revises: <previous>
Create Date: ...
"""
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    op.create_table(
        'niche',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('brand_id', sa.Integer(),
                  sa.ForeignKey('brand.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),

        # 시장 정의 (이전 Brand의 reference text)
        sa.Column('market_definition', sa.Text(), nullable=True),
        sa.Column('embedding_threshold', sa.Float(),
                  nullable=False, server_default='0.65'),

        # 우선순위 임계값 (이전 Brand나 admin_collection에 흩어진 것)
        sa.Column('trending_vph_threshold', sa.Integer(),
                  nullable=False, server_default='1000'),
        sa.Column('new_video_hours', sa.Integer(),
                  nullable=False, server_default='6'),
        sa.Column('long_term_score_threshold', sa.Integer(),
                  nullable=False, server_default='70'),

        # 수집 깊이 정책 (이전 Brand에서 옮김)
        sa.Column('collection_depth',
                  sa.Enum('fast', 'standard', 'deep', 'max',
                          name='collection_depth'),
                  nullable=False, server_default='standard'),
        sa.Column('keyword_variation_count', sa.Integer(),
                  nullable=False, server_default='5'),
        sa.Column('preset_per_video_limit', sa.Integer(),
                  nullable=False, server_default='1'),

        # 상태
        sa.Column('state',
                  sa.Enum('active', 'paused', 'archived', name='niche_state'),
                  nullable=False, server_default='active'),

        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )

    op.create_index('ix_niche_brand_state',
                    'niche', ['brand_id', 'state'])

    # 기존 Keyword/Campaign/Video 테이블에 niche_id nullable로 추가
    op.add_column('keyword',
        sa.Column('niche_id', sa.Integer(),
                  sa.ForeignKey('niche.id', ondelete='SET NULL'),
                  nullable=True, index=True))
    op.add_column('campaign',
        sa.Column('niche_id', sa.Integer(),
                  sa.ForeignKey('niche.id', ondelete='SET NULL'),
                  nullable=True, index=True))
    op.add_column('video',
        sa.Column('niche_id', sa.Integer(),
                  sa.ForeignKey('niche.id', ondelete='SET NULL'),
                  nullable=True, index=True))


def downgrade() -> None:
    op.drop_column('video', 'niche_id')
    op.drop_column('campaign', 'niche_id')
    op.drop_column('keyword', 'niche_id')
    op.drop_index('ix_niche_brand_state', table_name='niche')
    op.drop_table('niche')
    op.execute('DROP TYPE niche_state')
    op.execute('DROP TYPE collection_depth')
```

### 마이그레이션 파일 2: `backfill_niche_from_brand.py`

```python
"""backfill niche from brand 1:1

각 Brand에 default Niche 하나씩 생성하고 기존 Keyword/Campaign/Video를
연결한다. 이 마이그레이션 이후 Brand의 niche-specific 필드는 deprecated.
"""
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    # 1. 모든 Brand에 default Niche 1개씩 생성
    op.execute("""
        INSERT INTO niche (
            brand_id, name, description,
            market_definition, embedding_threshold,
            trending_vph_threshold, new_video_hours, long_term_score_threshold,
            collection_depth, keyword_variation_count, preset_per_video_limit,
            state, created_at, updated_at
        )
        SELECT
            b.id,
            COALESCE(b.name, '기본 시장') AS name,
            '자동 마이그레이션됨' AS description,
            b.embedding_reference_text,
            COALESCE(b.embedding_threshold, 0.65),
            COALESCE(b.trending_vph_threshold, 1000),
            COALESCE(b.new_video_hours, 6),
            COALESCE(b.long_term_score_threshold, 70),
            COALESCE(b.collection_depth, 'standard'),
            COALESCE(b.keyword_variation_count, 5),
            COALESCE(b.preset_per_video_limit, 1),
            'active',
            NOW(), NOW()
        FROM brand b
        WHERE NOT EXISTS (
            SELECT 1 FROM niche n WHERE n.brand_id = b.id
        );
    """)

    # 2. 각 Brand의 default Niche로 Keyword 연결
    op.execute("""
        UPDATE keyword k
        SET niche_id = (
            SELECT n.id FROM niche n
            WHERE n.brand_id = k.brand_id
            ORDER BY n.id ASC LIMIT 1
        )
        WHERE k.niche_id IS NULL AND k.brand_id IS NOT NULL;
    """)

    # 3. Campaign 연결
    op.execute("""
        UPDATE campaign c
        SET niche_id = (
            SELECT n.id FROM niche n
            WHERE n.brand_id = c.brand_id
            ORDER BY n.id ASC LIMIT 1
        )
        WHERE c.niche_id IS NULL AND c.brand_id IS NOT NULL;
    """)

    # 4. Video는 brand_id 직접 연결이 있으면 동일하게
    op.execute("""
        UPDATE video v
        SET niche_id = (
            SELECT n.id FROM niche n
            WHERE n.brand_id = v.brand_id
            ORDER BY n.id ASC LIMIT 1
        )
        WHERE v.niche_id IS NULL AND v.brand_id IS NOT NULL;
    """)


def downgrade() -> None:
    # 백필을 되돌릴 필요 없음 (FK는 nullable이라 데이터만 NULL로)
    op.execute("UPDATE keyword SET niche_id = NULL")
    op.execute("UPDATE campaign SET niche_id = NULL")
    op.execute("UPDATE video SET niche_id = NULL")
    op.execute("DELETE FROM niche")
```

### 마이그레이션 파일 3: `enforce_niche_not_null.py`

```python
"""enforce niche_id NOT NULL on keyword/campaign

이 마이그레이션은 백필이 100% 완료된 후에만 실행. 별도 PR이나
별도 배포로 분리 권장.

⚠ 주의: 이 마이그레이션은 PR-3에 포함하지 않고, PR-4 머지 후 안정성 확인되면
별도 마이그레이션으로 실행. 운영 중 데이터에서 모든 row가 niche_id 가졌는지
SELECT COUNT(*) WHERE niche_id IS NULL = 0 확인 필수.
"""
def upgrade() -> None:
    # SELECT 검증 후 실행
    conn = op.get_bind()
    null_kw = conn.execute(sa.text(
        "SELECT COUNT(*) FROM keyword WHERE niche_id IS NULL"
    )).scalar()
    null_cp = conn.execute(sa.text(
        "SELECT COUNT(*) FROM campaign WHERE niche_id IS NULL"
    )).scalar()
    if null_kw > 0 or null_cp > 0:
        raise Exception(
            f"niche_id NULL 데이터 있음: keyword={null_kw}, campaign={null_cp}. "
            "백필 먼저 완료해야 함."
        )

    op.alter_column('keyword', 'niche_id', nullable=False)
    op.alter_column('campaign', 'niche_id', nullable=False)
    # video는 niche_id가 reclassify 중에 잠시 NULL일 수 있어서 NOT NULL 안 걸음

def downgrade() -> None:
    op.alter_column('keyword', 'niche_id', nullable=True)
    op.alter_column('campaign', 'niche_id', nullable=True)
```

### Brand 컬럼 deprecate (이번 PR에서 제거하지 않음)

다음 컬럼들은 Niche로 이전됐지만 Brand에 남겨둡니다 (다음 메이저에서 삭제):
- `embedding_reference_text`
- `embedding_threshold`
- `trending_vph_threshold`
- `new_video_hours`
- `long_term_score_threshold`
- `collection_depth`
- `keyword_variation_count`
- `preset_per_video_limit`

각 컬럼에 주석으로 `# DEPRECATED: use Niche.{column}` 표시하고, 코드에서 더 이상 읽지 않습니다.

---

## 백엔드 변경

### 1. SQLAlchemy 모델 추가

`hydra/db/models.py`:

```python
class Niche(Base):
    __tablename__ = 'niche'

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey('brand.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    market_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_threshold: Mapped[float] = mapped_column(default=0.65)

    trending_vph_threshold: Mapped[int] = mapped_column(default=1000)
    new_video_hours: Mapped[int] = mapped_column(default=6)
    long_term_score_threshold: Mapped[int] = mapped_column(default=70)

    collection_depth: Mapped[CollectionDepth] = mapped_column(
        Enum(CollectionDepth), default=CollectionDepth.standard)
    keyword_variation_count: Mapped[int] = mapped_column(default=5)
    preset_per_video_limit: Mapped[int] = mapped_column(default=1)

    state: Mapped[NicheState] = mapped_column(
        Enum(NicheState), default=NicheState.active)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now())

    brand: Mapped["Brand"] = relationship(back_populates="niches")
    keywords: Mapped[list["Keyword"]] = relationship(back_populates="niche")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="niche")


class Brand(Base):
    # ... 기존 그대로 ...
    niches: Mapped[list["Niche"]] = relationship(
        back_populates="brand", cascade="all, delete-orphan")


class Keyword(Base):
    # ... 기존 그대로 ...
    niche_id: Mapped[int | None] = mapped_column(
        ForeignKey('niche.id', ondelete='SET NULL'), nullable=True, index=True)
    niche: Mapped["Niche | None"] = relationship(back_populates="keywords")


# Campaign, Video도 동일하게 niche_id 추가
```

### 2. 새 라우트: `hydra/web/routes/niches.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/niches/api", tags=["niches"])


class NicheCreate(BaseModel):
    brand_id: int
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    market_definition: str | None = None
    embedding_threshold: float = Field(0.65, ge=0, le=1)
    collection_depth: CollectionDepth = CollectionDepth.standard
    keyword_variation_count: int = Field(5, ge=0, le=50)
    preset_per_video_limit: int = Field(1, ge=1, le=10)


class NicheUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    market_definition: str | None = None
    embedding_threshold: float | None = Field(None, ge=0, le=1)
    trending_vph_threshold: int | None = Field(None, ge=0)
    new_video_hours: int | None = Field(None, ge=1, le=72)
    long_term_score_threshold: int | None = Field(None, ge=0, le=100)
    collection_depth: CollectionDepth | None = None
    keyword_variation_count: int | None = Field(None, ge=0, le=50)
    preset_per_video_limit: int | None = Field(None, ge=1, le=10)
    state: NicheState | None = None


class NicheResponse(BaseModel):
    id: int
    brand_id: int
    name: str
    description: str | None
    market_definition: str | None
    embedding_threshold: float
    trending_vph_threshold: int
    new_video_hours: int
    long_term_score_threshold: int
    collection_depth: CollectionDepth
    keyword_variation_count: int
    preset_per_video_limit: int
    state: NicheState
    keyword_count: int
    campaign_count: int
    video_pool_size: int
    created_at: datetime
    updated_at: datetime


@router.get("/list")
async def list_niches(brand_id: int | None = None,
                       state: NicheState | None = None,
                       ...) -> list[NicheResponse]: ...

@router.get("/{niche_id}")
async def get_niche(niche_id: int, ...) -> NicheResponse: ...

@router.post("/create")
async def create_niche(payload: NicheCreate, ...) -> NicheResponse: ...

@router.patch("/{niche_id}")
async def update_niche(niche_id: int, payload: NicheUpdate, ...) -> NicheResponse: ...

@router.delete("/{niche_id}")
async def delete_niche(niche_id: int, ...) -> dict: ...
```

### 3. 기존 Brand API 호환성 유지

기존 `/brands/api/list`, `/brands/api/{id}` 응답에 `niches` 배열 추가:

```python
class BrandResponse(BaseModel):
    # ... 기존 필드 ...
    niches: list[NicheSummary] = []   # 신규 필드
    default_niche_id: int | None = None  # 마이그레이션으로 생성된 첫 niche

class NicheSummary(BaseModel):
    id: int
    name: str
    state: NicheState
    keyword_count: int
    campaign_count: int
```

기존 Brand의 niche-specific 필드는 응답에 포함하되 deprecation 경고 헤더 추가:

```python
@router.get("/list")
async def list_brands(response: Response, ...):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 00:00:00 GMT"
    response.headers["Link"] = '</niches/api/list>; rel="successor-version"'
    ...
```

### 4. 기존 서비스 코드 변경

수집·분류·캠페인 파이프라인 코드가 `Brand.embedding_threshold` 등을 참조하던 곳을 `Niche.embedding_threshold`로 교체:

영향 받는 파일:
- `hydra/services/video_classifier.py` — embedding 점수 매기는 곳
- `hydra/services/video_filter.py` — hard block + 시장 정의
- `hydra/services/video_pipeline.py` — 분류 결과 적용
- `hydra/services/smart_video_collector.py` — 수집 깊이
- `hydra/services/campaign_service.py` — 캠페인 매칭

각 파일에서:
1. Brand에서 읽던 필드를 Niche에서 읽도록 변경
2. Niche를 못 찾으면 Brand의 default_niche로 fallback (마이그레이션 안전망)
3. 변경된 곳에 `# Migrated from Brand.{field} -> Niche.{field}` 주석

### 5. 글로벌 상태 (`YoutubeVideoGlobalState`) 영향

기존엔 영상이 여러 Brand에 매칭되는 시나리오를 처리. 이제 여러 Niche에 매칭. 로직은 변경 없음 (이미 다중 매칭 처리하던 구조). 단, 충돌 카운트 집계할 때 niche 단위로 group by.

---

## 프론트엔드 변경

이번 PR은 백엔드 위주. 프론트엔드는 **호환성 유지**만:

### 1. API 타입 정의 추가

`frontend/src/types/niche.ts`:

```ts
import { z } from 'zod'

export const CollectionDepthEnum = z.enum(['fast', 'standard', 'deep', 'max'])
export const NicheStateEnum = z.enum(['active', 'paused', 'archived'])

export const NicheSchema = z.object({
  id: z.number(),
  brandId: z.number(),
  name: z.string(),
  description: z.string().nullable(),
  marketDefinition: z.string().nullable(),
  embeddingThreshold: z.number(),
  trendingVphThreshold: z.number(),
  newVideoHours: z.number(),
  longTermScoreThreshold: z.number(),
  collectionDepth: CollectionDepthEnum,
  keywordVariationCount: z.number(),
  presetPerVideoLimit: z.number(),
  state: NicheStateEnum,
  keywordCount: z.number(),
  campaignCount: z.number(),
  videoPoolSize: z.number(),
  createdAt: z.string(),
  updatedAt: z.string(),
})

export type Niche = z.infer<typeof NicheSchema>
```

(서버는 snake_case지만 fetch wrapper에서 camelCase 변환 — 기존 패턴 유지)

### 2. TanStack Query hooks

`frontend/src/lib/queries.ts`에 추가:

```ts
export function useNiches(brandId?: number) {
  return useQuery({
    queryKey: ['niches', brandId],
    queryFn: () => api.get(`/niches/api/list`, { brand_id: brandId })
      .then(r => r.data.map(parseNiche)),
  })
}

export function useNiche(nicheId: number) { ... }
export function useCreateNiche() { ... }
export function useUpdateNiche() { ... }
```

### 3. 기존 브랜드 페이지 — 변경 최소

기존 브랜드 카드에 "시장 N개" 배지 추가. 클릭 동작 변경 없음 (PR-4에서 변경).

```tsx
// frontend/src/routes/brands/index.tsx
<Card>
  <h3>{brand.name}</h3>
  <p>{brand.category}</p>
  <Badge>{brand.niches.length}개 시장</Badge>  {/* 신규 */}
</Card>
```

---

## 마이그레이션 절차 (운영 중 시스템)

**반드시 이 순서로**:

### 1단계: Staging 검증
```bash
# 1. prod DB dump
pg_dump -h prod-host -U hydra hydra > prod-dump.sql

# 2. staging에 복원
psql -h staging-host -U hydra hydra_staging < prod-dump.sql

# 3. staging에서 마이그레이션 실행
cd /path/to/hydra-staging
alembic upgrade head

# 4. 검증 쿼리
SELECT
    (SELECT COUNT(*) FROM brand) AS brand_cnt,
    (SELECT COUNT(*) FROM niche) AS niche_cnt,
    (SELECT COUNT(*) FROM keyword WHERE niche_id IS NULL) AS keyword_orphan,
    (SELECT COUNT(*) FROM campaign WHERE niche_id IS NULL) AS campaign_orphan;
# brand_cnt == niche_cnt 이어야 하고 orphan은 0이어야 함

# 5. 롤백 테스트
alembic downgrade -2
# 다시 동일하게 작동하는지 확인
alembic upgrade head
```

### 2단계: Prod 배포
```bash
# 1. 백업 스냅샷
ssh prod "pg_dump -h localhost -U hydra hydra > /backup/pre-niche-$(date +%F).sql"

# 2. 코드 배포 (자동 git pull로 60초 내)
git push origin main

# 3. 마이그레이션 실행 (수동)
ssh prod "cd /opt/hydra && alembic upgrade head"

# 4. 헬스체크
curl https://hydra-prod.duckdns.org/api/health
curl https://hydra-prod.duckdns.org/niches/api/list

# 5. 자동 캠페인 분배 정상 작동 확인 (5분 대기 후 작업 큐 확인)
```

### 3단계: 모니터링 (24시간)
- 텔레그램 알림 모니터링
- 작업 큐 정상 동작 확인
- 에러 로그 (`/var/log/hydra/server.log`) 확인
- 24h 동안 이상 없으면 PR-4로 진행

### 4단계: NOT NULL 강제 (별도 배포)
- PR-3 머지 후 1주 안정 운영 확인되면
- 마이그레이션 파일 3 (`enforce_niche_not_null.py`) 별도 실행

---

## 엣지 케이스

- 백필 중 새 Brand가 생성되면? → 백필 후 niche가 안 생긴 Brand 있을 수 있음. `enforce_niche_not_null` 실행 전에 한 번 더 백필 쿼리 돌리는 가드 필요.
- Brand 삭제 시 Niche 처리 → ON DELETE CASCADE로 함께 삭제. 단, Niche에 캠페인 진행 중이면 Brand 삭제 막아야 (서비스 레이어에서 사전 검증).
- Niche를 archived로 두면 → 신규 task 생성 안 함. 진행 중 task는 그대로 완료시킴.
- 자동 마이그레이션으로 생성된 Niche의 이름이 Brand 이름과 동일 → 운영자가 PR-4 이후 직접 의미 있는 이름으로 수정 가능.

---

## 테스트

### 백엔드
- `tests/test_niche_crud.py`: 기본 CRUD + state 전환
- `tests/test_brand_niche_relationship.py`: Brand 삭제 시 Niche cascade
- `tests/test_migration.py`: Alembic upgrade/downgrade 양방향 (SQLite 메모리 DB)
- 백필 마이그레이션 SQL을 fixture로 검증 (가짜 Brand 3개 → Niche 3개 생성, Keyword/Campaign FK 정확)

### 프론트엔드
- 기존 brands 페이지 정상 표시 확인 (니치 배지 보임)
- 기존 모든 페이지 regression 확인 (PR-4 전이라 새 페이지는 없음)

### 수동 검증 (staging)
- prod 데이터 dump를 staging에 올린 후 마이그레이션 실행
- 자동 캠페인 분배 5분 돌려보고 정상 작동
- Niche 직접 생성/수정/삭제 → Keyword/Campaign 연결 정확

---

## 완료 정의

- [ ] Alembic 마이그레이션 파일 1, 2 작성 + 테스트
- [ ] 마이그레이션 파일 3은 별도 PR로 분리 (이번엔 머지 안 함)
- [ ] `Niche` 모델 추가됨
- [ ] Niche CRUD API 작동
- [ ] 기존 Brand API에 `niches` 배열 포함됨, deprecation 헤더 적용
- [ ] 수집/분류/캠페인 서비스 코드가 Niche에서 읽도록 변경 + Brand fallback
- [ ] 백엔드 테스트 통과
- [ ] **Staging에서 prod data dump로 dry-run 성공**
- [ ] 백업 스크립트 + 롤백 절차 문서화 (이 문서의 §마이그레이션 절차)
- [ ] Prod 배포 후 24h 안정 운영 확인
- [ ] PR 설명에 마이그레이션 검증 쿼리 결과 첨부

---

## 작업 순서

1. SQLAlchemy 모델 작성
2. Alembic 마이그레이션 1 (스키마)
3. Alembic 마이그레이션 2 (백필) — SQL 직접 작성, ORM 안 씀
4. 단위 테스트로 마이그레이션 양방향 검증
5. Niche CRUD API 작성 + 테스트
6. 기존 서비스 코드 변경 (video_classifier 등) + regression 테스트
7. 기존 Brand API 호환성 + deprecation 헤더
8. 프론트엔드 타입/쿼리 hook 추가
9. **Staging dry-run** (prod dump 사용)
10. PR 리뷰 + prod 배포
11. 24h 모니터링

예상 작업량: 2주.

---

## 위험 평가

| 위험 | 수준 | 완화 |
|---|---|---|
| 마이그레이션 실패로 데이터 손상 | **높음** | 백업 + staging dry-run + 양방향 alembic 테스트 |
| 기존 API 클라이언트 깨짐 | 중간 | deprecation 헤더만, 응답 구조 호환 유지 |
| 자동 캠페인 분배 멈춤 | 중간 | Brand fallback 로직 + 24h 모니터링 |
| niche_id NULL인 row 남음 | 낮음 | enforce NOT NULL 별도 PR로 분리, 백필 검증 쿼리 |
| 운영 중 새 Brand 생성 시 niche 누락 | 낮음 | Brand 생성 hook에 default Niche 자동 생성 추가 |
