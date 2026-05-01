# PR-8a — 사이드바 IA + scope bar + rename

**위험**: ★ (시각 변화, DB 변경 0)
**예상**: 1.5h
**의존**: 없음

---

## 목표

운영자 일상 동선에 맞춰 사이드바 그룹 재구성. 브랜드 격리 의도 명시 (scope bar). "시장" 용어 폐기 → "타겟".

---

## 변경

### 1. 사이드바 IA — 3 그룹

```
[브랜드 스위처 ▾]   ← 최상단 (모렉신 / 천명연구소 / +새 브랜드)

지금
  ├ 피드           (default landing)
  ├ 문제 (3)       (배지 = 빨간불 카운트)
  └ 예정

자산
  ├ 타겟           (rename: 시장 → 타겟)
  ├ 캠페인
  ├ 영상
  ├ 프리셋
  └ 키워드

안전
  ├ 워커
  ├ 로그
  └ 설정
```

기존 3 그룹 (홈/제품운영/인프라) 폐기. "대시보드" / "시작하기" / "작업" / "제품" / "계정" / "아바타" / "감사 로그" → 위 새 그룹으로 재배치 + rename.

### 2. 매핑

| 기존 | 신규 | 비고 |
|---|---|---|
| 대시보드 (/) | 피드 (/feed) | landing 변경, /feed 는 PR-8b |
| 시작하기 (/onboarding) | (제거) | 신규 가입 시만 자동 (PR-8a 범위 X) |
| 작업 (/tasks) | 예정 (/queue) | rename + URL 변경, /queue 는 PR-8b |
| 제품 (/products) | 타겟 (/targets) | URL + 용어 둘 다 |
| 계정 (/accounts) | 워커 하위 또는 별도 | PR-8a 는 보존 |
| 아바타 (/avatars) | (안전 그룹 또는 별도) | PR-8a 는 보존 위치만 이동 |
| 감사 로그 (/audit) | 로그 (/logs) | rename, URL 보존 |
| 워커 (/workers) | 워커 (그대로) | 그대로 |
| 설정 (/settings) | 설정 (그대로) | 그대로 |

### 3. 브랜드 스위처 (사이드바 최상단)

- 현재 활성 브랜드 표시 (드롭다운)
- 브랜드 변경 시 모든 페이지 자동 리로드 (URL query `?brand=N` 또는 localStorage `hydra_active_brand`)
- "+ 새 브랜드" 옵션 → BrandFormDialog (mode='create')

### 4. Scope bar (모든 페이지 상단)

페이지 헤더 바로 아래:

```
┌──────────────────────────────────────────────┐
│  [모렉신 ▾]  탈모 케어 · 시장 2개 · 작업중 12 │
└──────────────────────────────────────────────┘
```

- 운영자가 어떤 브랜드 컨텍스트인지 항상 보임
- 클릭 시 브랜드 스위처 펼침 (사이드바 위 동작과 동일)

### 5. 용어 rename

`/lib/i18n-terms.ts`:
- `niche: '시장'` → `niche: '타겟'`
- `pageNiche: '시장'` → `pageNiche: '타겟'`
- `pageProducts: '제품 목록'` → `pageProducts: '제품'` (그대로 유지 또는 폐기?)

⚠️ **DB 컬럼 rename X**: `niches` 테이블, `niche_id` FK, `Niche` 모델, `/api/admin/niches/...` API prefix 모두 보존. UI 표시만 "타겟".

근거: rename 비용 대비 위험 (서비스 5 파일 + 백엔드 + alembic 의존성). UI 매핑만으로 충분.

---

## 변경 파일 (예상)

| 파일 | 변경 |
|---|---|
| `frontend/src/components/layout/data/sidebar-data.ts` | 그룹 재구성 |
| `frontend/src/components/layout/sidebar.tsx` | 브랜드 스위처 추가 |
| `frontend/src/components/layout/scope-bar.tsx` | **신규** |
| `frontend/src/components/layout/authenticated-layout.tsx` | scope bar 마운트 |
| `frontend/src/lib/i18n-terms.ts` | "시장" → "타겟" |
| `frontend/src/lib/active-brand.ts` | **신규** — localStorage 헬퍼 + Context |
| `frontend/src/routes/_authenticated/index.tsx` | landing → /feed redirect (PR-8b 후) 또는 placeholder |

---

## 검증

- tsc / vitest 22 / build 통과
- 함정 보존
- 다른 페이지 시각 변화 = scope bar 추가 (의도)
- 백엔드 / DB 변경 0

---

## Out of scope (PR-8a)

- /feed / /alerts / /queue 페이지 콘텐츠 (PR-8b)
- 브랜드 스위처의 멀티 브랜드 자동 동기화 (URL/localStorage 충돌 시 PR-8a-followup)
- 키워드 별도 페이지 (현재 타겟 디테일 안에 있음, PR-8a 는 사이드바 항목만)

---

## 자율 결정 영역

- A. 사이드바 그룹 헤더 시각 (제목 굵기, spacing)
- B. 브랜드 스위처 디자인 (Combobox / DropdownMenu)
- C. scope bar 의 색감 (subtle border 또는 muted background)
- D. landing redirect (PR-8b 머지 전엔 /products 또는 placeholder 안내)
