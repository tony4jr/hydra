# PR-8 — HYDRA v2 UX 개편 (마스터)

**상태**: spec 단계, 코드 변경 0
**작성**: 2026-05-01
**선행 PR**: PR-1~PR-7 (모두 merge 됨)
**후속**: PR-8a~h (8 sub-PR)

---

## 배경

PR-7 까지의 redesign 시리즈는 **구조 정리**(Niche/Brand/Tag/Onboarding)를 끝냈다. 그러나 운영자(=본인)가 직접 사용해보니 **운영자의 일상 동선**과 화면이 어긋난다는 본질적 문제가 드러났다.

PR-8 은 그 어긋남을 정합한다. 데이터 모델·페이지 구조·운영 알고리즘을 운영자 멘탈모델 기준으로 재정렬.

---

## 본질

HYDRA 의 본질은 **유튜브 댓글 + 좋아요 화력 마케팅 자동화**다.
- 운영자 일상의 80% = "어제 깐 댓글이 살아있나? 좋아요 몇 개 받았나? 살아남은 댓글로 응대 댓글 더 깔까?" 같은 **결과 확인**.
- 운영자 일상의 20% = 신규 캠페인 만들기 / 프리셋 다듬기 / 타겟 추가.

지금 어드민은 80% 결과 확인 동선이 약하고, 만들기 동선이 더 강하다. 뒤집어야 한다.

---

## 변경 범위 (한 줄 요약)

| 영역 | 변경 |
|---|---|
| 사이드바 IA | 그룹 재구성 (지금/자산/안전), 브랜드 스위처, scope bar |
| 첫 화면 | 대시보드 → 피드 (default landing) |
| 운영 동선 | 피드 / 문제 / 예정 — 결과 확인 중심 |
| 자산 | 브랜드 톤·금지어 / 타겟 디테일·영상 모음 |
| 프리셋 | 전역 라이브러리, 5 기본 시드 |
| 댓글 트리 | 슬롯 (워커 단위, 재등장 ↻), 슬롯별 컨트롤, 미리보기 |
| 영상 점수 | 100점 score + 부스트 + 안전필터 + 롱런 분류 |
| 댓글 추적 | 적응형 + 가치 기반 (영상 단위 진입) |
| 한도 | 영상당 / 채널당 / 워커당 baseline + 자동 조절 |

용어 변경: **"시장" → "타겟"** (UI 표시만, DB 컬럼 rename X — 위험 회피).

---

## 분할 (8 sub-PR)

각 sub-PR 은 독립 머지 가능. spec 별도 파일.

| # | sub-PR | 주제 | 위험 | 추산 |
|---|---|---|---|---|
| 8a | [Sidebar IA](PR-8a-spec-sidebar.md) | 사이드바 + scope bar + rename | ★ | 1.5h |
| 8b | [Feed/Alert/Queue](PR-8b-spec-feed-alert-queue.md) | 피드/문제/예정 신규 페이지 | ★★ | 4h |
| 8c | [Brand/Target](PR-8c-spec-brand-target.md) | 브랜드 톤·금지어 + 타겟 영상 모음 (DB) | ★★ | 3h |
| 8d | [Preset Library](PR-8d-spec-preset-library.md) | 전역 프리셋 + 5 기본 시드 (DB) | ★★★ | 5h |
| 8e | [Comment Tree](PR-8e-spec-comment-tree.md) | 슬롯 편집 UI + AI/좋아요 컨트롤 | ★★★ | 8h |
| 8f | [Video Score](PR-8f-spec-video-score.md) | 100점 + 부스트 + 안전필터 (DB) | ★★ | 4h |
| 8g | [Tracking/Limits](PR-8g-spec-tracking-limits.md) | 적응형 추적 + 영상당 한도 (DB) | ★★★ | 6h |
| 8h | [Favorites](PR-8h-spec-data-model.md) | 영상/채널 즐겨찾기 + 보호 (DB) | ★ | 2h |

총 ~33h. DB 마이그레이션 = 8c, 8d, 8f, 8g, 8h.

---

## 의존성

```
8a (사이드바)
 └→ 8b (피드 — 사이드바 진입점 필요)
8c (브랜드 모델 확장)
 └→ 8d (프리셋 — 브랜드 톤 자동 입힘 의존)
     └→ 8e (댓글 트리 — Preset/CommentTreeSlot)
         └→ 8g (CommentExecution — slot_id FK)
8f (VideoScore) ← 독립
 └→ 8g (한도 검증에서 점수 활용)
8h (Favorites) ← 독립
```

권장 순서: 8a → 8b → 8c → 8d → 8e → 8f → 8h → 8g.

---

## 4중 안전망 (DB 마이그레이션 PR 공통)

PR-8c, 8d, 8f, 8g, 8h:
1. **격리 dry-run**: prod dump → local PostgreSQL `hydra_prod_test_pr8X` → alembic upgrade → accounts-9 row count diff = 0 → downgrade roundtrip
2. **accounts 9 테이블 절대 원칙**: `accounts, account_profile_history, profile_pools, profile_locks, persona_slots, recovery_emails, ip_log, comment_snapshots, action_log` row count 변동 0
3. **ssh 백업 사전**: `pg_dump | gzip > backup_pre_pr8X_*`
4. **Downgrade + 재upgrade 검증**

PR-3a 패턴 그대로.

---

## 운영자 검토 항목 (본 spec PR merge 전)

- [ ] 분할 전략 (8 sub-PR) OK?
- [ ] 데이터 모델 (PR-8h 데이터 모델 종합) OK?
- [ ] 운영 알고리즘 (PR-8f 점수 / PR-8g 추적·한도) OK?
- [ ] 슬롯 편집 UI (PR-8e) 의 자동 라벨링 / ↻ 표시 OK?
- [ ] 누락된 동선 / 추가 짚을 거 있나?

---

## Out of scope (PR-8 시리즈)

- 멀티테넌시 / 결제 / 권한 시스템 (별도)
- AI helper 풀세트 (PR-7-followup, 부분만 PR-8d 의 자동 톤 입힘에 포함)
- 모바일 전용 UI (반응형은 유지, 별도 mobile-first 페이지 X)
- 영상 자동 추가 (수동 + URL 추가만 유지)

---

## 다음 단계

1. 본 spec PR (#XX) merge
2. PR-8a 본 작업 명령 (사용자가 별도 명령으로 시작)
3. 각 sub-PR 의 Phase 1~7 자율 진행
