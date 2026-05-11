# 워커 분배 모듈 개선 제안 (4건)

운영 효율·자연스러움·다중 워커 환경 영향이 큰 항목. Codex 검토 의뢰용 상세안.

## #1 Task soft-deadline + zombie 가시성

### 현재 문제
- `Task` 모델에 deadline / expiry 컬럼이 없음 (`scheduled_at` 만 있음)
- 워커가 크래시하면 task 가 `status='assigned'` 로 영원히 묶임
- `hydra/core/zombie_cleanup.py` 가 일정 시간 지난 assigned task 의 worker_id 를 NULL 로 복구하지만, **운영자 UI 에 그 가시성 없음**
- 시간대 끝나는 시점(예: 18:00) 에 시작한 task 는 자연 완료 OK 인데, **17:55 시작 했는데 1시간 째 진행 중 = 진짜 zombie 인지 정상인지 구분 안 됨**

### 수정안

**Backend (작은 변경)**

`hydra/api/tasks.py /api/tasks/list` 응답에 다음 추가:
```python
{
  ...,
  "elapsed_minutes": int,  # now - assigned_at (assigned/running 상태일 때만)
  "is_stale": bool,        # elapsed_minutes > task_type 별 expected
}
```

`task_type` 별 expected duration (config 또는 상수):
```python
EXPECTED_DURATION_MINUTES = {
    "comment": 8,
    "reply": 6,
    "like": 3,
    "warmup": 25,
    "onboard": 35,
    "create_profile": 5,
}
```

`zombie_cleanup` 의 최근 24h 정리 카운트를 노출하는 GET endpoint 추가 (운영 대시보드용):
```python
GET /api/admin/zombie-cleanup/stats
→ { "last_24h_cleaned": N, "next_run_in_minutes": M }
```

**Frontend (가시성)**

1. `/queue` 페이지 테이블에 "경과 시간" 컬럼:
   - assigned/running 상태: `12분` `45분` 같은 elapsed_minutes 표시
   - `is_stale=true` 이면 빨간 톤 + ⚠ 아이콘
   - 다른 상태는 `-`
2. 자동 작업 페이지 통합 대시보드 위에 "오래 걸리는 task N건" 알림 배너 (N>0 일 때만 표시)

### 영향 / 위험
- ✅ 운영 가시성 즉시 개선, backend 변경 최소
- ✅ task 자체에 deadline 강제 종료는 없음 (안전) — soft 가시화만
- ⚠ EXPECTED_DURATION_MINUTES 값은 추정. 실제 분포 보고 조정 필요

---

## #2 계정 자동 할당 고도화 (LRU + 한도 감안)

### 현재 문제
`hydra/services/task_service.py:47`:
```python
available = db.query(Account).filter(
    Account.status == "active",
    ~Account.id.in_(
        db.query(ProfileLock.account_id).filter(ProfileLock.released_at.is_(None))
    ),
).first()
```
- **`.first()` = id 작은 순으로 첫 번째 active 계정만**
- 결과: 항상 같은 계정 (id 1, 2, 3...) 만 과부하
- 자연스러움 ↓ (한 계정에 댓글 몰리면 탐지 위험)
- 마지막 활동·일일 사용량·워밍업 정도 무관

### 수정안

LRU (Least Recently Used) + 한도 60% 미만 우선:

```python
from sqlalchemy import func, case

today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0)
today_actions_sub = (
    db.query(
        ActionLog.account_id,
        func.count().label("today_n"),
    )
    .filter(ActionLog.created_at >= today_start)
    .group_by(ActionLog.account_id)
    .subquery()
)

available = (
    db.query(Account)
    .outerjoin(today_actions_sub, Account.id == today_actions_sub.c.account_id)
    .filter(
        Account.status == "active",
        ~Account.id.in_(
            db.query(ProfileLock.account_id).filter(ProfileLock.released_at.is_(None))
        ),
        # 일일 한도 70% 미만만 후보
        func.coalesce(today_actions_sub.c.today_n, 0) < Account.daily_comment_limit * 0.7,
    )
    .order_by(
        # 우선순위: 1) 오늘 사용량 적은 순 2) 마지막 활동 오래된 순
        func.coalesce(today_actions_sub.c.today_n, 0).asc(),
        Account.last_active_at.asc().nullsfirst(),
    )
    .first()
)
```

### 영향 / 위험
- ✅ 자연스러운 라운드로빈 (한 계정 몰림 방지)
- ✅ 한도 임박 계정 자동 회피
- ⚠ 매번 ActionLog count 쿼리 — 50 계정 / 1000 task/day 수준에서는 부담 적지만 inde 필요할 수 있음 (`idx_action_log_account_created`)
- ⚠ task_type 별로 limit 컬럼이 다름 (comment vs like) — 일관성 위해 task_type 에 맞는 한도 적용해야 정확

