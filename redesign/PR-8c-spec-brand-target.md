# PR-8c — 브랜드 설정 + 타겟 디테일

**위험**: ★★ (DB 마이그레이션)
**예상**: 3h
**의존**: PR-8a (사이드바 진입), PR-8h (FavoriteVideo 활용은 PR-8h 후)

---

## 목표

브랜드의 운영 자산 (톤·금지어·핵심 메시지) 을 1 페이지에서 관리. 타겟 디테일에 "이 타겟의 영상" 모음 (점수 정렬) 추가.

---

## 페이지 1: /brands/$brandId/settings (브랜드 설정)

기존 BrandFormDialog 를 풀 페이지로 확장. 다이얼로그는 빠른 편집용으로 보존.

### 섹션

```
┌─ 기본 ────────────────────────┐
│ 이름   [모렉신]                │
│ 산업   [헬스케어 ▾]           │
└──────────────────────────────┘

┌─ 고객층 ──────────────────────┐
│ 연령    [20대][30대][40대]+   │
│ 성별    [남][여]              │
│ 관심사  [탈모, 헤어케어, ...] │
└──────────────────────────────┘

┌─ 톤앤매너 ────────────────────┐
│ ◉ 친근  ○ 전문  ○ 캐주얼  ○ 공감 │
└──────────────────────────────┘

┌─ 핵심 메시지 ─────────────────┐
│ [의학적 신뢰 + 자연 성분]    │
└──────────────────────────────┘

┌─ 자주 쓰는 표현 ──────────────┐
│ + 효과 보고 있어요 [✕]        │
│ + 추천합니다 [✕]              │
└──────────────────────────────┘

┌─ 금지어 ──────────────────────┐
│ + 부작용 [✕]                  │
│ + 광고성 [✕]                  │
└──────────────────────────────┘

┌─ 회피 경쟁사 ─────────────────┐
│ + 미녹시딜 [✕]                │
└──────────────────────────────┘
```

---

## 페이지 2: /products/$brandId/niches/$nicheId (개요 탭 확장)

기존 5탭 (개요/수집/메시지/캠페인/분석) 의 **개요 탭** 에 "이 타겟의 영상" 섹션 추가.

```
[기존 StatCard 4개]
[기존 임계값 요약]
[기존 진행 캠페인]

──── 신규 섹션 ────
이 타겟의 영상 (123)        [점수 ▾] [필터 ▾]
┌────────────────────────────────────┐
│ ⭐ 87점 │ 탈모 30대 자가진단        │
│        │ @건강채널 · 1.2M회        │
│        │ 댓글 3개 깔림              │
├────────────────────────────────────┤
│ ⭐ 81점 │ 두피 마사지 루틴          │
│        │ @헤어 · 230K회            │
├────────────────────────────────────┤
│ 🚫 제외 │ [광고] 신박한 영양제      │
│  (회색) │ 사유: 경쟁사 채널         │
└────────────────────────────────────┘
```

- 점수 정렬 default (PR-8f 의 VideoScore)
- 필터: 작업 중 / 대기 / 제외 / 보호
- 제외된 영상 회색 + 사유 표시

---

## DB 마이그레이션 (alembic)

### Brand 모델 확장

기존 컬럼 일부 (core_message, tone_guide, target_audience, mention_rules) 는 **이미 Brand 에 존재**. PR-3a 가 brand → niche 백필. 이번엔 추가 컬럼.

```python
op.add_column('brands', sa.Column('industry', sa.String(60)))
op.add_column('brands', sa.Column('tone', sa.String(20)))  # 친근/전문/캐주얼/공감
op.add_column('brands', sa.Column('common_phrases', sa.Text()))  # JSON array
op.add_column('brands', sa.Column('forbidden_words', sa.Text()))  # JSON array
op.add_column('brands', sa.Column('avoid_competitors', sa.Text()))  # JSON array
op.add_column('brands', sa.Column('target_demographics', sa.Text()))  # JSON {age, gender, interests}
```

7 컬럼, 모두 nullable.

### Niche → 'Target' 표시 변경

DB 컬럼 / 모델 / API rename **X**. UI 만 라벨 변경 (PR-8a 에서 i18n-terms 처리).

이번 PR (8c) 에선 새 페이지 헤더 / 사이드바 항목 모두 "타겟" 사용.

---

## 백엔드

`GET /brands/api/{brand_id}` — 기존 응답에 신규 컬럼 추가:
```json
{
  "id": 2, "name": "...",
  // ...
  "industry": "헬스케어",
  "tone": "친근",
  "common_phrases": ["효과 보고 있어요", ...],
  "forbidden_words": [...],
  "avoid_competitors": [...],
  "target_demographics": {"age": ["30대"], "gender": ["남"], "interests": [...]}
}
```

`PATCH /brands/api/{brand_id}/update` — 신규 7 필드 수용.

타겟 영상 모음:
`GET /api/admin/niches/{niche_id}/videos?sort=score&filter=working|pending|rejected|protected&limit=50`

PR-8f 의 VideoScore 가 있으면 점수순. 없으면 collected_at desc fallback.

---

## 변경 파일

| 파일 | 변경 |
|---|---|
| `alembic/versions/XX_brand_v2_columns.py` | **신규** — 7 컬럼 |
| `hydra/db/models.py` | Brand 클래스 +7 컬럼 |
| `hydra/web/routes/brands.py` | GET / PATCH 응답 확장 |
| `hydra/web/routes/niches.py` | `/{niche_id}/videos` 신규 (sort=score, filter) |
| `frontend/src/features/brands/settings.tsx` | **신규** 풀 페이지 |
| `frontend/src/features/products/niche-tabs/overview.tsx` | "이 타겟의 영상" 섹션 추가 |
| `frontend/src/routes/_authenticated/brands/$brandId/settings.tsx` | **신규** |
| `frontend/src/types/brand.ts` | **신규** 또는 기존 확장 |

---

## 격리 dry-run

PR-3a 패턴:
1. ssh prod dump → local hydra_prod_test_pr8c
2. alembic upgrade
3. accounts 9 row count diff = 0 (절대 원칙)
4. brands +7 컬럼 추가 확인 (모두 NULL default)
5. downgrade → 컬럼 제거 → 재upgrade
6. drop test DB

---

## 검증

- pytest 499 baseline keep
- vitest 22 / build / tsc
- DB: brands 7 컬럼 추가만, 타 테이블 변경 0
- accounts 9 = ALTER 0

---

## Out of scope

- target_demographics 의 자동 추천 (AI helper, PR-7-followup)
- 금지어 매칭 시 즉시 댓글 차단 (PR-8d 프리셋에서 자동 회피)
- 회피 경쟁사 검색 시 자동 제외 (PR-8f 안전필터에서)
