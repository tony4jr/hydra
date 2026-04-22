# HYDRA 설계 문서 Index

> 이 폴더의 문서들이 어떤 역할을 하는지, 언제 어떤 걸 읽고 업데이트해야 하는지 정리. **혼선 방지용 지도.**

---

## 📐 문서 계층

```
docs/superpowers/
  ├── README.md               ← 👉 지금 읽는 이 파일 (Index)
  │
  ├── specs/                  ← 🏛️ 설계 문서 (SPEC) — "왜 이렇게 짜는지"
  │   ├── 2026-04-16-*.md     ← Phase 0 ~ 기존 설계 (과거)
  │   ├── 2026-04-17-*.md     ← 브라우저 자동화 / UI 재설계
  │   ├── 2026-04-18-*.md     ← 프로필 생성 / IP 로테이션
  │   ├── 2026-04-21-*.md     ← 온보딩 verifier (완료됨)
  │   │
  │   └── 2026-04-22-*        ← 🔥 현재 진행 중: 배포 아키텍처
  │       ├── deployment-architecture-design.md      (기술 명세, 639줄)
  │       └── deployment-architecture-overview.md    (1페이지 시각 요약)
  │
  └── plans/                  ← 🔨 구현 계획 (PLAN) — "실제 task 단위로 어떻게 짜는지"
      ├── 2026-04-16-01 ~ 03  ← 기존 구현 (완료)
      ├── 2026-04-17, 18, 21  ← 브라우저 / IP / 온보딩 구현 (완료)
      │
      └── 2026-04-22-*        ← 🔥 현재 진행 중: Phase 1 구현
          ├── phase1-vps-server-setup.md    (45 task 상세 plan)
          └── phase1-overview.md            (1페이지 시각 로드맵)
```

---

## 🗺️ 어떤 문서 언제 보는지

### 질문: "왜 이렇게 설계했지?"
→ **spec 문서** (`specs/2026-04-22-deployment-architecture-design.md`)
- 아키텍처 결정의 근거
- 리스크 분석 + 완화책
- 미래 확장 고려 (D 단계)
- 639줄 — 긴 문서

### 질문: "시스템 어떻게 생겼는지 빨리 보고 싶어"
→ **overview 문서** (`specs/2026-04-22-deployment-architecture-overview.md`)
- 시각적 다이어그램 중심
- 하루의 흐름 시나리오
- 용어집 + FAQ
- 1페이지 완결

### 질문: "실제로 어떤 파일 만들고 어떤 코드 짜야 해?"
→ **상세 plan** (`plans/2026-04-22-phase1-vps-server-setup.md`)
- 45 task, 각 task 마다 파일 경로 + 코드 + 검증 명령
- TDD 형식 (실패 테스트 → 구현 → 통과 → commit)
- 3300+ 줄 — 구현 시 참조

### 질문: "Phase 1 전체 얼마나 걸리지? 어디쯤 있지?"
→ **plan overview** (`plans/2026-04-22-phase1-overview.md`)
- 5 sub-phase 타임라인
- 체크포인트
- 의존성 그래프
- 1페이지 시각 로드맵

---

## 🔄 문서 업데이트 규칙 (혼선 방지)

### ① **Spec vs Plan 의 경계**
- **Spec 변경** = 설계 결정이 바뀔 때 (예: "VPS → AWS 로 변경")
- **Plan 변경** = 구현 디테일이 바뀔 때 (예: "Task 15 에 Step 추가")
- Spec 과 Plan 이 **서로 모순되면 Spec 이 진실**

### ② **한 변경은 한 커밋**
예시:
- ✅ `docs: 워커 특화 추가 (spec + overview + plan 동시 커밋)`
- ❌ spec 만 먼저 커밋하고 plan 은 나중에 (일시적 불일치 → 혼선)

### ③ **파일 간 링크 유지**
- overview 는 spec 을 참조 (`See [design](./design.md)`)
- plan overview 는 plan 을 참조
- plan 은 spec 을 참조
- 파일 이름 바꾸면 **링크 전부 업데이트**

### ④ **완료된 문서에 "완료" 표시**
예: `2026-04-21-onboarding-verifier.md` — 구현 완료됨
→ 파일 상단에 `> **Status: ✅ 구현 완료 (2026-04-22)**` 추가

### ⑤ **새 Phase 나 기능 추가 시**
새 spec 시작 전 이 README 의 계층도와 "어떤 문서 언제 보는지" 섹션 업데이트.

---

## 📅 현재 활성 작업 (2026-04-22 기준)

| 주제 | 상태 | 문서 |
|---|---|---|
| 온보딩 verifier | ✅ 완료 (50계정 중 45 warmup) | `specs/2026-04-21-*`, `plans/2026-04-21-*` |
| **배포 아키텍처** | 🔥 **설계 완료, 구현 대기** | `specs/2026-04-22-*`, `plans/2026-04-22-*` |
| 계정 자동 생성 | ⏳ 설계 미정 (Phase 2 이후) | TBD |
| 댓글 워크플로우 | ⏳ 설계 미정 (Phase 3 이후) | TBD |
| UI/UX 재설계 (토스 수준) | ⏳ 보류 (Phase 1 완료 후) | `specs/2026-04-17-ui-ux-redesign.md` 참고 |

---

## 🎯 추천 읽는 순서

### 🆕 새로 합류한 개발자
1. `specs/2026-04-22-deployment-architecture-overview.md` (15분 — 큰 그림)
2. `plans/2026-04-22-phase1-overview.md` (10분 — 구현 로드맵)
3. 필요 시 세부 spec / plan 파고들기

### 🔧 지금 구현하러 온 사람
1. `plans/2026-04-22-phase1-overview.md` (체크포인트 확인)
2. `plans/2026-04-22-phase1-vps-server-setup.md` (task 시작)
3. 막히면 `specs/*.md` 근거 확인

### 🤔 설계 근거 궁금한 사람
1. `specs/2026-04-22-deployment-architecture-design.md` (섹션별로)
2. 관련 과거 spec 들 참고

---

## 🛠️ 로컬에서 보기 편하게 서버로 띄우기

```bash
source .venv/bin/activate
python scripts/serve_docs.py 8765
# 브라우저: http://localhost:8765
```

GitHub 스타일 다크 테마로 전 문서 렌더링 + 카드 뷰.

---

## 🧭 미래 확장 시 이 README 업데이트

새 설계 문서 추가할 때:
1. 이 README 의 계층도에 추가
2. "현재 활성 작업" 테이블 업데이트
3. 구 버전 파일이 있으면 "완료" 표시
