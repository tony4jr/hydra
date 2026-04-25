# HYDRA — 마스터 문서

> 단일 진입점. 모든 다른 문서는 여기서 출발해 분기.

**마지막 업데이트**: 2026-04-25

---

# 0. 30초 요약

```
🎯 목표: YouTube 댓글 마케팅 자동화 (시장 출시 가능 수준)
🏗 구성: VPS 서버 + Mac/Windows 워커 + USB 테더링 폰
✅ 완료: Phase 0+1 + Phase 2a T1-T3 + Phase 3a 전체 + Phase 3b 일부 (T14/T15)
🟡 진행: Phase 2a T4 (B2 코드 ✅, 자격증명 대기)
⬜ 외부 자격증명 필요: T4 B2 / T12 UptimeRobot / T13 staging / T16 YouTube API / T19 Claude API
⬜ Windows 필요: Phase 2b (T5) / Phase 2c (T6 + 24h) — '이번 실행' 종결
🔍 검증: 3계층 (pytest 478 / e2e 13섹션 / 육안)
🚀 임박: T4 자격증명 받으면 즉시 가동 → Phase 2a 게이트 통과 → Windows 복귀 시 Stage B/C
```

---

# 1. 목표 + 비즈니스 요건

## 1.1 #1 목표

**브랜드 간접 언급 기반 YouTube 댓글 마케팅 자동화**

- 다계정(50+) × 다영상 캠페인
- 퍼널 단계별(인지/고려/전환/리텐션) 댓글 생성
- 다워커 좋아요 부스트 → 상단 노출
- 안티디텍션 최우선 (프로필/IP/타이핑/FP 다양화)
- 어디서든 원격 운영 (어드민 UI)

## 1.2 핵심 운영 원칙

1. **1 계정 = 1 AdsPower 프로필** (DB UNIQUE 강제, 절대 침범 X)
2. **모든 행동 랜덤화** — 고정값/패턴 금지
3. **간접 언급** — 브랜드명 직접 X, 핵심 성분/방법 우회
4. **질보다 양보다 오래가기** — 계정 1개 1년 운영 > 계정 100개 1주 BAN
5. **사전 예상** — "오류 발생하면" 이 아니라 "발생 시 자동복구" 설계

---

# 2. 시스템 아키텍처

## 2.1 컴포넌트 맵

```
┌──────────────── VPS (Vultr Seoul, hydra-prod.duckdns.org) ────────────────┐
│                                                                           │
│   nginx ──┬── /api/*        ──→ FastAPI (127.0.0.1:8000)                 │
│           ├── /static/*     ──→ FastAPI (templates)                      │
│           ├── /healthz      ──→ "hydra-prod ok"                          │
│           └── /            ──→  /var/www/hydra (React SPA)               │
│                                                                           │
│   FastAPI ──┬── Auth (JWT 어드민, SHA-256 워커)                           │
│             ├── Task Queue v2 (SKIP LOCKED + ProfileLock)                │
│             ├── Worker Errors + Screenshots                              │
│             ├── Worker Commands (8종)                                    │
│             ├── Admin Endpoints (account/preset/campaign/...)            │
│             └── PostgreSQL                                               │
│                                                                           │
│   B2 백업 (cron 매일 04:00) ──→ Backblaze B2 (T4 진행 예정)               │
│                                                                           │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ HTTPS (IPv4 + IPv6 dual-stack)
                                    │ + Happy Eyeballs fallback
            ┌───────────────────────┼───────────────────────┐
            │                       │                       │
   ┌────────▼─────────┐   ┌─────────▼─────────┐   ┌─────────▼─────────┐
   │  Mac Worker      │   │  Windows Worker   │   │  Windows Worker   │
   │  (mac-dryrun)    │   │  (win-m2.2)       │   │  (...)            │
   │                  │   │                   │   │                   │
   │  • Heartbeat 15s │   │  • Heartbeat 15s  │   │                   │
   │  • Task fetch    │   │  • Task fetch     │   │                   │
   │  • AdsPower API  │   │  • AdsPower API   │   │                   │
   │    (127.0.0.1)   │   │    (127.0.0.1)    │   │                   │
   │  • Playwright    │   │  • Playwright     │   │                   │
   │  • Log shipper   │   │  • Log shipper    │   │                   │
   │  • Updater       │   │  • Task Scheduler │   │                   │
   │                  │   │                   │   │                   │
   └────────┬─────────┘   └─────────┬─────────┘   └────────┬──────────┘
            │ ADB                   │ ADB                   │ ADB
            ▼                       ▼                       ▼
   ┌────────────┐         ┌────────────┐         ┌────────────┐
   │ USB 테더 폰 │         │ USB 테더 폰 │         │ USB 테더 폰 │
   │ (IP 로테)   │         │ (IP 로테)   │         │ (IP 로테)   │
   └────────────┘         └────────────┘         └────────────┘
```

