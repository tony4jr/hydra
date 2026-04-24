# HYDRA 로드맵

> 작성: 2026-04-24 · 세션 합의본. Phase 전환 시 업데이트.

## 원칙

1. **작업마다 "성공 기준" 명문화** — 모호하게 "됐다" 넘어가지 않음
2. **3단 검증**: (a) 단위 테스트 (b) 실환경 probe (c) 사용자 육안 확인
3. **Phase 전환은 사용자 명시적 승인** — AI 가 "됐다" 선언 금지
4. **임시방편 금지** — 증상만 덮지 않고 근본 원인 규명 후 수정

## 워커 PC 세팅 운영 정책

새 워커 PC 세팅 시 순서:
1. `setup.ps1` 실행 (워커 enrollment + Task Scheduler 등록)
2. **AdsPower 앱 실행 + 로그인**
3. **AdsPower 앱에서 프로필 > 편집 > 브라우저 코어 > 모든 Chrome 버전 수동 다운로드**
4. `Start-ScheduledTask -TaskName HydraWorker` 로 워커 기동
5. 어드민 UI 에서 워커 online 확인

→ 첫 태스크 실행 시 커널 다운로드 대기로 실패하지 않음.
→ 자동화 스크립트는 안 씀 (AdsPower UI 가 더 신뢰성 있음).

---

## 현재 상태 (2026-04-24)

### 완료
- M0: 로컬 MVP
- M1: VPS 오케스트레이션 (FastAPI · PG · JWT · Task Queue v2)
- M2.1: DRY-RUN 신호 루프
- M2.2 Stage 0: 3 계정 복구 import
- 근본 해결: 서버 IPv6 AAAA + Happy Eyeballs fallback
- 근본 해결: SHA-256 O(1) auth + 가짜 워커 정리
- 근본 해결: nginx 정식 config (경로 라우팅)
- 워커 에러 리포팅 시스템 (DB + API + 훅 + sys.excepthook)
- 중앙집중 로그 (WARNING+ 자동 전송 + Task Scheduler stdout 파일화)
- 어드민 AdsPower API 키 분배
- AdsPower 브라우저 버전 preload 스크립트
- M2.2 Stage A: Windows 워커 heartbeat 안정화 + DRY-RUN 11건 완주

### 진행 중
- M2.2 Stage B: AdsPower 3 프로필 기동 검증 (2/3 완료 — k1bmpnry SunBrowser 144 다운로드 대기)

---

## Phase 1 — Stage C 전 안전장치 (반나절)

> **목표**: 실 댓글 돌릴 때 실패해도 원격에서 진단·복구·재시도 가능한 상태

### T1. 스크린샷 캡처 (45분)
**왜**: 실 YouTube 실패 시 원인 추정 불가. 육안 확인 수단 필수.

**설계**
- 서버 스토리지: `/var/www/hydra/screenshots/` (로컬 디스크, 1GB 제한, 7일 auto-delete)
- API: `POST /api/workers/report-error` multipart 확장 → `file=@screenshot.png` 저장 → `worker_errors.screenshot_url`
- 워커: `WorkerSession.capture_screenshot()` 헬퍼 — executor 예외 catch 시 자동 호출
- nginx: `/screenshots/` 정적 서빙 + 관리자 JWT 미들웨어

**검증 게이트**
- [ ] pytest: multipart 업로드 / 파일 존재 / URL 저장 / 어드민 접근 권한 (4건)
- [ ] 실환경: Mac worker 의도적 예외 → 서버에 파일 존재 + DB URL 저장 확인
- [ ] 사용자: 브라우저에서 스크린샷 URL 클릭 → 이미지 보임

---

### T2. 어드민 Errors UI + frontend VPS 서빙 (2.5시간)
**왜**: API 만 있고 UI 없으면 리포트 안 보임. frontend 가 VPS 에서 서빙 안 됨.

**설계**
- **frontend VPS 서빙**: deploy.sh 에 npm 설치 확인 + 빌드 산출물 rsync + nginx 검증
- **새 라우트**: `frontend/src/features/workers/errors-page.tsx`
  - 최신 100건 리스트 (시간순)
  - 필터: worker_id / kind / 날짜 범위
  - 행 클릭 → 상세 (traceback + context + screenshot 미리보기)
  - 자동 갱신 10초
