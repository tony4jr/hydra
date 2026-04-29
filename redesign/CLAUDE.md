# CLAUDE.md — HYDRA 어드민 재설계 컨텍스트

이 문서는 HYDRA 어드민 UI/UX 재설계 작업 전체에서 공유되는 컨텍스트입니다. PR 1~7 모든 작업에서 이 문서를 먼저 읽고 시작하세요.

---

## 1. 프로젝트 비전

HYDRA는 운영자 1명이 100~1000개의 YouTube 계정을 자동 운영해서 타겟 영상에 자연스러운 댓글을 대량으로 다는 여론 형성 시스템입니다. 백엔드와 워커는 거의 완성됐고, 어드민 UI를 운영자 멘탈모델에 맞게 재설계하는 것이 이번 작업의 목표입니다.

**최종 지향점은 SaaS화**입니다. 처음 사용하는 사람도 0→1 운영을 시작할 수 있어야 합니다.

---

## 2. 핵심 문제 진단 (현재 UI의 한계)

1. 같은 정보가 여러 페이지에 흩어져 있음 (브랜드 폼 + 타겟 페이지에 수집 정책이 이원화)
2. 사이드바 12개 메뉴가 운영 흐름이 아닌 명사 나열로 구성됨
3. 개발자 용어가 UI에 노출됨 (Phase 1, L tier, embedding score 등)
4. 작업 간 흐름 추적이 불가능 (영상 1개가 어떤 단계를 거쳤는지)
5. 분석 페이지가 비어있음 (운영의 피드백 루프 없음)
6. Brand 1계층 구조가 다중 시장 운영을 표현 못함

---

## 3. 새 정보 구조 (IA)

### 3.1 사이드바 — 3그룹 9페이지

```
홈
  └ 운영 현황 (전체 파이프라인 흐름)

제품 운영
  ├ 제품 목록 (Brand + Niche 트리)
  ├ 시장 상세 (Niche 페이지, 5탭)
  ├ 캠페인 통합 보기 (시장 가로지른 비교)
  ├ 영상 통합 보기 (영상 1개의 인생 추적)
  └ 작업 큐 (실시간 task 모니터링)

인프라
  ├ 계정 풀
  ├ 작업 PC (워커 + 에러 + IP 통합)
  ├ 아바타·페르소나
  └ 시스템 설정 (API 키 + 알림 + 보호 룰 + 감사 로그)
```

### 3.2 데이터 모델 변경 — Brand → Niche 계층 도입

```
Brand (제품/회사 식별 정보만 — 가벼움)
  └─ Niche (시장) ★ 신설
       ├ 키워드 정책 (긍정/부정 + 폴링 주기)
       ├ 시장 정의 텍스트 + 임베딩 임계값
       ├ 우선순위 분류 임계값
       ├ 톤 가이드 + 페르소나 슬롯
       └─ Campaign
            └─ Video, Task (기존 그대로)

Tag (자유 태그) ★ 신설
  └ Niche 또는 Campaign에 N:M으로 붙음
  └ 사용자가 정의 (예: 시장=한국, 시즌=봄, 각도=의학신뢰)
```

핵심: 한 Brand에 여러 Niche를 둘 수 있고, 각 Niche가 독립된 운영 단위입니다. 자유 태그로 교차 분석이 가능합니다.

---

## 4. 디자인 원칙 (5개)

모든 페이지가 이 원칙을 지켜야 합니다.

### 4.1 시각적 위계 = 사용 빈도 + 권한
- 매일 만지는 것: 펼쳐진 메인 영역
- 가끔 만지는 것: 접힌 고급 폴드 (`Collapsible`)
- 못 만지는 것: 회색 정보 표시

### 4.2 설정은 즉시 결과 시뮬레이션
- 슬라이더 움직이면 → 경계선 영상 카운트/제목 변화
- 키워드 추가하면 → 통과율 미리보기
- 추상 숫자 노출 금지, 항상 실제 데이터로

### 4.3 자동 작업의 "왜?" 항상 표시
- 탈락 영상은 사유 표시 (시장 부적합 / 제외 키워드 / 시스템 룰)
- 작업 안 됨도 사유 표시
- 운영자가 시스템을 디버깅 가능해야 함

### 4.4 운영자 용어 + 안전 디폴트 + 복원 가능
- 개발자 용어 추방 (용어 매핑표 §6 참조)
- 모든 설정에 합리적 디폴트
- "기본값으로 복원" 버튼

### 4.5 한 작업의 모든 정보는 한 화면에
- "왜 안 됐지?" 답이 다른 페이지에 있으면 안 됨
- 시장 페이지 안에 시스템 룰도 정보용으로 표시
- 영상 타임라인에 모든 이벤트 한 줄로

---

## 5. 기술 스택

