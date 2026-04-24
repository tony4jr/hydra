# HYDRA 로드맵 (최신화)

> 마지막 업데이트: 2026-04-24 · Windows 워커 복귀 가능 시점까지 원격 준비 단계.

## 원칙

1. **작업마다 "성공 기준" 명문화** — 모호하게 "됐다" 넘어가지 않음
2. **3단 검증**: (a) 단위 테스트 (b) 실환경 probe (c) 사용자 육안 확인
3. **Phase 전환은 사용자 명시적 승인** — AI 가 "됐다" 선언 금지
4. **임시방편 금지** — 증상만 덮지 않고 근본 원인 규명 후 수정
5. **계획 변경은 여기 문서에 반영 후** — 구두 대화로 흘려보내지 않음

## 워커 PC 세팅 운영 정책

새 워커 PC 세팅 시:
1. `setup.ps1` 실행 (enrollment + Task Scheduler)
2. AdsPower 앱 로그인
3. **AdsPower > 프로필 편집 > 브라우저 코어 > 전체 Chrome 버전 수동 다운로드**
4. `Start-ScheduledTask -TaskName HydraWorker`
5. 어드민에서 online 확인

---

# 현재 상태 (2026-04-24 18:30 기준)

## ✅ 완료 (29개 커밋 / 실환경 검증됨)

### M0 — 로컬 MVP
- 단일 계정 댓글 · 좋아요 (Playwright + AdsPower)

### M1 — VPS 오케스트레이션
- FastAPI + PostgreSQL + JWT 어드민
- Task Queue v2 (SKIP LOCKED + ProfileLock, 계정 1:1 프로필)
- 프리셋/캠페인/워밍업/계정 CRUD
- systemd 배포 (`/api/admin/deploy`)

### M2.1 — DRY-RUN 신호 루프
- `HYDRA_WORKER_DRY_RUN=1` 게이트
- Mac 워커 + Windows 워커 heartbeat/fetch/complete

### M2.2 — 실 환경 단계
- **Stage 0 완료** — 복구 3계정 (`k1bmpnnw/k1bmpnpk/k1bmpnry`) import
- **Stage A 완료** — Windows 워커 heartbeat 안정화 + DRY-RUN 11건 완주

### 근본 해결 (Windows 워커 가동 과정에서 발견 + 수정)

1. **서버 IPv6 dual-stack** (commit `767bf25`)
   - DuckDNS AAAA 레코드 등록 (`2401:c080:1c01:6dd:5400:6ff:fe19:603f`)
   - nginx `listen [::]:443 ssl http2`
   - 결과: DNS64 NAT64 경로 실패 우회

2. **워커 Happy Eyeballs fallback** (commit `448491d`, `9c5ecec`)
   - 기본 dual-stack → 실패 시 IPv4-only 자동 재시도 (sticky)
   - heartbeat 실패 시 spam 버그 수정 (초당 수십 번 → 30초 간격)
   - 매 요청 fresh httpx 클라이언트 (stale 커넥션풀 회피)

3. **워커 에러 리포팅 시스템** (commit `f9de32b`)
   - `worker_errors` 테이블 + `/api/workers/report-error`
   - kinds: heartbeat_fail / fetch_fail / task_fail / diagnostic / update_fail / other
   - 10분 dedupe, 관리자 JWT 조회 엔드포인트
   - Python logging WARNING+ 자동 전송 + sys.excepthook (commit `2f68785`)

4. **SHA-256 O(1) auth** (commit `a1189c1`, `9fb2fde`)
   - 워커 토큰 검증: 전수 bcrypt(7초) → SHA-256 인덱스 조회(100ms)
   - 죽은 테스트 워커 3개 정리 (DB DELETE)

5. **nginx 정식 설정** (commit `767bf25`)
   - 기존: `location / { return "hydra-prod ok" }` placeholder
   - 변경: `/api/*` → FastAPI, `/static/*` → FastAPI, `/` → `/var/www/hydra` React SPA
   - 80→443 redirect, 보안 헤더, SPA fallback, 정적 자산 캐시

6. **AdsPower API 키 중앙 분배** (commit `271c935`)
   - `workers.adspower_api_key_enc` (Fernet 암호화)
   - PATCH /api/admin/workers/{id} 로 설정
   - heartbeat 응답에 평문 포함 → 워커 os.environ 주입

7. **AdsPower 로컬 API 경로** (commit `7f3bf76`)
   - `local.adspower.net` → `127.0.0.1` 직접 (로컬 DNS 의존성 제거)

8. **워커 updater** (commit `f526f46`)
   - origin/main 도달 시 재시작 루프 방지 (no-op 분기)

---

## 🟡 진행 중 / 대기

