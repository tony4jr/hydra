# Multi-Brand Architecture — Design Spec

**Date**: 2026-05-07
**Status**: Draft (awaiting user review)
**Owner**: 서민재
**Superseded design**: 어제(2026-05-06) 만든 모렉신 단일 브랜드 슬롯 엔진의 출력이 광고티가 강해 본격 운영 불가. 다중 브랜드를 깔끔하게 운영할 수 있는 구조로 처음부터 재설계.

---

## 1. 목표

- 10+ 브랜드 SaaS 스케일에서 동작 가능한 데이터 모델
- 신규 브랜드 도입 비용 최소화 (10~15분 셋업)
- 어제 광고티 결과를 정면으로 푸는 슬롯 합성 구조
- 페르소나·AI 변주를 leverage 해 프리셋 수를 폭발시키지 않으면서도 다양성 확보

## 2. 결정 요약

| 항목 | 결정 |
|---|---|
| 운영 규모 | 10+ 브랜드 SaaS 스케일 (Q2: c) |
| 운영 주체 모델 | 미결 — super-admin 으로 시작, 멀티테넌시 마이그레이션 가능하게 설계 (Q3: d) |
| 프리셋 위치 | 글로벌 프리셋 + 브랜드 voice 런타임 합성 (Approach 2, Q5: a) |
| 영상 검색 키워드 위치 | Niche 종속 (현재 `Keyword` 엔티티 그대로 유지, Q6: b) |
| 다중 제품 관리 | Product 별도 엔티티 — Brand 1:N Product 1:N Niche (Q7-1: b) |
| 슬롯 템플릿 형식 | 의도 설명 + tone_anchor + 슬롯별 mention 정책 (Q8: B + anchor) |
| 운영 review 게이트 | **없음** — 자동화. 안전망 6개에 의존. |

## 3. 데이터 모델

### 3.1 Global Layer (브랜드 무관)

#### `GlobalPreset` (기존 `CommentPreset` 변형)
| 필드 | 의미 |
|---|---|
| `name` | 예: "F5 산후 자기답글" |
| `description` | 흐름 설명 |
| `flow_type` | F1 단발 / F2 Q&A / F4 트렌 / F5 자기답글 / F7 의심→오픈 / ... |
| `audience_hint` (JSON list) | `["postpartum", "menopause", ...]` — 매칭 추천용 |
| `is_global` | 항상 `True` (강제) |
| `slots` | `Slot[1..N]` |

#### `Slot` (기존 `CommentTreeSlot` 변형)
| 필드 | 의미 |
|---|---|
| `slot_label`, `position`, `reply_to_slot_label`, `same_account_as_slot_label` | 기존 그대로 |
| **`intent`** | 의도 설명 텍스트. 구체 카피 X. 예: "[메인·고민형] 영상 주제에 공감, 본인 입장에서 자연 토로. 제품/솔루션 언급 X" |
| **`tone_anchor`** (JSON list) | 톤 참고용 1-2개 예시. 어휘 그대로 쓰지 말 것 명시. |
| **`mention_brand`** (bool) | 이 슬롯에서 브랜드명 직접 노출 허용 여부 |
| **`mention_solution`** (bool) | 이 슬롯에서 솔루션 카테고리/성분 노출 허용 여부 |
| `length`, `emoji`, `ai_variation` | 기존 그대로 (ai_variation 권장 70~90) |
| `like_min`, `like_max`, `like_distribution` | 기존 그대로 |

**제거 컬럼**: `text_template` (구체 카피는 운영자가 못 박지 않음. AI 가 매번 생성)

#### `GlobalAdPhraseBlocklist`
| 필드 | 의미 |
|---|---|
| `phrase` | 광고 카피 어휘 |
| `added_by` | 운영자 user_id |
| `added_at` | 등록 시각 |

운영 누적용. 시드 비어있음 (운영자가 다중 브랜드 운영하며 발견된 공통 광고티 어휘 누적).

---

### 3.2 Tenant Layer

#### `Brand` (기존 변형)
| 필드 | 의미 |
|---|---|
| `name` | 회사명 |
| `category` | 영양제 / 식품 / 화장품 / 패션 / ... |
| `tone_guide` | 자유 텍스트 (회사 전반 톤) |
| `banned_keywords` (JSON list) | 회사 추가 + global blocklist 자동 상속 |
| `company_protected_terms` (JSON list, optional) | 회사명 등 |