## 2.2 데이터 흐름 (캠페인 → 댓글 게시)

```
1. 어드민 → 캠페인 생성 + 키워드 입력
   ↓
2. 백엔드: YouTube API 로 영상 수집 → campaign_videos 채우기
   ↓
3. 캠페인 스케줄러: 영상 × 계정 매트릭스 → tasks 생성 (comment, like_boost 등)
   ↓
4. 워커 PC 1: heartbeat → fetch_tasks → ProfileLock 획득
   ↓
5. 워커 PC 1: ADB IP 로테이션 → AdsPower 프로필 기동 → Playwright 연결
   ↓
6. 워커 PC 1: YouTube 접속 → 영상 시청 → 댓글 작성 (퍼널/브랜드 톤 적용)
   ↓
7. 워커 PC 1: complete_task → ProfileLock 해제
   ↓ (서버 hooks)
8. 댓글 게시 후 N분 → like_boost 태스크 enqueue (다른 워커 대상)
   ↓
9. 워커 PC 2,3 → 시간차로 좋아요 → 댓글 상단 노출
```

## 2.3 런타임 신호 흐름 (heartbeat)

```
Worker (15s tick)
   │
   POST /api/workers/heartbeat/v2
   ├── X-Worker-Token: <token>
   ├── body: { version, os_type, cpu, mem, ... }
   │
   ▼
Server
   ├── SHA-256 lookup (O(1) auth)
   ├── update workers.last_heartbeat
   ├── load pending_commands [최대 10개]
   ├── decrypt adspower_api_key (Fernet)
   │
   ▼
Response
   ├── current_version (워커 자동 git pull 트리거)
   ├── paused (전역 일시정지)
   ├── canary_worker_ids
   ├── worker_config { poll_interval, max_concurrent }
   ├── adspower_api_key (워커 os.environ 주입)
   └── pending_commands [{id, command, payload}, ...]
        │
        ▼
   Worker 명령 실행 → POST /command/{id}/ack
```

---

# 3. 구현 전략

## 3.1 레이어 별 핵심 패턴

### 백엔드 (FastAPI + PG)
- **DB 마이그레이션은 alembic 단방향** — downgrade 작성 (롤백 가능)
- **Pydantic v2 모델** — 응답 스키마 명시 (OpenAPI 자동)
- **JWT 어드민 + SHA-256 워커** — 분리된 인증 체계
- **SKIP LOCKED + ProfileLock** — 다워커 동시 fetch 안전
- **Fernet 암호화** — 비밀번호 / AdsPower 키

### 프론트엔드 (React + TanStack Router + shadcn/ui)
- **Vite 빌드** — Mac 에서 빌드 → rsync → VPS `/var/www/hydra/`
- **TanStack Router** — 파일 기반 라우팅, SPA fallback (nginx)
- **단일 axios 인스턴스** — JWT 자동 주입, 401 → 로그인 리다이렉트
- **자동 갱신** — 어드민 UI 10초 polling (Errors, Workers)
- **multipart 파일** — `http` 인스턴스로 (JWT 인터셉터 동일)

### 워커 (Python + asyncio + Playwright)
- **Happy Eyeballs (RFC 8305)** — dual-stack → IPv4 fallback (sticky)
- **Fresh httpx client per request** — stale 커넥션 회피
- **Log shipper (WARNING+)** — 로컬 + 서버 동시 기록
- **sys.excepthook** — 미처 잡히지 않은 예외도 서버로
- **Task Scheduler 자동 재시작** — RestartCount=3
- **Updater (heartbeat 응답 기반)** — current_version mismatch 시 git pull + exit

