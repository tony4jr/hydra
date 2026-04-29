# PR-7 — Onboarding wizard + AI 도우미

## 목표

신규 사용자가 0→1 운영 시작까지 손 잡고 안내하는 흐름. SaaS 진입 핵심.

브랜드 등록 → 첫 시장 만들기 → 키워드 추가 → 시장 정의 작성 → 첫 캠페인까지 1시간 안에 완료할 수 있어야 합니다.

또한 시장 정의를 AI가 다듬어주는 기능 추가 — 운영자가 "탈모 30대 남성"이라고만 써도 AI가 풍부한 시장 정의로 확장.

---

## 의존성

- 선행 PR: PR-1 ~ PR-6 모두
- 후속 PR: 없음 (마지막)

---

## 범위

### In
- `/onboarding` 라우트 — 신규 사용자 첫 진입 시 자동 리디렉션
- 5단계 wizard (브랜드 → 시장 → 키워드 → 시장 정의 → 첫 캠페인)
- AI 도우미 endpoint (시장 정의 다듬기, 키워드 추천)
- 빈 상태 안내 강화 (모든 페이지)
- 도움말 사이드 패널 (각 페이지 ?)

### Out
- 멀티테넌시 (별도 큰 작업)
- 결제·구독 (별도)
- 사용자 권한 시스템 (별도)

---

## 백엔드 변경

### 1. 사용자 첫 방문 감지

```python
# hydra/db/models.py — 기존 User 또는 Account 모델에
class User(Base):
    # ...
    onboarded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    onboarding_step: Mapped[int] = mapped_column(default=0)
    # 0=시작 안 함, 1~5=진행 중, 6=완료
```

기존 admin 단일 사용자 시스템이라 `User` 테이블 없으면 시스템 설정에 저장:

```python
class SystemSetting(Base):
    # ...
    # 키-값 기반이면
    # key='onboarding.completed_at', value='...'
```

### 2. AI 도우미 — 시장 정의 다듬기

```python
@router.post("/niches/api/ai/refine-market-definition")
async def refine_market_definition(
    payload: RefineRequest
) -> RefineResponse:
    """
    Claude Sonnet 4.6 호출. 운영자가 짧게 쓴 시장 묘사를
    의미 분류에 적합한 풍부한 텍스트로 확장.
    """

class RefineRequest(BaseModel):
    rough_description: str   # ex: "탈모 30대 남성"
    brand_context: str | None  # 브랜드 정보
    target_length: int = 200   # 글자 수

class RefineResponse(BaseModel):
    refined: str
    rationale: str  # 왜 이렇게 다듬었는지 한 줄 설명
```

프롬프트 전략:
```
너는 YouTube 영상 의미 분류용 시장 정의를 작성하는 전문가다.
운영자가 거친 묘사를 줬다. 이걸 200자 안팎의 풍부한 정의로 확장해라.

원칙:
1. 포함되어야 할 컨텐츠 명시 (구체적)
2. 제외할 컨텐츠 명시 (반대 케이스)
3. 청자/관심 분야 분명히
4. 완성된 단락 1-2개

[입력]
{rough_description}

[브랜드 컨텍스트]
{brand_context}

[출력 형식]
JSON: { "refined": "...", "rationale": "..." }
```

### 3. AI 도우미 — 키워드 추천

```python
@router.post("/niches/api/ai/suggest-keywords")
async def suggest_keywords(
    payload: SuggestRequest
) -> SuggestResponse:
    """
    시장 정의 기반으로 검색 키워드 5-10개 추천.
    """

class SuggestRequest(BaseModel):
    market_definition: str
    existing_keywords: list[str] = []  # 중복 피하기

class SuggestResponse(BaseModel):
    suggestions: list[KeywordSuggestion]

class KeywordSuggestion(BaseModel):
    keyword: str
    rationale: str  # 왜 이 키워드인지
    expected_volume: Literal["high", "medium", "low"]  # 예상 검색량 (체감)
```

Claude Haiku 4.5 사용 (간단한 작업).

### 4. 첫 캠페인 템플릿

```python
@router.get("/niches/api/{niche_id}/onboarding/campaign-template")
async def get_first_campaign_template(niche_id: int) -> CampaignTemplate:
    """
    첫 캠페인용 합리적 디폴트 추천.
    - 시드 댓글 + 동조 프리셋 (2개만)
    - 30일 기간
    - 영상당 1세트
    - 영상 50개 목표
    """
```

### 5. 권한

이 wizard는 admin 권한 필요. AI 호출은 quota 영향 — 도우미 호출도 기록.

---

## 프론트엔드 변경

### 1. 라우트

