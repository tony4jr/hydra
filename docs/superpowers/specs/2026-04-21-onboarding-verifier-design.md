# 온보딩 Verifier 재설계 Spec

## 배경 / 문제

현재 `worker/onboard_session.py` 가 50계정 배치에서 반복 실패.

**실측 문제 (2026-04-20 ~ 2026-04-21 디버그 세션)**:
- 40/50 계정이 `Login failed: Locator.wait_for: Timeout 10000ms exceeded` 로 실패 — 실은 이미 로그인됐거나 IPE challenge 중간 상태인데 linear `auto_login` 이 email input 대기로만 분기
- rename/handle/avatar 각각 상이한 타이밍/모달/셀렉터 이슈로 False 반환. 로그에 `True` 로 찍혔지만 서버엔 미저장된 사례 다수 (검증 부재)
- 수동 개입 이후 배치 재실행 시 중간 상태에서 실패 반복 (재진입 불가)

**근본 원인**:
- `auto_login` 은 email→pwd→2FA 순차 linear. 돌발 URL (`/challenge/ipe/verify`, `/gds/recoveryoptions`) 분기 부재
- `run_onboard_session` 은 monolithic. 어느 phase 든 실패하면 `ok=False`, 나머지 skip
- DB 상태가 실제 Google/YT 상태와 괴리 (DB: onboard_completed, 실제: 핸들 미변경)
- goal 간 idempotency 보장 안 됨

## 목표

앞으로도 반복 사용 가능한 안정된 온보딩 시스템.

비목표: 기존 action 라이브러리 (`rename_channel`, `change_handle`, `ensure_korean_language` 등) 재작성. 이들은 그대로 재사용.

## 설계 원칙

1. **Stateless 우선 (A그룹)**: DB 캐시 대신 매번 Google/YT 실제 상태 관찰 후 판단. 수동 개입해도 자동 동기화.
2. **DB 가 source (B그룹)**: OTP 시크릿처럼 외부 관찰 불가한 필드만 DB 기반.
3. **Fail-forward**: 각 goal 독립. 하나 실패해도 다음 goal 계속. 계정 끝에 집약 리포트.
4. **Login 은 state machine**: URL 감지 → 해당 핸들러. 어디서든 재진입 가능.
5. **기존 action 재사용**: 현재 `worker/` 액션 함수는 유지. 새 패키지가 감싼다.

## 아키텍처

```
onboarding/
  __init__.py
  session.py       # 브라우저 세션 (IP 로테 → AdsPower → CDP → 탭 정리)
  login_fsm.py     # 로그인 state machine (URL 기반)
  goals.py         # Goal 정의 (detect + apply 함수 쌍)
  selectors.py     # 중앙 셀렉터 상수 (DOM 변경 시 1곳 수정)
  verifier.py      # 오케스트레이터: goal 순차 실행, 리포트 생성
  report.py        # 실행 결과 구조화
scripts/
  run_verifier.py  # CLI 진입점 (account_id or 범위)
```

단일 API: `await verify_account(account_id: int) -> Report`

## Login FSM

**현재 URL 패턴 → 핸들러 매핑**:

| URL 패턴 | 핸들러 | 다음 상태 기대값 |
|---|---|---|
| `/signin/identifier` | `type_email` | `/challenge/pwd` |
| `/signin/challenge/pwd` | `type_password` | `/challenge/ipe/verify` or `/gds/*` or `myaccount` |
| `/signin/challenge/selection` | `pick_recovery_option` | `/challenge/ipe/verify` |
| `/signin/challenge/ipe/verify` | `submit_recovery_code` (911panel) | `/gds/*` or `myaccount` |
| `/gds/web/recoveryoptions` | `click_skip` (Huỷ) | 다음 gds 또는 myaccount |
| `/gds/web/homeaddress` | `click_skip` (Bỏ qua) | 다음 gds 또는 myaccount |
| `/gds/web/*` | `click_skip` (범용) | 진전 |
| `myaccount.google.com/*` | `DONE` | - |
| `youtube.com/*` (avatar-btn 있음) | `DONE` | - |
| 미등록 URL | `log_unknown + abort` | - |

**루프 규칙**:
```python
async def run_login_fsm(page, acct, max_iter=20):
    prev_url = None
    same_count = 0
    for i in range(max_iter):
        url = page.url
        handler = match_handler(url)
        if handler is None:
            return "failed_unknown_state", url
        if handler == "DONE":
            return "done", url
        if url == prev_url:
            same_count += 1
            if same_count >= 2:
                return "failed_stuck", url
        else:
            same_count = 0
        await handler(page, acct)
        await wait_url_change(page, prev=url, timeout=15_000)
        prev_url = url
    return "failed_max_iter", url
```

## Goals

각 Goal 는 동일 인터페이스:

```python
class Goal(Protocol):
    name: str
    required: bool  # 실패 시 warmup 전이 차단 여부

    async def detect(self, page, acct) -> Literal["done", "not_done", "blocked"]
    async def apply(self, page, acct) -> Literal["done", "failed", "blocked"]
```

**정의된 goals** (실행 순서):

