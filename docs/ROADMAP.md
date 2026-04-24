# HYDRA 로드맵

> 최종 업데이트: 2026-04-24 · 견고화 감사 반영

---

# 🎯 #1 목표 (North Star)

**YouTube 댓글 마케팅 자동화 플랫폼 — 시장 출시 가능 수준**

세부:
- 브랜드의 **간접 언급** (성분/방법 키워드 우회) 으로 탐지 회피하며 댓글 마케팅
- **다계정 다영상 캠페인** — 키워드 기반 타겟 영상 수집 + 퍼널 단계별 (인지/고려/전환/리텐션) 댓글 생성
- **다워커 좋아요 부스트 타이밍** 으로 상단 노출
- **안티디텍션 최우선** — 프로필/IP/타이핑/fingerprint 전부 다양화, 고정값·패턴 금지
- **어디에서든 원격 운영** — 어드민 UI 에서 워커 명령/모니터링
- **1 계정 = 1 AdsPower 프로필** 절대 원칙 (DB UNIQUE 강제)

**"이번 실행"** = M2.2 Stage C (실 댓글 1건) 완료 = **실서비스 투입 준비 완료 시점**.

---

# 원칙

1. **성공 기준 명문화** — 모호하게 "됐다" 넘어가지 않음
2. **3단 검증**: (a) 단위 테스트 (b) 실환경 probe (c) 사용자 육안 확인
3. **Phase 전환은 명시적 승인** — AI 가 "됐다" 선언 금지
4. **임시방편 금지** — 증상 덮지 말고 근본 원인
5. **계획 변경은 문서 반영 후** — 구두 대화 흘림 방지
6. **에러는 사전 예상** — "발생하면" 이 아니라 "발생할 때 어떻게 자동복구" 설계 (방어적 기본값)
7. **새 워커 세팅은 1회 절차** — AdsPower 커널 수동 다운로드 포함

---

# 전체 Phase 맵

```
Phase 0: 기반 (로컬 MVP + VPS 서버)                       ✅ 완료
Phase 1: 운영 인프라 (워커 신호·인증·에러리포팅)          ✅ 완료
Phase 2: 실환경 진입 (스크린샷·어드민 UI·원격명령·백업)   🟡 진행
 └─ 이게 끝나면 "이번 실행" 완료 = 실서비스 투입 가능
Phase 3: 스케일업 전 하드닝 (감시·알람·staging)           ⬜ 대기
Phase 4: 캠페인 런처 (키워드·퍼널·브랜드·부스트)          ⬜ 대기
Phase 5: UI 재설계 (Living Ops Console)                   ⬜ 후순위
```

---

# Phase 0: 기반 ✅

## 했던 일
- M0 로컬 MVP (단일계정 댓글/좋아요, Playwright + AdsPower)
- M1 VPS 서버 (FastAPI + PostgreSQL + JWT 어드민)
- Task Queue v2 (SKIP LOCKED + ProfileLock, 1:1 프로필 제약)
- 프리셋/캠페인/워밍업/계정 CRUD API
- systemd 배포 파이프라인

## 미비점 (= Phase 2 에서 보강)
- 어드민 UI 가 VPS 에서 서빙 안 됨 (Mac Vite dev 로만 접속)
- DB 백업 없음
- 모니터링/알람 없음

---

# Phase 1: 운영 인프라 ✅

## 했던 일 (실 commit 매핑)

