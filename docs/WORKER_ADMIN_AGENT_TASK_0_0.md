# Task 0.0 — Windows Admin Agent + Desktop Worker Redesign

## 결론

현재 워커 운영 구조는 실패했다. AdsPower 인증 버그 자체보다 더 큰 문제는
워커 PC가 이미 원격 worker로 연결되어 있는데도, 운영자가 여전히 해당 PC에 가서
PowerShell을 직접 열고 명령을 입력해야 한다는 점이다.

앞으로 워커 복구/진단/업데이트는 서버 Admin UI에서 끝나야 한다. 전용 워커 PC라면
초기 1회 관리자 설치 이후에는 물리 접근 없이 관리 가능해야 한다.

## 현재 상태

기존 Windows 설치 스크립트는 `HydraWorker`를 Task Scheduler에 등록한다.

- 설치 파일: `setup/hydra-worker-setup.ps1`
- 등록 방식: `SYSTEM` + `RunLevel Highest`
- 실행 대상: `python -m worker`
- 로그: `C:\hydra\logs\worker-YYYYMMDD.log`

즉 로컬 권한 자체는 이미 강하다. 문제는 권한이 없는 것이 아니라, 그 권한을
서버에서 조작할 원격 관리 채널이 없다는 것이다.

## 왜 운영자가 계속 왔다갔다 했나

서버와 워커는 연결되어 있지만 현재 연결은 "태스크 실행용"이다.

현재 가능한 것:

- heartbeat
- task fetch/complete/fail
- 제한된 `pending_commands`
- 일부 AdsPower 진단/중지/update 명령

현재 불가능하거나 부족한 것:

- 임의 PowerShell 실행
- stdout/stderr/exit_code 확인
- 실행 중 프로세스/Task Scheduler/service 상태 조회
- git/env/curl 진단
- worker 재시작/kill/update를 중앙에서 확실히 제어
- 장시간 실행 명령 streaming
- 실패한 command lease/retry

따라서 worker가 SYSTEM 권한으로 떠 있어도, 서버는 그 권한을 제대로 쓰지 못했다.

## 하면 안 되는 구조

Windows Service 하나가 모든 일을 직접 하면 안 된다.

서비스는 보통 Session 0에서 실행된다. AdsPower, Playwright, Chrome 같은 GUI/desktop
세션 기반 자동화와 충돌할 수 있다.

금지 구조:

```text
Hydra Windows Service
  - heartbeat
  - task fetch
  - AdsPower browser start
  - Playwright automation
  - update
  - PowerShell console
```

이 구조는 권한은 강해도 GUI 자동화가 깨질 위험이 높다.

## 목표 구조

```text
Hydra Admin Agent Service
  - Windows Service
  - SYSTEM 또는 관리자 권한
  - 부팅 후 자동 실행
  - PowerShell / process / file / git / scheduler / log 관리
  - Desktop Worker launch / stop / restart / update 담당

Hydra Desktop Worker
  - 사용자 desktop/session에서 실행
  - AdsPower / Playwright / YouTube task 담당
  - task fetch/complete/fail 담당
```

역할 분리:

- Admin Agent: PC 관리 권한
- Desktop Worker: 브라우저 자동화 권한
- Server: 둘을 하나의 물리 worker PC로 묶어서 UI에 표시

## 기존 시스템과 충돌 지점

### 1. Worker identity/token 충돌

현재 `WorkerCommand`는 `worker_id` 하나에 붙는다.

문제:

- Agent와 Desktop Worker가 같은 `worker_id`/token을 쓰면 command를 서로 가로챈다.
- `update_now`는 Agent가 받아야 한다.
- `stop_all_browsers`는 Desktop Worker 또는 AdsPower가 보이는 세션에서 받아야 한다.

필요 변경:

- `workers.role`: `admin_agent`, `desktop_worker`
- 또는 별도 `worker_agents` 테이블
- command에 `target_role` 또는 `capability` 추가

### 2. update ownership 충돌

현재 Desktop Worker가 직접 `git reset --hard origin/main`, `pip install`, `sys.exit`를 한다.

문제:

- Agent도 update하면 repo/venv를 두 프로세스가 동시에 만진다.
- 실행 중인 worker 파일을 자기 자신이 바꾼다.
- restart가 Task Scheduler에 강결합되어 있다.

필요 변경:

- update 소유권은 Admin Agent로 이전
- Desktop Worker는 "drain requested"만 처리
- Agent가 stop desktop worker -> git/pip -> start desktop worker 수행

### 3. Task Scheduler 중복 실행

현재 `worker/task_register.py`는 없으면 `HydraWorker` task를 자가 등록한다.

문제:

- Service Agent가 Desktop Worker를 관리하는데, Desktop Worker가 다시 Scheduler를 등록하면
  중복 실행/중복 heartbeat/task fetch 가능성이 생긴다.

필요 변경:

- Agent 구조에서는 Desktop Worker의 self-register 비활성화
- `HYDRA_DISABLE_TASK_REGISTER=1` 같은 플래그 필요
- 기존 Task Scheduler는 migration 단계에서만 사용

### 4. Command delivery 신뢰성

현재 heartbeat에서 command가 내려가면 서버는 바로 `delivered`로 바꾼다.

문제:

- worker가 command를 받은 직후 죽으면 command가 유실된다.
- 원격 shell/업데이트/재시작 같은 명령에는 치명적이다.

필요 변경:

- `lease_expires_at`
- `attempt_count`
- `started_at`
- `heartbeat command lease renew`
- idempotency key
- retry 가능/불가능 command 구분

### 5. Full terminal과 단발 command의 차이

단발 command:

```text
입력 -> 실행 -> stdout/stderr/exit_code 반환
```

Full terminal:

```text
세션 유지
cwd 유지
stdout/stderr streaming
Ctrl+C
long-running process
명령 history
```

운영상 최종 목표는 full terminal이다. 다만 구현은 단계적으로 간다.

## 단계별 구현

### Phase 0 — 설계/모델 정리

- Agent와 Desktop Worker identity 결정
- command routing model 결정
- update ownership을 Agent로 이전하는 설계 확정
- 기존 Task Scheduler와 Service 공존/마이그레이션 방식 결정

### Phase 1 — 원격 PowerShell 단발 실행

목표: 워커 PC에 가지 않고 진단 가능.

기능:

- Admin UI/API에서 worker 선택
- command 입력
- Agent 또는 기존 worker가 PowerShell 실행
- stdout/stderr/exit_code 반환
- timeout
- output size limit
- audit log

예시:

```powershell
git rev-parse --short HEAD
$env:ADSPOWER_API_KEY.Length
curl.exe http://127.0.0.1:50325/status
Get-ScheduledTaskInfo -TaskName HydraWorker
```

### Phase 2 — Admin Agent Service

목표: 재부팅/worker 죽음/업데이트 실패에도 원격 복구.

기능:

- Windows Service 설치
- Agent heartbeat
- Agent command queue
- Desktop Worker process 관리
- log tail
- process list
- git update
- venv/pip install
- Desktop Worker restart

### Phase 3 — Update ownership 이전

목표: Desktop Worker가 자기 자신을 업데이트하지 않게 함.

흐름:

```text
server current_version changed
  -> Agent receives update command
  -> Agent requests Desktop Worker drain
  -> Agent waits idle or force timeout
  -> Agent stops Desktop Worker
  -> Agent git fetch/reset + pip install
  -> Agent starts Desktop Worker
  -> Agent reports result
```

### Phase 4 — Full web terminal

목표: Admin UI에서 진짜 PowerShell처럼 사용.

필요:

- terminal session table
- command streaming endpoint
- stdout/stderr chunks
- interrupt/kill
- cwd/session env 유지
- inactivity timeout

## 최소 DB/API 변경 후보

### Option A: workers 테이블 확장

컬럼:

- `role`: `admin_agent` | `desktop_worker`
- `parent_worker_id`
- `capabilities`: JSON
- `agent_status`

장점:

- 기존 UI/API 재사용 쉬움

단점:

- `workers` 의미가 흐려짐

### Option B: worker_agents 별도 테이블

테이블:

- `worker_agents`
- `worker_agent_commands`
- `worker_agent_heartbeats`

장점:

- 책임 분리 명확
- task worker와 admin agent를 섞지 않음

단점:

- UI/API 추가 작업 많음

권장: Option B. 다만 빠른 MVP는 Option A도 가능.

## 우선순위

Claude Code 리뷰 결과, 원격 PowerShell 단발 실행과 command lease/retry를 분리하면 안 된다.
heartbeat에서 command를 내려준 직후 워커가 죽으면 `delivered` 상태로 유실되기 때문이다.

