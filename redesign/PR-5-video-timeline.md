# PR-5 — 영상 통합 보기 + 타임라인

## 목표

영상 1개가 시스템에 들어와서부터 지금까지 일어난 모든 일을 시간순으로 추적하는 페이지를 신설합니다. 운영자의 핵심 디버깅 도구.

"왜 이 캠페인 잘 안 됐지?" 답을 한 화면에서 찾을 수 있게 합니다.

---

## 의존성

- 선행 PR: PR-1 (용어), PR-3 (Niche 모델)
- 후속 PR: 없음 (독립적)

---

## 범위

### In
- `/videos` — 전체 영상 검색·필터 페이지
- `/videos/$videoId` — 영상 상세 (타임라인)
- 신규 백엔드 API 2개 (검색, 타임라인)
- 사이드바 "영상" 메뉴 활성화 (PR-4에서 placeholder만 만든 것)

### Out
- 영상 수동 추가 기능 (기존 URL 추가 모달 그대로 유지)
- 영상 삭제 / 차단 (기존 기능 그대로)

---

## 백엔드 변경

### 1. 영상 검색 API: `GET /videos/api/search`

```python
class VideoSearchParams(BaseModel):
    q: str | None = None  # 제목·채널 검색
    niche_id: int | None = None
    state: VideoState | None = None
    tier: Literal["L1", "L2", "L3", "L4"] | None = None
    min_views: int | None = None
    posted_after: datetime | None = None
    has_active_campaign: bool | None = None
    sort: Literal["recent", "views", "fitness", "comment_count"] = "recent"
    page: int = 1
    page_size: int = 50

class VideoSearchResult(BaseModel):
    videos: list[VideoSummary]
    total: int
    page: int
    page_size: int

class VideoSummary(BaseModel):
    id: int
    youtube_id: str
    title: str
    channel: str
    view_count: int
    posted_at: datetime
    discovered_at: datetime
    state: VideoState
    tier: str | None
    market_fitness: float | None
    niche_count: int  # 매칭된 niche 수
    active_campaigns: int
    total_comments_posted: int
    last_action_at: datetime | None
```

### 2. 영상 타임라인 API: `GET /videos/api/{video_id}/timeline`

```python
class TimelineEvent(BaseModel):
    at: datetime
    kind: Literal[
        "discovered",          # 키워드 폴링에서 발견
        "classified",          # 자동 분류 (tier 결정)
        "rejected_filter",     # hard block 또는 시장 부적합
        "pool_entered",        # 풀 진입
        "task_created",        # task 생성
        "comment_posted",      # 댓글 작성
        "boost_wave",          # 좋아요 부스트
        "ghost_check_passed",  # 24h 생존 확인
        "ghost_check_failed",  # 댓글 삭제됨
        "blocked",             # 운영자가 차단
        "reclassified",        # 운영자가 재분류
        "next_revisit",        # 다음 재방문 예정 (미래)
    ]
    actor: Literal["system", "operator", "worker"] | None
    actor_detail: str | None  # 워커 이름, 운영자 이름
    niche_id: int | None
    niche_name: str | None
    campaign_id: int | None
    campaign_name: str | None
    account_email: str | None
    metadata: dict  # kind별 추가 정보 (댓글 텍스트, 점수 등)

class VideoTimelineResponse(BaseModel):
    video: VideoSummary
    events: list[TimelineEvent]  # 시간순 (오래된 것부터)
    upcoming: list[TimelineEvent]  # 예정된 이벤트 (revisit 등)
```

### 3. 데이터 소스

기존 시스템에 다음 로그가 흩어져 있음:
- `Video.created_at` (discovered)
- `Video.classified_at` (classified)
- `Video.state` 변경 이력 → `VideoStateLog` 테이블이 있는지 확인. 없으면 신설
- `Task` 테이블 (created, in_progress, done, failed)
- `CommentLog` (실제 작성된 댓글)
- `LikeBoostLog` (좋아요 부스트)
- `GhostCheckLog` (생존 검증)
- `AuditLog` (운영자 액션)

이 PR에서 일부 로그는 신설 또는 보강 필요:

