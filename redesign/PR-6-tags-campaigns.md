# PR-6 — 자유 태그 + 캠페인 통합 보기

## 목표

사용자 정의 태그 시스템 도입. Niche/Campaign에 임의의 태그를 붙여 차원 분류 가능. 캠페인 통합 보기에서 태그로 필터링하고 비교.

이 PR은 SaaS 멀티테넌시·다차원 분석의 마지막 퍼즐입니다.

---

## 의존성

- 선행 PR: PR-1 (용어), PR-3 (Niche), PR-4 (시장 페이지)
- 후속 PR: 없음

---

## 범위

### In
- `Tag` 테이블 + N:M 관계 (Niche, Campaign)
- 태그 CRUD API
- 시장 페이지 / 캠페인 카드에 태그 UI
- `/campaigns` 캠페인 통합 보기 페이지 (태그 필터링)

### Out
- 영상에 태그 (이번 PR엔 niche/campaign만)
- 태그 자동 추천 (수동 입력만)
- 태그 색상 커스터마이즈 (자동 hash 색상으로 시작)

---

## DB 변경

```python
"""add tag tables"""

def upgrade() -> None:
    op.create_table(
        'tag',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('namespace', sa.String(60), nullable=False, index=True),
        # ex: "market", "season", "angle" — 사용자가 임의 정의
        sa.Column('value', sa.String(120), nullable=False),
        # ex: "한국", "봄", "의학신뢰"
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('namespace', 'value', name='uq_tag_ns_value'),
    )

    op.create_table(
        'niche_tag',
        sa.Column('niche_id', sa.Integer(),
                  sa.ForeignKey('niche.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('tag_id', sa.Integer(),
                  sa.ForeignKey('tag.id', ondelete='CASCADE'),
                  primary_key=True),
    )

    op.create_table(
        'campaign_tag',
        sa.Column('campaign_id', sa.Integer(),
                  sa.ForeignKey('campaign.id', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('tag_id', sa.Integer(),
                  sa.ForeignKey('tag.id', ondelete='CASCADE'),
                  primary_key=True),
    )

    op.create_index('ix_niche_tag_tag', 'niche_tag', ['tag_id'])
    op.create_index('ix_campaign_tag_tag', 'campaign_tag', ['tag_id'])

def downgrade() -> None:
    op.drop_index('ix_campaign_tag_tag', table_name='campaign_tag')
    op.drop_index('ix_niche_tag_tag', table_name='niche_tag')
    op.drop_table('campaign_tag')
    op.drop_table('niche_tag')
    op.drop_table('tag')
```

태그는 운영 중인 시스템에 영향 없음. 새 테이블만 추가, 기존 데이터 변경 없음.

---

## 백엔드 변경

### 1. SQLAlchemy 모델

```python
class Tag(Base):
    __tablename__ = 'tag'
    id: Mapped[int] = mapped_column(primary_key=True)
    namespace: Mapped[str] = mapped_column(String(60), index=True)
    value: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint('namespace', 'value', name='uq_tag_ns_value'),
    )

    niches: Mapped[list["Niche"]] = relationship(
        secondary="niche_tag", back_populates="tags")
    campaigns: Mapped[list["Campaign"]] = relationship(
        secondary="campaign_tag", back_populates="tags")


class Niche(Base):
    # ... 기존 ...
    tags: Mapped[list["Tag"]] = relationship(
        secondary="niche_tag", back_populates="niches")


class Campaign(Base):
    # ... 기존 ...
    tags: Mapped[list["Tag"]] = relationship(
        secondary="campaign_tag", back_populates="campaigns")
```

### 2. 태그 CRUD API

```python
# hydra/web/routes/tags.py

@router.get("/list")
async def list_tags(
    namespace: str | None = None,
) -> list[TagResponse]:
    """
    Returns all tags. Filter by namespace optional.
    Useful for autocomplete.
    """

@router.post("/create")
async def create_tag(payload: TagCreate) -> TagResponse:
    """
    Idempotent: if (namespace, value) exists, return existing.
    """

@router.delete("/{tag_id}")
async def delete_tag(tag_id: int) -> dict:
    """
    Delete tag and all associations. Confirm-required on UI side.
    """
```

### 3. 태그 연결 API

