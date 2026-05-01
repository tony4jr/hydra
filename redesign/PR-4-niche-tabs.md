# PR-4 — 시장 상세 5탭 페이지 (가장 큰 작업)

> **정리 노트 (PR-4 spec-fix, 2026-05-01)** — 본 작업 시작 전 부정합 정리:
>
> 1. **Sub-PR 개수**: "5개 sub-PR" 표현 → **6개 (PR-4a~f)** 로 통일. 실제 분할 목록과 작업 순서가 6개임.
> 2. **5탭 정식 명칭/순서**: **개요 / 수집 / 메시지 / 캠페인 / 분석** (이 순서). URL suffix 는 개요=없음(default), 나머지=`/collection`, `/messaging`, `/campaigns`, `/analytics`.
> 3. **루트 URL**: `/products/$brandId/niches/$nicheId/...` (단순 `/niches/$nicheId` 아님 — 브레드크럼/Brand 컨텍스트 보존).
> 4. **사이드바 변경 시점**: PR-4a 는 **새 "제품 운영" 메뉴 추가만**, 기존 [브랜드][타겟][캠페인][분석] 메뉴는 **PR-4f (분석 탭) 머지 후 제거** (한동안 병존, 운영자 혼란 최소화 — "위험 평가" 표와 일치).
> 5. **백엔드 API prefix**: PR-3b 가 실제 배포한 prefix 는 `/api/admin/niches`. PR-4 신규 endpoint 는 동일 컨벤션 따라 **`/api/admin/niches/{niche_id}/overview`**, `/collection/flow`, `/keywords`, `/recent-videos`, `/simulate-threshold`, `/messaging`, `/personas`, `/campaigns`, `/analytics` (이전 spec 의 `/niches/api/...` 표기는 deprecated).
> 6. **페르소나 모델**: PR-3a 마이그레이션에서 페르소나 컬럼 흡수 안 함 (Niche 12 비즈니스 컬럼에 없음). PR-4d (메시지 탭) 안에서 별도 마이그레이션 필요 — `niche_personas` join 테이블 또는 `personas.niche_id` FK 추가. 본 PR 범위.
> 7. **자동 백필 Niche 이름 = Brand 이름**: PR-3a 결과 Niche.name 이 Brand.name 동일. PR-4a 제품 목록 트리에서 동일 이름 노출되어 혼란 가능. UX 메모: PR-4a 에서 Niche 이름 옆에 "(default)" 같은 hint 표기 또는 운영자에게 rename 유도 빈 상태 안내.
> 8. **PR-3 후속 마이그레이션**: niche_id NOT NULL 변경, TargetCollectionConfig drop 등은 PR-4 머지 후 안정성 확인되면 (PR-3 spec L266) — 본 PR 범위 X.

## 목표

운영자 멘탈모델의 핵심 페이지. 한 시장(Niche)의 모든 운영을 한 페이지 5탭에서 처리합니다.

기존 [브랜드 폼] + [타겟 페이지] + [캠페인 일부] + [분석 일부]가 이 페이지로 통합됩니다. 정보 흩어짐 문제의 핵심 해결.

이 PR은 가장 큰 작업이라 **탭 단위로 점진적 머지**합니다 (6개 sub-PR — PR-4a~f).

---

## 의존성

- 선행 PR: PR-1 (용어), PR-3 (Niche 모델, PR-3a/b/c 모두 merge 됨)
- 후속 PR: PR-5 (영상 통합 보기에서 이 페이지 링크), PR-6 (태그)

---

## 범위

### In
- 사이드바에 "제품 운영" 그룹 + 4개 메뉴 추가 (제품 목록 / 캠페인 / 영상 / 작업 큐)
- 제품 목록 페이지 (`/products`) — Brand+Niche 트리
- 시장 상세 페이지 (`/products/$brandId/niches/$nicheId/...`) — 5탭
  - 개요 탭
  - 수집 탭 (5단계 깔때기)
  - 메시지 탭
  - 캠페인 탭
  - 분석 탭
- 사이드바 "관리"의 브랜드/타겟/캠페인 메뉴 제거

### Out
- 캠페인 통합 보기 페이지 (PR-6)
- 영상 통합 보기 페이지 (PR-5)
- 자유 태그 (PR-6)
- Onboarding wizard (PR-7)