#### 신설 테이블 (필요 시)
```python
class VideoStateLog(Base):
    __tablename__ = 'video_state_log'
    id: Mapped[int]
    video_id: Mapped[int]
    from_state: Mapped[str | None]
    to_state: Mapped[str]
    reason: Mapped[str | None]  # 자동/수동/사유
    actor_id: Mapped[int | None]
    created_at: Mapped[datetime]
```

이미 비슷한 테이블이 있으면 재사용. 없으면 신설하고 기존 코드의 state 변경 지점에 INSERT 추가 (트리거 또는 service-level hook).

### 4. 인덱스 확인

타임라인 쿼리는 `video_id`로 여러 테이블 조회. 다음 인덱스 필수:
- `Task(video_id, created_at DESC)`
- `CommentLog(video_id, posted_at DESC)`
- `LikeBoostLog(video_id, created_at DESC)`
- `GhostCheckLog(video_id, checked_at DESC)`
- `VideoStateLog(video_id, created_at DESC)`

없는 인덱스는 마이그레이션으로 추가.

### 5. 권한

영상 검색·타임라인은 admin 인증으로 충분.

---

## 프론트엔드 변경

### 1. 라우트 구조

```
frontend/src/routes/videos/
├── index.tsx          # 영상 검색·필터
└── $videoId.tsx       # 영상 타임라인
```

### 2. 영상 검색 페이지 (`/videos`)

```
┌──────────────────────────────────────────────────────────┐
│ 영상                                                      │
│ 전체 영상 검색·추적                                       │
├──────────────────────────────────────────────────────────┤
│ [검색...] [시장 ▾] [상태 ▾] [티어 ▾] [캠페인 ▾] [정렬 ▾]│
├──────────────────────────────────────────────────────────┤
│ 1247개 영상                                               │
│ ┌────┬────────────────────┬────────┬──────┬──────┬─────┐│
│ │ 상│ 제목·채널           │ 시장    │ 티어 │ 적합도│댓글  ││
│ ├────┼────────────────────┼────────┼──────┼──────┼─────┤│
│ │ ●  │ 6년 동안 샴푸를...  │ 탈모30 │트렌딩│ 0.82 │ 3   ││
│ │    │ @건강채널 1.2M      │        │      │      │     ││
│ │ ●  │ 탈모 초기증상 자가...│ 탈모30 │ 신규 │ 0.78 │ 2   ││
│ │ ⏸  │ 두피 마사지 루틴   │ 산후탈모│장기자산│ 0.71│ 12  ││
│ │ ✗  │ [광고] 신박한 영양제│ -      │ -    │ -    │ 0   ││
│ └────┴────────────────────┴────────┴──────┴──────┴─────┘│
│ [이전] 1 / 25 [다음]                                     │
└──────────────────────────────────────────────────────────┘
```

- 행 클릭 → `/videos/$videoId` 타임라인
- 상태 LED:
  - 활성 (●) — 작업 가능
  - 일시정지 (⏸) — 작업 안 함
  - 차단 (✗) — 영구 제외
- 티어/적합도 컬럼은 §6 용어 매핑 사용
- 검색은 디바운스 300ms

### 3. 영상 타임라인 페이지 (`/videos/$videoId`)

전체 레이아웃:

```
┌──────────────────────────────────────────────────────────┐
│ ← 영상 검색                                               │
├──────────────────────────────────────────────────────────┤
│ 6년 동안 샴푸를 쓰지 않고 탈모를 완치한 남자의 비결        │
│ @건강채널 · 1.2M views · 트렌딩 (L3) · 활성              │
│ [매칭 시장: 탈모 30대 남성] [캠페인 2개]                  │
│                                                          │
│ [▶ YouTube에서 보기]  [재분류] [차단] [일시정지]         │
├──────────────────────────────────────────────────────────┤
│ 타임라인                                                  │
│                                                          │
│ ●─ 3일 전 14:23 · 수집                                    │
│    키워드 [탈모] 일배치 폴링에서 발견                     │
│                                                          │
│ ●─ 3일 전 14:24 · 분류                                    │
│    시장 적합도 0.82 통과 · 트렌딩 판정 (시간당 4,200)    │
│                                                          │
│ ●─ 3일 전 14:25 · 풀 진입                                │
│    활성 영상으로 등록 · 우선순위 높음                     │
│                                                          │
│ ●─ 3일 전 15:02 · 첫 댓글 (시드)                         │
│    [신제품 인지도 푸시] · phuoclocphan36                 │
│    "저도 비슷하게 6년 고생했는데, 결국 두피 환경이..."    │
│                                                          │
│ ●─ 3일 전 15:18~15:47 · 좋아요 부스트 wave               │
│    5개 계정 좋아요 → 베스트 댓글 진입 성공               │
│                                                          │
│ ●─ 2일 전 15:08 · 24h 생존 검증                          │
│    댓글 살아있음 (실제 좋아요 23개 누적)                  │
│                                                          │
│ ●─ 1일 전 09:15 · 동조 댓글                              │
│    [신제품 인지도 푸시] · phuonganhlethi                 │
│    "맞아요 ㅠㅠ 저도..."                                 │
│                                                          │
│ ○─ 예정 · 5일 후                                         │
│    재방문 예정 (안정 단계 · 14일 간격)                    │
└──────────────────────────────────────────────────────────┘
```

#### TimelineEvent 컴포넌트

```tsx
// 이벤트 종류별 색상
const eventColors = {
  discovered: 'info',        // 파랑
  classified: 'gray',
  pool_entered: 'success',   // 초록
  task_created: 'gray',
  comment_posted: 'success',
  boost_wave: 'success',
  ghost_check_passed: 'success',
  ghost_check_failed: 'danger',  // 빨강
  rejected_filter: 'danger',
  blocked: 'danger',
  reclassified: 'info',
  next_revisit: 'tertiary',  // 점선
}
```

각 이벤트 row:
- 왼쪽: 점 (색상으로 종류 표시) + 세로선 (다음 이벤트와 연결)
- 시각: "3일 전 14:23 · 수집" 형식 (relative + 절대)
- 본문: 한 줄 설명
- 메타데이터: 캠페인 이름은 클릭 가능 (해당 캠페인 페이지로), 계정은 hover로 상세
- 댓글 텍스트는 인용 박스 (회색 배경)

#### 액션 버튼

상단 액션:
- **YouTube에서 보기** → 새 탭으로 영상 URL
- **재분류** → 현재 niche에서 분류 다시 돌림 (`POST /videos/api/{id}/reclassify`)
- **차단** → state=blocked로 변경 (영구)
- **일시정지** → state=paused (재개 가능)

각 액션은 confirm 모달 후 실행. 액션 자체도 타임라인에 이벤트로 추가됨.

### 4. 빈 상태 / 에러

- 영상 검색 결과 0개 → "조건에 맞는 영상이 없어요. 필터 조정해보세요."
- 타임라인 이벤트 0개 (방금 발견된 영상) → "수집 후 첫 분류 대기 중. 잠시 후 새로고침."
- API 에러 → 메시지 + 재시도 버튼

### 5. 빠른 진입점

- 시장 페이지 개요 탭 → 영상 풀 카운트 클릭 → `/videos?niche_id=...`
- 시장 페이지 캠페인 탭 → 캠페인 카드 → `/videos?campaign_id=...`
- 작업 큐 → task 클릭 → `/videos/$videoId`
- 홈 파이프라인 흐름 → 단계 카드 클릭 → `/videos?...` 적절한 필터

---

## 데이터 fetch 전략

```tsx
// 검색 페이지: TanStack Query infinite scroll
useInfiniteQuery({
  queryKey: ['videos', filters],
  queryFn: ({ pageParam = 1 }) => api.get('/videos/api/search', {
    ...filters,
    page: pageParam
  }),
  getNextPageParam: (last) =>
    last.page * last.page_size < last.total ? last.page + 1 : undefined,
})

// 타임라인 페이지
useQuery({
  queryKey: ['video-timeline', videoId],
  queryFn: () => api.get(`/videos/api/${videoId}/timeline`),
  staleTime: 30_000,
  refetchOnWindowFocus: true,
})
```

타임라인은 30초 stale + 윈도우 포커스 시 refetch (실시간 업데이트 욕구 있을 때만 새로고침).