### 백엔드
- FastAPI (async)
- PostgreSQL 15 (prod) / SQLite (dev)
- SQLAlchemy 2.0 + Alembic
- uvicorn
- Anthropic SDK (Claude Sonnet 4.6 / Haiku 4.5)

### 프론트엔드
- React 19 + Vite 5
- TypeScript (strict)
- TanStack Router (file-based routing)
- TanStack Query (서버 상태)
- Tailwind CSS 4 + shadcn/ui
- pnpm (npm/yarn 아님)
- Zod + react-hook-form
- Sonner (toast), Lucide (icons)

### 인프라
- Ubuntu 22.04 VPS, nginx, systemd
- GitHub 단일 main 브랜치, 60초 auto-pull
- Cloudflare/duckdns

---

## 6. 용어 매핑 (개발자 → 운영자)

UI 표시 문자열만 변경하고, 코드 내부 식별자(DB 컬럼명, API 필드명, 변수명)는 유지합니다. 코드 변경 최소화 원칙.

| 코드 내부 (유지) | UI 표시 (변경) |
|---|---|
| `phase_1`, `phase_2` | (UI에서 노출하지 않음) |
| `lifecycle_phase=1` | "신규 영상" |
| `lifecycle_phase=2` | "활성" |
| `lifecycle_phase=3` | "안정" |
| `lifecycle_phase=4` | "장기" |
| `tier=L1` | "장기 자산" |
| `tier=L2` | "신규" |
| `tier=L3` | "트렌딩" |
| `tier=L4` | "롱테일" |
| `embedding_score` | "시장 적합도" |
| `embedding_reference_text` | "시장 정의" |
| `hard_block_rules` | "자동 제외" |
| `ghost_detection` | "댓글 생존 검증" |
| `ghost_count` | "삭제된 댓글 수" |
| `quota` | "API 사용량" |
| `worker` | "작업 PC" |
| `account_limits` | "계정 일·주 한도" |
| `video_protection` | "영상 보호 룰" |
| `priority=high/normal/low` | "우선순위 높음/보통/낮음" |
| `state=active/paused/blocked/retired` | "활성/일시정지/차단/은퇴" |
| `preset_a` ~ `preset_j` | 의미 있는 이름 (시드, 질문 유도, 동조 등 — 기존 매핑 유지) |
| `topic` | "분야" (아바타에서) |
| `niche` ★ 신규 | "시장" |
| `tag` ★ 신규 | "태그" |

번역 헬퍼는 `frontend/src/lib/i18n-terms.ts`에 단일 파일로 둡니다.

---

## 7. 프로젝트 구조

```
hydra/                        # 백엔드 루트
├── core/                     # config, crypto, scheduler
├── db/
│   ├── models.py             # SQLAlchemy 모델 (이번 작업으로 Niche, Tag 추가)
│   └── session.py
├── ai/agents/                # comment_agent, persona, keyword_expander
├── services/                 # 비즈니스 로직 (task_service, video_pipeline 등)
├── web/                      # FastAPI app + routes
│   └── routes/
│       ├── brands.py
│       ├── niches.py         # ★ 신규
│       ├── tags.py           # ★ 신규
│       ├── campaigns.py
│       ├── videos.py
│       ├── keywords.py
│       └── ...
├── api/                      # 워커 API
└── infra/

worker/                       # 워커 PC

frontend/                     # React 어드민
├── src/
│   ├── routes/               # TanStack Router file-based
│   │   ├── __root.tsx
│   │   ├── index.tsx                       # 홈 (운영 현황)
│   │   ├── products/
│   │   │   ├── index.tsx                   # 제품 목록
│   │   │   └── $brandId/
│   │   │       └── niches/
│   │   │           └── $nicheId/
│   │   │               ├── index.tsx       # 시장 개요
│   │   │               ├── collection.tsx  # 수집 탭
│   │   │               ├── messaging.tsx   # 메시지 탭
│   │   │               ├── campaigns.tsx   # 캠페인 탭
│   │   │               └── analytics.tsx   # 분석 탭
│   │   ├── campaigns/index.tsx             # 캠페인 통합
│   │   ├── videos/
│   │   │   ├── index.tsx                   # 영상 통합 검색
│   │   │   └── $videoId.tsx                # 영상 타임라인
│   │   ├── tasks/index.tsx                 # 작업 큐
│   │   ├── infra/
│   │   │   ├── accounts.tsx
│   │   │   ├── workers.tsx
│   │   │   ├── avatars.tsx
│   │   │   └── settings.tsx
│   │   └── ...
│   ├── components/
│   │   ├── ui/               # shadcn/ui 기본
│   │   ├── shared/           # 도메인 공통 (StatCard, PipelineFlow 등)
│   │   └── niche/            # 시장 페이지 전용
│   ├── lib/
│   │   ├── api.ts            # fetch wrapper
│   │   ├── queries.ts        # TanStack Query hooks
│   │   ├── i18n-terms.ts     # 용어 매핑 헬퍼
│   │   └── utils.ts
│   └── types/                # API 응답 타입 (Zod schema)
└── ...

alembic/                      # DB 마이그레이션
deploy/                       # systemd
scripts/                      # bootstrap, deploy
```

