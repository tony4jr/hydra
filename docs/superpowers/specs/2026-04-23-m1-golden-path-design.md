# M1 — Golden Path MVP 설계

> 작성일: 2026-04-23
> 관련 메모리: "AI 하네스 설계", "프리셋 원자적 실행", "1 계정 = 1 프로필"

## 1. 목적

**자동 전이 파이프라인 검증**. 운영자가 계정 1개를 어드민 UI 에서 등록하면, 이후
**온보딩 → 워밍업 → 활성화 → 댓글/좋아요** 까지 **수동 개입 없이** 워커를 통해
진행된다. M1 은 최종 제품이 아니라 파이프라인 골격을 end-to-end 로 증명하는
첫 마일스톤이다.

## 2. 스코프

### 포함 (M1)
- 계정 상태 머신 (registered → warmup(3 step) → active) 자동 전이
- 이벤트 훅 (task.complete 시 즉시 다음 단계) + 백업 스케줄러 (30초 tick)
- 스텁 캠페인 1개 — active 계정에 하드코딩 프리셋 적용 → comment/like 태스크 생성
- 워커 신규 API 전환 (`/api/workers/heartbeat/v2`, `/api/tasks/v2/*`)
- `worker/executor.py` 의 `SessionLocal` 제거 — `AccountSnapshot` 페이로드만 사용
- AI 에이전트 호출 경로 정리 — 워커가 `X-Worker-Token` 으로 `/api/generate-comment`
  호출 가능하도록 (현재 `admin_session` 뒤에 있어 401)
- Mac 로컬 워커 1회 실전 완주
- 각 단계 실행 로직은 **기존 `worker/executor.py` 재활용** — 신규 작성 최소

### 제외 (M2 이후)
- 캠페인 생성 UI (타겟 영상 등록, 프리셋 선택, 기간 설정, 시작/정지)
- 복수 캠페인 동시 실행
- 멀티테넌트 (customer_id 활용) + 결제
- UI 전면 재설계 ("토스 수준")
- Windows 워커 실전 연결
- 실제 신규 계정 자동 생성 로직 (hook 만 남기고 본문은 나중)

### 워밍업 기간 축소
실운영 워밍업은 3일이지만 M1 은 **즉시 연속 실행**으로 축소 (검증 시간 단축).
state_transition 함수 안의 다음 태스크 `scheduled_at` 을 현재 시각으로
세팅하면 됨. 실운영 전환은 `scheduled_at=now + 24h` 로 바꾸기만 하면 완료.

## 3. 아키텍처

```
┌──────────────────────────────────────────────────────────┐
│ 운영자 (내부 사용자)                                         │
│   /accounts "계정 등록" 폼 → POST /api/admin/accounts/register
│   대시보드에서 진행 모니터링                                  │
└─────────┬────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────┐
│ 서버 — 자동 전이 엔진                                        │
│                                                           │
│   Hook (inline in /api/tasks/v2/complete, /fail):         │
│     orchestrator.on_task_complete(task_id, session)        │
│       → 상태 전이 + 다음 태스크 enqueue (같은 트랜잭션)       │
│                                                           │
│   Scheduler (hydra/services/background, 30s tick):        │
│     orchestrator.sweep_stuck_accounts()                    │
│     campaign_stub.scan_active_accounts()                   │
│                                                           │
│   Campaign stub (seed data):                              │
│     active 전환 감지 → 하드코딩 프리셋 적용 → comment/like 태스크 생성
└─────────┬────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────┐
│ 워커 (Mac 로컬, 신규 v2 API)                                 │
│   heartbeat/v2 → fetch/v2 → execute → complete/v2          │
│   executor: task_type 별 기존 로직 재활용                     │
│              (AccountSnapshot 페이로드만 사용, 로컬 DB 없음)   │
└──────────────────────────────────────────────────────────┘
```

## 4. 상태 머신

**Account.status** 전이 표:

| 현재 상태 | 트리거 | 다음 상태 | Side Effect |
|---|---|---|---|
| (없음) | `POST /api/admin/accounts/register` | `registered` (warmup_day=0) | `onboarding_verify` task enqueue |
| `registered` | `onboarding_verify` task complete | `warmup` (warmup_day=1) | `onboard_completed_at`=now · 다음 `warmup` task enqueue |
| `warmup` (day 1) | `warmup` task complete | `warmup` (day 2) | 다음 `warmup` task enqueue |
| `warmup` (day 2) | `warmup` task complete | `warmup` (day 3) | 다음 `warmup` task enqueue |
| `warmup` (day 3) | `warmup` task complete | `active` (warmup_day=4) | 캠페인 스텁에서 감지 가능 |
| `active` | 캠페인 스텁 tick | (변화 없음) | `comment` / `like` task enqueue (한 번만) |
| any | 같은 태스크의 `Task.retry_count >= max_retries (3)` | `suspended` | 운영자 확인 필요 — UI 노출 |