### AdsPower 통합
- **127.0.0.1:50325 직접** — DNS 의존성 제거
- **v1 list (50개 정상) + v2 ua/start** — 엔드포인트별 검증된 것 사용
- **Rate limit 준수** — 0.6s 간격 (2 req/sec)
- **수동 커널 다운로드 정책** — 워커 세팅 시 AdsPower UI 에서 모든 Chrome 버전 받기

### IP 로테이션
- **ADB svc data off/on** — 모바일 핫스팟 유지 (airplane 아닌 이유)
- **`ip_log` 테이블** — 같은 IP 다계정 30분 이내 사용 차단
- **계정당 cooldown** — 운영 정책

## 3.2 안티디텍션 원칙

| 영역 | 패턴 |
|---|---|
| 프로필 | 1 계정 = 1 AdsPower 프로필 (영구) |
| 브라우저 버전 | 다양한 Chrome 버전 (127~144) — 분포 자연화 |
| Fingerprint | 정기 `new-fingerprint` (30~60일, ±지터) |
| IP | USB 테더 ADB 토글 → 다른 IP 매번 |
| IP 충돌 | 30분 윈도우 내 다계정 동일 IP 차단 |
| 타이핑 | 로그노말 분포 + 오타 패턴 |
| 클릭 | 정중앙 회피 + 자연스러운 hover |
| 휴식 | persona 별 speed/typing 프로파일 + 활동량 multiplier |
| 댓글 | 퍼널 단계별 톤 + 브랜드 우회 멘션 |
| 좋아요 | 다워커 시간차 (clustering 회피) |
| 본인인증 | identity_challenge 핸들러 (코드 있음, 실 검증 Stage C) |

## 3.3 안정성 패턴

| 영역 | 패턴 | 위치 |
|---|---|---|
| 네트워크 간헐 실패 | Happy Eyeballs + 30s sleep on heartbeat fail | `worker/client.py` |
| DB 손실 | B2 daily 백업 (T4) | `scripts/backup_db.sh` |
| 워커 크래시 | Task Scheduler RestartCount=3 | `setup.ps1` |
| 워커 버전 mismatch | updater 자동 pull + exit | `worker/updater.py` |
| 원격 명령 | 8종 (restart/update_now/run_diag/...) | `worker/commands.py` |
| 에러 가시성 | log_shipper (WARNING+) + screenshot 캡처 | `worker/log_shipper.py` |
| 프로덕션 변경 | alembic 마이그레이션 + deploy.sh | `scripts/deploy.sh` |
| TLS 만료 | certbot.timer (자동 갱신) | systemd |
| 비상 정지 | server_config.is_paused + stop_all_browsers fan-out | (T8 예정) |

---

# 4. 진행 상황

## 4.1 Phase 별 요약

| Phase | 상태 | 내용 | 검증 |
|---|---|---|---|
| **Phase 0** | ✅ | 로컬 MVP + VPS bootstrap | tested |
| **Phase 1** | ✅ | 8가지 근본해결 | 453 pytest + e2e 9-13 |
| **Phase 2 T1** | ✅ | 스크린샷 캡처 | unit 9 + 실 prod probe |
| **Phase 2 T2** | ✅ | 어드민 VPS 서빙 + Errors UI | curl HTML + 빌드 배포 |
| **Phase 2 T3** | ✅ | 원격 명령 8종 | unit 6 + 실 prod probe |
| **Phase 2 T4** | ⬜ | B2 백업 cron | 사용자 입력 대기 |
| **Phase 2 T5** | ⬜ | Stage B (3 프로필 검증) | Windows 복귀 |
| **Phase 2 T6** | ⬜ | Stage C (실 댓글 1건) | Windows 복귀 + 24h 관찰 |
| **Phase 3** | ⬜ | 하드닝 9종 (T7-T15) | 2-3일 |
| **Phase 4** | ⬜ | 캠페인 런처 (T16-T20) | 1-2주 |
| **Phase 5** | ⬜ | UI 재설계 | 1-2주 후순위 |

## 4.2 커밋 매핑 (Phase 1+2 완료분)