---

## 8. 코딩 컨벤션

### 백엔드
- 모든 endpoint는 async
- Pydantic v2 schema로 request/response 검증
- 에러는 `HTTPException`보다 도메인 예외 → 미들웨어에서 변환 권장 (현재 패턴 유지)
- DB 변경은 반드시 Alembic 마이그레이션으로
- 운영 중 시스템: 무중단 마이그레이션, 컬럼 삭제 금지 (deprecate만)
- 새 테이블은 nullable FK로 시작해서 백필 후 NOT NULL 전환

### 프론트엔드
- 모든 컴포넌트는 함수 컴포넌트
- 서버 상태는 TanStack Query, 클라이언트 상태는 useState/useReducer
- 폼은 react-hook-form + Zod
- 토스트는 Sonner (`toast.success`, `toast.error`)
- 새 컴포넌트는 shadcn/ui 우선 → 없을 때만 직접 작성
- Tailwind만 사용 (별도 CSS 파일 금지, 단 Tailwind config 확장은 가능)
- 폴더당 `index.tsx` 패턴 (TanStack Router 규칙)
- 모든 fetch는 `lib/api.ts` wrapper 통해
- API 응답은 Zod로 parse → 타입 추론

### 공통
- 함수·변수: camelCase (TS), snake_case (Python)
- 컴포넌트: PascalCase
- 한국어 주석은 그대로 유지 (운영자 도큐먼트화)
- 커밋 메시지: `feat(niche): ...`, `fix(api): ...` (Conventional Commits)

---

## 9. 작업 순서 (PR 7개)

각 PR은 별도 문서로 상세 명세가 있습니다. 의존성에 따른 순서:

1. **PR-1** — 용어 정비 (i18n 헬퍼 + UI 라벨 일괄 교체)
2. **PR-2** — 홈 파이프라인 흐름 (대시보드 교체)
3. **PR-3** — Niche 모델 신설 + 마이그레이션 (DB 변경 ★ 위험)
4. **PR-4** — 시장 상세 5탭 페이지 (가장 큰 작업)
5. **PR-5** — 영상 통합 보기 + 타임라인
6. **PR-6** — 자유 태그 + 캠페인 통합 보기
7. **PR-7** — Onboarding wizard + AI 도우미

각 PR 시작 전에 해당 PR 문서의 §의존성 항목을 확인하고 선행 PR이 머지된 상태인지 확인하세요.

---

## 10. 안전 가이드 (운영 중 시스템)

이 시스템은 이미 운영 중이고 데이터를 날리면 안 됩니다.

### DB 마이그레이션 룰
1. 모든 마이그레이션은 Alembic으로
2. 새 컬럼은 nullable로 추가 → 백필 → NOT NULL (3단계)
3. 기존 컬럼 삭제 금지 (deprecate 후 다음 메이저에서)
4. PR-3 마이그레이션은 staging에서 prod 데이터 dump로 dry-run 필수
5. 롤백 스크립트 반드시 제공

### API 호환성
1. 기존 endpoint는 PR-3 후에도 작동해야 함 (deprecation 헤더 + 새 endpoint 병행)
2. 응답 schema에 필드 추가는 OK, 삭제는 금지
3. Breaking change는 새 endpoint로 (`/api/v2/...` 또는 새 path)

### 배포
1. 운영자(=user)와 소통 없이 prod에 영향 가는 변경 금지
2. 스테이징 → prod 순서 유지 (현재 구조에 staging 없으면 PR-3 시작 전에 만들기)
3. 한 PR이 한 번의 prod 배포로 끝나야 함

---

## 11. 테스트 전략

### 백엔드
- 모든 신규 endpoint는 pytest 테스트 작성
- 기존 endpoint 변경 시 regression 테스트 추가
- DB 마이그레이션은 `alembic upgrade head && alembic downgrade -1` 양방향 테스트

### 프론트엔드
- 페이지 단위 Playwright E2E (시장 페이지 5탭, 영상 타임라인 등 핵심)
- 컴포넌트 단위 unit test는 복잡한 로직만 (대부분 컴포넌트는 E2E로 충분)
- TanStack Query hook은 mock으로 테스트

---

## 12. 작업 시작 전 체크리스트

각 PR 시작할 때:
- [ ] 이 CLAUDE.md를 읽었는가
- [ ] 해당 PR 문서의 §의존성을 확인했는가
- [ ] 선행 PR이 머지된 상태인가 (해당하는 경우)
- [ ] 운영 데이터 영향이 있는가? 있으면 백업 확인
- [ ] 이 PR의 §완료 정의를 정확히 이해했는가