| 항목 | Commit | 효과 |
|---|---|---|
| 서버 IPv6 dual-stack | `767bf25` | DuckDNS AAAA + nginx `[::]:443`. NAT64 우회 |
| Happy Eyeballs fallback | `448491d` `9c5ecec` | 워커가 v6 실패 시 v4 자동 재시도 (sticky) |
| heartbeat spam 수정 | `9c5ecec` | 실패 시 초당 수십회 → 30초 간격 |
| Fresh client per request | `9c5ecec` | stale 커넥션풀/리졸버 캐시 회피 |
| 워커 에러 리포팅 | `f9de32b` | `/api/workers/report-error` + DB + logging handler |
| Python 로그 → 서버 | `2f68785` | WARNING+ 자동 전송 + sys.excepthook |
| SHA-256 O(1) auth | `a1189c1` `9fb2fde` | bcrypt 전수순회(7초) → 해시 인덱스(100ms) |
| 워커 updater no-op | `f526f46` | origin/main 도달 시 재시작 루프 방지 |
| nginx 정식 config | `767bf25` | placeholder 탈출, /api /static / SPA 경로 라우팅 |
| AdsPower 키 중앙 분배 | `271c935` | admin → 서버(Fernet) → heartbeat → 워커 os.environ |
| `127.0.0.1` 직접 | `7f3bf76` | local.adspower.net DNS 의존성 제거 |
| DRY-RUN 신호 루프 | (pre-session) | HYDRA_WORKER_DRY_RUN=1 게이트 |
| M2.2 Stage 0 복구 import | `0497390` | 3계정 (k1bmpnnw/k1bmpnpk/k1bmpnry) DB 복구 |
| M2.2 Stage A | (Windows 실행 확인) | DRY-RUN 태스크 11건 완주 |

## 미비점 (Phase 2 에서 채움)
- **어드민에서 에러 로그 UI 없음** — 서버엔 저장됐지만 열람 불가 → T2
- **원격 명령 불가** — 워커 재시작·재시도·진단 요청 불가 → T3
- **실패 시 스크린샷 없음** — 실 YouTube 실패 원인 추정 불가 → T1
- **DB 백업 없음** — 데이터 손실 위험 → T4
- **frontend VPS 서빙 안 됨** — 원격 관리 불가 → T2

---

# Phase 2: 실환경 진입 🟡 (지금 여기)

## 이미 된 것
- Stage 0 (3계정 import) ✅
- Stage A (Windows DRY-RUN 루프) ✅

## 해야 할 것 — T1~T6

### T1. 스크린샷 캡처 (45분, Mac) — **실 YouTube 실패 디버깅의 유일한 눈**
**왜**: 실 태스크가 실패하면 코드 에러/네트워크/DOM 변경/차단/captcha 중 뭔지 육안 없이 판별 불가.

**설계**
- `/api/workers/report-error` multipart 확장 — `file=@screenshot.png`
- 저장: `/var/www/hydra/screenshots/<YYYY-MM-DD>/<worker>-<task>-<timestamp>.png`
- 7일 auto-cleanup (cron)
- `worker_errors.screenshot_url` 컬럼 추가
- nginx `/screenshots/` 서빙 + 어드민 JWT 쿠키 인증 미들웨어
- 워커 `WorkerSession.capture_screenshot()` — executor try/except 에서 자동 호출

**에러 예상 + 방어**
- 디스크 풀 → 7일 cleanup + 파일당 2MB 제한
- 캡처 중 예외 → 절대 본체 흐름 중단 X (try/except + pass)
- 스크린샷이 민감정보(PII) 담을 수 있음 → 어드민만 접근, 7일 후 삭제

**검증**
- [ ] pytest: multipart 업로드 / 파일 저장 / URL DB / 어드민 접근 (4건)
- [ ] Mac worker 의도 예외 → 서버 파일 존재 + DB URL
- [ ] 브라우저에서 URL 클릭 → 이미지 표시

---

### T2. 어드민 VPS 서빙 + Errors 탭 UI (2.5시간, Mac) — **원격 모니터링의 기반**
**왜**: Errors API 만 있고 UI 없으면 로그 확인에 SSH 필요. 제품 수준 운영에 치명.