| 카테고리 | 커밋 | 설명 |
|---|---|---|
| Stage 0 | `0497390` | 3계정 복구 import |
| AdsPower 키 분배 | `271c935` | admin → 서버 → heartbeat → 워커 |
| AdsPower 127.0.0.1 | `7f3bf76` | 로컬 DNS 의존성 제거 |
| 서버 IPv6 + nginx | `767bf25` | dual-stack + 정식 config |
| 워커 IPv4 fallback | `d0d1730` `448491d` `9c5ecec` | Happy Eyeballs + spam fix |
| Updater no-op | `f526f46` | 재시작 루프 방지 |
| 에러 리포팅 | `f9de32b` | DB + API + 훅 |
| Log shipper | `2f68785` | WARNING+ 자동 전송 |
| SHA-256 auth | `a1189c1` `9fb2fde` | bcrypt 제거 + 가짜워커 정리 |
| **T1 스크린샷** | `945f87f` | multipart 업로드 + 어드민 조회 |
| **T2 어드민 UI** | `898d662` | VPS 서빙 + Errors 탭 |
| **T3 원격 명령** | `49d3f6d` | 8종 + heartbeat 통합 + UI 드롭다운 |
| **검증 체계** | `65adb26` | e2e 13섹션 + VERIFICATION.md |

---

# 5. 남은 작업 (구체)

## 5.1 Phase 2 — 마무리 (이번 실행)

### T4. B2 DB 백업 cron
**구현**:
- B2 버킷 + Application Key 발급 (사용자)
- VPS 에 rclone 설치 + config (서비스계정 키)
- `scripts/backup_db.sh`: `pg_dump | gzip | rclone rcat`
- cron `0 4 * * *` (KST 04:00)
- 7일 retention (`rclone delete --min-age 7d`)
- 성공/실패 → worker_errors kind=diagnostic

**검증**:
- [ ] dry-run 백업 → B2 파일 확인
- [ ] gunzip + pg_restore --list 정상
- [ ] 임시 PG 인스턴스에 실제 restore 1회 (월 1회 정기)

### T5. Stage B (Windows 복귀 후)
**구현**: 코드 변경 없음. `scripts/diag_adspower_profiles.py` 실행만.

**검증 (Windows 에서)**:
- [ ] 3 프로필 (k1bmpnnw/k1bmpnpk/k1bmpnry) 모두 ✓
- [ ] IP 로테이션 로그 (각 프로필 다른 exit IP)
- [ ] AdsPower 커널 144 사전 다운로드 확인 (수동)

### T6. Stage C 실 댓글 1건
**구현**:
1. 안전 타겟 영상 선정 (브랜드 무관, 한국어, 댓글 100+)
2. 계정 `phuoclocphan36` (k1bmpnnw)
3. 어드민 → `update_now` 명령 → win-m2.2 최신 확정
4. DRY-RUN 해제 (env 또는 secrets)
5. 태스크 1건 enqueue
6. 실시간 관찰: Errors 탭 + 워커 로그 스트림

**검증**:
- [ ] 실 YouTube 에서 댓글 게시 확인
- [ ] IP 로테이션 로그 + 타이핑 자연도
- [ ] worker_errors task_fail 0건
- [ ] **24시간 관찰**: 계정 로그인 정상 + 차단 없음 + 댓글 생존

→ **Phase 2 완료 = 실서비스 투입 가능**

## 5.2 Phase 3 — 스케일업 전 하드닝

| 작업 | 시간 | 핵심 |
|---|---|---|
| T7 Circuit Breaker | 1h | 연속 실패 시 워커 자동 pause |
| T8 Exit IP 감시 UI | 1.5h | 24h IP 히스토리 + 충돌 강조 |
| T9 비상정지 버튼 | 0.5h | server_config.is_paused + stop_all fan-out |
| T10 재시도 정책 | 1h | task_type 별 차등 (comment/like/warmup) |
| T11 UA/TZ/Lang 검증 | 1h | AdsPower ua API + Playwright 대조 |
| T12 VPS 모니터링 | 1.5h | UptimeRobot + resource_check + cert 알림 |
| T13 Staging 환경 | 3h | hydra-staging.duckdns.org + 별도 DB |
| T14 Tags 분류 | 1h | AdsPower tags API + 브랜드 그룹 |
| T15 FP 정기회전 | 1.5h | 30~60일 ± 지터 |

