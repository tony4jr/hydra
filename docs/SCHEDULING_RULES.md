# Hydra 스케줄링 우선순위 · 규정 (운영 참조)

운영자가 알아야 할 task / step / 계정 단위 모든 규칙. 코드 ref 같이.

## 1. Task 처리 우선순위

### 1.1 step pull 순서 (Worker 가 다음에 뭘 할지)
- **1차 정렬: `Video.priority`** (Integer, default 5, 낮을수록 우선)
- **2차 정렬: `CampaignStep.scheduled_at`** (먼저 예약된 게 우선)
- `hydra/core/scheduler.py:83` — `.order_by(Video.priority, CampaignStep.scheduled_at)`

### 1.2 step pickup 가드 (가져갈 수 있는 조건)
| 조건 | 코드 ref |
|---|---|
| step.status == PENDING | scheduler.py:79 |
| step.scheduled_at <= now | scheduler.py:80 |
| Campaign.status == IN_PROGRESS | scheduler.py:81 |
| **profile_lock 비어있음** (계정 단위 직렬화) | scheduler.py:91 |
| account.status == ACTIVE | scheduler.py:95 |
| **선행 step 모두 DONE/CANCELLED** (tikitaka 순서 보장) | scheduler.py:98-107 |

### 1.3 Task 우선순위 (worker_api pickup)
- Task 모델 `priority: 'normal' | 'high' | 'urgent'` (default 'normal')
- 같은 priority 안에서는 FIFO

---

## 2. Task 재시도 정책 (`orchestrator.py:67`)

```
comment            → max 1회 재시도  (보수적, 노출 위험)
like               → max 3회         (적극, 영향 적음)
watch_video        → max 2회
warmup             → max 5회         (덜 중요 + 자연스러움 우선)
onboarding_verify  → max 2회
create_account     → max 1회         (비싼 작업)
기타               → 3회 (fallback)
```

- task.max_retries 와 정책 중 **min** 값 사용 (정책이 상한, task 가 더 낮으면 task 우선)
- 재시도 횟수 초과 → **계정 status = 'suspended'** (orchestrator.py:151)

---

## 3. 영구 실패 (재시도 없이 즉시 계정 격리)

에러 메시지에 다음 키워드 포함 시 (정규화: 공백·`_`·`-` 제거 후 lower):
- `account suspended`
- `captcha_persistent`
- `profile_locked_elsewhere`
- `banned`
- `permanent`

→ **즉시 계정 status='suspended'**, 재시도 없음 (`orchestrator.py:78-86, 138-142`)

---

## 4. 워커 Circuit Breaker (`orchestrator.py:93`)

- **5회 연속 실패** 시 워커 자동 pause (`status='paused'`, `paused_reason='circuit-breaker: N consecutive failures'`)
- task 성공 시 카운터 0 리셋
- 워커 재가동은 관리자가 해야 함 (`/workers` 페이지)

---

## 5. 계정 단위 잠금 (Profile Lock)

- 같은 계정의 task 는 **동시에 1개만** 실행 (AdsPower 프로필 충돌 방지)
- step pickup 시 `is_locked(db, account_id)` 체크
- task 시작 시 lock, 완료/실패 시 unlock
- 잠금 모델: `ProfileLock` (account_id, task_id, acquired_at)

---

## 6. 계정 단위 한도 (Account model)

| 컬럼 | 기본값 | 의미 |
|---|---|---|
| `daily_comment_limit` | 15 | 하루 댓글 최대 |
| `daily_like_limit` | 50 | 하루 좋아요 최대 |
| `weekly_comment_limit` | 70 | 주 댓글 최대 |
| `weekly_like_limit` | 300 | 주 좋아요 최대 |

→ 한도 초과 시 그 계정에 새 task 배정 X (자연 분산 / 차단 회피)

---

## 7. 영상별 쿨다운

`hydra/core/campaign.py:75` — 같은 영상에 같은 계정이 **N일 안에 다시 작업 X**
- `same_task_same_video_days` (default 7일) — config 로 조정 가능
- 다른 계정은 가능 (계정 풀 자연 회전)

---

## 8. 계정 상태 전이 (`hydra/core/enums.py`)

```
REGISTERED → PROFILE_SET → WARMUP → ACTIVE → COOLDOWN ↺ ACTIVE
                                            ↘ RETIRED  (terminal)
                                            ↘ GHOST    (탐지 표시 — 일시)
                                            ↘ SUSPENDED (terminal — 영구 격리)
                                            ↘ IDENTITY_CHALLENGE (구글 본인 인증 요구)
```

- **IDENTITY_CHALLENGE** 상태일 때 `identity_challenge_until` 이전 = 모든 task 배정 금지 (보통 7일)
- **COOLDOWN** = 일시 휴식. `ghost_cooldown_days` (default 7) 지나면 자동 ACTIVE 복귀

---

## 9. Worker IP 회전 정책

- `ip_rotation_cooldown_minutes` (default 30분) — 같은 IP 로 N분 안에 다시 작업 X
- `ip_rotation_task_retry_max` — IP 로테이션 실패 시 최대 재시도

---

## 10. 자동 작업 (AutoJob) 분산

운영자가 `/campaigns` 페이지에서 설정:
- **시간대** (예: 평일 10:00~20:00)
- **하루 한도** (예: 12건)
- → scheduler 가 시간대 안에서 약 `(end-start)*60 / limit` 분 간격으로 task 발행

예: 10~20시 (10h) × 12건 → **50분마다 1건** 발행

`다음 실행` 시각 = scheduler 가 계산한 다음 발행 슬롯. 한 번에 다 처리 X.

---

## 11. 댓글 세트 분해

한 영상에 공감 프리셋(슬롯 A/B/C/D) + 좋아요 부스트 작업하면:

```
Campaign
├─ CampaignStep#1: A 메인 댓글       → Task[comment, account=A]
├─ CampaignStep#2: B → A 답글       → Task[reply, account=B]     (step#1 완료 후)
├─ CampaignStep#3: C → A 답글       → Task[reply, account=C]     (step#1 완료 후)
├─ CampaignStep#4: D → B 답글       → Task[reply, account=D]     (step#2 완료 후)
└─ Like Boost (별도 모델)            → Task[like × 8]             (댓글 게시 후 시간 텀)
```

- step.step_number 순서대로 직렬 강제 (선행 step 미완 시 후행 안 픽업)
- 좋아요는 별도 큐, 댓글 게시 완료 후 다른 계정들이 누름

---

## 12. 글로벌 Kill Switch

`system_config.server_config.paused = 'true'` → 모든 워커 새 task 픽업 X
- 진행 중 task 는 끝까지 처리 후 새 task 만 X
- `/workers` 페이지 또는 직접 DB

---

## 변경 이력
- 2026-05-11 초기 정리 (현재 origin/main 기준)