```
frontend/src/routes/
├── onboarding/
│   ├── index.tsx              # wizard 시작
│   ├── 1-brand.tsx            # 브랜드 등록
│   ├── 2-niche.tsx            # 첫 시장
│   ├── 3-keywords.tsx         # 키워드 추가
│   ├── 4-market-def.tsx       # 시장 정의
│   └── 5-campaign.tsx         # 첫 캠페인
└── ...
```

또는 단일 페이지 stepper로 구현 (URL 파라미터 `?step=1`).

### 2. 신규 사용자 자동 리디렉션

`__root.tsx`에 가드:

```tsx
beforeLoad: async ({ context }) => {
  const isOnboarded = await checkOnboardingStatus()
  if (!isOnboarded && location.pathname !== '/onboarding') {
    throw redirect({ to: '/onboarding' })
  }
}
```

기존 운영자(이미 brand가 있는 시스템)는 onboarded 자동 처리.

### 3. Wizard UX

각 step 공통:
- 상단 진행 바 (1/5, 2/5, ...)
- 본문: 친근한 안내 + 입력 폼
- 하단: [이전] [건너뛰기] [다음] 버튼
- 우측 도움말 패널 (선택, 닫기 가능)

#### Step 1 — 브랜드 등록

```
[1/5] 어떤 제품을 홍보하시나요?

브랜드명 [_____________]
카테고리 [_____________]
한 줄 설명 [_____________]

[건너뛰기]                                   [다음 →]
```

도움말: "브랜드는 회사 또는 제품 단위입니다. 한 회사가 여러 제품을 가졌다면 각각 따로 등록하세요."

#### Step 2 — 첫 시장 만들기

```
[2/5] {brand_name}을(를) 어느 시장에 노출시킬까요?

시장 이름 [예: 탈모 30대 남성]

(시장은 한 브랜드 안에서 다른 청중이나 다른 메시지를 다룰 때 나눕니다.
나중에 더 추가할 수 있어요.)

[← 이전]                                     [다음 →]
```

#### Step 3 — 키워드 추가

```
[3/5] 어떤 영상을 찾을까요?

YouTube 검색에 던질 단어를 추가하세요. 5분 안에 영상을 찾아옵니다.

[탈모 ×] [모발이식 ×] [+ 추가]

[✨ AI에게 추천받기]   ← 클릭하면 시장 이름 기반으로 키워드 5개 추천

[← 이전]                                     [다음 →]
```

AI 추천 클릭 시 모달:
```
이런 키워드는 어떨까요?

☑ 두피케어 — 인접 관심사
☑ M자이마 — 직접적
☑ 미녹시딜 — 의약품 관심
☐ 헤어로스 — 영문 표기
☐ 머리숱 — 일반 표현

[추가]
```

#### Step 4 — 시장 정의

```
[4/5] 이 시장을 한 단락으로 묘사해주세요.

AI가 영상이 이 시장에 맞는지 자동으로 판단할 때 사용합니다.

[textarea — 자유롭게 작성]

[✨ AI에게 다듬어달라기]   ← 클릭하면 짧은 묘사를 200자로 확장

(예시) "30대 한국 남성이 겪는 안드로겐성 탈모와 그에 대한 관리·치료...
       제외: 여성 탈모, 항암 탈모"

[← 이전]                                     [다음 →]
```

AI 다듬기 클릭 시 modal에 변경 전/후 비교 → 적용/취소.

#### Step 5 — 첫 캠페인

```
[5/5] 첫 캠페인을 만들까요?

저희가 추천하는 시작 설정:
- 프리셋: 시드 댓글 + 동조 (2개)
- 영상 50개 목표
- 30일 기간

이 설정으로 바로 시작할 수 있고, 나중에 조정할 수 있어요.

[기본 설정 사용 →] 또는 [커스텀 설정 →] 또는 [나중에 만들기 →]
```

기본 사용 클릭 → niche 페이지로 이동 + 첫 캠페인 자동 생성 + 토스트 환영 메시지.

### 4. 빈 상태 강화

각 페이지의 빈 상태에 가이드 추가:

#### `/products` 빈 상태
```
아직 제품이 없어요.

HYDRA는 제품(브랜드) → 시장 → 캠페인 순서로 작동합니다.
첫 제품을 만들어볼까요?

[+ 첫 제품 만들기]   또는   [→ 가이드로 다시 시작]
```

#### 시장 페이지 수집 탭 — 키워드 0개일 때
```
첫 키워드를 추가해보세요.

YouTube에서 어떤 영상을 찾고 싶으신가요?
키워드를 추가하면 5분 안에 첫 영상을 찾아옵니다.

[+ 첫 키워드]   [✨ AI 추천]
```

각 페이지마다 비슷한 패턴. 모두 친근하고 다음 액션 명확.

### 5. 도움말 사이드 패널

각 페이지 우상단 `?` 아이콘 → 우측에서 sliding panel:

```
시장 페이지 — 도움말

이 페이지에서 무엇을 할 수 있나요?
- 한 시장의 영상 풀, 메시지, 캠페인을 모두 관리합니다
- 5개 탭으로 작업 단계가 나뉩니다

각 탭 설명:
- 개요: 시장 한눈에
- 수집: 어떤 영상을 모을지 정의
- 메시지: 어떤 댓글을 만들지
- 캠페인: 작업 실행
- 분석: 결과 확인

자주 하는 질문:
[Q] 시장과 브랜드 차이?
[Q] 키워드 통과율이 낮아요...
...
```

도움말 콘텐츠는 `frontend/src/help/` 디렉토리에 마크다운으로 관리. 페이지마다 1개 파일.

### 6. 진행 상태 저장

각 step 완료 시 백엔드에 저장 → 새로고침해도 진행 위치 유지.

```tsx
const updateStep = useUpdateOnboardingStep()
// step 완료 시 updateStep.mutate(currentStep + 1)
```

### 7. 건너뛰기

각 step에 "건너뛰기" 옵션. 마지막 step에 "나중에" 옵션. 모두 onboarding을 완료 상태로 전환 (다시 안 묻음).

운영자가 wizard 다시 보고 싶으면 시스템 설정에서 "온보딩 다시 시작" 버튼.

---

## AI 도우미 UX 가이드

AI 호출은 시간이 걸려서 (1-3초) UX 처리 중요:

- 버튼 클릭 즉시 로딩 상태 (스피너 + "생각 중...")
- 최대 5초 wait, 그 후 timeout 안내
- 실패 시 친근한 메시지 ("AI가 잠시 쉬고 있어요. 직접 작성하시거나 잠시 후 다시 시도하세요.")
- 결과는 항상 변경 전/후 비교로 보여주고 운영자가 선택

---

## 엣지 케이스

- 운영자가 wizard 중간에 새로고침 → 마지막 step부터 재개
- 브랜드 등록 후 시장 만들기 전에 닫음 → 다음 진입 시 step 2부터
- AI 응답이 부적절 (한국어 깨짐 등) → 운영자가 직접 수정 옵션 항상 활성
- 첫 캠페인 만들 때 niche에 키워드 0개 → 캠페인은 만들되 amber 안내 "키워드 추가 후 작동"
- 모든 step 건너뛰기 → 빈 시스템 상태 + 가이드 + "wizard 다시 보기" 옵션

---

## 테스트

### 백엔드
- AI endpoints: mock으로 다양한 응답 (성공/실패/부적절 응답)
- onboarding step 저장·조회

### 프론트엔드 E2E
- 신규 사용자 (DB 비움) → 자동 onboarding 리디렉션
- 5단계 모두 정상 진행 → 시장 페이지 도착
- 새로고침 → 마지막 step 재개
- 건너뛰기 → 정상 진입
- AI 추천 모달 → 적용/취소

### 수동 검증
- 친구나 동료에게 wizard 첫 시도 시켜보기 → 막히는 곳 관찰
- 어색한 안내 문구 다듬기

---

## 완료 정의

- [ ] `/onboarding` 5단계 wizard 작동
- [ ] 신규 사용자 자동 리디렉션
- [ ] 진행 상태 저장
- [ ] AI 시장 정의 다듬기 작동
- [ ] AI 키워드 추천 작동
- [ ] 첫 캠페인 자동 생성 옵션
- [ ] 모든 페이지 빈 상태에 가이드 메시지
- [ ] 도움말 사이드 패널 (최소 5개 페이지)
- [ ] E2E 테스트 통과
- [ ] 수동 검증 (1명 이상 새 사용자 시도)

---

## 작업 순서

1. AI endpoint 2개 + 프롬프트 튜닝 (mock 응답 비교)
2. 백엔드 onboarding 상태 저장
3. wizard 라우트 + 5단계 컴포넌트
4. 자동 리디렉션 가드
5. AI 도우미 모달 (시장 정의, 키워드)
6. 빈 상태 강화 (모든 페이지)
7. 도움말 패널 + 콘텐츠 작성
8. 첫 캠페인 자동 생성
9. E2E + 수동 검증

예상 작업량: 2주.

---

## 위험 평가

| 위험 | 수준 | 완화 |
|---|---|---|
| AI 응답 품질 (한국어) | 중간 | Sonnet 사용, 프롬프트 튜닝, 항상 운영자 수정 옵션 |
| 첫 시도자 길 잃음 | 중간 | 1명 이상 수동 검증, 어색한 곳 다듬기 |
| AI 호출 quota 영향 | 낮음 | wizard는 운영자당 1회, 도우미는 quota 추적 |
| 기존 운영자에게 wizard 강제 | 낮음 | 기존 brand 있으면 onboarded 자동 |