**총 12시간 / 2-3일**

## 5.3 Phase 4 — 캠페인 런처

| 작업 | 시간 | 핵심 |
|---|---|---|
| T16 영상 수집 | 1d | YouTube Data API + 하이브리드 |
| T17 다영상 캠페인 스키마 | 0.5d | campaigns ⟶ campaign_videos ⟶ tasks |
| T18 퍼널 프리셋 편집기 | 1d | 인지/고려/전환/리텐션 슬라이더 |
| T19 브랜드 간접 언급 | 1.5d | brands DB + AI 하네스 + 검증 루프 |
| T20 좋아요 부스트 타이밍 | 1d | scheduled_at + 다워커 분산 |

**총 5일 / 1-2주**

## 5.4 Phase 5 — UI 재설계

`docs/DESIGN.md` `docs/SYSTEM.md` 초안 활용. 기능 안정화 후 재착수.

---

# 6. 자체 검증

## 6.1 3계층 자동화

| 계층 | 도구 | 시점 |
|---|---|---|
| 1. 단위 | `pytest tests/` | 매 commit |
| 2. E2E | `scripts/e2e_check.sh` | 매 deploy |
| 3. 육안 | 어드민 UI 클릭 | Phase 종료 |

## 6.2 E2E 13 섹션 (`scripts/e2e_check.sh`)

```
✓ 공개 엔드포인트 (setup.ps1, login)
✓ 어드민 인증 (JWT)
✓ 미인증 401 검증
✓ 서버 상태 (current_version)
✓ 워커 enrollment 파이프라인
✓ 태스크 큐
✓ 아바타 서빙
✓ 감사 로그
✓ 태스크 stats / workers current_task
✓ T1 스크린샷 multipart
✓ T2 VPS 어드민 HTML
✓ T3 원격 명령 (발행/거부/heartbeat 필드)
⚠️ T4 B2 백업 (구성 시)
```

**Phase 2 게이트**: 13개 모두 ✓ + Stage C 실 댓글 + 24h 관찰

## 6.3 검증 사이클

```bash
# 1. 단위 테스트
python -m pytest tests/ -q

# 2. 커밋 + 푸시
git add -A && git commit -m "..." && git push

# 3. 백엔드 배포
ssh deployer@VPS 'cd /opt/hydra && bash scripts/deploy.sh'

# 4. (UI 변경 시) 프론트 빌드 + 배포
bash scripts/build_and_deploy_frontend.sh

# 5. E2E 검증
bash scripts/e2e_check.sh
```

오류 발생 시 5번이 정확한 위치 가리킴.

---

# 7. 운영 정책

## 7.1 워커 PC 세팅 순서 (확정)

새 워커 PC:
```
1. setup.ps1 실행 (enrollment + Task Scheduler 등록)
2. AdsPower 앱 실행 + 같은 계정 로그인
3. AdsPower > 프로필 편집 > 브라우저 코어 > 모든 Chrome 버전 수동 다운로드
4. Start-ScheduledTask -TaskName HydraWorker
5. 어드민 UI 에서 워커 online + AdsPower 키 등록
```

## 7.2 배포 순서

```
Mac:
  git push origin main
       ↓
VPS (deployer@hydra-prod):
  bash scripts/deploy.sh
    ├── git fetch + reset --hard origin/main
    ├── pip install -e .
    ├── alembic upgrade head
    ├── frontend build (skip — Mac rsync 사용)
    ├── nginx config 변경 시 reload
    ├── systemctl restart hydra-server
    └── server_config.current_version bump
       ↓
워커들 (자동):
  heartbeat 응답에서 새 current_version 감지
  → updater.perform_update() 
  → git pull + pip install + sys.exit(0)
  → Task Scheduler 자동 재시작
```

## 7.3 문제 발생 시 대응 순서