**제거 컬럼**: `product_name`, `product_category`, `core_message`, `mention_rules`, `selling_points`, `allowed_keywords` (모두 Product 로 이동)

#### `Product` (신규)
| 필드 | 의미 |
|---|---|
| `brand_id` (FK) | 소속 회사 |
| `product_name` | 예: "모렉신" |
| `protected_terms` (JSON list) | 표기 lock — `["모렉신", "체성케라틴"]` (어제 lock 그대로) |
| `core_keywords` (JSON list) | AI 슬롯의 "[핵심키워드]" 자리 substitution — `["체성케라틴", "케라틴", "모근 단백질"]` |
| `description`, `core_message` | 제품 설명 |

#### `Niche` (기존 변형)
| 필드 | 의미 |
|---|---|
| `product_id` (FK) | 소속 제품 (기존 brand_id 도 유지 — denorm) |
| `name` | 예: "산후맘" |
| `target_audience` | 자유 텍스트 |
| `mention_intensity` (0~100) | 광고티 강도. system prompt 에 "이 니치는 노출 강도 N/100 — N 낮을수록 공감/정보 톤 우선, 높을수록 직접적 추천 톤 허용" 형태로 주입. 기본 40. |
| `voice_override` (JSON, optional) | niche 만의 톤 추가/금지어 추가 |
| `keywords[]` | 기존 `Keyword` 엔티티 (변경 없음) — 영상 검색용 |
| `personas[]` | 페르소나 풀 |
| `selected_presets` | `NichePresetSelection` (N:M, with weight) |

**제거 컬럼**: `comment_preset_id` (1:1 FK 제거, N:M 으로 대체)

#### `NichePresetSelection` (신규 join)
| 필드 | 의미 |
|---|---|
| `niche_id` (FK) | |
| `preset_id` (FK GlobalPreset) | |
| `weight` (int) | 사용 가중치 (캠페인 enqueue 시 영상별 프리셋 선택 분포) |
| `enabled` (bool) | |

#### `Keyword` (기존 그대로)
변경 없음. `niche_id` + `brand_id` (denorm) 유지.

#### 변경 없음
- `Account`, `Persona` (관계 변경 없음)
- `Task`, `CampaignVideo` (어제 slot_engine 컬럼 유지)
- `Campaign` (어제 추가한 `comment_preset_id` 컬럼은 새 `NichePresetSelection` 흐름에서 미사용 — deprecate)

---

## 4. 런타임 합성 — 슬롯 1개 system prompt 빌드

```
[Global layer]
  - Slot.intent
  - Slot.tone_anchor (참고만, 어휘 베끼지 X)
  - Slot.length / emoji / mention_brand / mention_solution
  - GlobalAdPhraseBlocklist 어휘 (validator 입력)

[Brand layer]
  - Brand.tone_guide
  - Brand.banned_keywords (+ global blocklist 자동 상속)
  - Brand.company_protected_terms

[Product layer] (slot.mention_brand=True 또는 mention_solution=True 인 경우)
  - Product.product_name
  - Product.protected_terms (validator 강 lock)
  - Product.core_keywords (intent 의 [핵심키워드] substitution 후보)

[Niche layer]
  - Niche.target_audience
  - Niche.mention_intensity (의도 해석 가중치)
  - Niche.voice_override

[Persona layer]
  - 슬롯에 할당된 account.persona JSON (나이/성별/지역/직업/말투)

[Conversation layer]
  - parent_task.text (부모 댓글 — 답글 슬롯만)
  - 형제 슬롯 텍스트 (중복 회피)
```

→ AI 가 매번 6 layer 합성 prompt 받아 새로 작성. ai_variation 70~90.

---

## 5. 운영 흐름 (UX)

### 5.1 신규 브랜드 온보딩 (총 10~15분)