| # | Goal | required | detect | apply |
|---|---|---|---|---|
| 1 | `login` | ✅ | `check_logged_in(page)` True ? | `login_fsm.run(page, acct)` |
| 2 | `ui_lang_ko` | ✅ | `/language` 선호 언어 == "한국어" | `ensure_korean_language` |
| 3 | `display_name` | ✅ | `/profile/name` 값 == `persona.name` | `update_account_name` |
| 4 | `totp_secret` | ❌ | `acct.totp_secret` 존재 (DB) | `register_otp_authenticator` + DB write |
| 5 | `video_lang_ko` | ❌ | `/account_playback` 언어 == "한국어" | `set_primary_video_language` |
| 6 | `identity_challenge` | ✅ | Studio 진입 후 모달 감지 → 모달 없으면 done | `handle_identity_challenge` (locked 시 account 상태 전이 + 쿨다운) |
| 7 | `channel_name` | ✅ | Studio 입력값 == `persona.channel_plan.title` | `rename_channel` |
| 8 | `channel_handle` | ❌ | 현재 핸들이 `persona.channel_plan.handle` 로 **시작** (suffix `-xx` 허용) | `change_handle` |
| 9 | `avatar` | ❌ | `avatar-btn src` 에 `AIdro_` 없음 (업로드된 상태) | `upload_avatar` (policy == `set_during_warmup` 만 실행) |
| 10 | `finalize_warmup` | - | `acct.status == warmup` | 필수 goal 모두 done → DB 전이 |

**"blocked" 의미**:
- `identity_challenge` goal 이 `locked` 반환 시 → 전체 goals 루프 중단, 계정 상태 `identity_challenge` 로 전환, 7일 쿨다운 기록
- 그 외 goal 에서 `blocked` 는 "apply 시도할 수 없는 구조적 이유 (예: avatar policy != set_during_warmup)" → skip 으로 처리

## 실행 루프 (verifier.py)

```python
async def verify_account(account_id: int) -> Report:
    report = Report(account_id)

    acct = load_account(account_id)
    if acct.status in ("identity_challenge", "suspended", "retired"):
        return report.skip(f"status={acct.status}")

    session = await open_session(acct)  # IP rotate + AdsPower + CDP + tab cleanup
    try:
        page = session.page
        for goal in GOALS:
            try:
                state = await goal.detect(page, acct)
            except Exception as e:
                report.error(goal.name, f"detect: {e}")
                continue

            if state == "done":
                report.skip(goal.name, "already done")
                continue
            if state == "blocked":
                report.skip(goal.name, "blocked by precondition")
                continue

            try:
                result = await goal.apply(page, acct)
            except Exception as e:
                report.error(goal.name, f"apply: {e}")
                continue

            report.add(goal.name, result)

            # identity_challenge locked → abort
            if goal.name == "identity_challenge" and result == "blocked":
                break

            # login 실패 → 뒤의 goal 도 의미 없음 (모두 로그인 필요)
            if goal.name == "login" and result != "done":
                break
    finally:
        await session.close()

    return report
```

## Data Flow

입력: `account_id`

DB 읽기:
- `Account.persona` (name, channel_plan, avatar policy)
- `Account.password` (암호화)
- `Account.recovery_email`, `Account.totp_secret`, `Account.adspower_profile_id`

브라우저:
- IP 로테 (`adb shell svc data disable/enable`)
- AdsPower `start_browser(profile_id)` → CDP endpoint
- Playwright `connect_over_cdp` → context
- 작업 탭 1개만 유지 (start.adspower 등 close)
- `ctx.on("page")` 로 이후 열리는 잉여 탭 자동 close
- `page.on("dialog")` 로 JS dialog 자동 accept

DB 쓰기:
- `totp_secret` (B그룹, 한 번만)
- `onboard_completed_at` (finalize 시)
- `warmup_group/start_date/end_date/day` (finalize 시)
- `identity_challenge_until/count/status` (locked 시)

출력: `Report` 객체 — `{goal_name: status, reason?, error?}` JSON 직렬화 가능

## 에러 처리

**계정 내 goal 실패**: fail-forward — 로그에 기록, 다음 goal 계속

**브라우저 연결 끊김**: `_is_connection_error` 로 감지, critical_failure 마킹, goals 루프 즉시 종료

**Identity challenge locked**: 즉시 goals 루프 종료, 계정 상태 전환 + 쿨다운

**Login 실패**: 나머지 goals 는 로그인 필요하므로 즉시 종료

**Unknown login state**: abort, 계정 skip (수동 점검 큐로)

## 테스트

**유닛 테스트 (제한적)**:
- Goal 인터페이스 준수 (name, required, detect/apply 시그니처)
- Report 구조화
- FSM 상태 전이 규칙 (mock page.url)

**통합 테스트 (실제 계정 2~3개)**:
- 신규 계정 (처음 로그인) → 완주
- 이미 로그인된 계정 → login goal skip
- 부분 완료 계정 → 미완료 goal 만 실행

**롤아웃 전략**:
1. 기존 `run_onboard_session` 유지
2. 새 `verify_account` 추가, 기존과 병렬
3. 계정 2~3개로 검증 (결과 직접 비교)
4. OK 확인 후 `scripts/verify_repair.py`, `scripts/batch_onboard.py` 를 새 API 로 교체
5. 잉여 경로 제거

## 마이그레이션 영향

**유지**: `worker/{login,google_account,channel_actions,data_saver,language_setup}.py` 의 액션 함수들. 이들은 재사용.

**변경 불필요**: DB 스키마. 기존 컬럼 그대로 사용.

**신규**: `onboarding/` 패키지 (6개 파일, 총 예상 ~800줄)

**제거 대상 (Step 5)**: `worker/onboard_session.py` (대체됨), `scripts/batch_onboard.py` 의 login 관련 로직 (verifier 로 위임)

## 성공 지표

- 50개 계정 배치 1회 실행으로 **90%+ goal 완료** (기존 배치: ~60%)
- 부분 실패 계정 재실행 시 **100% 이어서 완주** (기존: 재시도로 재실패 반복)
- 신규 돌발 Google 화면 나타났을 때 **unknown state 로깅** → 1일 내 패치 가능 (기존: 가장 먼저 실패하는 시점을 찾기 어려움)