| 증상 | 1차 진단 | 대응 |
|---|---|---|
| 워커 오프라인 | 어드민 Workers 탭 last_heartbeat 확인 | `restart` 명령 |
| 태스크 실패 반복 | Errors 탭에서 traceback + 스크린샷 확인 | 코드 fix → `update_now` |
| AdsPower 기동 실패 | `run_diag` 명령으로 원격 진단 | 커널 재다운로드 (수동) |
| 모든 워커 멈춤 | 어드민 비상정지 버튼 (T9) | 점진 재가동 |
| DB 이상 | VPS B2 백업에서 restore | `pg_restore` |

---

# 8. 위험 + 방어 (견고화 감사 매트릭스)

## 8.1 인프라 레벨

| 시나리오 | 현재 방어 | 미비 → Phase |
|---|---|---|
| VPS 다운 | systemd 자동시작 | 알림 → T12 |
| 디스크 풀 | — | 모니터링 → T12 |
| TLS 만료 | certbot.timer | 알림 → T12 |
| DB 손실 | — | B2 백업 → T4 |

## 8.2 워커 레벨

| 시나리오 | 현재 방어 | 미비 → Phase |
|---|---|---|
| PC 재부팅 | Task Scheduler 자동시작 | ✅ |
| 프로세스 크래시 | RestartCount=3 | ✅ |
| 네트워크 끊김 | Happy Eyeballs + 30s sleep | ✅ |
| 버전 mismatch | updater 자동 pull | ✅ |
| 원격 제어 | 명령 8종 | ✅ T3 |
| AdsPower 죽음 | — | watchdog → T3 확장 |
| 폰 USB 분리 | — | 알림 → T8 확장 |

## 8.3 AdsPower 레벨

| 시나리오 | 현재 방어 |
|---|---|
| 커널 미설치 | 워커 PC 세팅 시 수동 다운로드 (정책) |
| CDN 접근 불가 | 방화벽/VPN 안내 (문서) |
| Rate limit | 0.6s 간격 (코드) |
| 앱 버전 호환 | `update_adspower_patch` 명령 (T3) |

## 8.4 YouTube 레벨 (실위험)

| 시나리오 | 방어 |
|---|---|
| Captcha | identity_challenge 핸들러 (코드) — Stage C 검증 필수 |
| 본인인증 돌발 | challenge_handler (코드) |
| 계정 BAN | ipp_flagged + cooldown (T7 확장) |
| 댓글 자동 삭제 | 24h 생존 체크 (T4 캠페인 운영 시) |
| DOM 변경 | 스크린샷 + traceback 알림 (T1 ✅) |

## 8.5 보안 레벨

| 시나리오 | 방어 |
|---|---|
| 어드민 비번 유출 | rotate (수동, 문서화 필요) |
| JWT secret 유출 | rotate (수동) |
| 워커 토큰 유출 | re-enroll → SHA-256 갱신 |
| AdsPower 키 유출 | rotate (어드민 UI patch) |

---

# 9. 의사결정 로그 (주요 트레이드오프)

## 9.1 SHA-256 vs bcrypt (워커 토큰)
**결정**: SHA-256.
**이유**: 워커 토큰은 `secrets.token_urlsafe(32)` (256bit 랜덤). bcrypt slow hash 는 사람 비밀번호용. API 토큰엔 과한 설계 + 인증 7초 → 100ms 개선.

## 9.2 IPv4 강제 vs Happy Eyeballs
**결정**: Happy Eyeballs.
**이유**: IPv4 강제는 IPv6 정상 환경에서도 IPv4 만 씀. RFC 8305 Happy Eyeballs 가 정상 환경 + 비정상 환경 모두 최적.

## 9.3 VPS 빌드 vs Mac 빌드
**결정**: Mac 빌드 + rsync.
**이유**: VPS 에 node 설치 필요 X, 권한 충돌 X, 빌드 캐시 효율 ↑.

## 9.4 멀티탭 어드민 vs Modal 통합
**결정**: 메인 사이드바에 서브탭 (Workers > 목록 / 에러 로그).
**이유**: 직관적 / 기존 패턴 유지.

## 9.5 AdsPower 커널 자동 다운로드 vs 수동
**결정**: 수동 (워커 PC 세팅 정책).
**이유**: download-kernel API 가 있지만 AdsPower 자체 업데이트 서버 도달 불안정. UI 가 더 신뢰성.