---

## 라우트 구조

TanStack Router file-based:

```
frontend/src/routes/
├── products/
│   ├── index.tsx                                    # 제품 목록
│   └── $brandId/
│       ├── route.tsx                                # Brand layout (breadcrumb)
│       └── niches/
│           └── $nicheId/
│               ├── route.tsx                        # Niche layout (탭 헤더)
│               ├── index.tsx                        # 개요 탭 (default)
│               ├── collection.tsx                   # 수집 탭
│               ├── messaging.tsx                    # 메시지 탭
│               ├── campaigns.tsx                    # 캠페인 탭
│               └── analytics.tsx                    # 분석 탭
```

URL 예시:
- `/products` — 전체 제품 목록
- `/products/12/niches/34` — 시장 개요 (default)
- `/products/12/niches/34/collection` — 수집 탭
- `/products/12/niches/34/messaging` — 메시지 탭
- ...

브레드크럼: `제품 / 모렉신 / 탈모 30대 남성 [ 개요 | 수집 | ... ]`

---

## 백엔드 변경

각 탭이 사용할 신규/변경 endpoint:

### 1. 시장 개요 (탭 1)
- `GET /api/admin/niches/{niche_id}/overview` (신규)
  ```python
  class NicheOverviewResponse(BaseModel):
      niche: NicheResponse
      stats: dict  # video_pool_size, active_campaigns, comments_7d, ghost_rate
      active_campaigns: list[CampaignSummary]  # max 3
      recent_alerts: list[Alert]  # 최근 24h 병목/이상
  ```

### 2. 수집 탭 (탭 2)

5단계 깔때기에 필요한 데이터:

- `GET /api/admin/niches/{niche_id}/collection/flow` (신규)
  - PR-2의 `/api/admin/pipeline/flow`와 동일 구조, niche 단위
  - `?window_hours=24` 지원

- `GET /api/admin/niches/{niche_id}/keywords` (신규, 기존 keywords API 재구성)
  ```python
  class KeywordWithMetrics(BaseModel):
      id: int
      text: str
      kind: Literal["positive", "negative"]
      polling: Literal["5min", "30min", "daily"]
      variations: list[str]
      variation_enabled: dict[str, bool]  # 각 변형 on/off
      metrics_7d: dict  # discovered, passed_market, pass_rate
  ```

- `POST /api/admin/niches/{niche_id}/keywords` (신규)
- `PATCH /api/admin/niches/{niche_id}/keywords/{kw_id}` (폴링 변경, 변형 on/off)
- `DELETE /api/admin/niches/{niche_id}/keywords/{kw_id}`

- `GET /api/admin/niches/{niche_id}/recent-videos` (신규)
  ```python
  # 키워드별/시장별 최근 발견 영상 + 통과/탈락 사유
  class RecentVideo(BaseModel):
      video_id: int
      youtube_id: str
      title: str
      channel: str
      view_count: int
      keyword_matched: str | None
      market_fitness: float | None
      result: Literal["passed", "rejected_market", "rejected_negative_keyword",
                       "rejected_hard_block"]
      result_reason: str | None
  ```

- `POST /api/admin/niches/{niche_id}/simulate-threshold` (신규, 시장 정의 시뮬레이션)
  ```python
  class ThresholdSimulationRequest(BaseModel):
      market_definition: str | None = None  # 변경 시 미리보기
      embedding_threshold: float

  class ThresholdSimulationResponse(BaseModel):
      passed: int
      rejected: int
      borderline: list[RecentVideo]  # 임계값 ±0.05 영상들
  ```

  주의: 이 API는 새 임계값으로 즉시 영향 주지 않음. 미리보기만. 실제 적용은 `PATCH /api/admin/niches/{niche_id}` 호출.

### 3. 메시지 탭 (탭 3)
- `GET /api/admin/niches/{niche_id}/messaging` (신규)
  ```python
  class NicheMessaging(BaseModel):
      core_message: str  # 핵심 메시지 (Brand에서 niche로 옮김)
      tone_guide: str | None
      target_audience: str | None
      mention_rules: str | None
      promotional_keywords: list[str]
      personas: list[Persona]   # Niche에 할당된 페르소나 슬롯
      preset_selection: list[str]   # 활성화된 프리셋 키
  ```