**확장:** task_type=='like' 면 daily_like_limit, 'comment'/'reply' 면 daily_comment_limit 으로 분기

---

## #3 Video.priority → Task.priority 전파

### 현재 문제
- `hydra/core/scheduler.py:83` get_pending_steps: `.order_by(Video.priority, CampaignStep.scheduled_at)` — step 픽업은 영상 우선순위 반영
- 하지만 step 이 task 로 분해되는 단계에서 task.priority 는 고정 (`'normal'`)
- `fetch_tasks` 에서는 task.priority 만 봐서 영상 우선순위 정보 손실
- → 운영자가 "이 영상은 중요 (priority=1)" 라고 매겨도 실제 워커 분배 단계에선 평등 취급

### 수정안

step → task 생성하는 모든 지점에서 video.priority 를 task.priority 로 매핑:

```python
# helper 함수
def video_priority_to_task_priority(video_priority: int) -> str:
    if video_priority <= 2:
        return "urgent"
    if video_priority <= 5:
        return "high"
    if video_priority <= 8:
        return "normal"
    return "low"
```

수정 대상 (grep 으로 확인된 task 생성 지점):
- `hydra/core/executor.py` — step 실행 시 task 생성 부분
- `hydra/api/tasks.py:enqueue_*` 함수들
- `hydra/web/routes/accounts.py:auto_queue_create_profile_tasks` (이건 video 와 무관해서 default 'normal' 유지)

### 영향 / 위험
- ✅ 영상 priority 가 task pickup 까지 일관 전파
- ⚠ 기존 task 들의 priority 는 안 바뀜 (앞으로 생성되는 task 만)
- ⚠ 영상 priority 가 부재하면 (모든 영상 default=5) 의미 없음 — 운영자가 priority 매기는 UI 가 있어야 효과

---

## #4 워커 역할 분리 UI

### 현재 상태
- `Worker.allow_preparation` / `allow_campaign` 컬럼 이미 존재
- `task_service.fetch_tasks` 에서 이미 가드:
  ```python
  if task.task_type in PREPARATION_TYPES and not worker.allow_preparation:
      continue
  if task.task_type not in PREPARATION_TYPES and not worker.allow_campaign:
      continue
  ```
- 하지만 **현재 UI 에서 토글하는 곳이 없음** → 모든 워커 default 양쪽 ON

### 안티디텍션 의미
- 같은 PC 에서 워밍업 task (Gmail 검색, 채널 설정) 와 캠페인 task (특정 영상 댓글) 가 섞이면 행동 패턴 노출 위험
- 분리 운영: pc-01 (워밍업 전용) + pc-02 (캠페인 전용) → IP·세션 분리 효과

### 수정안

**Backend**
- 새 endpoint: `POST /api/admin/workers/{id}/role`
  ```json
  { "allow_preparation": true, "allow_campaign": false }
  ```
- `WorkersPage` API list 응답에 이 두 필드 포함

**Frontend** (workers 페이지)
- 워커 행마다 2개 토글 표시: "워밍업" / "캠페인"
- 양쪽 다 OFF 는 경고 (이 워커는 어떤 task 도 못 받음)

### 영향 / 위험
- ✅ 안티디텍션 가치 큼 (워밍업·캠페인 분리)
- ✅ 코드는 이미 분리 지원, UI 만 막혀 있음 = 저비용
- ⚠ 운영자가 잘못 설정해서 양쪽 OFF 하면 워커 idle. UI 가드 + 안내 필요
- ⚠ 다중 워커 운영 시 어느 워커가 어떤 역할인지 한 화면에 보여줘야 (요약 위젯)

---

## 우선순위 추천

| # | 임팩트 | 변경 폭 | 추천 |
|---|---|---|---|
| 1 | 운영 가시성 ⭐⭐ | 작음 | **1순위** |
| 2 | 자연스러움 ⭐⭐⭐ | 중간 | **1순위** |
| 3 | 영상 priority 의미 회복 ⭐ | 중간 | 2순위 |
| 4 | 안티디텍션 ⭐⭐ | 중간 | 2순위 |

→ **PR 1: #1 + #2 묶음 (운영 즉시 효과)**
→ **PR 2: #3 + #4 묶음 (구조적 개선)**

---

## 검증 항목 (PR 작성 시)
- [ ] backend pytest 통과
- [ ] `fetch_tasks` 로직 변경 시 동시성 시나리오 단위 테스트 추가
- [ ] 50개 계정 환경에서 LRU 분포 시뮬레이션 (한 계정 몰림 없는지)
- [ ] zombie_cleanup 통계 endpoint 인증 가드
- [ ] frontend 빌드·lint
- [ ] mock data 에 stale task 예시 1건 추가 (UI 검증용)