**Task 실패 처리**: 실패 시 Account 상태는 유지. 기존 `Task.retry_count` 와 `Task.max_retries`
(default 3) 필드를 활용 — orchestrator 가 fail 훅에서 `retry_count` 증가, 임계 도달 시
Account 를 `suspended` 로 전환. 추가 DB 컬럼 없이 처리 가능.

## 5. 핵심 모듈

### 5-1. 서버 신규

#### `hydra/core/orchestrator.py`
```python
def on_task_complete(task_id: int, session: Session) -> None:
    """task_api 가 commit 직전에 호출 — 같은 트랜잭션."""
    task = session.get(Task, task_id)
    if task is None or task.account_id is None:
        return
    account = session.get(Account, task.account_id)
    _advance_state(account, task, session)  # 표 5-1 의 상태 머신 반영


def sweep_stuck_accounts() -> int:
    """백업 tick. 진행 중인 account 중 next task 가 없는 것 탐지 + 재enqueue."""
```

#### `hydra/core/campaign_stub.py`
```python
HARDCODED_PRESET = {
    "target_video_id": os.getenv("M1_TEST_VIDEO_ID", ""),
    "steps": [
        {"type": "comment", "payload": {"ai_generated": True}},
        {"type": "like",    "payload": {}},
    ],
}

def scan_active_accounts(session: Session) -> int:
    """active 전환됐는데 아직 이번 프리셋을 실행 안 한 계정 대상으로 태스크 생성."""
```

#### `hydra/web/routes/admin_accounts.py` (신규 파일)
```python
@router.post("/register")
def register_account(req: AccountRegisterRequest, _session=Depends(admin_session)):
    """운영자 수동 등록 — 향후 자동 생성 로직이 같은 함수를 내부 호출."""
    # Account INSERT (status=registered)
    # Task(type=onboarding_verify, account_id=new.id) INSERT
```

### 5-2. 서버 수정

#### `hydra/web/routes/tasks_api.py`
- `complete` / `fail` 핸들러 `db.commit()` 직전에
  `orchestrator.on_task_complete(task.id, db)` 추가

#### `hydra/services/background.py`
- 30초 tick 에 `orchestrator.sweep_stuck_accounts()` 와
  `campaign_stub.scan_active_accounts()` 호출

### 5-3. 워커 수정 (현재 legacy 경로 → v2)

#### `worker/client.py`
- `heartbeat()` → `POST /api/workers/heartbeat/v2` · 응답 dict 반환
- `fetch_tasks()` → `POST /api/tasks/v2/fetch`
- `complete_task()` / `fail_task()` → `/api/tasks/v2/*`
- enroll 은 별도 flow — 시크릿 없는 초기 실행 시 enrollment_token 입력 요구

#### `worker/app.py`
- heartbeat 응답에서 `paused=True` → 이 tick 에 fetch 스킵
- `current_version` 달라지면 `updater.maybe_update(is_idle=...)` 호출
- 현재 진행 중 task 추적 `self._current_task_id` — complete/fail 시 None 복원

#### `worker/executor.py`
- 파일 상단의 `from hydra.db.session import SessionLocal` 완전 제거
- 각 핸들러(`_handle_onboarding_verify`, `_handle_warmup`, `_handle_comment`, `_handle_like`)
  가 `task["account_snapshot"]` → `AccountSnapshot.from_payload(task)` 로 계정 정보 획득
- 기존 `acct.gmail`, `acct.password`, `acct.persona` 접근은 snap 속성으로 대체 (같은 이름)
- `acct.totp_secret` 복호화 제거 (snap 이 이미 평문)
- AI 댓글 생성 호출 (`httpx.post("/api/generate-comment")`) 에 `X-Worker-Token` 헤더 추가

## 6. 데이터 흐름 (end-to-end 한 번)

