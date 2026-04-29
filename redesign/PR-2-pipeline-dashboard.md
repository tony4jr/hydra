# PR-2 — 홈 파이프라인 흐름 (대시보드 교체)

## 목표

기존 대시보드(`/`)의 단발 카운트 카드들을 5단계 파이프라인 흐름 시각화로 교체합니다. 운영자가 한눈에 "어디서 막혔는지" 파악할 수 있어야 합니다.

---

## 의존성

- 선행 PR: PR-1 (용어 헬퍼 사용)
- 후속 PR: 없음 (독립적)

---

## 범위

### In
- 신규 백엔드 endpoint `GET /api/admin/pipeline/flow`
- 홈 페이지(`/`)의 메인 영역을 파이프라인 흐름으로 교체
- 단계별 카운트 카드 + 병목 자동 감지 + 이탈 사유 패널
- 10초 polling

### Out
- 시장별 파이프라인 (PR-4 시장 페이지 수집 탭에서 별도 구현)
- 분석 페이지 (PR-4 시장 페이지 분석 탭)
- 알림(텔레그램) 변경

---

## 백엔드 변경

### 1. 신규 endpoint: `GET /api/admin/pipeline/flow`

**Query params**
- `window_hours` (int, default=24): 집계 윈도우. 24/12/6/1 지원
- `niche_id` (int, optional): 특정 시장만 보고 싶을 때. 비어있으면 전체

**Response schema (Pydantic v2)**

```python
class PipelineStageMetric(BaseModel):
    stage: Literal["discovered", "auto_passed", "keyword_matched",
                   "market_fit", "task_created", "comment_posted",
                   "survived_24h"]
    count: int
    pass_rate: float | None  # 직전 단계 대비 통과율, 0~1
    is_bottleneck: bool       # 통과율 30% 미만 또는 절대치 급감 시 True

class PipelineExitReason(BaseModel):
    from_stage: str
    to_stage: str
    total_dropped: int
    reasons: list[dict]   # [{ "label": "시장 적합도 미달", "count": 38 }, ...]

class PipelineFlowResponse(BaseModel):
    window_hours: int
    stages: list[PipelineStageMetric]
    exit_reasons: list[PipelineExitReason]
    bottleneck_message: str | None   # 병목 있으면 사람이 읽는 한 줄 설명
    generated_at: datetime
```

### 2. 데이터 소스 (서비스 레이어)

`hydra/services/pipeline_metrics.py` 신설:

```python
class PipelineMetricsService:
    async def get_flow(
        self,
        window_hours: int = 24,
        niche_id: int | None = None,
    ) -> PipelineFlowResponse:
        ...
```

각 단계의 카운트는 다음에서 추출:
- `discovered`: 신규 발견된 영상 수 (수집 로그 또는 `Video.created_at`)
- `auto_passed`: hard block 통과 영상 수
- `keyword_matched`: 긍정 키워드 매칭 + 부정 키워드 미해당
- `market_fit`: embedding score >= threshold 통과
- `task_created`: 위에서 task가 생성된 수 (`Task` 테이블)
- `comment_posted`: 댓글 작성 완료 task 수
- `survived_24h`: ghost detection 통과 댓글 수

이탈 사유는 각 단계의 차이로 산출:
- `discovered → auto_passed` 이탈: hard block 사유별 그룹핑 (영상 길이, 키즈 카테고리, 차단 채널 등)
- `keyword_matched → market_fit` 이탈: 임베딩 점수 분포에서 임계값 미만
- `task_created → comment_posted` 이탈: 워커 부족, 계정 한도 초과, 영상 보호 룰

### 3. 병목 감지 로직

`bottleneck_message`는 단계별로:
- 통과율이 직전 단계 대비 30% 미만이면 amber
- task_created → comment_posted 이탈이 task 수의 50% 이상이면 워커 문제 의심

메시지 예시:
- "4단계 댓글 작성에서 task 15개 적체 — 워커 1대만 온라인. 다른 워커 확인 필요."
- "3단계 시장 적합도 통과율 18% — 시장 정의 검토 권장."

### 4. 캐싱

이 API는 운영 중 자주 호출됨 (10초 polling). DB 부하 줄이기:
- Redis 또는 메모리 캐시로 30초 TTL
- `niche_id` 별로 캐시 키 분리

Redis 미설정이면 메모리 LRU로 시작 (`functools.lru_cache` 부적합 — async라 별도 구현 필요. `cachetools.TTLCache` 권장).

### 5. 권한

기존 admin 인증 미들웨어 그대로 사용. 추가 권한 없음.

---

## 프론트엔드 변경

### 1. 새 컴포넌트

```
frontend/src/components/shared/PipelineFlow/
├── index.tsx                # 메인 컨테이너
├── StageCard.tsx            # 단계별 카운트 카드
├── BottleneckBanner.tsx     # 병목 amber 배너
├── ExitReasons.tsx          # 이탈 사유 그리드
└── pipeline.types.ts        # Zod schema
```

### 2. `routes/index.tsx` 변경

**기존 구성** (스크린샷 기준):
- Hero (오늘 댓글 큰 숫자)
- Server Status Bar (버전·일시정지·비상정지·배포·로그)
- System Status (LED + 워커·캠페인 수)
- Stat Cards 4개 (오늘 댓글 / 좋아요 / 활성 계정 / 미해결 오류)
- 진행 중 캠페인
- 실시간 활동 (최근 14개 task)

**신규 구성**:
- Server Status Bar (그대로 유지)
- ★ Pipeline Flow (신규, 메인 영역 차지)
- Stat Cards 4개 (그대로 유지하되 위치 하단으로)
- 진행 중 캠페인 (그대로)
- 실시간 활동 (그대로)