```python
# Niche에 태그 추가
@router.post("/niches/api/{niche_id}/tags")
async def attach_tag_to_niche(
    niche_id: int,
    payload: TagAttachRequest  # tag_id 또는 (namespace, value) 새로 만들기
) -> NicheResponse:
    ...

@router.delete("/niches/api/{niche_id}/tags/{tag_id}")
async def detach_tag_from_niche(...) -> NicheResponse: ...

# Campaign에 동일
@router.post("/campaigns/api/{cp_id}/tags")
@router.delete("/campaigns/api/{cp_id}/tags/{tag_id}")
```

### 4. 캠페인 통합 검색 API

```python
@router.get("/campaigns/api/search")
async def search_campaigns(
    q: str | None = None,
    state: CampaignState | None = None,
    niche_ids: list[int] = Query([]),
    tag_ids: list[int] = Query([]),  # AND 조건
    sort: Literal["recent", "performance", "comments"] = "recent",
    page: int = 1,
    page_size: int = 50,
) -> CampaignSearchResponse:
    ...
```

여러 태그 ID 입력 시 AND 검색 (모든 태그 가진 캠페인만).

### 5. 기존 응답에 태그 포함

```python
class NicheResponse(BaseModel):
    # ... 기존 ...
    tags: list[TagSummary] = []

class CampaignResponse(BaseModel):
    # ... 기존 ...
    tags: list[TagSummary] = []
```

### 6. namespace 자동 등록

운영자가 새 namespace를 처음 입력하면 자동 등록. 별도 namespace 관리 테이블 없음. 태그 검색에서 distinct namespace로 추출.

```python
@router.get("/tags/api/namespaces")
async def list_namespaces() -> list[str]:
    """SELECT DISTINCT namespace FROM tag ORDER BY namespace"""
```

---

## 프론트엔드 변경

### 1. TagInput 컴포넌트 (재사용)

```tsx
// frontend/src/components/shared/TagInput.tsx

type Props = {
  value: Tag[]
  onChange: (tags: Tag[]) => void
  placeholder?: string
}

export function TagInput({ value, onChange, placeholder }: Props) {
  // namespace:value 형식으로 입력
  // 예: "시장:한국" enter → Tag { namespace: "시장", value: "한국" }
  // namespace 자동완성 (기존 namespaces fetch)
  // value 자동완성 (선택된 namespace 내)
  // 칩 형태로 표시, x로 제거
}
```

태그 칩 색상은 namespace의 hash로 자동 할당:
- "시장" → 파랑 ramp
- "시즌" → 초록 ramp
- "각도" → 자주 ramp
- ...

```tsx
function namespaceColor(ns: string): string {
  const hash = simpleHash(ns) % 6
  return ['blue', 'green', 'purple', 'amber', 'teal', 'coral'][hash]
}
```

### 2. 시장 페이지 — 태그 표시

시장 layout 헤더에 태그 그룹 추가:

```
┌──────────────────────────────────────────────────────────┐
│ 모렉신 / 탈모 30대 남성                                   │
│ [시장: 한국] [시즌: 봄] [각도: 의학신뢰] [+ 태그]         │
│                                                          │
│ [영상 풀 1247] [진행 캠페인 3] ...                       │
└──────────────────────────────────────────────────────────┘
```

"+ 태그" 클릭 → TagInput 열림.

태그 클릭 → 캠페인 통합 보기로 이동 + 해당 태그 필터 적용.

### 3. 캠페인 통합 보기 페이지 (`/campaigns`)

기존 캠페인 페이지를 통합 보기로 재구성:

```
┌──────────────────────────────────────────────────────────┐
│ 캠페인 통합                                               │
│ 모든 시장의 캠페인을 한눈에 비교                          │
├──────────────────────────────────────────────────────────┤
│ [검색...] [상태 ▾] [시장 ▾]                              │
│ 태그 필터: [시장:한국 ×] [+ 추가]                        │
├──────────────────────────────────────────────────────────┤
│ [전체 캠페인 24] [진행중 8] [완료 16] [평균 성공률 91%]   │
├──────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 신제품 인지도 푸시                                  │ │
│ │ 모렉신 / 탈모 30대 남성 · [시장:한국][각도:의학신뢰]│ │
│ │ 진행중 68% · 댓글 342 · 성공률 96%                 │ │
│ │ [▶ 상세] [⏸]                                        │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                          │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 의료 신뢰도 빌드업                                  │ │
│ │ 모렉신 / 탈모 30대 남성 · [시장:한국][각도:가성비]  │ │
│ │ 진행중 34% · 댓글 89 · 성공률 87%                  │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                          │
│ ...                                                      │
├──────────────────────────────────────────────────────────┤
│ A/B 비교 (선택된 2개)                                    │
│ [신제품 인지도 푸시 vs 의료 신뢰도 빌드업]               │
│ [차트: 두 캠페인의 일별 댓글, 성공률, 고스트율 추이]      │
└──────────────────────────────────────────────────────────┘
```