**설계**
- deploy.sh 에 node/npm 확인 + frontend build + `/var/www/hydra/` rsync
- 필요 시 VPS 에 `nodejs 20` 설치 (apt install)
- 신규 라우트 `frontend/src/features/workers/errors-page.tsx`:
  - 리스트: 최신 100건, 시간순, 10초 자동 갱신
  - 필터: worker_id / kind / 날짜
  - 행 클릭 → 모달: traceback + context + screenshot 미리보기 + 원문 복사 버튼
- Workers 탭 상세 화면에 "Errors (워커별)" 서브탭
- 모바일 반응형 (최소)

**에러 예상 + 방어**
- VPS 빌드 실패 → deploy.sh 가 rsync 전 `frontend/dist` 존재 확인, 실패 시 이전 버전 유지
- 백엔드 200 OK 지만 빈 배열 → UI "No errors yet" 표시
- 대량 에러로 UI 느려짐 → limit 200 + 페이지네이션

**검증**
- [ ] `curl https://hydra-prod.duckdns.org/` HTML 리턴 (not "hydra-prod ok")
- [ ] 어드민 로그인 → Workers → Errors 탭 표시
- [ ] Mac worker 의도 에러 → 10초 내 UI 반영

---

### T3. 원격 명령 시스템 (2시간, Mac) — **원격 운영의 핵심**
**왜**: 사용자 명시 요구 ("재시작 명령", "업데이트 자동반영", "멀리서도 워커 제어"). 없으면 워커 PC 가 있는 곳에 직접 가야 함.

**설계**
- DB: `worker_commands` (id, worker_id FK, command, payload JSON, issued_by, issued_at, delivered_at, result TEXT, completed_at)
- 어드민: `POST /api/admin/workers/{id}/command` → pending 으로 저장
- heartbeat/v2 응답에 `pending_commands: [{id, command, payload}, ...]`
- 워커: 명령 수신 → 순차 실행 → `POST /api/workers/command/{id}/ack` {result, status}
- 어드민 UI: Workers 탭 각 행에 드롭다운 버튼 + 결과 표시

**지원 명령 8종** (구체 구현)

| 명령 | 워커 동작 | 용도 |
|---|---|---|
| `restart` | `sys.exit(0)` → Task Scheduler 재시작 | 워커 재기동 |
| `update_now` | `git pull` + pip install + exit | 즉시 최신 코드 적용 |
| `run_diag` | `diag_adspower_profiles.py` subprocess | 프로필 상태 원격 진단 |
| `retry_task` | task_id 를 pending 으로 UPDATE (서버측) | 실패 태스크 재시도 |
| `screenshot_now` | 현재 활성 브라우저 → 캡처 → 업로드 | 라이브 화면 확인 |
| `stop_all_browsers` | `/api/v2/browser-profile/stop-all` | 비상정지 |
| `refresh_fingerprint` | `/api/v2/browser-profile/new-fingerprint` (지정 프로필) | FP 재생성 |
| `update_adspower_patch` | `/api/v2/browser-profile/update-patch` | AdsPower 앱 자체 업데이트 |

**에러 예상 + 방어**
- 워커 오프라인 → 명령 pending 유지, online 시 자동 전달
- 중복 명령 발행 → issued_at 1분 쿨다운 (같은 타입)
- `update_now` 중 git pull 실패 → 롤백 (`updater.py` 의 prev SHA 재활용)
- 워커가 ack 못 보내고 죽음 → 10분 후 `timeout` 으로 자동 마크
- 악의적 명령 주입 → admin_session 필수 + audit_log 기록

**검증**
- [ ] E2E: 발행 → heartbeat → 수신 → ack → UI 결과 표시
- [ ] Mac worker 에 `run_diag` 명령 → 30초 내 왕복 완료
- [ ] 오프라인 워커 → online 복귀 시 pending 명령 실행

---

### T4. B2 DB 백업 cron (30분, Mac → VPS) — **데이터 보호**
**왜**: Vultr Auto Backup OFF. 실 댓글 시작되면 이력 가치 급상승. DB 날아가면 복구 불가.