- **Workers 상세**: 해당 워커 최근 에러 서브탭

**검증 게이트**
- [ ] pytest: API 기존 7건 유지
- [ ] 실환경: `curl https://hydra-prod.duckdns.org/` → HTML 리턴 (현재 "hydra-prod ok" 탈출)
- [ ] 사용자: 브라우저 `/admin` 접속 → Workers → Errors 탭 → 최근 리포트 리스트 + 상세 보임

---

### T3. B2 DB 백업 cron (30분)
**왜**: Vultr Auto Backup OFF. DB 날아가면 끝. 실 댓글 쌓이면 데이터 가치 급상승.

**설계**
- B2 버킷 + rclone 설정
- `scripts/backup_db.sh`: `pg_dump hydra_prod | gzip | rclone copyto b2:hydra-backups/db-YYYYMMDD.sql.gz`
- cron 매일 04:00
- 7일 유지 (rclone --min-age cleanup)
- 성공/실패 worker_errors kind=diagnostic 업로드

**검증 게이트**
- [ ] shell test: dry-run 백업 exit 0
- [ ] 실환경: 수동 1회 실행 → B2 파일 확인 + gunzip + pg_restore --list 테이블 정상
- [ ] 복원 테스트: 임시 DB 에 실제 restore 1회 성공

---

### T4. 원격 명령 시스템 (1.5시간)
**왜**: 워커 원격 제어 불가 시 실패 나면 Windows 까지 가야 함. 스케일업 전 필수.

**설계**
- DB: `worker_commands` (id, worker_id, command, payload, issued_by, issued_at, delivered_at, result, completed_at)
- 어드민 API: `POST /api/admin/workers/{id}/command` — command 중 하나:
  - `restart` / `run_diag` / `retry_task` / `clear_playwright_cache`
  - `update_now` / `pause` / `resume` / `screenshot_now`
- heartbeat 응답에 `pending_commands: [...]` 추가
- 워커: 명령 수신 → 실행 → `POST /api/workers/command/{id}/ack`
- 어드민 UI: Workers 탭 각 행에 명령 버튼 드롭다운

**검증 게이트**
- [ ] pytest: E2E (발행 → 수신 → ack → 결과 표시)
- [ ] 실환경: `run_diag` 명령 → 10초 내 워커 실행 + 결과 업로드
- [ ] 사용자: UI 에서 명령 버튼 클릭 → 결과 확인

> **이 Task 끝나면 원격 디버깅 + 자동 복구 피드백 루프 100% 완성.**

---

## Phase 2 — M2.2 Stage C 실 댓글 1건 (1시간)

### T5. Stage C 실행
**사전 조건**: T1-T4 모두 완료 + Gate 통과

**순서**
1. 안전 타겟 영상 선정 (브랜드 무관, 한국어, 댓글 활발, 중간 규모 채널)
2. 계정 1개 선택 — phuoclocphan36 (k1bmpnnw) 우선
3. 워커 DRY-RUN 해제 (ENV 플래그 제거)
4. 태스크 1건 enqueue (`comment`, 지정 video_id, win-m2.2 전용)
5. 관찰 (Errors UI + 워커 로그 스트림 병렬)
6. 성공: 실제 YouTube 에서 댓글 확인, IP 로테이션 로그, 타이핑 검증
7. 실패: 스크린샷 + traceback → 원격 명령으로 재시도 or 롤백

**검증 게이트**
- [ ] Phase 1 Gate 모두 통과
- [ ] 댓글 게시 성공
- [ ] **24시간 관찰**: 다음날 계정 로그인 정상, 차단/경고 없음
- [ ] 사용자 "실 댓글 남음 + 24h 후 계정 정상" 확인

---

## Phase 3 — 스케일업 전 하드닝 (2-3일)

### T6. Circuit Breaker (1시간)
- N회 연속 task_fail → 워커 자동 pause + 어드민 경고
- 임계치 worker_config 로 설정

### T7. Exit IP 감시 UI (1.5시간)
- Workers 탭 "최근 24h exit IP 히스토리" 그래프
- 같은 IP 가 다른 계정에 재사용 → 빨간 강조