```
Step 1. Brand 등록 (1분)
  - name, category, tone_guide, banned_keywords (회사 추가)

Step 2. Product 등록 (제품당 2~3분)
  - product_name, protected_terms, core_keywords, description

Step 3. Niche 등록 (니치당 5분)
  - name, product_id, target_audience, mention_intensity
  - Keyword 시드 3-5개 입력 → AI 자동 long-tail 확장 → 운영자 검토
  - Persona 자동 생성 (persona_agent, target_audience 기반 100명) → 운영자 검토·삭제
  - 글로벌 프리셋 audience_hint 매칭 자동 추천 → 가중치 슬라이더로 선택
```

### 5.2 캠페인 생성 (1분)

```
1. Niche 선택
2. 영상 자동 매칭 (Niche.keywords 로 수집된 영상 풀에서 점수·신선도·중복 회피 필터)
3. 캠페인 enqueue
   - 영상마다 NichePresetSelection.weight 로 프리셋 1개 랜덤 선택
   - 슬롯 엔진(어제 작성) 으로 Task 생성
4. 텍스트 자동 생성 (generate_texts_for_campaign)
   - 슬롯별 6 layer 합성 → AI 호출
   - 자동 안전망 통과 → status=ready (자동)
5. 워커 fetch → 게시
```

### 5.3 자동 안전망 (게이트 X, 안전망 O)

| 안전망 | 어디서 | 운영자 책임 |
|---|---|---|
| 표기 lock | `Product.protected_terms` | 신규 제품 등록 시 정확히 |
| 알려진 오타 자동 교정 | autocorrect | 코드 (모렙신→모렉신 등) |
| banned 카피 | `Brand.banned_keywords` + global blocklist | 운영하며 누적 |
| mention 정책 | `Slot.mention_brand` / `Slot.mention_solution` | 글로벌 프리셋 작성 시 정확히 |
| ai_variation | `Slot.ai_variation` 70~90 | 글로벌 프리셋 작성 |
| mention_intensity | `Niche.mention_intensity` | 니치별 광고티 강도 |
| 페르소나 다양성 | `Niche.personas[]` 100+ | persona_agent 자동 생성 + 검토 |

### 5.4 모니터링 대시보드 (사후 샘플 점검, 게이트 X)

```
대시보드:
  - 최근 24h 게시 댓글 샘플 50개 (랜덤)
  - validator retry 횟수 통계 (니치별)
  - autocorrect 발생 통계
  - "광고티" 클릭 시 텍스트+슬롯+페르소나+캠페인 표시
       → 다음 운영 룰에 활용 (banned 추가, mention_intensity 조절)
```

---

## 6. 다양성 전략 — 프리셋 폭발 회피

```
다양성 = 프리셋 다양성  ×  페르소나 다양성  ×  AI 변주 다양성
```

| 축 | 시작 | 1년 후 | 통제 위치 |
|---|---|---|---|
| 글로벌 프리셋 | 10~15 | 30~50 | 운영자 |
| 페르소나 (브랜드당) | 30~50 | 100~200 | persona_agent 자동 + 운영자 검토 |
| AI 변주 | `ai_variation=70~85` | `80~90` | Slot 필드 |

**프리셋 100+ 절대 비추천**. 페르소나/voice 다양화 leverage 가 훨씬 큼.

---

## 7. 마이그레이션

| 현재 | 새 구조 | 작업 |
|---|---|---|
| `Brand.product_name` | `Product.product_name` | alembic: products 테이블 + Brand row 마다 Product 1개 자동 생성 |
| `Brand.product_category` | `Brand.category` | 컬럼 rename |
| `Brand.allowed_keywords` | `Product.core_keywords` | 데이터 이전 |
| `Brand.mention_rules` JSON | `Slot.mention_brand` + `Slot.mention_solution` | 글로벌 프리셋 새로 작성 시 결정 |
| `Niche.comment_preset_id` (1:1) | `NichePresetSelection` (N:M with weight) | 새 join 테이블 |
| `CommentPreset.is_global` | `True` 강제 | 모렉신 9개 deprecate |
| `CommentTreeSlot.text_template` | `intent` + `tone_anchor` + `mention_*` | 슬롯 재작성 |
| `Keyword`, `Account`, `Task` | 변경 없음 | — |

**모렉신 9 프리셋(어제 작성) 은 deprecate**. 의도 설명형으로 새로 작성 (PR-C).

---

## 8. 후속 PR 시퀀스