**설계**
- Backblaze B2 버킷 생성
- rclone config (서비스 계정 + 앱 키)
- `scripts/backup_db.sh`:
  ```
  pg_dump hydra_prod | gzip | rclone rcat b2:hydra-backups/db-$(date +%Y%m%d-%H%M).sql.gz
  rclone delete b2:hydra-backups/ --min-age 7d
  ```
- cron `0 4 * * *` (KST 04:00 = 트래픽 최저)
- 성공/실패 → worker_errors kind=diagnostic (서버 자체 보고)

**에러 예상 + 방어**
- B2 장애 → cron 실패 알림 (Telegram)
- 덤프 크기 초과 → gzip 레벨 9 + 점진적 증가 모니터
- 복원 테스트 없는 백업 = 백업 아님 → **월 1회 임시 DB 로 복원 dry-run** (T4.1)

**검증**
- [ ] dry-run 백업 성공
- [ ] B2 콘솔에서 파일 확인 (gunzip 가능, pg_restore --list 정상)
- [ ] 복원 테스트: 임시 PG 인스턴스에 실제 restore 1회

---

### T5. Stage B 재확인 (30분, Windows 복귀 후) — **AdsPower 3 프로필 실 기동**
**왜**: 실 댓글 전에 프로필 × IP 로테이션이 실제 동작하는지 눈으로 확인 필수.

**순서**
1. Windows 로 복귀
2. `scripts/diag_adspower_profiles.py` 실행
3. 기대: 3/3 profiles healthy + IP 프로필마다 다름
4. 문제 시 `run_diag` 원격 명령으로 반복 진단

**에러 예상 + 방어**
- 프로필 기동 실패 → 커널 수동 다운로드 재확인 (원칙: 워커 PC 세팅 정책 준수)
- IP 로테이션 실패 → ADB 연결 상태 확인 (`adb devices`)
- 특정 프로필만 실패 → AdsPower 앱에서 해당 프로필 설정 검토

---

### T6. Stage C 실 댓글 1건 (1시간 + 24h 관찰, Windows) — **이번 실행의 종결**
**왜**: 실서비스 투입 가능 판정의 유일한 기준.

**사전조건** (모두 체크):
- [ ] T1 스크린샷 캡처 작동
- [ ] T2 어드민 Errors UI 브라우저 확인 가능
- [ ] T3 원격 명령 E2E 성공
- [ ] T4 B2 백업 파일 최근 24h 존재
- [ ] T5 Stage B 3/3 healthy

**순서**
1. **안전 타겟 영상 선정**:
   - 브랜드 무관 (법적 리스크 0)
   - 한국어 영상, 댓글 수 100+ (우리 댓글 묻힘)
   - 채널 크기 중간 (10만~50만 구독, 너무 작으면 채널주 개인 관찰 높음)
2. **계정 1개**: `phuoclocphan36` (k1bmpnnw, 복구 계정 중 첫째)
3. 어드민 UI 에서 `update_now` 명령 → win-m2.2 최신 코드 확정
4. 태스크 enqueue: `comment` 타입, video_id, win-m2.2 지정
5. **DRY-RUN 해제**: 서버 env or secrets 에서 `HYDRA_WORKER_DRY_RUN` 제거 + `restart` 명령
6. 실시간 관찰:
   - 어드민 Errors 탭
   - 워커 Workers 탭 현재 태스크
   - AdsPower 앱에서 k1bmpnnw 기동 확인
7. **성공 기준**:
   - [ ] 댓글 게시 완료 (YouTube 에서 육안 확인)
   - [ ] IP 로테이션 로그 있음
   - [ ] 타이핑 속도 자연 (로그노말 분포)
   - [ ] worker_errors 에 task_fail 없음
8. **24시간 관찰**:
   - [ ] 다음날 계정 로그인 정상
   - [ ] 차단/경고 메시지 없음
   - [ ] 댓글 그대로 살아있음 (삭제 안 됨)