### Stage B — AdsPower 3 프로필 실 기동 검증
- 스크립트: `scripts/diag_adspower_profiles.py` (commit `f9fdce5` — IP 로테이션 포함)
- **Windows 에서 실행 필요** — 복귀 후 5분 작업
- 사용자 사무실 복귀 시 실행

### Stage C — DRY-RUN 해제 후 실 댓글 1건
- Stage B 완료 + Phase 1 완료 후
- 사용자 사무실 복귀 시

---

# 앞으로 (우선순위 순)

## 🔴 Phase 1 — Stage C 전 안전장치 (오늘밤 Mac 에서 가능)

### T1. 스크린샷 캡처 (45분) — **실패 시 육안 확인 수단**
- 서버 `/api/workers/report-error` multipart 확장
- `/var/www/hydra/screenshots/` 저장 + 7일 auto-cleanup
- nginx `/screenshots/` 정적 서빙 (관리자 JWT 체크)
- 워커 `WorkerSession.capture_screenshot()` 헬퍼 — executor 예외 catch 시 자동 호출
- 검증: Mac 에서 의도 예외 → 서버 디스크에 파일 + DB URL 저장 + 브라우저로 열림

### T2. 어드민 VPS 서빙 + Errors 탭 UI (2.5시간) — **원격 관리 가능**
- deploy.sh 에 npm 빌드 + rsync 확인 (VPS 에 node 설치 필요할 수 있음)
- `frontend/src/features/workers/errors-page.tsx` 신규
  - 최신 100건 리스트 (시간순)
  - 필터: worker_id / kind / 날짜 범위
  - 상세: traceback + context + screenshot 미리보기
  - 자동 갱신 10초
- Workers 상세에도 서브탭 추가
- 검증: `curl https://hydra-prod.duckdns.org/admin` HTML 리턴 + 브라우저 진입

### T3. 원격 명령 시스템 (2시간) — **워커 원격 제어의 핵심**
- DB `worker_commands` 테이블 (id, worker_id, command, payload, issued_by, issued_at, delivered_at, result, completed_at)
- 어드민 API: `POST /api/admin/workers/{id}/command`
- heartbeat 응답에 `pending_commands[]`
- 워커: 명령 수신 → 실행 → `POST /api/workers/command/{id}/ack`

**지원 명령 (8종)**:

| 명령 | 효과 |
|---|---|
| `restart` | Task Scheduler 프로세스 재시작 |
| `update_now` | `git pull` + pip install + 즉시 재시작 (버전 bump 기다리지 않고) |
| `run_diag` | `scripts/diag_adspower_profiles.py` 실행 → 결과 업로드 |
| `retry_task` | 특정 task_id 를 `pending` 으로 되돌림 |
| `screenshot_now` | 현재 브라우저 화면 캡처 업로드 |
| `stop_all_browsers` | AdsPower `/api/v2/browser-profile/stop-all` 호출 (비상정지) |
| `refresh_fingerprint` | 지정 프로필 `/api/v2/browser-profile/new-fingerprint` |
| `update_adspower_patch` | AdsPower 앱 자체 패치 `/api/v2/browser-profile/update-patch` |

- 어드민 UI: Workers 탭 각 행에 드롭다운 버튼
- 검증: UI 에서 `run_diag` 클릭 → 10초 내 워커 실행 + Errors 탭에 결과

### T4. B2 DB 백업 cron (30분) — **데이터 보호**
- rclone + B2 버킷
- `scripts/backup_db.sh`: `pg_dump | gzip | rclone copyto`
- cron 매일 04:00 / 7일 retention
- 성공/실패 → worker_errors kind=diagnostic
- 검증: 복원 테스트 1회

**Phase 1 합계: 약 6시간**

---

## 🟡 Phase 2 — Stage B + Stage C (Windows 복귀 후, 1.5시간)

### T5. Stage B 재확인 (30분)
- Windows 에서 `diag_adspower_profiles.py` 실행
- 3/3 profiles healthy + IP 로테이션 3번 확인
- 커널 수동 다운로드 완료 가정 (어제 사용자 직접)

### T6. Stage C 실 댓글 1건 (1시간)
1. 안전 타겟 영상 선정
2. `phuoclocphan36` (k1bmpnnw) 계정 1개
3. 어드민에서 `update_now` 명령 → 워커 최신 코드로
4. 태스크 1건 enqueue (`comment`, win-m2.2 전용)
5. Errors UI + 스크린샷 실시간 관찰
6. 성공: YouTube 에서 댓글 확인 + IP 로테이션 로그 + 타이핑 자연도
7. **24시간 관찰** → 다음날 계정 정상 확인

---

## 🟢 Phase 3 — 스케일업 전 하드닝 (2-3일)

### T7. Circuit Breaker (1시간)
- N회 연속 task_fail → 워커 자동 pause + 어드민 경고

### T8. Exit IP 감시 UI (1.5시간)
- Workers 탭 24h exit IP 히스토리 그래프
- 같은 IP 다계정 재사용 → 빨간 경고