---

## 엣지 케이스

- 영상 1개가 여러 niche에 매칭 → 타임라인 이벤트에 niche 라벨 표시 (어느 시장 컨텍스트에서 일어난 일인지)
- 영상의 매칭 niche가 archived → 타임라인은 그대로 보이고 "보관 중인 시장" 배지
- 댓글이 ghost로 판정 → 빨강 이벤트 + 어떤 댓글이 사라졌는지 + 어떤 계정이 영향받았는지
- 영상 자체가 YouTube에서 삭제됨 → state=retired, 타임라인 마지막에 "YouTube에서 영상 삭제됨"
- 100+ 이벤트 (장기 자산) → 가상 스크롤 또는 "더 보기" 페이지네이션. 일단 기본은 100개 limit, 더 보면 페이지네이션
- 운영자가 영상 차단 → 즉시 진행 중 task 취소. 타임라인에 "차단됨 by {operator}" 추가

---

## 성능

타임라인 쿼리는 한 영상의 모든 이벤트를 다양한 테이블에서 SELECT 후 merge. 영상당 50-200개 이벤트 예상.

최적화:
- 각 테이블 쿼리에 limit 100 (탑 100 이벤트만)
- video_id 인덱스 필수
- 응답 30초 캐시

검색 쿼리는 더 무거움. 인덱스:
- `Video.discovered_at DESC`
- `Video.view_count DESC`
- `Video.market_fitness DESC`
- niche_id, state, tier 필터용 복합 인덱스

---

## 테스트

### 백엔드
- `tests/test_video_search.py`: 다양한 필터 조합
- `tests/test_video_timeline.py`: 이벤트 시간순 정렬, 다중 niche 매칭, ghost 케이스
- 100+ 이벤트 영상의 타임라인 응답 시간 확인 (<500ms)

### 프론트엔드 (E2E)
- 검색 페이지: 필터 적용·해제·페이지네이션
- 타임라인: 다양한 이벤트 종류 시각 확인
- 영상 행 클릭 → 타임라인 정확
- 차단 버튼 → 모달 → 확인 → state 변경 + 타임라인에 이벤트 추가

---

## 완료 정의

- [ ] `GET /videos/api/search` 작동 + 필터 모두 정확
- [ ] `GET /videos/api/{id}/timeline` 작동 + 모든 이벤트 종류 포함
- [ ] VideoStateLog (또는 동등) 테이블 존재, state 변경 시 자동 기록
- [ ] `/videos` 페이지 + 검색·필터·페이지네이션
- [ ] `/videos/$videoId` 페이지 + 타임라인 + 액션 버튼
- [ ] 사이드바 "영상" 메뉴 활성화
- [ ] 다른 페이지에서 영상으로 진입하는 링크들 모두 작동 (시장/캠페인/작업/홈)
- [ ] E2E 테스트 통과
- [ ] 100+ 이벤트 영상 응답 < 500ms
- [ ] 스크린샷 첨부 (검색, 타임라인, 액션)

---

## 작업 순서

1. VideoStateLog 테이블 (없으면) + 마이그레이션
2. state 변경 hook 추가 (서비스 코드)
3. 검색 API + 타임라인 API + 단위 테스트
4. 프론트엔드 라우트 + Zod 타입
5. 검색 페이지 (테이블 + 필터)
6. 타임라인 페이지
7. 액션 버튼 (재분류/차단/일시정지)
8. 다른 페이지에서 진입점 추가 (링크들)
9. E2E 테스트

예상 작업량: 2주.

---

## 위험 평가

| 위험 | 수준 | 완화 |
|---|---|---|
| 이벤트 데이터가 흩어져 있어 누락 | 중간 | 모든 state 변경 hook 한번에 점검, fixture로 검증 |
| 타임라인 응답 느림 | 중간 | 인덱스 추가, 100 limit, 캐시 |
| 검색 API 부하 | 중간 | 디바운스 + 페이지네이션 + 인덱스 |
| 운영 중 영상 차단으로 진행 task 깨짐 | 낮음 | task cancel 로직 이미 있음, 재사용 |