**에러 예상 + 방어**

| 시나리오 | 방어 |
|---|---|
| 로그인 시도 중 captcha/2FA | `hydra/browser/login.py` 의 challenge 핸들러 작동 검증 필수 |
| YouTube DOM 변경 | 스크린샷 + traceback → 즉시 어드민 인지 |
| 태스크 중 네트워크 끊김 | `reschedule_task` 자동 호출 (기존 로직) |
| 댓글 게시 성공인데 30분 내 삭제 | 24h 관찰로 발견 → 해당 계정 cooldown |
| AdsPower 프로필 자체 차단 | ipp_flagged 플래그 set + 해당 계정 휴식 |
| BAN (계정 정지) | 다른 계정으로 확산 방지 — 1건 확인 후 배치 중단 |

---

## Phase 2 합계
**Mac 작업 (T1-T4): ~6시간** — 오늘밤 완료 목표
**Windows 작업 (T5-T6): 1.5시간 + 24h 관찰** — 사무실 복귀 후

**Phase 2 완료 = "이번 실행" 완료 = 실서비스 투입 준비 완료**

---

# Phase 3: 스케일업 전 하드닝 ⬜ (2-3일)

## 목적
**Stage C 1건 성공 → 10건/일 → 100건/일 → 스케일업 전에** 운영 안정성 확보.

## 해야 할 것 — T7~T15

### T7. Circuit Breaker (1시간)
- N회 연속 task_fail → 워커 자동 `pause` + Telegram 경고
- 임계치 worker_config (기본 5회 / 10분 윈도우)
- 어드민 UI 에서 해제 가능

**예상 오류**: 네트워크 일시 장애로 false pause → 재시도 3회 + exponential backoff 이후 판정

### T8. Exit IP 감시 UI (1.5시간)
- Workers 탭 "최근 24h exit IP" 타임라인 그래프
- 같은 IP 가 다른 계정 사용 → 빨간 플래그
- `hydra/infra/ip.py` 의 `check_ip_available` 활용

**예상 오류**: CGN 공유 IP 가 여러 계정에 우연 배정 → ip_log 에 계정 배타 락 (이미 있음) + 알림 우선

### T9. 비상정지 버튼 (30분)
- 어드민 최상단 빨간 "전체 정지" 버튼
- 클릭 → `server_config.is_paused=True` + 모든 워커에 `stop_all_browsers` fan-out
- 확인 모달 "정말 모든 워커 중단?"

**예상 오류**: 실수 클릭 → 2단계 확인 모달 + 10초 카운트다운

### T10. 재시도 정책 재검토 (1시간)
- 태스크 종류별 차등:
  - `comment` 실패: 영구 실패(ban/captcha) 면 0회, 일시면 2회
  - `like` 실패: 3회
  - `warmup` 실패: 5회 (덜 중요)
- 영구 에러 분류: "account suspended", "captcha_persistent", "profile_locked_elsewhere"
- 일시 에러: "timeout", "network", "rate_limited"

### T11. UA/Timezone/Language 검증 (1시간)
- AdsPower `/api/v2/browser-profile/ua` 로 의도 UA 조회
- Playwright 런타임 `navigator.userAgent` 와 대조
- 불일치 시 warning + 해당 프로필 격리
- 주 1회 cron

### T12. VPS 모니터링 + 알람 (1.5시간)
- UptimeRobot `/healthz` 1분 주기 → 다운 시 Telegram
- `scripts/resource_check.py` cron 5분 — CPU/RAM/Disk 임계 → 알림
- Let's Encrypt 만료 14일 전 알림
- 어드민 대시보드 최상단에 VPS 상태 표시

### T13. Staging 환경 (3시간)
- `hydra-staging.duckdns.org` + 별도 DB
- `deploy.sh --env staging`
- 어드민 배포 UI 에 "staging 먼저" 체크박스
- 중요 변경은 staging 에서 24h 검증 후 prod

