# PR-8b — 피드 / 문제 / 예정

**위험**: ★★ (신규 페이지 3개)
**예상**: 4h
**의존**: PR-8a (사이드바 진입점)

---

## 목표

운영자 일상 80% (결과 확인) 을 직접 지원하는 3 페이지 신설.

- **피드** = "지금 무슨 일이 일어나고 있나" 보는 default 첫 화면
- **문제** = "당장 손 봐야 할 것" (빨간불만)
- **예정** = "다음 24시간 안에 일어날 작업"

---

## 페이지 1: 피드 (/feed)

### 레이아웃

```
┌─ Scope bar (모렉신) ──────────────────────────┐
│                                              │
│  [최근 1h] [24h] [이번 주] [이번 달] [사용자 지정] │
│  [전체 시장 ▾] [모든 상태 ▾]                  │
│                                              │
│  ┌──────────────────────────────────┐        │
│  │ 14:23 · 댓글 작성 · 모렉신       │        │
│  │ 영상: "탈모 30대..."             │        │
│  │ ▸ 우리 댓글 3개:                 │        │
│  │   - "정말 도움됐어요" (워커 A) 좋아요 12 │  │
│  │   - "감사합니다 :)" (B) 좋아요 5 │        │
│  │   - "추천합니다" (C) 좋아요 0    │        │
│  └──────────────────────────────────┘        │
│                                              │
│  ┌──────────────────────────────────┐        │
│  │ 13:48 · 영상 발견 · 모렉신       │        │
│  │ ...                              │        │
│  └──────────────────────────────────┘        │
└──────────────────────────────────────────────┘
```

### 데이터 소스 (lean)

- `ActionLog` (action_type='comment'/'reply') — 댓글 이벤트
- `Video.collected_at` — 영상 발견 이벤트
- `Campaign` 상태 변경 (created/active/paused) — campaign 이벤트

기존 데이터로 reverse construct. 신규 EventLog 테이블 X (lean, PR-5a 와 동일 패턴).

### 백엔드

`GET /api/admin/feed?window=1h|24h|week|month|custom&niche_id=&status=`

```python
class FeedEvent(BaseModel):
    at: datetime
    kind: Literal["comment_posted", "video_discovered", "campaign_event"]
    actor: str | None  # 워커 / 시스템
    niche_id: int | None
    niche_name: str | None
    video_id: str | None
    video_title: str | None
    metadata: dict  # comment_text / status / etc
```

영상별 그룹핑 (같은 video_id 의 댓글들 묶음).

### 기간 토글

- 최근 1시간 / 24시간 / 이번 주 / 이번 달 / 사용자 지정
- 사용자 지정 = date range picker (2 날짜)

### 필터

- 시장: 활성 브랜드의 niches 만 노출 (scope bar 와 일관)
- 상태: comment / video / campaign 이벤트 종류

---

## 페이지 2: 문제 (/alerts)

### 정의

빨간불 = **운영자가 즉시 손 봐야 할 상황**:
- 캠페인 중 워커 차단 발견
- 24h 안에 댓글 N% 이상 삭제됨 (고스트율 ↑)
- 영상이 안전필터 (PR-8f) 에 걸림
- 키워드 적합도 낮음 (≤30%)
- API quota 임박

### 데이터 소스 (lean)

기존 신호로 derived:
- `Account.status` 변경 (워커 차단)
- `CommentSnapshot.is_deleted` (고스트)
- `Video.state='blacklisted'` + 사유
- 새 신호는 PR-8b-followup

### 사이드바 배지

`/alerts` 항목 우측에 빨간불 카운트 배지 (count > 0 일 때만 노출).

### 백엔드

`GET /api/admin/alerts?niche_id=`

```python
class Alert(BaseModel):
    id: str  # composite (kind + entity_id)
    kind: Literal["worker_banned", "ghost_spike", "blacklisted_video",
                  "low_keyword_fit", "quota_warning"]
    severity: Literal["info", "warn", "critical"]
    title: str
    detail: str
    related_link: str | None  # 클릭 시 이동할 URL
    created_at: datetime
```

---

## 페이지 3: 예정 (/queue)

### 정의

**다음 24시간 안에 일어날 작업**:
- 예약된 댓글 task
- 예약된 좋아요 부스트
- 추적 일정 (PR-8g)
- 다음 영상 수집 폴링

### 데이터 소스

- `Task` 테이블 (status='pending', scheduled_at <= now+24h)
- `LikeBoostQueue` (scheduled_at)
- `Video.next_revisit_at` (재방문 예정)

기존 `/tasks` 페이지가 비슷한 정보를 제공하지만, "예정 = 24h 안" 윈도우 한정 + 시간순 unified view.

### 백엔드

`GET /api/admin/queue?window_hours=24&niche_id=`

```python
class QueueItem(BaseModel):
    at: datetime
    kind: Literal["task_comment", "task_like", "boost", "revisit", "poll"]
    niche_id: int | None
    video_id: str | None
    detail: str
    actor: str | None  # 예약된 워커
```

---

## 변경 파일 (예상)

| 파일 | 변경 |
|---|---|
| `hydra/web/routes/feed.py` | **신규** — feed/alerts/queue endpoints (또는 별도 3 파일) |
| `hydra/web/app.py` | router 등록 |
| `frontend/src/features/feed/index.tsx` | **신규** |
| `frontend/src/features/alerts/index.tsx` | **신규** |
| `frontend/src/features/queue/index.tsx` | **신규** |
| `frontend/src/hooks/use-feed.ts` | **신규** |
| `frontend/src/hooks/use-alerts.ts` | **신규** |
| `frontend/src/hooks/use-queue.ts` | **신규** |
| `frontend/src/routes/_authenticated/feed/index.tsx` | **신규** |
| `frontend/src/routes/_authenticated/alerts/index.tsx` | **신규** |
| `frontend/src/routes/_authenticated/queue/index.tsx` | **신규** |
| `frontend/src/components/layout/data/sidebar-data.ts` | feed/alerts/queue 항목 + 배지 |
| `frontend/src/routes/_authenticated/index.tsx` | landing → /feed redirect |

---

## 검증

- tsc / vitest / build / pytest baseline keep
- 신규 endpoint 모두 401 (auth)
- 사이드바 배지 동작 (alerts count > 0 시)
- 함정 보존
- DB schema 변경 0
- accounts 9 = SELECT 만 (action_log 등)

---

## Out of scope

- 알림 이메일 / push (별도)
- /alerts 의 자동 fix 액션 (현재는 링크만)
- /queue 에서 직접 작업 cancel (별도)
- /feed 의 댓글 inline 답글 (PR-8e 댓글 트리에서 다룸)
