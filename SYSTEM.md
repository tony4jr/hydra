# HYDRA System Context — for Claude Design / 외부 디자인 툴

> 2026-04-24 · 시각 디자인은 [DESIGN.md](./DESIGN.md) 참조. 이 문서는 **기능/데이터/흐름** 만.

## 1. 한 문장 개요

YouTube 마케팅 **서비스**. 운영자가 대량 Google/YouTube 계정을 워밍업하고, 고객 영상에 댓글/좋아요를 자동 작업. 다수 Windows PC (워커) 가 서버 지시를 받아 실행.

## 2. 운영자 (주 사용자) 하루

```
  아침 → 대시보드 열기
    - 어젯밤 진행 상황 확인 (캠페인 N% 완료)
    - 오프라인 워커 있으면 PC 재부팅
  오전 → 새 계정 배치 등록 (가입 완료 건)
    - 이후 자동으로 온보딩 → 워밍업 3일 → active 전환
  점심 → 고객 의뢰 들어오면 캠페인 생성
    - 영상 URL + 프리셋 선택 + 활성 계정 배정 → 시작
  오후 → 진행 모니터링, 장애 대응
    - 좀비 태스크, 실패 계정 처리
    - 긴급정지/카나리 배포
  저녁 → 분석 리포트 (댓글 상단 노출 등)
```

## 3. 핵심 객체 (Data Models)

### Account (계정)
```
id            : int
gmail         : "user@gmail.com"
password      : 암호화 문자열
adspower_profile_id : "k1xxx" (1 계정 = 1 AdsPower 프로필)
recovery_email, phone_number, totp_secret
status        : registered | warmup | active | suspended | retired
warmup_day    : 0=미시작, 1~3=진행, >3=졸업
onboard_completed_at
daily_comment_limit, daily_like_limit, weekly_*_limit
persona       : JSON {이름, 나이, 관심사…}
identity_challenge_until : 본인인증 돌발 시 7일 쿨다운
ghost_count   : 좀비 의심 카운트
```

### Worker (작업 PC)
```
id, name
status        : online | offline | paused
os_type, current_version
last_heartbeat
allowed_task_types : ["*"] or ["comment","like"] 식 (업무 분리)
allow_preparation, allow_campaign
current_task  : { id, task_type, started_at } | null
```

### Task (작업 단위)
```
id, account_id, worker_id, campaign_id
task_type     : onboarding_verify | warmup | comment | like | watch_video | create_account
status        : pending | running | done | failed
priority      : low | normal | high
payload       : JSON (영상 ID, 댓글 텍스트 등)
scheduled_at  : 미래 시각 지정 시 그 이후에만 fetch
retry_count, max_retries
```

### Campaign (마케팅 단위)
```
id, name
brand_id, target_video_id
preset_id     : 어떤 시나리오로 돌릴지
assigned_account_ids
status        : draft | running | paused | completed
total_tasks, completed_tasks
scheduled_at, completed_at
```

### Preset (스텝 시나리오)
```
id, name, code
steps : JSON 배열 [
  { type: "comment", payload: {...} },
  { type: "like", count: 3 },
  { type: "watch_video", duration_sec: 60 },
]
is_system : true(운영자 공용) / false(사용자 커스텀)
```

## 4. 자동 상태 전이 (M1 구현됨)

```
[계정 등록] → status=registered
    ↓ (워커가 onboarding_verify 태스크 처리)
status=warmup, warmup_day=1
    ↓ (warmup 태스크 complete × 3회)
warmup_day=4, status=active
    ↓ (active 계정 + 대기 중 캠페인 있으면 스케줄러가 comment/like 태스크 생성)
워커가 처리 → status 유지, 일일 한도 소진 시 재개 대기
```

실패 3회 반복 → `suspended` (운영자 확인).

## 5. 주요 API (실제 존재)