### T14. Tags 기반 프로필 분류 (1시간)
- AdsPower `/api/v2/browser-tags/*` 활용
- 브랜드별 프로필 태깅 (`brand:탈모-체성케라틴`)
- 제외 리스트 (특정 프로필 → 특정 브랜드 금지)

### T15. 정기 Fingerprint 회전 (1.5시간)
- 계정당 30-60일 간격 `new-fingerprint` 호출
- 주기 ± 무작위 지터 (패턴화 방지)
- 회전 후 첫 24h 쿨다운 (자연스러운 재시작)

---

# Phase 4: 캠페인 런처 (M3) ⬜ (1-2주)

목적: 실 마케팅 운영 가능한 수준.

### T16. 키워드 → 영상 수집 (1일)
- YouTube Data API v3 `search.list`
- 하이브리드: 자동 + 수동 URL
- 필터: 구독자/업로드/언어/댓글활성도

### T17. 다영상 캠페인 스키마 (반나절)
- `campaigns ⟶ campaign_videos (N) ⟶ tasks`
- 퍼널 분배 + 커버율 + 우선순위

### T18. 퍼널 프리셋 편집기 (1일)
- 인지/고려/전환/리텐션 단계별
- 톤 · 직접성 · 길이 · 질문여부 슬라이더
- AI 미리보기 3개

### T19. 브랜드 간접 언급 시스템 (1.5일)
- `brands`: 핵심 성분/방법/금칙어/톤
- AI 하네스: 브랜드명 직접 금지 + 우회 멘션
- 생성 검증 루프

### T20. 다워커 좋아요 부스트 타이밍 (1일)
- 댓글 후 N분 뒤 부스트 예약
- 여러 워커 분산 (같은 댓글 → 같은 IP 클러스터 방지)
- `scheduled_at` + ProfileLock 조합

---

# Phase 5: UI 재설계 ⬜ (1-2주, 후순위)

### T21. Living Ops Console
- 기능 안정화 후 재착수
- `docs/DESIGN.md` `docs/SYSTEM.md` 초안 활용

---

# 🛡 견고화 감사 — 예상 실패 시나리오 + 방어

> "오류 발생 전에 예상" 원칙. 현재 시스템이 다음 상황에 **자동으로 버티거나 알림** 하는지 감사.

## 인프라 레벨

| 시나리오 | 현재 상태 | 미비점 | 해결 Phase |
|---|---|---|---|
| VPS 다운 | ❌ 모니터링 없음 | Telegram 알림 | T12 |
| VPS 재부팅 | ✅ systemd 자동 시작 | - | - |
| DB 디스크 풀 | ❌ | 알림 + auto-vacuum cron | T12 |
| Let's Encrypt 만료 | ⚠️ certbot.timer 자동 갱신하지만 실패 알림 없음 | 만료 14d 전 알림 | T12 |
| VPS IP 변경 | ⚠️ DuckDNS 수동 업데이트 | 자동 ddclient | T12 |
| DB 데이터 손실 | ❌ 백업 없음 | B2 백업 | T4 |
| 서버 버전 롤백 필요 | ✅ `git reset` + deploy.sh | 어드민 UI 미비 | T3 (update_now 에 sha 지정) |

## 워커 레벨

| 시나리오 | 현재 상태 | 미비점 | 해결 |
|---|---|---|---|
| 워커 PC 재부팅 | ✅ Task Scheduler 자동 시작 | - | - |
| 워커 프로세스 크래시 | ✅ RestartCount=3 | - | - |
| 네트워크 일시 끊김 | ✅ Happy Eyeballs + heartbeat 30s 대기 | - | - |
| DNS 간헐 실패 | ✅ IPv6 직통 (NAT64 우회) + v4 fallback | - | - |
| 서버 버전 mismatch | ✅ updater 자동 git pull + 재시작 | - | - |
| 워커 원격 제어 | ❌ | 원격 명령 시스템 | T3 |
| 워커 로그 원격 확인 | ✅ WARNING+ 자동 전송 (log_shipper) | UI 필요 | T2 |
| AdsPower 앱 죽음 | ❌ 워커가 connect 실패 | auto-restart 감지 필요 | T3 (watchdog) |
| USB 테더 폰 분리 | ❌ ADB 호출 실패 | 알림 + 워커 pause | T3 |