- `PATCH /api/admin/niches/{niche_id}/messaging`
- `POST /api/admin/niches/{niche_id}/personas` — 페르소나 추가 (max 10 슬롯)
- `DELETE /api/admin/niches/{niche_id}/personas/{persona_id}`

### 4. 캠페인 탭 (탭 4)
- `GET /api/admin/niches/{niche_id}/campaigns` (신규)
  - 기존 `/campaigns/api/list?niche_id=`와 동일하지만 niche 컨텍스트 강제
- `POST /api/admin/niches/{niche_id}/campaigns` (신규, 단순화된 wizard 백엔드)
  - 기존 4-step wizard 대신 2-step:
    - step 1: 프리셋 + 영상 비율
    - step 2: 기간 + 목표 영상 수
  - 메시지·페르소나는 niche에서 자동 inherit
- `POST /campaigns/api/{cp_id}/pause` (백엔드 연결 — 기존 UI는 있는데 작동 안 함)
- `POST /campaigns/api/{cp_id}/resume` (백엔드 연결)

### 5. 분석 탭 (탭 5)
- `GET /api/admin/niches/{niche_id}/analytics` (신규)
  ```python
  class NicheAnalytics(BaseModel):
      window_days: int  # 7 / 30 / all
      daily_workload: list[dict]  # [{ date, comments, likes }]
      campaign_performance: list[dict]
      persona_performance: list[dict]
      preset_performance: list[dict]
      hourly_pattern: list[dict]
      ranking_summary: dict  # 베스트 진입률
  ```

  데이터는 기존 `/api/analytics/*` (memory 기반) 통합 + niche 필터링.

---

## 프론트엔드 변경

### 1. 사이드바 메뉴 재구성