```
PR-F: 어제 슬롯 엔진 (Phase A~D) prod 머지·배포  ← 즉시 가능, 다른 PR 과 병렬

PR-A: 데이터 모델 (alembic + 모델)
   - Product 테이블 신설
   - Brand 컬럼 정리
   - Niche.product_id, NichePresetSelection
   - CommentTreeSlot 컬럼 변경 (intent/tone_anchor/mention_*)
   - GlobalAdPhraseBlocklist

PR-B: 슬롯 엔진·AI agent 업데이트
   - slot_agent 6 layer 합성
   - validator 에 mention 정책 검증
   - tone_anchor "변주 시드 X" 명시

PR-C: 새 글로벌 프리셋 10~15개 작성 (의도 설명형)
   - F1 단발 / F2 Q&A / F4 트렌 / F5 자기답글 / F7 의심→오픈
   - 길이 변형 1~2개씩
   - seed 스크립트

PR-D: 어드민 UI — Brand/Product/Niche 등록 wizard
   - Persona 자동 생성 + 검토
   - Keyword 시드 + AI 확장 검토
   - 글로벌 프리셋 가중치 슬라이더

PR-E: 어드민 UI — 캠페인 + 모니터링 대시보드
   - 영상 자동 매칭, 캠페인 enqueue
   - status=ready 자동
   - 모니터링 대시보드 (사후 샘플)
```

### 진행 추천 순서

```
1주차:
  Day 1   PR-F prod 머지·배포
  Day 2-3 PR-A 데이터 모델
  Day 4-5 PR-B 슬롯 엔진 업데이트

2주차:
  Day 1-2 PR-C 새 글로벌 프리셋
  Day 3-5 PR-D 어드민 wizard

3주차:
  Day 1-3 PR-E 캠페인 + 대시보드
  Day 4-5 모렉신으로 첫 운영 검증 + 안전망 튜닝

4주차+:
  새 브랜드 1개 추가 → SaaS 흐름 검증
```

---

## 9. 미해결 / 후속 결정

- **멀티테넌시 권한 모델** — Q3 미결. PR-A 의 데이터 모델은 brand 단위 격리 가능하게 두고, 인증/RBAC 은 후속 PR.
- **persona_agent 품질 검증** — niche.target_audience 받아 100명 자동 생성. 결과 다양성·자연성 검증 필요 (PR-D 안에서).
- **글로벌 프리셋 사용 통계** — 어떤 프리셋이 잘 먹는지 데이터 추적 → 운영자가 가중치 조정 (PR-E 또는 후속).
- **모렉신 9 프리셋 → 의도 설명형 변환** — PR-C 의 일부. 운영자 = 본인이 직접 작성 (광고티 안 나는 의도 설명).
- **Campaign.comment_preset_id 컬럼 처리** — 어제 추가했지만 새 흐름에서 미사용. PR-A 에서 deprecate 또는 제거.

---

## 10. 결정 로그

| Q | 답 |
|---|---|
| Q1. 가장 큰 통증 | 광고티 + 신규 브랜드 도입 비용 + UI 흐름 + 운영 시 헷갈림 + 데이터 모델 모두 (a~e) |
| Q2. 1년 운영 브랜드 수 | 10+ SaaS 스케일 (c) |
| Q3. 운영 주체 모델 | 미결 — super-admin 으로 시작 (d) |
| Q5. 프리셋 위치 | Approach 2 — 글로벌 + 브랜드 voice 런타임 합성 (a) |
| Q6. Niche 위치 | 브랜드 종속 (b), 영상 키워드도 브랜드/니치 종속 |
| Q7-1. 다중 제품 | Product 별도 엔티티 (b) |
| Q7. Brand voice profile | Brand=회사 voice (tone_guide + banned_keywords + company_protected_terms), Product=제품 표기·키워드 분리. 추가 필드(mention_intensity 등)는 Niche 레벨로. |
| Q8. 슬롯 템플릿 형식 | 의도 설명 + tone_anchor + slot 별 mention 정책 (B + anchor) |
| Review 게이트 | 없음, 자동 안전망 6개에 의존 |
| 광고 카피 어휘 자동 banned | 시드 비움. 운영자가 운영하며 누적. ("확실히/직접 보충" 도 도메인에 따라 OK) |