## AdsPower 레벨

| 시나리오 | 현재 상태 | 미비점 | 해결 |
|---|---|---|---|
| 커널 미설치 | ⚠️ "update failed" 발생 | 수동 다운로드 정책 명시 | ✅ |
| CDN 접근 불가 | ❌ update failed 반복 | 방화벽/VPN 안내 | 문서 |
| 프로필 구성 깨짐 (`auth_list`) | ❌ | 자동 격리 + 알림 | T3 |
| API rate limit 초과 | ⚠️ 600ms 간격 | 동적 조절 | Phase 3 |
| AdsPower 앱 버전 호환 깨짐 | ❌ | `update_adspower_patch` 명령 | T3 |

## YouTube 레벨 (실 위험)

| 시나리오 | 현재 상태 | 미비점 | 해결 |
|---|---|---|---|
| captcha 챌린지 | ⚠️ 일부 핸들러 있음 | 2Captcha 통합 검증 | Stage C 리허설 |
| 본인인증 돌발 | ✅ identity_challenge 핸들러 (코드 있음) | 실환경 검증 | Stage C |
| 계정 정지 (ban) | ❌ 자동 감지 없음 | `ipp_flagged` 확장 + 다른 계정 보호 | Phase 3 T7 |
| 댓글 자동 삭제 | ❌ 24h 체크 없음 | 주기적 생존 확인 cron | Phase 4 |
| IP 차단 | ⚠️ 로테이션 있음 | 차단 감지 시 쿨다운 | Phase 3 T7 |
| DOM 구조 변경 | ❌ 셀렉터 fragile | 스크린샷 + 알림 → 수동 대응 | T1 |

## 운영/보안 레벨

| 시나리오 | 현재 상태 | 미비점 | 해결 |
|---|---|---|---|
| 어드민 비밀번호 유출 | ❌ | rotate 프로세스 문서화 | T12 |
| JWT_SECRET 노출 | ❌ | rotate 프로세스 | T12 |
| 워커 토큰 유출 | ✅ SHA-256 저장 + 재발급 가능 | UI 필요 | T3 |
| AdsPower 키 유출 | ⚠️ 채팅 히스토리 노출 | 운영 시작 전 rotate | 정책 |
| 악의적 배포 (CI 탈취) | ❌ | 서명된 배포 + 2FA | Phase 3+ |
| DB 직접 접근 우회 | ✅ deployer 유저만 SSH + 키 기반 | - | - |

---

# 현재 "이번 실행" 까지 남은 구체 작업 (요약)

```
오늘밤 (Mac 에서):
  T1. 스크린샷 캡처                    45분   ← 바로 시작
  T2. 어드민 VPS 서빙 + Errors UI      2.5시간
  T3. 원격 명령 시스템                  2시간
  T4. B2 백업 cron                     30분
  ────────────────────────────────────
  합계 ~6시간

내일 (Windows):
  T5. Stage B 3/3 확인                30분
  T6. Stage C 실 댓글 1건             1시간 + 24h 관찰
  ────────────────────────────────────
  합계 1.5시간 + 관찰

이 둘이 끝나면 Phase 2 완료 = 실서비스 투입 준비 완료.
```

---

# 변경 이력
- 2026-04-24 14:00: 초안
- 2026-04-24 18:30: Phase 별 완전 재구조 — 목표 명시, 견고화 감사 테이블 추가, 예상 실패 시나리오 + 방어 체계화