**어드민** (JWT 필수):
- `POST /api/admin/accounts/register` — 계정 등록 (운영자 수동)
- `POST /api/admin/workers/enroll` — 워커 설치 토큰 발급
- `GET /api/admin/workers/` — 워커 목록 (current_task 포함)
- `PATCH /api/admin/workers/{id}` — 역할/task_type 변경
- `GET /api/admin/server-config` — 전역 상태 (paused, current_version, canary)
- `POST /api/admin/pause | unpause | deploy | canary` — 운영 제어
- `GET /api/admin/tasks/stats | recent` — 태스크 통계/이력
- `GET /api/admin/audit/list` — 감사 로그
- `GET/POST/DELETE /api/admin/avatars/*` — 프로필 사진 관리

**워커** (X-Worker-Token):
- `POST /api/workers/heartbeat/v2` — 살아있음 알림, 서버 상태 수신
- `POST /api/tasks/v2/fetch` — 작업 받기 (SKIP LOCKED)
- `POST /api/tasks/v2/complete | fail` — 결과 보고
- `GET /api/avatars/{path}` — 아바타 다운로드

## 6. 현재 있는 페이지 (기능 = 유지, 디자인 = 재설계)

| 라우트 | 기능 |
|---|---|
| `/` 대시보드 | 전체 상황 + 긴급정지/배포 |
| `/brands` | 브랜드 목록/등록 (CRUD 약함) |
| `/targets` | 타겟 영상 목록 (약함) |
| `/campaigns` | 캠페인 목록 **(생성/관리 UI 부재 — M2.3 에서 신규)** |
| `/tasks` | 태스크 큐 + stats |
| `/analytics` | 분석 리포트 (약함) |
| `/accounts` | 계정 목록 + 등록 폼 |
| `/workers` | 워커 카드 + 편집 |
| `/avatars` | 아바타 관리 |
| `/audit` | 감사 로그 |
| `/settings/*` | 프리셋 (편집기 X), 행동 패턴, 외관 |

## 7. 운영자가 하고 싶은 일 (User Jobs) — 새 UI 에 보장해야

1. **첫 눈에 전체 건강 상태 파악** — 워커/계정/태스크 정상 여부, 오늘 진행량
2. **긴급 제어** — 한 클릭 긴급정지 / 재개 / 배포
3. **계정 상태 관리** — 상태별로 몇 개인지, 각 계정 현재 어디에 있는지
4. **실패 대응** — 실패한 태스크 목록, 재시도/중단 판단
5. **캠페인 생성** — 영상 URL 붙여넣기 → 프리셋 선택 → 계정 할당 → 시작
6. **진행 추적** — 특정 캠페인이 언제 끝날지, 지금 누가 하고 있는지
7. **성과 확인** — 댓글 상단 노출 여부, 좋아요 수, 댓글 삭제율
8. **키보드로 빠르게** — `Cmd+K` 로 계정/캠페인 이동, 단축키로 자주 쓰는 액션
9. **모바일에서 급할 때** — 출근길에 폰으로 긴급정지, 진행 확인

## 8. 새 UI 가 풀어야 할 진짜 문제

- **대시보드 정보 밀도** vs **처음 보는 사람의 이해도** — 둘 다 만족
- **"신호 흐름" 시각화** — 추상적 (테이블) 이 아닌 구체적 (움직이는 맵)
- **상태 변화 피드백** — 태스크 1건 완료의 미세 성취감
- **실패/장애의 감각적 경고** — 빨간 숫자만이 아닌 사운드/진동/파동 같은 감각
- **키보드 퍼스트 파워유저 경험** — 운영자가 하루 종일 쓰는 툴
- **모바일에서도 감성 유지** — 줄여도 망가지지 않는 정보 계층

## 9. 절대 타협하지 말아야 할 것

- 상태 머신 자동 전이 (이미 돌아감) → UI 는 이걸 **볼 수 있게**만
- 1 계정 = 1 AdsPower 프로필 (DB UNIQUE) → UI 에서 중복 생성 허용 X
- 모든 어드민 쓰기 작업은 감사 로그에 기록됨 → UI 에 이력 조회 경로 제공
- 민감 정보 (password, totp_secret) 절대 UI 에 평문 노출 X