```
t+0s   운영자 UI: POST /api/admin/accounts/register
       → Account(id=1, status=registered, warmup_day=0)
       → Task(type=onboarding_verify, account_id=1, status=pending)

t+5s   워커 heartbeat/v2 → fetch/v2 → onboarding_verify task 수신
       (응답에 account_snapshot 동봉: 복호화된 password/persona 포함)

t+30s  워커 executor: 온보딩 로직 실행 → /api/tasks/v2/complete
       → orchestrator.on_task_complete():
           Account(status=warmup, warmup_day=1, onboard_completed_at=now)
           Task(type=warmup, account_id=1) INSERT

t+35s  워커 fetch → warmup(day1) → complete
       → orchestrator: warmup_day=2, 다음 warmup task INSERT

t+...  (3회 반복) warmup_day=4, status=active

t+N    30초 tick: campaign_stub.scan_active_accounts() 감지
       → Task(type=comment, preset 하드코딩), Task(type=like) INSERT

t+N+   워커 comment → complete → orchestrator (변화 없음)
       워커 like → complete → orchestrator (변화 없음)
       스텁 캠페인 1회 완료 기록 (meta 로)
```

## 7. 테스트 전략

### 단위 (pytest, in-memory sqlite + StaticPool)
- `orchestrator.on_task_complete` 각 전이 케이스
  - registered + onboarding_complete → warmup(day1)
  - warmup(dayN) + warmup_complete → warmup(day N+1) [N=1,2]
  - warmup(day3) + warmup_complete → active
  - 실패 3회 → suspended
- `campaign_stub.scan_active_accounts` 가 active 계정에만 task 생성
- `sweep_stuck_accounts` 누수 복구

### 통합 (TestClient)
- 어드민 register 호출 → Account + onboarding task 검증
- 가짜 워커가 fetch/complete 반복 → Account 상태가 최종 active 도달 확인
- 같은 account 에 병렬 fetch 시도 → ProfileLock 이 1개만 허용

### E2E
- `docs/e2e-checklist.md` 의 "Worker 실전 연결 후" 섹션을 M1 완료 기준으로 전환
- Mac 로컬 워커 구동 → 계정 1개 등록 → 자동 완주 관찰

## 8. 실패/복구

| 시나리오 | 처리 |
|---|---|
| 단일 task 실패 | fail 호출 → 동일 task_type 재enqueue (`retry_count++`) · Account 상태 유지 |
| 동일 task 3회 실패 | Account.status = `suspended` · 운영자 UI 에 "suspend 계정" 목록 표시 |
| 워커 크래시 중 running | 기존 `hydra/core/zombie_cleanup` (Task 22, 30분 임계) → pending 복원 |
| 이벤트 훅 누락 (DB 커밋 후 전이 실패) | 30초 tick 의 `sweep_stuck_accounts` 가 감지 + 재enqueue |
| 스텁 캠페인이 이미 실행된 계정 재지정 | campaign_stub 에 중복 방지 로직 — 한 account 당 프리셋 1회만 |

## 9. 마이그레이션 / 데이터

- **신규 Alembic 마이그레이션 필요 없음** — 기존 `Task.retry_count`,
  `Task.max_retries` 필드로 실패 누적 처리 가능. `Account.status = "suspended"` 는
  문자열 값이라 스키마 변경 불필요.
- 캠페인 스텁 seed: `M1_TEST_VIDEO_ID` env 로 타겟 영상 ID 주입.
- `/api/generate-comment` 라우터를 `app.py` 의 `_ADMIN_DEPS` 마운트에서 제거하고
  별도 `worker_auth` Depends 로 재등록 (워커 전용).

## 10. 성공 기준

M1 완료 판정:
1. `pytest` 전체 GREEN
2. Mac 로컬 워커로 신규 계정 1개 등록 → 자동으로 active 도달
3. 스텁 캠페인이 그 계정에 comment/like 태스크 1건씩 생성
4. 워커가 두 태스크 모두 complete 로 처리
5. AuditLog 에 각 전이 이벤트 기록 (register/pause 등은 이미 있음)
6. `scripts/e2e_check.sh` 통과 (기존 14개 + M1 관련 신규)

## 11. 이후 (M2 preview)

M1 완료 후 바로 이어지는 작업 (이 스펙 범위 밖):
- 캠페인 생성/관리 UI (타겟 URL, 프리셋 선택, 시작/정지)
- 복수 캠페인 동시 실행 + account 할당 로직
- UI 전면 재설계 (토스 수준 — 메모리 "다음 세션")
- 워밍업 실제 기간 (24h scheduled_at 지연)

M3 에서 멀티테넌트/결제 (customer_id + Stripe).