### T8. 비상정지 버튼 (30분)
- 어드민 최상단 빨간 버튼 → 전 워커 즉시 pause
- `server_config.is_paused=True` (이미 있음) + UI

### T9. 재시도 정책 재검토 (1시간)
- 태스크 종류별 차등 (comment/like/warmup)
- 영구 에러 vs 일시 에러 분류 + 차등 재시도

### T10. UA/Timezone/Language 검증 (1시간)
- Playwright `navigator.userAgent`, `Intl.DateTimeFormat()`, `navigator.language` 체크
- AdsPower 프로필 설정 값과 대조 → 불일치 경고

### T11. VPS 모니터링 + 알람 (1.5시간)
- UptimeRobot `/healthz` 1분 체크 → 다운 시 Telegram
- `scripts/resource_check.py` cron — CPU/RAM/Disk 임계 알림
- Let's Encrypt 만료 14일 전 알림

### T12. Staging 환경 (3시간)
- `hydra-staging.duckdns.org` + 별도 DB
- `deploy.sh --env staging`
- 어드민 "staging 먼저 배포" 체크박스

---

## Phase 4 — M3 캠페인 런처 (1-2주)

### T13. 키워드 → 영상 수집 (1일)
- YouTube Data API v3 `search.list`
- 하이브리드: 자동 + 수동 URL
- 필터: 구독자/업로드날짜/언어

### T14. 다영상 캠페인 스키마 (반나절)
- `campaigns ⟶ campaign_videos(N) ⟶ tasks`
- 퍼널 단계 분배 / 커버율 / 우선순위

### T15. 퍼널 프리셋 편집기 (1일)
- 인지/고려/전환/리텐션 단계별
- 톤 · 직접성 · 길이 · 질문 여부 슬라이더
- AI 미리보기 샘플 3개

### T16. 브랜드 간접 언급 시스템 (1.5일)
- `brands` 테이블: 핵심 성분/방법 키워드 + 금칙어 + 톤
- AI 하네스: 브랜드명 직접 금지 + 성분 우회 멘션
- 생성 검증 루프

### T17. 다워커 좋아요 부스트 타이밍 (1일)
- 댓글 게시 → N분 후 부스트 예약
- 여러 워커 분산 (같은 댓글 같은 IP 피함)
- `scheduled_at` + `ProfileLock` 조합

---

## Phase 5 — UI 재설계 (1-2주, 후순위)

### T18. Living Ops Console
- `docs/DESIGN.md` · `docs/SYSTEM.md` 초안 활용
- 기능 안정화 후 재착수

---

## 검증 자동화

### scripts/e2e_check.sh — Phase 종료 시 전체 probe

```bash
bash scripts/e2e_check.sh --phase=1
```

Phase 1 기준 체크:
- `/healthz` 응답
- `/admin/` HTML 응답 (not "hydra-prod ok")
- 워커 heartbeat v2 < 200ms
- `/api/workers/report-error` multipart 정상
- nginx `/screenshots/` 경로 권한
- B2 백업 최근 24h 파일 존재
- 원격 명령 왕복 < 30s
- `worker_errors` 최근 1h < 10건

**전부 ✓ 아니면 다음 Phase 진입 차단.**

---

## Phase 전환 템플릿

Phase 종료 시 AI 가 사용자에게 제시:

```
[Phase N 완료 점검]
  ✓ T-X 항목명: 방법 → 결과
  ⚠️ 사용자 확인 필요:
     - 항목 1
     - 항목 2
  → Phase N+1 진입할까요?
```

사용자 **명시적 "ㄱ"** 받아야 다음 Phase 시작.

---

## 합산 시간

| Phase | 작업량 | 시작 조건 |
|---|---|---|
| Phase 1 (T1-T4) | 반나절 | Stage B 완료 후 |
| Phase 2 (T5) | 1시간 | Phase 1 Gate 통과 |
| Phase 3 (T6-T12) | 2-3일 | Stage C 성공 + 1일 안정 운영 |
| Phase 4 (T13-T17) | 1-2주 | Phase 3 완료 |
| Phase 5 (T18) | 1-2주 | Phase 4 완료 |

---

## 변경 이력

- 2026-04-24: 초안 작성 (세션 합의)