Hero의 "오늘 댓글 0" 큰 숫자는 제거. Pipeline Flow가 더 풍부한 정보를 같은 위치에서 제공.

### 3. PipelineFlow 컴포넌트 인터페이스

```tsx
type Props = {
  nicheId?: number     // 없으면 전체
  windowHours?: 24 | 12 | 6 | 1
}

export function PipelineFlow({ nicheId, windowHours = 24 }: Props) {
  // useQuery로 /api/admin/pipeline/flow 호출
  // 10초 refetchInterval
  // 5단계 카드 가로 배치 (모바일에선 2x3 grid)
  // 병목 단계는 amber border + 배지
  // 카드 클릭 → 해당 시장 페이지의 수집 탭으로 이동 (nicheId 있을 때)
}
```

### 4. 시각 디자인

5개 카드를 가로로 배치 (1024px 이상). 각 카드:
- 단계 이름 (위, 11px, secondary)
- 카운트 (큰 숫자, 24px, medium)
- 통과율 (아래, 11px, success/warning)

병목 단계만 amber border + 좌측 배지(`⚠`).

병목 메시지가 있으면 카드 위에 amber 배너 1줄.

이탈 사유는 카드 아래 grid 2열로:
- "discovered → auto_passed" 이탈: 사유 리스트
- "keyword_matched → market_fit" 이탈: 사유 리스트

### 5. 인터랙션

- 카드 클릭: 해당 단계가 발생하는 페이지로 이동
  - `discovered` 카드 → 영상 통합 보기 (`/videos`, 신규 정렬)
  - `market_fit` 카드 → 시장 페이지 수집 탭 (시장 컨텍스트 있을 때만)
  - `task_created` 카드 → 작업 큐
- 윈도우 토글: 24h / 12h / 6h / 1h (오른쪽 상단 segmented)
- 병목 배너의 "확인" 버튼: 해당 페이지로 이동 + 토스트로 가이드

### 6. 빈 상태

- 데이터 0개일 때: "아직 활동이 없어요. 첫 시장을 만들어보세요." + 링크
- API 에러: "흐름 데이터를 불러오지 못했어요. 새로고침해주세요." + retry 버튼

### 7. 로딩 상태

10초 polling이라 첫 로드만 skeleton. 이후 `keepPreviousData: true`로 깜빡임 방지.

---

## DB 변경

**없음.** 기존 테이블에서 집계만.

---

## 엣지 케이스

- `survived_24h`는 24h 전 댓글 기준이므로 window가 1h일 때 0으로 표시 (NA가 아니라 명시적 0)
- 시스템 처음 가동 직후엔 `discovered` 카운트가 작아서 통과율 의미 없음 → 카운트 < 5면 `pass_rate = null`
- niche가 삭제됐는데 캐시에 남아있을 때 → 캐시 키에 niche_id 포함, niche 변경 시 invalidate

---

## 성능

- 30초 캐시 + 10초 polling = 평균 3 hit가 캐시. DB 부담 적음
- 단일 niche 쿼리도 윈도우별 복잡 — 인덱스 확인:
  - `Video.created_at`
  - `Task.created_at + Task.status`
  - `CommentLog.posted_at`
- 이미 인덱스 있으면 OK, 없으면 마이그레이션 추가

---

## 테스트

### 백엔드
- `tests/test_pipeline_metrics.py`:
  - 빈 DB일 때 모든 stage가 0
  - 단계별 카운트 합산 정확성 (fixture로 영상·task 만들기)
  - 병목 감지: 통과율 20%일 때 `is_bottleneck=True`
  - 캐시 동작 확인 (mock으로 시간 흐름)

### 프론트엔드
- Playwright E2E:
  - `/` 진입 시 5개 카드 보임
  - 병목이 있으면 배너 보임
  - 카드 클릭 시 라우팅 정확
- TanStack Query mock으로 빈 상태/에러 상태 컴포넌트 테스트

---

## 완료 정의

- [ ] `GET /api/admin/pipeline/flow` 작동, 30초 캐시 적용
- [ ] 새 컴포넌트 5개 파일 생성됨
- [ ] 홈 페이지에 PipelineFlow 컴포넌트 배치됨
- [ ] 10초 polling 작동, 깜빡임 없음
- [ ] 병목 자동 감지 메시지 표시
- [ ] 이탈 사유 grid 표시
- [ ] 카드 클릭 시 라우팅 정확
- [ ] 백엔드/프론트 테스트 통과
- [ ] 운영 중인 시스템에서 5단계 모두 0 아닌 카운트 표시 확인 (실데이터 검증)
- [ ] 변경 전/후 스크린샷 첨부

---

## 작업 순서

1. 백엔드 서비스 + endpoint 작성 + 단위 테스트
2. Postman/curl로 응답 schema 확인
3. 프론트엔드 Zod schema + TanStack Query hook
4. PipelineFlow 컴포넌트 (정적 mock 데이터로 먼저)
5. 실 API 연결
6. 홈 페이지에 통합
7. E2E 테스트
8. 스테이징 배포 → prod

예상 작업량: 1주.

---

## 위험 평가

| 위험 | 수준 | 완화 |
|---|---|---|
| DB 부하 (집계 쿼리) | 중간 | 30초 캐시 + 인덱스 확인 |
| 기존 대시보드 정보 상실 | 낮음 | 카드는 유지, hero만 교체 |
| 캐시 데이터 신선도 | 낮음 | 30초 + 10초 polling으로 충분 |