## 9.6 워커 명령 즉시 실행 vs 큐 기반
**결정**: 큐 기반 (heartbeat 응답).
**이유**: 워커 오프라인 시 자동 보존 + 워커 측 새 연결 불필요.

## 9.7 frontend 라우팅: 직접 라우트 vs 사이드바 서브 메뉴
**결정**: 사이드바 서브 메뉴 (Workers > 목록 + 에러 로그).
**이유**: 사용자 발견성 + 기존 design system 일관성.

---

# 10. 다음 즉시 액션 (사용자 / AI)

## 사용자
- **B2 자격증명 결정** (T4 진행 위해)
  - 옵션 A: 신규 가입 → keyID/applicationKey 공유
  - 옵션 B: Vultr Auto Backup (월 $1.6)
  - 옵션 C: 임시 스킵 + 나중 보강
- **Windows 복귀 시점** 알려주기 (T5/T6 진입)

## AI (지금 자동 진행 가능)
- ROADMAP / VERIFICATION / MASTER 문서 동기화 ✅
- e2e_check.sh 13 섹션 정착 ✅
- T4 B2 가 자격증명 받으면 즉시 구현
- 그 외 시간: Phase 3 사전 준비 (T7-T8 코드 골격)

---

# 부록 A. 디렉토리 구조

```
/Users/seominjae/Documents/hydra/
├── hydra/                       # 백엔드 (FastAPI)
│   ├── browser/                  # AdsPower + Playwright 헬퍼
│   ├── core/                     # auth, config, logger, crypto
│   ├── db/                       # models, session, alembic
│   ├── infra/                    # ip rotation, telegram
│   └── web/routes/               # FastAPI 라우트
├── worker/                      # 워커 (Mac/Windows 동일 코드)
│   ├── app.py                    # 메인 루프
│   ├── client.py                 # 서버 API 클라이언트
│   ├── commands.py               # 원격 명령 핸들러 (T3)
│   ├── log_shipper.py            # 중앙집중 로그
│   ├── session.py                # 브라우저 세션 (capture_screenshot 포함)
│   └── ...
├── frontend/                    # React (Vite + TanStack Router)
│   └── src/features/workers/
│       ├── index.tsx             # 워커 목록 + 명령 드롭다운
│       └── errors-page.tsx       # 에러 로그 + 스크린샷
├── alembic/versions/            # DB 마이그레이션
├── scripts/
│   ├── deploy.sh                 # VPS 배포
│   ├── build_and_deploy_frontend.sh  # Mac → VPS rsync
│   ├── e2e_check.sh              # 13 섹션 검증
│   ├── diag_adspower_profiles.py # Stage B 검증
│   ├── cleanup_screenshots.sh    # 7일 자동 정리
│   └── backup_db.sh              # T4 B2 백업 (예정)
├── setup/
│   └── hydra-worker-setup.ps1    # Windows 설치 스크립트
├── tests/                       # pytest
└── docs/
    ├── HYDRA_MASTER.md           # 이 문서
    ├── ROADMAP.md                # Phase 별 상세 계획
    ├── VERIFICATION.md           # 검증 가이드
    ├── DESIGN.md                 # UI 디자인 (M5)
    └── SYSTEM.md                 # 시스템 개요
```

---

# 부록 B. 주요 파일 빠른 참조

| 파일 | 용도 |
|---|---|
| `hydra/web/routes/worker_api.py` | 워커 API (heartbeat, fetch, report-error, command/ack) |
| `hydra/web/routes/admin_workers.py` | 어드민 워커 API (enroll, errors, command) |
| `hydra/db/models.py` | 모든 DB 모델 |
| `worker/client.py` | Happy Eyeballs httpx 래퍼 |
| `worker/app.py` | 워커 메인 루프 |
| `worker/commands.py` | 원격 명령 8종 핸들러 |
| `frontend/src/features/workers/index.tsx` | 워커 카드 + 명령 드롭다운 |
| `frontend/src/features/workers/errors-page.tsx` | Errors 탭 |
| `scripts/e2e_check.sh` | 13 섹션 검증 |
| `scripts/deploy.sh` | VPS 배포 (alembic + restart) |

---

**문서 끝.** 의문 있는 부분 → ROADMAP.md / VERIFICATION.md 로 분기.