#### A/B 비교 기능

- 캠페인 카드에 체크박스
- 2개 선택하면 하단에 비교 차트 표시
- 비교 차원: 일별 댓글 수, 성공률, 고스트율, 베스트 진입률
- 3개 이상 선택하면 차트 그대로 (max 4개), 5개째부터 첫 번째 deselect

### 4. 캠페인 태그 편집

캠페인 카드 hover 시 "태그 편집" 메뉴 → 모달 → TagInput.

또는 시장 페이지 캠페인 탭에서 캠페인 클릭 → 상세 모달에서 태그 편집.

### 5. 사이드바 활성화

PR-4에서 placeholder만 만든 `/campaigns` 메뉴를 이번 PR에서 활성화.

---

## UX 가이드 — 태그 운영

운영자에게 태그 사용법 안내:

```
태그는 자유 분류 시스템입니다.
namespace:value 형식으로 입력합니다.

자주 쓰는 namespace 예시:
- 시장: 한국, 미국, 일본
- 시즌: 봄, 여름, 가을, 겨울
- 각도: 의학신뢰, 가성비, 자연주의
- 캠페인유형: 런칭, 트렌딩, 상시
- 우선순위: 핵심, 보조

자유롭게 만들고 사용하세요. 비슷한 캠페인을 묶어서 비교 분석하는 데 유용합니다.
```

이 안내는 태그 처음 추가할 때 모달 상단에 표시.

---

## 엣지 케이스

- 같은 namespace에 다른 캐주얼 표기 (`시장`, `Market`, `market`) → 서버는 case-sensitive로 저장. UI에서 자동완성으로 통일 유도.
- 태그 30개 넘게 붙으면 → niche 헤더가 깨지지 않게 max 5개 표시 + "+N개 더" 펼치기
- 태그 삭제 시 어떤 캠페인/시장에 영향 미치는지 → confirm 모달에 "이 태그가 붙은 X개 캠페인, Y개 시장에서 제거됩니다" 표시
- A/B 비교에서 한 캠페인이 archived → 차트에 표시하되 회색 라인

---

## 성능

- 태그 검색은 작은 테이블이라 DB 부하 낮음
- 캠페인 통합 검색은 N+1 쿼리 주의: `selectinload(Campaign.tags)` 사용
- 자동완성은 namespace+prefix 기반 ILIKE — 인덱스 (B-tree on namespace, GIN on value)

---

## 테스트

### 백엔드
- 태그 CRUD: 생성·중복 방지·연결·삭제
- AND 검색: 여러 태그 ID로 정확히 매칭
- cascade: tag 삭제 시 연결 삭제 확인

### 프론트엔드 E2E
- 태그 추가 → 칩 표시 → 시장 헤더 갱신
- 캠페인 통합에서 태그 필터 → 결과 정확
- A/B 비교: 2개 선택 → 차트 렌더 → 1개 해제 → 차트 사라짐

---

## 완료 정의

- [ ] Tag, niche_tag, campaign_tag 테이블 + 마이그레이션
- [ ] 태그 CRUD API + 연결 API
- [ ] 캠페인 통합 검색 API (태그 AND 필터)
- [ ] TagInput 컴포넌트 (시장/캠페인에서 재사용)
- [ ] 시장 페이지 헤더에 태그 표시
- [ ] `/campaigns` 통합 보기 페이지
- [ ] A/B 비교 차트
- [ ] 캠페인 카드에 태그 표시 + 편집
- [ ] E2E 테스트 통과

---

## 작업 순서

1. DB 마이그레이션 + 모델
2. 태그 CRUD API + 테스트
3. 태그 연결 API
4. 캠페인 통합 검색 API
5. TagInput 컴포넌트
6. 시장 페이지 태그 통합
7. 캠페인 통합 보기 페이지
8. A/B 비교 차트

예상 작업량: 2주.

---

## 위험 평가

| 위험 | 수준 | 완화 |
|---|---|---|
| 태그 namespace 난립 | 낮음 | UI에서 자동완성 + 가이드 문구 |
| 캠페인 통합 검색 N+1 | 낮음 | selectinload 적극 사용 |
| 기존 시스템 영향 | 매우 낮음 | 새 테이블만, 기존 변경 없음 |