### T9. 비상정지 버튼 (30분)
- 어드민 최상단 빨간 버튼
- `server_config.is_paused=True` + 모든 워커에 `stop_all_browsers` 명령 fan-out

### T10. 재시도 정책 재검토 (1시간)
- 태스크 종류별 차등 (comment/like/warmup)
- 영구 vs 일시 에러 분류 + 차등 재시도 횟수

### T11. UA/Timezone/Language 검증 (1시간)
- AdsPower `/api/v2/browser-profile/ua` 로 **기동 없이** 의도 UA 조회
- Playwright 런타임 값과 대조 → 불일치 경고

### T12. VPS 모니터링 + 알람 (1.5시간)
- UptimeRobot `/healthz` 1분 체크 → 다운 시 Telegram
- `scripts/resource_check.py` cron — CPU/RAM/Disk 임계 알림
- Let's Encrypt 만료 14일 전 알림

### T13. Staging 환경 (3시간)
- `hydra-staging.duckdns.org` + 별도 DB
- `deploy.sh --env staging`
- 어드민 "staging 먼저 배포" 체크박스

### T14. Tags 기반 프로필 분류 (1시간)
- AdsPower `/api/v2/browser-tags/*` 활용
- 브랜드별 프로필 태깅 + 제외 리스트

### T15. 정기 Fingerprint 회전 (1.5시간)
- 계정당 30-60일 간격 `new-fingerprint` 호출
- 주기 · 무작위 지터
- 회전 후 첫 댓글은 쿨다운

---

## 🚀 Phase 4 — M3 캠페인 런처 (1-2주)

### T16. 키워드 → 영상 수집 (1일)
- YouTube Data API v3 `search.list`
- 하이브리드: 자동 크롤 + 수동 URL 추가
- 필터: 구독자/업로드날짜/언어

### T17. 다영상 캠페인 스키마 (반나절)
- `campaigns ⟶ campaign_videos(N) ⟶ tasks`
- 퍼널 단계 분배 + 커버율 + 우선순위

### T18. 퍼널 프리셋 편집기 (1일)
- 인지/고려/전환/리텐션 단계별 프리셋
- 톤 · 직접성 · 길이 · 질문 여부 슬라이더
- AI 미리보기 샘플 3개

### T19. 브랜드 간접 언급 시스템 (1.5일)
- `brands` 테이블: 핵심 성분/방법 키워드 + 금칙어 + 톤
- AI 하네스: 브랜드명 직접 금지 + 성분 우회 멘션
- 생성 검증 루프 (금칙어 필터 + 자연도)

### T20. 다워커 좋아요 부스트 타이밍 (1일)
- 댓글 게시 → N분 후 부스트 예약
- 여러 워커 분산 (같은 댓글 같은 IP 피함)
- `scheduled_at` + `ProfileLock` 조합

---

## 🎨 Phase 5 — UI 재설계 (1-2주, 후순위)

### T21. Living Ops Console
- 기능 안정화 후 재착수

---

# 검증 자동화

## scripts/e2e_check.sh (Phase 종료 체크)

```bash
bash scripts/e2e_check.sh --phase=1
```

Phase 1 통과 기준:
- `/healthz` 200
- `/admin/` HTML 리턴 (not "hydra-prod ok")
- 워커 heartbeat v2 < 200ms
- `/api/workers/report-error` multipart 정상
- `/screenshots/` nginx 권한 체크
- B2 최근 24h 백업 파일 존재
- 원격 명령 왕복 < 30s
- 최근 1h worker_errors < 10건

**전부 ✓ 아니면 다음 Phase 차단.**

---

# 합산 시간

| Phase | 작업량 | 시작 조건 | 장소 |
|---|---|---|---|
| **Phase 1 (T1-T4)** | ~6시간 | 지금 | **Mac 가능** |
| Phase 2 (T5-T6) | 1.5시간 + 24h 관찰 | Phase 1 완료 | **Windows 필요** |
| Phase 3 (T7-T15) | 2-3일 | Stage C 성공 + 1일 안정 | 어디든 |
| Phase 4 (T16-T20) | 1-2주 | Phase 3 완료 | 어디든 |
| Phase 5 (T21) | 1-2주 | Phase 4 완료 | 어디든 |

---

# 변경 이력

- 2026-04-24 14:00: 초안 작성
- 2026-04-24 18:30: **최신화**
  - T3 (원격 명령) 에 8가지 명령 전부 구체화
  - 완료 섹션에 실제 커밋 SHA 매핑
  - AdsPower API 조사 결과 반영 (v2 엔드포인트, 커널 수동 다운로드 정책)
  - Phase 3 신규: T14 (Tags), T15 (Fingerprint 회전)
  - "장소 (Mac/Windows)" 컬럼 추가 — 원격 작업 가능 여부 명시