수정된 우선순위:

1. 원격 PowerShell 단발 실행 + command lease/retry + 사전 충돌 방지 플래그
2. Admin Agent Service 설치
3. Desktop Worker launch/restart 관리
4. update ownership 이전
5. full terminal streaming

## Slice 1 — 원격 PowerShell 단발 + 유실 방지

첫 PR은 아래를 하나로 묶는다. 쪼개면 운영상 의미가 없다.

### 1. WorkerCommand lease 추가

`worker_commands`에 추가:

- `lease_expires_at`
- `attempt_count`
- `started_at`

서버는 pending command를 worker heartbeat에 내려줄 때 즉시 영구 `delivered`로 고정하지 않는다.
대신 짧은 lease를 걸고, worker가 ack 하지 못하면 다시 pending으로 돌릴 수 있어야 한다.

권장 상태:

- `pending`
- `leased`
- `running`
- `done`
- `failed`
- `timeout`

### 2. shell_exec command 추가

새 command:

```json
{
  "command": "shell_exec",
  "payload": {
    "shell": "powershell",
    "script": "git rev-parse --short HEAD",
    "timeout_sec": 30
  }
}
```

워커 실행:

```powershell
powershell.exe -NoProfile -NonInteractive -Command <script>
```

반환:

```json
{
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "truncated": false,
  "duration_ms": 1234
}
```

가드:

- payload script 길이 제한
- timeout 제한
- stdout/stderr size cap
- `issued_by` 기록
- result JSON 저장

### 3. Admin API/UI 최소 추가

추가 API:

- `POST /api/admin/workers/{worker_id}/shell`
- 내부적으로 `WorkerCommand(command="shell_exec")` 생성
- 기존 command list에서 결과 확인 가능

UI 최소 요건:

- worker 선택
- textarea
- 실행 버튼
- stdout/stderr/exit_code 결과 표시

full terminal은 나중이다. Slice 1은 "명령 한 번 실행하고 결과 받기"만 목표다.

### 4. `HYDRA_DISABLE_TASK_REGISTER` 선행 추가

Agent 구조로 넘어가면 Desktop Worker가 스스로 Task Scheduler를 다시 등록하면 안 된다.

`worker/task_register.py` 진입부:

```python
if os.getenv("HYDRA_DISABLE_TASK_REGISTER"):
    return
```

이 플래그는 Slice 1에 미리 넣는다. Phase 2에서 중복 실행을 막기 위한 선행 안전장치다.

### 5. update owner gate 선행 추가

현재 `update_now`는 Desktop Worker가 직접 repo를 갱신한다. Agent 도입 후에는 위험하다.

Slice 1에서 기본 동작은 유지하되, 나중에 Agent로 소유권을 넘길 수 있게 게이트를 둔다.

예:

```python
if os.getenv("HYDRA_UPDATE_OWNER", "self") != "self":
    raise RuntimeError("self-update disabled; update is owned by admin agent")
```

### 6. 테스트

필수 테스트:

- admin이 `shell_exec` 발행 가능
- worker heartbeat가 command lease 획득
- ack 없고 lease 만료 시 재전달 가능
- worker가 `shell_exec` 결과 JSON ack
- stdout/stderr truncation
- timeout 처리
- `HYDRA_DISABLE_TASK_REGISTER=1`이면 scheduler 등록 skip
- `HYDRA_UPDATE_OWNER=agent`이면 self-update 거부

## Claude Code 리뷰 통합

Claude Code 독립 리뷰 결론:

- 제안서의 현황 진단은 코드와 일치한다.
- `SYSTEM` + `RunLevel Highest` 등록은 사실이다.
- `WorkerCommand` 유실 위험은 실제다.
- `perform_update()`가 Desktop Worker 내부에서 repo/venv를 직접 바꾸는 구조는 Agent 도입 후 충돌난다.
- `task_register.py` 비활성화 플래그가 없으면 Service 전환 시 중복 등록/중복 실행 위험이 크다.

리뷰에서 보강된 지점:

- `shell_exec`와 command lease/retry는 같은 PR에 들어가야 한다.
- Phase 2 전에 AdsPower가 어떤 Windows session에서 실행되는지 확인해야 한다.
- SYSTEM service에서 여는 PowerShell은 사용자 GUI 세션 접근에 제한이 있으므로, full terminal이 모든 GUI 문제를 해결한다고 보면 안 된다.
- 단기 MVP는 별도 `worker_agents` 테이블보다 기존 `WorkerCommand` 확장이 더 빠르다.
- 별도 agent table/role 분리는 Slice 1 이후 결정해도 된다.

통합 판단:

- 지금 바로 필요한 것은 Service 전체 구현이 아니라, 서버에서 워커 PC에 명령을 실행하고 결과를 받는 통로다.
- 단, 그 통로는 command lease/retry 없이 만들면 불완전하다.
- 따라서 첫 구현은 `shell_exec + lease/retry + task_register/update_owner 사전 플래그`다.

## Implementation Status — Slice 1

Working checklist (updated live as work progresses):

- [x] DB: `WorkerCommand` 에 `lease_expires_at`, `attempt_count`, `started_at` 추가
- [x] Alembic migration (`y7z8wcmdlease`)
- [x] `worker_api.heartbeat_v2` 가 pending command 를 lease 로 잡고, lease 만료 시 재전달
- [x] `admin_workers.ALLOWED_COMMANDS` 에 `shell_exec` 추가
- [x] `POST /api/admin/workers/{worker_id}/shell` convenience endpoint
- [x] `worker/commands.py` 에 `shell_exec` 핸들러 (PowerShell / sh fallback, timeout, output cap)
- [x] `worker/task_register.py` 에 `HYDRA_DISABLE_TASK_REGISTER` 플래그
- [x] `worker/updater.py` 에 `HYDRA_UPDATE_OWNER=agent` gate (기본 `self` = 현행 유지)
- [x] 테스트: admin shell_exec 발행 + convenience endpoint
- [x] 테스트: heartbeat lease + 만료 재전달
- [x] 테스트: worker shell_exec 결과 shape / timeout / truncation
- [x] 테스트: `HYDRA_DISABLE_TASK_REGISTER=1` → schtasks skip
- [x] 테스트: `HYDRA_UPDATE_OWNER=agent` → self-update 거부

Slice 1 follow-up (Codex 리뷰 보완):

- [x] generic `/api/admin/workers/{id}/command` 의 `shell_exec` payload 도
      `_validate_shell_exec_payload` helper 로 동일 검증 + 정규화. 두 경로
      payload 가드 parity 보장
- [x] frontend `worker-debug-drawer.tsx` CommandsTab 에 PowerShell textarea +
      timeout input + 실행 버튼 추가. `POST /api/admin/workers/{id}/shell`
      호출. 결과는 기존 명령 이력 polling 으로 확인
- [x] 테스트: generic `/command` shell_exec invalid payload 7종 reject
      (missing/empty/oversized/bad shell/bad timeout/...)
- [x] 테스트: generic `/command` shell_exec valid payload 가 normalized 되어
      DB 저장 (default shell=powershell, timeout_sec=30)
- [x] frontend `tsc -b --noEmit` 통과 (exit 0)

Out of scope (Phase 2+):
- Windows Service Admin Agent 설치
- streaming terminal (chunked stdout)
- `workers.role` 컬럼 / `worker_agents` 분리

## 이번 AdsPower 장애와의 관계

Admin Agent가 AdsPower Bearer 버그를 자동으로 고치지는 않는다. 그러나 다음을 가능하게 한다.

- 워커 PC에서 실제 `hydra.browser.adspower` header 확인
- AdsPower local API curl 직접 실행
- env/current process 차이 확인
- git HEAD 확인
- worker restart
- 로그 수집
- hotfix 배포 후 결과 검증

따라서 AdsPower 자체 수정 전에 이 관리 경로를 먼저 까는 판단은 타당하다.
지금처럼 운영자가 물리 PC/PowerShell에 의존하면 같은 문제가 반복된다.

## 최종 판단

이 프로젝트의 Windows worker는 전용 머신이다. 따라서 일반 SaaS worker보다 강한 원격 관리가
필요하고, 보안보다 운영 복구성이 더 중요하다.

단, 구조는 반드시 다음 원칙을 지킨다.

- Service Agent는 관리 전담
- Desktop Worker는 브라우저 자동화 전담
- task ownership은 Desktop Worker만 가진다
- update ownership은 Agent가 가진다
- command는 role/capability로 라우팅한다
- 기존 Task Scheduler와 중복 실행을 막는다
