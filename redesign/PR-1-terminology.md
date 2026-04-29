# PR-1 — 용어 정비 (i18n 헬퍼 + UI 라벨 일괄 교체)

## 목표

개발자 용어를 운영자 멘탈모델 용어로 교체합니다. 코드 내부 식별자(DB 컬럼, API 필드, 변수명)는 유지하고 **UI 표시 문자열만** 변경합니다.

이 PR은 후속 모든 PR의 기반입니다. 작은 변화로 큰 사용성 개선이 나오고 위험이 거의 없어서 가장 먼저 수행합니다.

---

## 의존성

- 선행 PR: 없음
- 후속 PR: 모든 PR이 이 PR의 헬퍼를 사용

---

## 범위

### In (이번 PR에 포함)
- `frontend/src/lib/i18n-terms.ts` 신설 (한국어 용어 매핑 헬퍼)
- 기존 React 페이지의 모든 UI 텍스트를 헬퍼 통해 출력하도록 변경
- 새 용어가 들어가는 헤더·라벨·툴팁·placeholder
- 코드 주석에 "운영자 용어 X / 코드 용어 Y" 매핑 한 번 명시

### Out (이번 PR에 포함하지 않음)
- DB 컬럼명 변경 (절대 안 함)
- API 엔드포인트 경로 변경 (안 함)
- 새 페이지 추가 (PR-2~7)
- 분석 페이지 비어있는 상태 채우기 (PR-2 이후)

---

## 백엔드 변경

**없음.** 백엔드는 전혀 건드리지 않습니다.

---

## 프론트엔드 변경

### 1. `frontend/src/lib/i18n-terms.ts` 신설

```ts
// 코드 식별자 → UI 표시 문자열 매핑
// CLAUDE.md §6 용어 매핑표 기준

export const lifecyclePhase = {
  1: '신규 영상',
  2: '활성',
  3: '안정',
  4: '장기',
} as const

export const tier = {
  L1: '장기 자산',
  L2: '신규',
  L3: '트렌딩',
  L4: '롱테일',
} as const

export const taskState = {
  pending: '대기',
  in_progress: '진행중',
  done: '완료',
  failed: '실패',
} as const

export const accountState = {
  active: '활성',
  warmup: '워밍업',
  cooldown: '쿨다운',
  suspended: '정지',
  ghost: '고스트',
  verifying: '본인 인증',
} as const

export const videoState = {
  active: '활성',
  pending: '대기',
  blocked: '차단',
  paused: '일시정지',
  retired: '은퇴',
} as const

export const priority = {
  high: '높음',
  normal: '보통',
  low: '낮음',
} as const

// 헬퍼: 안전하게 매핑 (없는 키도 fallback)
export function term<T extends Record<string, string>>(
  map: T,
  key: keyof T | string,
  fallback?: string,
): string {
  return (map as any)[key] ?? fallback ?? String(key)
}

// 단일 진실의 원천: 자주 쓰는 도메인 라벨
export const labels = {
  // 사이드바 그룹
  groupHome: '홈',
  groupOperation: '제품 운영',
  groupInfra: '인프라',

  // 페이지명
  pageHome: '운영 현황',
  pageProducts: '제품 목록',
  pageNiche: '시장',
  pageCampaigns: '캠페인',
  pageVideos: '영상',
  pageTasks: '작업 큐',
  pageAccounts: '계정 풀',
  pageWorkers: '작업 PC',
  pageAvatars: '아바타·페르소나',
  pageSettings: '시스템 설정',

  // 도메인 핵심 용어
  niche: '시장',
  marketDefinition: '시장 정의',
  marketFitness: '시장 적합도',
  collectionFunnel: '수집 흐름',
  autoExclusion: '자동 제외',
  protectionRules: '영상 보호 룰',
  ghostDetection: '댓글 생존 검증',
  apiQuota: 'API 사용량',

  // 상태 동사
  pause: '일시정지',
  resume: '재개',
  emergency: '비상정지',
  deploy: '배포',
  restoreDefault: '기본값으로 복원',
} as const
```

### 2. 일괄 교체 가이드

기존 페이지에서 다음 패턴을 찾아 교체:

| 검색 (기존) | 교체 (신규) |
|---|---|
| `"Phase 1"`, `"Phase 2"` 등 (UI 텍스트) | 제거 또는 `lifecyclePhase[n]` 사용 |
| `"L1"`, `"L2"`, `"L3"`, `"L4"` (UI에서) | `term(tier, "L1")` |
| `"embedding score"`, `"임베딩 점수"` | `labels.marketFitness` |
| `"reference text"`, `"reference"` | `labels.marketDefinition` |
| `"Hard Block"`, `"hard block"` | `labels.autoExclusion` |
| `"ghost"`, `"ghost rate"` (단독) | `labels.ghostDetection` 또는 "고스트율" |
| `"Worker"` (네비게이션) | `labels.pageWorkers` |
| `"브랜드"` (사이드바) | 그대로 유지하되 페이지 내부에서 새 IA 용어 사용 |
| `"타겟"` (사이드바) | PR-4에서 제거됨, 이 PR에선 그대로 |

### 3. 사이드바 그룹 라벨 변경

> **⏸ PR-2와 함께 처리 (이 PR에선 deferred).**
> 이번 PR-1 범위에선 라벨 변경을 빼서 작업 단위를 깔끔하게 유지하고 롤백을 단순하게 합니다. 라벨 변경 시 메뉴 항목 정리도 함께 가야 그룹명-내용 mismatch가 없어지므로, PR-2 (홈 파이프라인 흐름) 작업 시작 시 함께 처리합니다.