> ⚠️ **분할 시점 주의 (정리 노트 #4 참조)**: PR-4a 는 새 "제품 운영" 그룹과 메뉴를 **추가만** 한다. 기존 [브랜드][타겟][캠페인][분석] 메뉴 **제거는 PR-4f (분석 탭) 머지 시점에 일괄**. PR-4a~e 동안은 두 진입점이 병존 — 운영자 혼란 최소화 + 회귀 안전.

`frontend/src/components/sidebar.tsx`:

```tsx
const menu = {
  home: [
    { path: '/', label: t.pageHome, icon: 'home' },
  ],
  operation: [
    { path: '/products', label: t.pageProducts, icon: 'package' },
    { path: '/campaigns', label: t.pageCampaigns, icon: 'megaphone' },  // PR-6에서 활성화
    { path: '/videos', label: t.pageVideos, icon: 'video' },              // PR-5에서 활성화
    { path: '/tasks', label: t.pageTasks, icon: 'list' },
  ],
  infra: [
    { path: '/infra/accounts', label: t.pageAccounts, icon: 'users' },
    { path: '/infra/workers', label: t.pageWorkers, icon: 'monitor' },
    { path: '/infra/avatars', label: t.pageAvatars, icon: 'image' },
    { path: '/infra/settings', label: t.pageSettings, icon: 'settings' },
  ],
}
```

기존 사이드바의 "브랜드", "타겟", "캠페인", "분석", "감사 로그" 메뉴 제거.
- 브랜드/타겟 → `/products` 통합
- 캠페인/분석 → 시장 페이지 탭
- 감사 로그 → 시스템 설정

### 2. 제품 목록 페이지 (`/products`)

```
┌──────────────────────────────────────────────────────────┐
│ 제품                                          [+ 새 제품] │
│ 모든 브랜드와 시장을 한눈에                                │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ▼ 모렉신 (탈모 케어) · 시장 2개                          │
│     ├─ 탈모 30대 남성       1247영상  3캠페인  운영중    │
│     └─ 산후 탈모 시장        320영상  1캠페인  운영중    │
│                              [+ 시장 추가]                │
│                                                          │
│  ▶ 천명연구소 (사주명리) · 시장 1개                        │
│                                                          │
│  ▶ XX 영양제 (건강기능식품) · 시장 0개   [⚠ 시장 없음]  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

- 브랜드는 expandable 트리. 펼치면 niches 보임.
- niche 한 행 클릭 → `/products/$brandId/niches/$nicheId` 로 이동 (개요 탭)
- "+ 새 제품" → Brand 생성 모달 (PR-7에서 wizard로 발전)
- "+ 시장 추가" → Niche 생성 모달
- 시장이 0개인 브랜드엔 amber 배지

### 3. 시장 상세 — 공통 layout (`route.tsx`)

```tsx
// $nicheId/route.tsx
export const Route = createFileRoute('/products/$brandId/niches/$nicheId')({
  component: NicheLayout,
  loader: ({ params }) => queryClient.ensureQueryData(nicheOverviewQuery(params.nicheId)),
})

function NicheLayout() {
  const { nicheId } = Route.useParams()
  const { data: niche } = useNiche(nicheId)

  return (
    <div>
      {/* 브레드크럼 */}
      <Breadcrumb>
        <Link to="/products">제품</Link>
        <Link to={`/products/${niche.brandId}`}>{niche.brand.name}</Link>
        <span>{niche.name}</span>
      </Breadcrumb>

      {/* 시장 헤더 + 4개 stat card */}
      <NicheHeader niche={niche} />

      {/* 탭 네비 */}
      <Tabs>
        <TabLink to="./">개요</TabLink>
        <TabLink to="./collection">수집</TabLink>
        <TabLink to="./messaging">메시지</TabLink>
        <TabLink to="./campaigns">캠페인</TabLink>
        <TabLink to="./analytics">분석</TabLink>
      </Tabs>

      <Outlet />
    </div>
  )
}
```

### 4. 탭 1 — 개요 (`index.tsx`)

```
┌──────────────────────────────────────────────────────────┐
│ [영상 풀 1247] [진행 캠페인 3] [7일 댓글 428] [고스트율 2.1%]│
├──────────────────────────────────────────────────────────┤
│  영상 수집 상태       │  메시지 · 페르소나                │
│  ● 자동 수집 중       │  3개 활성                          │
│  키워드 5개 활성       │  - 30대 직장인 남성 (60%)         │
│  마지막 수집: 12분 전  │  - 헤어케어 입문자 (30%)          │
│  신규 후보: 23개      │  - 의료 전문 관심자 (10%)         │
│                       │                                   │
├──────────────────────────────────────────────────────────┤
│  진행 중 캠페인                          [+ 새 캠페인]    │
│  [신제품 푸시 68%] [신뢰 빌드 34%] [트렌딩 cover 상시]   │
├──────────────────────────────────────────────────────────┤
│  최근 24시간 알림                                         │
│  ⚠ 키워드 "두피케어" 통과율 12% — 시장 정의 검토 권장     │
└──────────────────────────────────────────────────────────┘
```

빠른 진입점:
- 수집 상태 클릭 → 수집 탭
- 메시지 클릭 → 메시지 탭
- 캠페인 카드 클릭 → 캠페인 탭의 해당 캠페인 상세
- 알림 "확인" → 해당 탭으로 이동

### 5. 탭 2 — 수집 (`collection.tsx`) ★ 핵심

이전 대화에서 만든 5단계 깔때기 구조 그대로. CLAUDE.md의 디자인 원칙 5개를 가장 엄격히 적용하는 페이지.

레이아웃 (위에서 아래로):

```
┌──────────────────────────────────────────────────────────┐
│ 최근 24시간 수집 흐름                                     │
│ [142 발견] [128 자동제외 통과] [98 키워드매칭] [42⚠시장적합] [38 풀진입] │
├──────────────────────────────────────────────────────────┤
│ 키워드 (펼침, 메인)                            [자주 만짐]│
│ - 키워드 테이블 (이름·7일발견·통과율·폴링·액션)            │
│ - 행 클릭 → 변형 키워드 + 최근 발견 영상 샘플 펼침        │
│ - 새 키워드 추가 input                                    │
│ - 부정 키워드 칩 그룹                                     │
├──────────────────────────────────────────────────────────┤
│ 시장 정의 (펼침, 메인)                         [가끔 만짐]│
│ - textarea (200자, AI 다듬기 버튼)                        │
│ - 임계값 슬라이더 + 즉시 시뮬레이션 (통과/경계/탈락 카운트)│
│ - 경계선 영상 3-5개 amber 박스                            │
├──────────────────────────────────────────────────────────┤
│ ▸ 우선순위 분류 기준 (접힘)                    [거의 안만짐]│
├──────────────────────────────────────────────────────────┤
│ ▸ 자동 제외 룰 (접힘)                          [정보 표시]│
├──────────────────────────────────────────────────────────┤
│ ▸ 영상 보호 룰 (접힘)                          [정보 표시]│
└──────────────────────────────────────────────────────────┘
```

#### 5-1. KeywordTable 컴포넌트

```tsx
// frontend/src/components/niche/KeywordTable.tsx
export function KeywordTable({ nicheId }: { nicheId: number }) {
  const { data: keywords } = useKeywords(nicheId)
  const updateKeyword = useUpdateKeyword(nicheId)

  // 컬럼: 키워드 / 7일 발견 / 통과율 / 폴링 segment / 액션
  // 폴링 segment 클릭 = 즉시 PATCH (낙관적 업데이트)
  // 통과율 < 30% 일 때 amber 행
  // 행 클릭 = expanded state로 토글 (변형 + 영상 샘플)
}
```

#### 5-2. MarketDefinitionEditor 컴포넌트

```tsx
export function MarketDefinitionEditor({ niche }: { niche: Niche }) {
  const [text, setText] = useState(niche.marketDefinition ?? '')
  const [threshold, setThreshold] = useState(niche.embeddingThreshold)

  // 디바운스 300ms로 simulate API 호출
  const sim = useDebouncedSimulation(niche.id, text, threshold)

  // textarea + 슬라이더 + 시뮬레이션 결과
  // 저장 버튼 (저장 안 하면 미리보기만)
  // "AI 다듬기" 버튼 → /api/admin/niches/$id/refine-definition (PR-7에서 신설, 이 PR에선 placeholder)
}
```

시뮬레이션 동작:
- text 또는 threshold 변경 시 디바운스 300ms 후 `POST /api/admin/niches/{id}/simulate-threshold`
- 응답으로 통과/탈락/경계 카운트 + 경계선 영상 표시
- 저장 전엔 niche의 실제 값에 영향 없음

#### 5-3. CollectionFlowBar (5단계 카운트)

PR-2의 PipelineFlow 컴포넌트를 재사용 (props로 nicheId 전달).

### 6. 탭 3 — 메시지 (`messaging.tsx`)

```
┌──────────────────────────────────────────────────────────┐
│ 핵심 메시지                                               │
│ [textarea — 댓글에 자연스럽게 녹일 셀링 포인트]           │
├──────────────────────────────────────────────────────────┤
│ 톤 가이드                                                 │
│ [textarea — 어떤 어조로 말할지]                          │
├──────────────────────────────────────────────────────────┤
│ 타겟 청중                                                 │
│ [textarea — 댓글이 도달할 사람의 특징]                   │
├──────────────────────────────────────────────────────────┤
│ 페르소나 슬롯 (3 / 10)                       [+ 페르소나]│
│ ┌─────────────────────────┐ ┌─────────────────────────┐ │
│ │ 30대 직장인 남성 60%     │ │ 헤어케어 입문자 30%     │ │
│ │ 서울 거주, IT 종사자     │ │ 20대 후반, 외모 관심     │ │
│ │ [편집] [삭제]            │ │ [편집] [삭제]            │ │
│ └─────────────────────────┘ └─────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│ 사용 프리셋                                               │
│ ☑ 시드 댓글 (A)   ☑ 질문 유도 (B)   ☐ 동조 (C)         │
│ ☑ 비포애프터 (D)  ...                                    │
└──────────────────────────────────────────────────────────┘
```

페르소나 카드는 클릭 시 모달로 편집 (이름, 나이, 직업, 거주지, 말투, 비율 %).

### 7. 탭 4 — 캠페인 (`campaigns.tsx`)

```
┌──────────────────────────────────────────────────────────┐
│ 진행 중 (3)                              [+ 새 캠페인]    │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐     │
│ │ 신제품 푸시  │ │ 신뢰 빌드업  │ │ 트렌딩 cover │     │
│ │ 68% · 12일   │ │ 34% · 25일   │ │ 상시 · 일30개│     │
│ │ ⏸ 일시정지   │ │ ⏸           │ │ ⏸           │     │
│ └──────────────┘ └──────────────┘ └──────────────┘     │
├──────────────────────────────────────────────────────────┤
│ 완료 (8)                                                  │
│ - 5월 신제품 런칭 캠페인  · 1342댓글 · 96% 성공률  ▶보기 │
│ - 4월 트렌딩 헤어케어     · 870댓글  · 91% 성공률  ▶보기 │
│ ...                                                       │
└──────────────────────────────────────────────────────────┘
```

#### 새 캠페인 모달 (단순화된 2-step wizard)

기존 4-step → 2-step:

```
[Step 1/2] 프리셋과 영상 비율
  - 프리셋 선택 (다중)
  - 영상당 세트 수 (1-5)
  - Shorts:롱폼 비율 슬라이더

[Step 2/2] 기간과 목표
  - 시작일 / 종료일 (또는 "상시")
  - 목표 영상 수 (또는 "무제한")
```

메시지·페르소나는 niche에서 자동 사용 (별도 step 없음).

#### pause/resume

기존 UI 버튼은 있는데 백엔드 미연결. 이번 PR에서 연결:
- 클릭 → `POST /campaigns/api/{id}/pause`
- 낙관적 업데이트 + 토스트
- pause 중에도 진행 중 task는 완료, 신규 task만 안 만듦

### 8. 탭 5 — 분석 (`analytics.tsx`)

기존 비어있던 분석 페이지를 시장 컨텍스트로 채움. 차트 컴포넌트는 기존 사용 라이브러리 (Recharts) 그대로:

```
┌──────────────────────────────────────────────────────────┐
│                                          [7일][30일][전체]│
├──────────────────────────────────────────────────────────┤
│ [총 댓글 428] [총 좋아요 1.2k] [작업 영상 87] [고스트율 2.1%]│
├──────────────────────────────────────────────────────────┤
│ 일별 작업량 (bar chart)                                   │
│  [차트]                                                   │
├──────────────────────────────────────────────────────────┤
│ 캠페인별 성과                                             │
│ 캠페인 │ 댓글 │ 좋아요 │ 고스트 │ 성공률                  │
│ ...                                                       │
├──────────────────────────────────────────────────────────┤
│ 페르소나별 성과 │ 프리셋별 성과 │ 시간대별 성과            │
│ [작은 차트 3개 grid]                                      │
└──────────────────────────────────────────────────────────┘
```

데이터 소스: `/api/analytics/comment-snapshots`, `/account-stability`, `/ghost-rate`, `/ranking-summary` 통합 + niche 필터.

---

## 데이터 fetch 전략

각 탭은 자기 데이터만 fetch (탭 전환 시 lazy load). TanStack Query로 캐싱:

```tsx
// 시장 layout이 미리 fetch
useNicheOverview(nicheId)  // 모든 탭 공통

// 탭 진입 시 추가 fetch
useNicheCollection(nicheId) // 수집 탭
useNicheMessaging(nicheId)  // 메시지 탭
useNicheAnalytics(nicheId, window) // 분석 탭
```

stale time:
- overview: 30초
- collection (키워드, 영상): 60초
- messaging: 5분 (자주 안 바뀜)
- campaigns: 30초
- analytics: 5분

---

## 엣지 케이스

- 시장이 archived면 → 모든 탭에 amber 배너 "보관 중인 시장입니다. 신규 작업 안 만들어집니다."
- 시장 정의가 비어있으면 → 수집 탭 시장 정의 카드에 amber 배너 "시장 정의 비어있음 — 의미 분류 작동 안 함"
- 키워드 0개면 → 수집 탭 키워드 카드에 빈 상태 + "+ 첫 키워드 추가" 큰 버튼
- 페르소나 0개면 → 메시지 탭에 "페르소나 없이는 댓글 다양성이 떨어집니다. 추가하세요." 안내
- 임계값 시뮬레이션 API 실패 시 → 슬라이더 옆에 "시뮬레이션 일시 중단" 표시, 슬라이더는 작동
- 시장 삭제 → 진행 중 캠페인 있으면 confirm + 캠페인 취소 안내
- 캠페인 pause/resume 실패 시 → 낙관적 업데이트 롤백 + 에러 토스트

---

## 테스트

### 백엔드
- 각 신규 endpoint: 정상 케이스 + 4xx 케이스 + 권한
- 시뮬레이션 endpoint: 동일 input → 동일 output (deterministic 확인)
- pause/resume: state 전환 정확성

### 프론트엔드 (Playwright E2E)
- `/products` → niche 클릭 → 5탭 전환 모두 동작
- 키워드 추가/삭제/폴링 변경
- 시장 정의 슬라이더 → 시뮬레이션 결과 변화
- 새 캠페인 모달 2-step → 생성 성공
- pause/resume 버튼 동작

### 수동 검증
- prod에서 시장 1개로 모든 흐름 한 번 돌려보기
- 자동 수집 → 분류 → 풀 진입이 새 UI에서 정확히 보이는지

---

## 완료 정의

### 6개 sub-PR로 분할 (PR-4a~f)

각 sub-PR이 독립 머지 가능:
- **PR-4a** — 라우트 구조 + 사이드바 "제품 운영" 신설 + 제품 목록 + 시장 layout (탭 헤더만, 기존 사이드바 메뉴 제거 X)
- **PR-4b** — 개요 탭 (overview API + UI)
- **PR-4c** — 수집 탭 (가장 큰 sub-PR — 5단계 깔때기, 키워드 테이블, 시뮬레이션)
- **PR-4d** — 메시지 탭 (페르소나 모델 마이그레이션 + messaging API + UI)
- **PR-4e** — 캠페인 탭 (2-step 모달 + pause/resume 백엔드 연결)
- **PR-4f** — 분석 탭 + **사이드바 정리** (기존 [브랜드][타겟][캠페인][분석] 메뉴 제거)

각 sub-PR마다:
- [ ] 해당 백엔드 endpoint 작동 + 테스트
- [ ] 해당 탭 UI 구현
- [ ] CLAUDE.md 디자인 원칙 5개 준수 확인
- [ ] 빈 상태/에러 상태/로딩 상태 모두 처리
- [ ] E2E 테스트 통과
- [ ] 스크린샷 첨부

전체 완료:
- [ ] 6개 sub-PR 모두 머지됨 (PR-4a~f)
- [ ] PR-4f 머지 시점에 사이드바에서 기존 [브랜드] [타겟] [캠페인] [분석] 메뉴 사라짐 (PR-4a~e 동안은 새 메뉴와 병존)
- [ ] 모든 운영자 액션이 시장 페이지 안에서 가능
- [ ] regression: 기존 자동 캠페인 분배가 정상 작동

---

## 작업 순서

1. PR-4a: 라우트 구조 + 사이드바 변경 + 제품 목록 페이지
2. PR-4b: 개요 탭 + overview API
3. PR-4c: 수집 탭 (3주, 가장 오래 걸림)
   - flow API + 키워드 API + simulate API
   - KeywordTable 컴포넌트 + 통과율
   - MarketDefinitionEditor + 시뮬레이션
   - 우선순위/시스템 룰 접힘 영역
4. PR-4d: 메시지 탭 + messaging API + 페르소나 모달
5. PR-4e: 캠페인 탭 + 2-step 모달 + pause/resume 백엔드
6. PR-4f: 분석 탭 + 차트

예상 작업량: 4-5주 (1인 풀타임).

---

## 위험 평가

| 위험 | 수준 | 완화 |
|---|---|---|
| 작업량이 너무 큼 | 높음 | 6개 sub-PR로 분할, 각각 독립 머지 |
| 기존 페이지 사라져서 운영자 혼란 | 중간 | PR-4a에서 사이드바에 기존 메뉴와 새 메뉴 한동안 병존 가능. 안정화 후 기존 제거 |
| 시뮬레이션 API 부하 | 중간 | 디바운스 300ms + 결과 캐시 |
| 페르소나 데이터 모델 (Brand에 있던 것) | 중간 | PR-3에서 niche로 옮겼지만 모델 점검 필요 |
| 분석 탭 데이터가 niche에 안 묶여있음 | 중간 | 기존 analytics API에 niche_id 필터 추가 (백엔드 작업) |