`frontend/src/components/sidebar.tsx` (또는 동등 위치):

```tsx
// 기존: 운영 / 관리 / 시스템
// 신규: 홈 / 제품 운영 / 인프라

// 단, 이 PR은 라벨만 바꿀 뿐 메뉴 항목은 그대로 유지.
// 새 IA 메뉴 추가/제거는 각 후속 PR에서.
```

| 기존 그룹 | 신규 그룹 |
|---|---|
| 운영 | 홈 |
| 관리 | 제품 운영 (이번 PR에선 빈 그룹이지만 라벨만 변경) |
| 시스템 | 인프라 |

### 4. 변경 대상 파일 목록

```
frontend/src/lib/i18n-terms.ts                  # 신설
frontend/src/components/sidebar.tsx              # 그룹 라벨
frontend/src/routes/index.tsx                    # 대시보드 텍스트
frontend/src/routes/brands/*.tsx                 # 브랜드 폼/리스트
frontend/src/routes/targets/*.tsx                # 타겟 페이지 (Phase, L tier 노출 부분)
frontend/src/routes/campaigns/*.tsx              # 캠페인
frontend/src/routes/tasks/*.tsx                  # 작업 큐 (state 표시)
frontend/src/routes/accounts/*.tsx               # 계정 (state 표시)
frontend/src/routes/workers/*.tsx                # 워커
frontend/src/routes/analytics/*.tsx              # 분석 (있다면 라벨만)
frontend/src/routes/settings/*.tsx               # 설정
frontend/src/components/**/*.tsx                 # 공유 컴포넌트 텍스트
```

각 파일을 열어서 §6 용어 매핑표에 해당하는 모든 표현을 검색·교체합니다.

---

## API 변경

**없음.**

---

## DB 변경

**없음.**

---

## UI/UX 상세

### 인터랙션 변경 없음
이 PR은 텍스트만 바꿉니다. 클릭 동작, 페이지 흐름, 컴포넌트 구조는 그대로입니다.

### 시각적 차이가 나는 곳
- 작업 큐의 LED 옆 상태 텍스트가 한국어로 (`pending` → `대기`)
- 영상 풀 테이블의 tier 컬럼이 `L1` → `장기 자산` 등
- 분류 설정 패널의 `reference 비어있음` 경고가 `시장 정의 비어있음 — 의미 분류 작동 안 함`으로

---

## 엣지 케이스

- 매핑 테이블에 없는 키가 들어오면 `term()` 헬퍼가 fallback으로 원본 키를 그대로 출력합니다. 콘솔 경고 없이 조용히. 이는 의도된 동작.
- 기존 코드에 영문 라벨이 하드코딩된 곳이 있으면 검색에서 누락될 수 있음 → grep으로 `Phase`, `tier`, `embedding`, `quota`, `worker`, `ghost` 한 번씩 훑어 빠진 것 확인.

---

## 테스트

### 자동 테스트
- `frontend/src/lib/i18n-terms.test.ts`: `term()` 헬퍼의 fallback 동작 확인 (10줄짜리 단위 테스트)

### 수동 검증
- 모든 페이지 한 번씩 클릭해보면서 영문 개발자 용어가 남아있는지 확인
- 검색 키워드: `Phase`, `L1`, `L2`, `L3`, `L4`, `embedding`, `reference`, `ghost rate`, `quota`, `Worker`

---

## 완료 정의

- [ ] `frontend/src/lib/i18n-terms.ts` 파일이 존재하고 §6 용어 매핑표의 모든 항목 포함
- [ ] 사이드바 그룹 라벨이 "홈 / 제품 운영 / 인프라"로 변경됨
- [ ] 기존 모든 페이지에서 영문 개발자 용어(`Phase 1`, `L1`, `embedding score` 등)가 사라짐
- [ ] 단위 테스트 통과
- [ ] `grep -r "Phase 1\|Phase 2\|embedding\|reference text\|hard block\|ghost rate\|quota" frontend/src/` 결과가 코드 식별자(주석·변수명) 외엔 없음
- [ ] 수동으로 모든 페이지 한 번씩 둘러본 결과 영문/개발자 용어 노출 없음
- [ ] PR 설명에 변경 전/후 스크린샷 (대시보드, 작업 큐, 타겟 페이지 최소 3장)

---

## 작업 순서

1. `frontend/src/lib/i18n-terms.ts` 작성 + 단위 테스트
2. `frontend/src/components/sidebar.tsx` 그룹 라벨 변경
3. 각 페이지 파일을 열어서 검색·교체 (위 §변경 대상 파일 목록 순서대로)
4. 페이지마다 dev 서버에서 시각 확인
5. grep으로 누락 확인
6. 스크린샷 첨부해서 PR 올림

예상 작업량: 1주 (1인 풀타임 기준).

---

## 위험 평가

| 위험 | 수준 | 완화 |
|---|---|---|
| 기존 코드 깨짐 | 매우 낮음 | 텍스트만 변경 |
| DB 영향 | 없음 | DB 안 건드림 |
| API 영향 | 없음 | API 안 건드림 |
| 운영자 혼란 (라벨 바뀜) | 낮음 | 직관적 한국어로 바꾸는 거라 오히려 명확해짐 |
