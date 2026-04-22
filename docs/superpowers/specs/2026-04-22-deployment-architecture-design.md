# HYDRA 배포 아키텍처 설계

> **작성일:** 2026-04-22
> **목적:** 10~20대 Windows 워커 fleet + VPS 서버 운영 체계. Mac 개발 → git push → VPS/워커 즉각 반영되는 파이프라인 설계. 초반 고빈도 수정에 견딜 수 있는 구조.

---

## 1. 배경과 목표

### 1.1 현재 상태
- **완성**: 온보딩 파이프라인 (45/50 계정 warmup 편입). Mac 로컬에서 실행되는 코드. 기본 워커 HTTP API (`heartbeat`, `fetch_tasks`).
- **미완성**: VPS 상용 서버, Windows 워커 상시 배치, 자동 배포, 원격 디버깅 도구, 로그/스크린샷 중앙 수집.

### 1.2 목표
HYDRA 프로젝트 C 단계 (내부 상용 시스템) 진입을 위한 인프라 기반을 잡는다:
1. **빠른 반복**: Mac 에서 수정 → 1~2분 내 전 워커 반영 (재설치/USB 접근 불필요).
2. **안전한 배포**: 중간 태스크 끊기지 않게 graceful drain + 긴급정지 버튼.
3. **원격 디버깅**: 워커에서 발생한 문제를 Mac 에서 "앞에 앉은 것처럼" 파악.
4. **미래 확장**: D 단계 (외부 고객 SMM 상품화) 시 redesign 없이 extend 만 가능한 구조.

### 1.3 비목표
- 멀티 리전/고가용성 (10대 넘어가면 고려)
- 결제/고객 포털 (D 단계에서)
- 100대 이상 스케일 최적화

---

## 2. 물리 아키텍처

### 2.1 노드 구성

```
┌─────────────────────────────────────────────────────────────┐
│  [개발 Mac]                                                  │
│   • 코드 작성, 디버깅, git push                               │
│   • VPS 어드민 UI 접속                                        │
│   • Tailscale 로 워커 PC 직접 접근 (비상시)                   │
└──────────────────┬──────────────────────────────────────────┘
                   │ git push
                   ↓
┌─────────────────────────────────────────────────────────────┐
│  [GitHub - main 브랜치]                                       │
└──────────────────┬──────────────────────────────────────────┘
                   │ git pull (server deploy 시 + worker heartbeat 시)
          ┌────────┴────────┐
          ↓                 ↓
┌──────────────────┐   ┌──────────────────────────────┐
│   [VPS - Vultr]   │   │  [워커 PC × 10~20]            │
│    Seoul 리전     │←──│   Windows 10/11              │
│                   │   │   + USB 휴대폰 (테더링)        │
│  • FastAPI       │   │   + AdsPower 앱              │
│  • PostgreSQL    │   │   + Playwright               │
│  • nginx + TLS   │   │   + hydra-worker.exe         │
│  • 어드민 UI      │   │   + Tailscale 클라이언트      │
│  • 로그/이미지     │   └──────────────────────────────┘
└──────────────────┘
```

### 2.2 각 노드의 역할

### 2.2.1 어드민 UI 핵심 요구사항 (중요)

**완전한 반응형 설계 — 모바일에서 PC 와 동등한 모든 기능 제공 가능해야 함.**

- **Feature parity:** 휴대폰에서 PC 의 모든 기능 접근 가능 (간단 명령 + 구체적 설정 편집 + 상세 조회 전부)
- **대상 화면 크기:** Mobile (360~480px) / Tablet (768~1024px) / Desktop (1280px+) 모두 일급 지원
- **터치 친화:** 모바일에서 버튼/링크 최소 44pt, 스와이프 제스처 활용
- **복잡한 폼:** 모바일에선 다단계 위저드 형태로 분할 가능하되 **모든 필드 편집 가능**
- **비상 기능:** kill switch, 태스크 재시도, 스크린샷 뷰어는 모바일 최적화 우선순위
- **PWA (Progressive Web App) 권장:** 설치 가능한 웹앱으로 패키징 → 홈 화면에서 바로 실행 + 푸시 알림 (Discord 대체 가능)

### 2.2.2 인프라 노드

**VPS (Vultr Seoul, 2vCPU/4GB RAM/80GB SSD, $24/월)**
- FastAPI: 워커 HTTP API + 어드민 UI API + 로그 수집 API
- PostgreSQL: 계정/태스크/로그/캠페인 DB
- nginx: TLS 종단, 정적 프론트 서빙, rate limit
- Systemd: `hydra-server` 서비스 상시 실행
- 일 1회 자동 스냅샷 (Vultr), 일 1회 DB 덤프 → S3/Backblaze 업로드
- 한국 리전 선택 이유: 한국 워커와 지연 5~15ms (ISP 수준), 타 리전 대비 저지연

**워커 PC (Windows 10/11)**

**설치 방식:** 하이브리드 — **초기 1회만 PowerShell 설치 스크립트 (`.exe` wrap)**, **이후 업데이트는 git pull**.

- 초기 배포: `hydra-worker-setup.exe` (Inno Setup 으로 wrap 된 PowerShell 스크립트, ~50MB)
  - Python 3.11 / Git / ADB / Tailscale 자동 설치 (Chocolatey 경유)
  - `C:\hydra\` 에 repo clone + venv + pip install
  - Playwright 브라우저 다운로드
  - NTP 시계 동기화 설정 (w32tm)
  - 어드민 UI 에서 발급한 **1회용 enrollment token** 입력 → VPS 에서 per-worker 환경변수 수신
  - Task Scheduler 등록 (부팅 시 자동 실행 + 크래시 재시작)
  - 첫 heartbeat 테스트로 연결 검증
- 이후 모든 업데이트: git pull + pip install + restart (섹션 4 참조)

**PyInstaller 단일 exe 방식을 택하지 않는 이유:**
- 매 배포마다 Windows 에서 재빌드 필요 (Mac 에선 직접 불가 → CI 필요)
- bytecode 화되어 에러 스택 trace 읽기 어려움
- 파일 크기 3배 증가 (100MB → 300MB)
- 긴급 시 Tailscale 로 직접 접속해서 코드 수정/테스트 불가

**워커 상주 컴포넌트:**

- hydra-worker: Python 워커 프로세스 — heartbeat + fetch + execute loop
- AdsPower 앱: 브라우저 프로필 클라우드 싱크 (프로필 데이터는 AdsPower 클라우드 저장 → 어느 워커든 어느 계정이든 접근 가능, 단 동시 실행은 AdsPower 자체 락으로 1대만 허용)
- Playwright: 브라우저 자동화
- ADB: 휴대폰 IP 로테이션 제어
- Windows Task Scheduler: 부팅 시 hydra-worker 자동 실행 + 크래시 시 재시작
- Tailscale: VPN 메시 — Mac 에서 원격 접근용

**개발 Mac**
- 로컬 코드 저장소 + 개발 DB (선택적 로컬 PostgreSQL)
- VPS SSH 접속으로 서버 로그 확인
- Tailscale 로 워커 PC 직접 접근 (RDP/SSH)

---

## 3. 통신 프로토콜

### 3.0 아바타 파일 저장소 (중앙 집중)

**2.1GB / 953 파일 규모의 프로필 이미지를 VPS 에 중앙 저장하고, 워커는 태스크별로 필요한 파일만 다운로드.**

#### 저장 위치
```
VPS: /var/hydra/avatars/
  ├── female/20s/f20_001.png
  ├── female/30s/f30_012.png
  ├── male/20s/m20_005.png
  └── object/flower/flower_003.png
```

#### 접근 제어 (nginx + 인증)
```nginx
location /avatars/ {
    # 워커 토큰 또는 관리자 세션 검증
    auth_request /internal/auth-check;
    alias /var/hydra/avatars/;
    add_header Cache-Control "public, max-age=86400";  # 워커 24h 캐시 허용
}
```

#### 워커 측 다운로드 로직
```python
async def fetch_avatar(relative_path: str) -> Path:
    """VPS 에서 아바타 다운로드 → 로컬 temp 파일 반환."""
    cache_key = hashlib.md5(relative_path.encode()).hexdigest()
    cached = CACHE_DIR / f"{cache_key}.png"
    if cached.exists() and cached.stat().st_mtime > time.time() - 86400:
        return cached   # 24h 캐시 hit
    url = f"{SERVER_URL}/api/avatars/{relative_path}"
    async with httpx.AsyncClient() as c:
        resp = await c.get(url, headers={"X-Worker-Token": TOKEN})
        resp.raise_for_status()
        cached.write_bytes(resp.content)
    return cached
```

#### 초기 Mac → VPS 마이그레이션
```bash
# 개발자 Mac 에서 1회 실행 (VPS 세팅 직후)
rsync -avz --progress data/avatars/ \
    deployer@vps.hydra.com:/var/hydra/avatars/

# 권한 조정
ssh deployer@vps.hydra.com "chown -R www-data:www-data /var/hydra/avatars/"
```

#### 어드민 UI 업로드 기능 (Phase 1 필수)
- **다중 파일 드래그 앤 드롭** 업로드
- **ZIP 업로드** 시 서버에서 자동 해제 (폴더 구조 보존)
- **카테고리 선택 UI** — female/male/object + 세부 (20s/30s/flower/cat 등 동적)
- **미리보기 + 개별 삭제**
- **모바일 대응** — 카메라 앨범 직접 선택, 터치 업로드
- **용량 제한** — 파일당 5MB, 전체 업로드 200MB
- **저장 전 자동 리사이즈** — 800×800px 초과 시 축소 (원본도 별도 백업)

#### API 엔드포인트
| 메서드 | 경로 | 용도 | 인증 |
|---|---|---|---|
| GET | `/api/avatars/{path}` | 워커가 파일 다운로드 | 워커 토큰 |
| GET | `/api/admin/avatars/list` | 어드민 UI 가 목록 조회 (트리 구조) | 관리자 세션 |
| POST | `/api/admin/avatars/upload` | 파일 업로드 (multipart) | 관리자 세션 |
| POST | `/api/admin/avatars/upload-zip` | ZIP 업로드 후 서버에서 해제 | 관리자 세션 |
| DELETE | `/api/admin/avatars/{path}` | 개별 삭제 | 관리자 세션 |

#### 백업
- `/var/hydra/avatars/` 를 일 1회 Backblaze B2 로 rsync 백업
- DB 백업과 별도 (바이너리 대용량)
- 30일 주기로 삭제 파일 정리

#### 미래 확장 (필요 시 B2 이관)
현재는 VPS 로컬 저장, 10~50GB 넘어가면 B2 object storage 로 이관 고려.
API 레이어만 유지하면 저장 위치 변경이 투명함 (`/api/avatars/{path}` 엔드포인트 구현만 교체).

---

### 3.0.5 시크릿 관리 (민감 정보 배포)

**문제:** DB 암호화 키, worker token, 외부 API 키 등 민감 정보를 워커 PC 에 어떻게 안전하게 배포할까.

**원칙:**
- git 저장소에 **평문 .env 절대 금지**
- 워커 PC 의 .env 파일은 **VPS 에서 pull 받아 생성** (수작업 복붙 금지)
- 어드민 UI 에서 **per-worker 토큰 발급** (각 워커 고유)

**흐름:**
```
[어드민 UI] "새 워커 추가" 버튼
  → 서버가 워커 레코드 생성 + 1회용 enrollment_token 발급 (24시간 유효)
  → 화면에 PowerShell 명령 1줄 표시:
    iwr -Uri https://api.hydra.com/api/workers/setup.ps1 `
        -OutFile setup.ps1 && .\setup.ps1 -Token ABC123...

[워커 PC] 관리자가 그 명령 실행
  → setup.ps1 이 VPS 에 enrollment_token 제출
  → 서버가 토큰 검증 + worker_token (영구) 발급
  → 필요한 환경변수 묶음 반환 (DB_CRYPTO_KEY, SERVER_URL 등)
  → 워커 PC 로컬에 암호화된 secrets.enc 파일로 저장
    (Windows DPAPI 로 해당 PC 에서만 복호화 가능)
  → enrollment_token 서버에서 삭제 (1회용)
```

**장점:**
- 개발자가 직접 .env 전달 불필요
- 1회용 토큰이라 탈취 리스크 제한적
- Windows DPAPI = PC 하드웨어 / 사용자 계정 바인딩 → 파일만 훔쳐도 복호화 불가

### 3.0.6 DB 마이그레이션 도구 (Alembic)

**현재:** SQLite + 수동 ALTER TABLE (예: `ipp_flagged` 컬럼 추가를 직접 sqlite3 로).
**Phase 1 에서 전환:** SQLAlchemy + **Alembic** 마이그레이션 프레임워크.

**구조:**
```
alembic/
  versions/
    001_initial_schema.py
    002_add_ipp_flagged.py
    003_add_customer_id.py
    004_add_server_config.py
    005_add_execution_logs.py
    ...
  env.py
  alembic.ini
```

**배포 시 자동 마이그레이션:**
```bash
# deploy.sh 에 포함
alembic upgrade head   # 최신 버전으로 업그레이드
```

**롤백 가능:**
```bash
alembic downgrade -1   # 이전 버전으로
```

모든 스키마 변경이 **git 커밋 히스토리에 기록** + **순서대로 실행** + **실패 시 롤백 가능**.

### 3.0.7 감사 로그 (Audit Log)

**테이블:**
```sql
CREATE TABLE audit_logs (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  action VARCHAR(64) NOT NULL,        -- deploy / pause / unpause / create_campaign / upload_avatar 등
  target_type VARCHAR(32),            -- campaign / worker / account
  target_id INTEGER,
  metadata TEXT,                       -- JSON (before/after 상태, 입력 데이터)
  ip_address VARCHAR(45),
  user_agent TEXT,
  timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
  INDEX idx_user_time (user_id, timestamp DESC),
  INDEX idx_action (action, timestamp DESC)
);
```

**자동 기록 대상 (미들웨어):**
- 배포 버튼 클릭 (`action='deploy'`, metadata=version)
- 긴급정지/재개
- 캠페인 생성/수정/삭제
- 계정 수동 변경 (status, ipp_flagged 등)
- 아바타 업로드/삭제
- 워커 등록/제거
- 로그인/로그아웃
- 권한 변경

**UI:** 어드민 UI 에 "활동 로그" 탭 — 필터 (사용자/액션/기간) + CSV 내보내기.

### 3.0.8 워커 시간 동기화 (NTP)

**문제:** Windows 시계 드리프트 → TOTP 6자리 코드 생성 시 30초 윈도우 벗어나면 실패. 태스크 스케줄도 어긋남.

**해결:** 설치 스크립트에서 `w32tm` 설정.
```powershell
# setup.ps1 에 포함
w32tm /config /manualpeerlist:"time.windows.com,time.google.com" /syncfromflags:manual /reliable:yes /update
Restart-Service w32time
w32tm /resync
```

주 1회 자동 동기화. 워커 heartbeat 에 `time_offset_ms` 포함 → VPS 가 허용 범위(5초) 초과 시 알림.

### 3.0.9 재해 복구 절차 (Runbook)

**별도 문서:** `docs/runbook.md` (Phase 4 에서 작성, 구현과 병행).

**포함 내용:**
- VPS 완전 삭제 시 30분 내 복구 절차
  1. Vultr 스냅샷 복원 or 새 서버 프로비저닝
  2. DB 덤프 로드 (Backblaze B2 에서 다운로드)
  3. 아바타 파일 rsync 복원
  4. `.env` 복구 (1Password 저장 백업에서)
  5. 도메인 DNS 재연결 (Cloudflare API)
  6. TLS 재발급 (certbot)
  7. 서비스 기동 + 헬스체크
  8. 워커 재연결 확인 (heartbeat 정상)
- 워커 PC 전면 리셋
- DB 손상 시 복원
- Git 레포 소실 시 (GitHub 가 있으니 희귀)
- 장애 대응 연락망 / 권한자 매트릭스

**월 1회 복구 연습 (drill)** 정기화.

---

### 3.1 서버 ↔ 워커 (Poll 기반 HTTP)

워커가 아웃바운드 HTTPS 로만 서버와 통신. 인바운드 포트 열 필요 없음 → NAT/방화벽 무관.

**핵심 엔드포인트:**

| 메서드 | 경로 | 용도 |
|---|---|---|
| POST | `/api/workers/heartbeat` | 15초 주기. 워커 상태 보고 + 서버 제어 플래그 수신 |
| POST | `/api/tasks/fetch` | 다음 실행할 태스크 1~N개 수신 |
| POST | `/api/tasks/complete` | 완료 보고 |
| POST | `/api/tasks/fail` | 실패 보고 (사유 + 스크린샷 URL) |
| POST | `/api/logs/batch` | 실행 로그 묶음 업로드 (10초 주기 or 100개 버퍼) |
| POST | `/api/screenshots` | 스크린샷 파일 업로드 |

**인증:** `X-Worker-Token` 헤더. 워커마다 개별 토큰. 서버 DB 에 salt+bcrypt 해시 저장.

### 3.2 heartbeat 응답 구조

```json
{
  "current_version": "v1.2.4",        // 배포된 최신 버전 해시
  "paused": false,                     // 전역 일시정지 플래그
  "canary_worker_ids": [2],            // 카나리 배포 대상 워커 id 리스트
  "restart_requested": false,          // 특정 워커 강제 재시작 요청
  "worker_config": {                   // 런타임에 전달되는 워커 개별 설정
    "poll_interval_sec": 15,
    "max_concurrent_tasks": 1,
    "drain_timeout_minutes": 15
  }
}
```

### 3.3 heartbeat 요청 구조

```json
{
  "version": "v1.2.3",
  "hostname": "worker-02",
  "os_type": "windows",
  "cpu_percent": 23.5,
  "mem_used_mb": 4123,
  "disk_free_gb": 45,
  "adb_devices": ["RZ8N1234"],
  "adspower_version": "6.0.8",
  "playwright_browsers_ok": true,
  "current_task_id": 42               // null 이면 idle
}
```

---

## 4. 업데이트 배포 구조 (Pull-based + Drain)

### 4.1 전체 플로우

```
[Mac]  git commit → git push origin main
          ↓
[GitHub]  main 브랜치 업데이트됨
          ↓
[개발자]  어드민 UI 에서 "배포 v1.2.4" 버튼 클릭
          ↓
[VPS]  POST /api/deploy
        → deploy.sh 실행:
          1. git pull
          2. cd frontend && npm ci && npm run build (원자적)
          3. pip install -r requirements.txt
          4. systemctl restart hydra-server
          5. UPDATE server_config SET current_version = 'v1.2.4'
          ↓
[워커 fleet]  15초 내 heartbeat 시 current_version 확인
              자기 버전과 다름 → drain mode 진입
              현재 태스크 완료 후 → git pull + pip install + 자기 자신 재시작
```

### 4.2 프론트엔드 원자적 배포

중간 상태 (새 index.html + 이전 assets 404) 방지:

```bash
cd frontend
npm ci
npm run build -- --outDir dist-new   # 별도 디렉토리로 빌드
mv dist dist-old 2>/dev/null || true
mv dist-new dist                     # 원자 rename (POSIX)
rm -rf dist-old
```

nginx 는 파일 내용을 메모리 캐싱하지 않음 → 재시작 불필요. 단 `nginx.conf` 가 변경되는 경우는 예외.

**브라우저 캐시 대비:**
- Vite/React 기본 해시 파일명 (`main-abc123.js`)
- `index.html` 만 no-cache, assets 는 1년 캐시 (immutable 해시라 안전)

```nginx
location = /index.html {
    add_header Cache-Control "no-store, no-cache, must-revalidate";
}
location /assets/ {
    add_header Cache-Control "public, max-age=31536000, immutable";
}
```

### 4.3 워커 Drain Mode

워커가 `current_version != 자기 버전` 감지하면:
1. 새 태스크 fetch 중단 (drain 상태 플래그)
2. 현재 실행 중 태스크만 끝내기 위해 최대 `drain_timeout_minutes` (기본 15분) 대기
3. 타임아웃 도달 시 태스크 강제 fail 처리 + DB lock 해제
4. `git pull` + `pip install --quiet` 실행
5. 실패 시 이전 버전 태그로 `git reset --hard` 롤백
6. 자기 프로세스 exit (Task Scheduler 가 자동 재시작)

**주의:** 로그인 FSM 중간 강제 종료 시 계정 상태 일관성 깨질 수 있으므로 drain 우선, 타임아웃은 최후 수단.

### 4.4 카나리 배포

```
1. VPS: canary_worker_ids = [2] 설정 → 워커2 만 current_version 인식
2. 워커2 만 drain → 업데이트 → 재시작
3. 5~10분 로그/실패율 관찰
4. 이상 없음 → canary_worker_ids = [] 해제 → 나머지 전 워커 자동 업데이트
5. 이상 있음 → server_config SET paused=true + rollback
```

### 4.5 긴급 정지 (Kill Switch)

어드민 UI 의 "전체 일시정지" 버튼 → `server_config.paused = True`.
워커들 다음 heartbeat 시 감지 → 새 태스크 fetch 중단 → running 태스크만 완료 후 idle 대기.
문제 해결 후 "해제" → 자동 재개.

---

## 5. 태스크 배분 (Dynamic Dispatch)

### 5.1 전제 변경 사항

**이전에 가정했던 잘못된 제약**: ~~"AdsPower 프로필이 로컬 PC 에 저장되므로 계정-워커 고정 필요"~~

**실제 구조**: AdsPower 프로필은 **클라우드 저장**. 어느 워커 PC 든 어느 계정이든 접근 가능. AdsPower 자체 락으로 동시 실행은 1대만 허용됨.

또한 **IP 는 매 태스크마다 ADB 로 새로 로테이션**되므로 워커별 IP 일관성 개념 무의미. → 계정-워커 어파니티 **불필요**.

### 5.2 분배 알고리즘

**Dynamic load-balanced dispatch**: 모든 태스크는 공용 풀. 먼저 fetch 요청한 워커가 가져감.

```sql
-- 서버 측 fetch_tasks 핵심 쿼리 (PostgreSQL)
SELECT t.*
  FROM tasks t
 WHERE t.status = 'pending'
   AND t.scheduled_at <= NOW()
   AND t.account_id NOT IN (
     SELECT account_id FROM account_locks WHERE released_at IS NULL
   )
 ORDER BY t.priority DESC, t.scheduled_at ASC
 LIMIT 1
 FOR UPDATE SKIP LOCKED;   -- 동시성 안전 (두 워커 경합 방지)
```

이후 같은 트랜잭션에서:
1. `UPDATE tasks SET status='running', worker_id=<요청워커>, started_at=NOW() WHERE id=<picked>`
2. `INSERT INTO account_locks(account_id, worker_id, task_id, locked_at) VALUES (...)`
3. 커밋
4. 태스크 JSON 워커에 반환

### 5.3 좀비 태스크 복구

```
VPS 5분마다 실행되는 크론:
  SELECT * FROM tasks
   WHERE status='running'
     AND started_at < NOW() - INTERVAL '30 minutes';
  → 각 좀비 태스크:
     - status = 'pending'
     - worker_id = NULL
     - account_locks 해제
     - 경고 알림 Discord 로 전송
```

`30 minutes` 는 기본값. 태스크 타입별로 다르게 설정 가능 (natural_browsing 은 15분, login 은 10분 등).

### 5.4 계정 락

```sql
CREATE TABLE account_locks (
  id SERIAL PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  worker_id INTEGER NOT NULL REFERENCES workers(id),
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  locked_at TIMESTAMP NOT NULL DEFAULT NOW(),
  released_at TIMESTAMP,
  INDEX idx_active (account_id) WHERE released_at IS NULL
);
```

**불변식**: 동일 account_id 에 대해 released_at IS NULL 인 row 는 최대 1개. UNIQUE partial index 로 DB 차원에서 강제.

---

## 6. DB 스키마 변경 사항

### 6.1 기존 테이블에 추가

```sql
-- accounts: 이미 있는 ipp_flagged, retired_reason 유지
ALTER TABLE accounts ADD COLUMN customer_id INTEGER NULL;  -- D 단계 대비

-- tasks: customer_id 미리 추가 (D 단계 대비)
ALTER TABLE tasks ADD COLUMN customer_id INTEGER NULL;
ALTER TABLE tasks ADD COLUMN screenshot_urls TEXT;  -- JSON 배열 (실패 시 여러 장)

-- campaigns: customer_id 미리 추가 (D 단계 대비)
ALTER TABLE campaigns ADD COLUMN customer_id INTEGER NULL;

-- workers: 확장 정보
ALTER TABLE workers ADD COLUMN tailscale_ip VARCHAR(45);
ALTER TABLE workers ADD COLUMN health_snapshot TEXT;  -- JSON, 마지막 heartbeat 의 sys info
```

### 6.2 신규 테이블

```sql
CREATE TABLE server_config (
  id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- 싱글톤 row
  current_version VARCHAR(64) NOT NULL,
  paused BOOLEAN NOT NULL DEFAULT FALSE,
  canary_worker_ids TEXT DEFAULT '[]',  -- JSON array
  last_deploy_at TIMESTAMP,
  last_deploy_by VARCHAR(64)
);

CREATE TABLE execution_logs (
  id BIGSERIAL PRIMARY KEY,
  task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
  worker_id INTEGER REFERENCES workers(id),
  account_id INTEGER REFERENCES accounts(id),
  timestamp TIMESTAMP NOT NULL,
  level VARCHAR(16) NOT NULL,  -- DEBUG/INFO/WARN/ERROR
  message TEXT NOT NULL,
  context TEXT,  -- JSON: {url, selector, step, ...}
  screenshot_url VARCHAR(512),
  INDEX idx_task (task_id),
  INDEX idx_worker_time (worker_id, timestamp DESC),
  INDEX idx_account_time (account_id, timestamp DESC)
);

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'operator',  -- admin | operator | customer
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  last_login_at TIMESTAMP
);
```

### 6.3 로그 회전

`execution_logs` 는 고볼륨. 30일 이상 된 로그 자동 삭제 or S3 아카이브:

```sql
-- 매일 03:00 cron
DELETE FROM execution_logs WHERE timestamp < NOW() - INTERVAL '30 days';
-- 또는 아카이브 후 삭제: pg_dump → S3 → DELETE
```

스크린샷 파일도 동일 정책: 30일 지난 건 S3 Glacier 로 이동 또는 삭제.

---

## 7. 크로스 플랫폼 호환성 (Mac 개발 / Windows 워커)

### 7.1 주요 함정과 대응

| 범주 | 함정 | 대응 |
|---|---|---|
| 인코딩 | Windows 기본 CP949, Mac UTF-8 | 모든 `open()` 에 `encoding="utf-8"`. `subprocess` 에 `encoding="utf-8"`. 스크립트 상단 `sys.stdout.reconfigure(encoding='utf-8')` |
| 줄바꿈 | CRLF vs LF | `.gitattributes` 로 강제 (`* text=auto eol=lf`, `*.bat text eol=crlf`) |
| 경로 | `/` vs `\` | `pathlib.Path` 일관 사용. 하드코딩된 `/tmp/` 류 금지 |
| 경로 길이 | Windows 260자 제한 | 설치 경로 짧게 (`C:\hydra\`). Long Path 지원 레지스트리 활성화 |
| venv 활성화 | 명령 다름 | 스크립트에서 `python -m` 으로 실행 (activate 불필요) |
| 외부 명령 | PATH 다름, `.exe` | ADB/Node 등 절대경로. config 에 플랫폼별 경로 |
| subprocess | asyncio 동작 차이 | 1 브라우저/워커 원칙 유지로 영향 최소화. 복잡한 multiprocessing 피함 |
| 파일시스템 대소문자 | Linux VPS 민감 | 소문자 파일명 규칙. import 문 대소문자 정확히 |

### 7.2 예방 인프라

**① "상시 테스트 워커" 1대**
- Windows PC 1대를 상용 투입 안 하고 테스트 전용
- 모든 배포가 **먼저 이 워커에 반영** → 10분 관찰 → 문제 없으면 상용 워커에 배포
- `canary_worker_ids` 메커니즘으로 자동화

**② 크로스플랫폼 CI (GitHub Actions)**
- push 마다 macOS + Windows 두 러너에서 pytest 실행
- 주요 검증: import 성공 여부, 인코딩 에러, 기본 유닛 테스트
- 실패 시 자동으로 배포 차단 (어드민 UI 가 "빌드 통과" 필수)

**③ 코드 리뷰 체크리스트** (`CLAUDE.md` 에 반영)
- [ ] `open()` 전부 `encoding="utf-8"` 명시?
- [ ] 외부 경로를 `pathlib.Path` 사용?
- [ ] `subprocess` 호출 시 `encoding="utf-8"` + 절대경로?
- [ ] 하드코딩된 Unix 경로 (`/tmp/`, `/home/`) 없음?
- [ ] 새 파일명 소문자?

---

## 8. 원격 디버깅 / 관측성

### 8.1 5계층 진단 데이터

**Layer 1 — 로그 스트리밍**
```python
class RemoteLogHandler(logging.Handler):
    def emit(self, record):
        self.buffer.append(record)
        if len(self.buffer) >= 100 or time.time() - self.last_flush > 10:
            server.post("/api/logs/batch", json=self.buffer)
            self.buffer.clear()
```
- 네트워크 실패 시 로컬 파일로 fallback + 나중에 재전송
- 어드민 UI: 워커별 / 태스크별 / 시간별 필터
- 선택적 Grafana Loki 연동 (고급 검색)

**Layer 2 — 스크린샷 자동 캡처**
```python
try:
    await goal.apply(page, acct)
except Exception as e:
    shot = await page.screenshot(type="png")
    url = await server.upload_screenshot(shot, task_id, goal.name)
    raise GoalFailedError(str(e), screenshot_url=url) from e
```
- 어드민 UI: 실패한 goal 클릭 → 해당 순간 스크린샷 인라인 표시
- 성공한 태스크도 주요 단계 마다 스크린샷 (옵션, 기본 OFF — 부하/용량 고려)

**Layer 3 — 브라우저 콘솔 로그**
```python
page.on("console", lambda msg: log_to_buffer({
    "type": msg.type, "text": msg.text, "location": msg.location
}))
page.on("pageerror", lambda err: log_to_buffer({"type": "js_error", "text": str(err)}))
```
- Google 이 뱉는 JS 에러, 우리 셀렉터 실패 단서

**Layer 4 — 구조화된 실행 trace**
태스크마다 타임라인 형태로 저장:
```json
{
  "task_id": 42,
  "events": [
    {"t": "...", "step": "ip_rotate", "result": "ok"},
    {"t": "...", "step": "adspower_start", "port": 53611},
    {"t": "...", "step": "goal_channel_profile", "result": "failed",
     "error": "auth_dialog_blocking", "screenshot": "..."}
  ]
}
```
어드민 UI 의 "타임라인 뷰" — 각 단계 소요 시간과 결과 한눈에.

**Layer 5 — 시스템 상태**
heartbeat 로 CPU/RAM/디스크/ADB/AdsPower 상태 동반 전송 (섹션 3.3 참조). 어드민 UI 대시보드에 실시간 그래프.

### 8.2 Tailscale 원격 접근

**목적:** Mac 에서 워커 PC 로 **NAT/방화벽 무관** 직접 접근 (비상시 RDP/SSH).

- 무료 플랜 20 디바이스까지 (우리 규모 충분)
- 워커 PC 에 Tailscale Windows 클라이언트 설치 → 자동 로그인
- Mac 에서 `ping worker-02.<tailnet>.ts.net` 이나 `mstsc worker-02.<tailnet>.ts.net` RDP 접속
- 보안: MagicDNS + ACL 로 권한자만 접근

### 8.3 Replay 기능

실패한 태스크를 Mac 에서 동일 조건 재현:
```bash
# 어드민 UI 에서 "이 태스크 로컬 재현" 버튼
python scripts/replay_task.py --task-id 42

# 스크립트:
# - 서버 API 로 task payload + account 정보 가져옴
# - Mac 에서 AdsPower 프로필 싱크 (AdsPower 이미 Mac 에 설치)
# - IP 로테이션: Mac 은 ADB 테더링 같은 휴대폰 환경이 없을 수 있으므로
#   로컬 개발 시에는 IP 로테이션 생략하거나, VPN 로테이션 (Mullvad 등) 대체
# - 동일 코드 경로 실행, 브레이크포인트 가능
# (구체 IP 로테이션 대체 방식은 후속 구현 계획에서 결정)
```

### 8.4 Discord 알림

실패 즉시 Discord 웹훅으로 구조화된 알림:
```
🚨 Worker 2 | Task #123 failed
Goal: channel_profile
Error: ytcp-auth-confirmation-dialog blocking inputs
Screenshot: https://hydra.com/screenshots/123.png
[View Admin] [Retry] [7d Cooldown]
```
- 에러 유형별 채널 분리 (login / channel_profile / network)
- 반복 실패 패턴 (같은 에러 5회 이상) 시 별도 긴급 알림

### 8.5 Admin UI "Live Worker" 뷰

각 워커별 실시간 상태 섹션:
- 현재 실행 중 태스크 (진행률, 경과 시간)
- 최근 100개 이벤트 스트림 (tail -f 느낌)
- CPU/RAM/디스크 실시간 그래프
- 연결된 ADB 기기 목록
- 마지막 heartbeat 시각

---

## 9. 미래 대비 (D 단계 상용 상품화)

### 9.1 지금 반영하는 것 (작은 비용, 큰 미래 효과)

| 영역 | 지금 할 것 | 미래 효과 |
|---|---|---|
| DB 스키마 | `customer_id` 컬럼 nullable 로 추가 (campaigns/tasks/accounts) | 멀티테넌시 마이그레이션 불필요 |
| API 경로 | `/api/admin/*` vs `/api/v1/*` 네임스페이스 분리 | 공개 API 따로 버전 관리 |
| 인증 | `users` 테이블 + `role` 필드 (admin/operator/customer) | 역할 추가만으로 고객 권한 대응 |
| 도메인 계획 | `admin.hydra.com` (내부) vs `app.hydra.com` (고객, 나중) | 동일 서버 내 분리 가능 |
| 하드코딩 제거 | 수치/한도 전부 config/DB 로 | 고객별 상이한 한도 설정 가능 |

### 9.2 지금 안 넣는 것 (YAGNI)

- 결제/구독 시스템
- 고객 포털 UI
- 복잡한 RBAC
- 멀티 리전
- 언어 국제화

D 단계 진입 시 위 5가지를 **추가**만 하면 됨 (기존 설계 재작업 없음).

---

## 10. 리스크와 완화책

### 10.1 인프라 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| VPS SPOF (단일 장애점) | 전 워커 정지 | 일 1회 Vultr 스냅샷 + DB 덤프 S3 업로드. 재구축 < 1시간 |
| GitHub 장애 | 배포 불가 | 일시적 — 긴급 시 SSH 로 VPS 에서 로컬 수정 후 수동 배포 |
| AdsPower 서비스 다운 | 워커 작업 불가 | 외부 의존. AdsPower 상태 모니터링 + 알림. 장애 시 일시정지 |
| Cloudflare 장애 (사용 시) | 고객 접속 불가 | D 단계에서 고민 (지금은 직접 VPS) |

### 10.2 운영 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| 워커 Drain 무한 대기 (태스크 stuck) | 구버전 붙들림 | drain_timeout 15분. 초과 시 강제 fail + 재시작 |
| Task "running" 좀비화 | 영원히 pending 안 됨 | 서버 크론 30분마다 stale running → pending 복원 + 알림 |
| Task fetch race | 두 워커가 같은 계정 pick | PostgreSQL `FOR UPDATE SKIP LOCKED` 로 DB 레벨 보장 |
| Windows Update 재부팅 | 워커 죽음 | 업무 시간 외 정책. Task Scheduler 로 부팅 시 자동 재시작 |
| Windows 전원 관리 (USB 서스펜드) | ADB 끊김 → IP 로테 실패 | 전원 플랜 "고성능". 절전 완전 비활성 |
| AdsPower 자동 업데이트로 호환성 깨짐 | 워커 작업 실패 | AdsPower 자동 업데이트 OFF. 수동 업데이트 시 테스트 워커 먼저 |
| 휴대폰 테더링 불안정 | IP 로테 실패 | 태스크 시작 직전 ADB 헬스체크. 실패 시 skip + 알림 |

### 10.3 보안 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| `worker_token` 노출 | 악성 워커 접근 | 토큰 per-worker + bcrypt 해시 저장 + 로테이션 기능 |
| VPS 포트 스캔/공격 | 서버 다운 | Cloudflare 프록시 (TLS + bot protection). nginx rate limit |
| DB 자격증명 노출 | 데이터 유출 | `.env` 파일 644 권한. systemd EnvironmentFile 로 전달 |
| 민감 데이터 (비밀번호, 쿠키) 평문 | 탈취 위험 | `hydra.core.crypto` 로 AES 암호화 이미 적용. KEY 는 .env |

### 10.4 데이터 리스크

| 리스크 | 영향 | 완화 |
|---|---|---|
| DB 손상/삭제 | 전 계정 데이터 소실 | 일 1회 자동 백업. 월 1회 복구 연습 |
| execution_logs 폭주 | 디스크 풀 | 30일 자동 삭제 크론. 스크린샷 동일 |
| `.env` 파일 사라짐 (VPS 재설치 시) | 서비스 불가 | 1Password/로컬 암호화 저장소에 복사본. 배포 문서에 절차 |

### 10.5 운영 플레이북 (필수)

spec 구현과 병행해서 **장애 대응 매뉴얼** 작성 필요:
- 어떤 알림(Discord 메시지, 이메일) 왔을 때 → 무슨 명령 → 어떻게 확인
- VPS 재구축 절차 (스냅샷 복원 → DB 덤프 로드 → .env 복구 → 서비스 재시작)
- 워커 전면 리셋 절차
- 긴급 연락처, 권한자 명단

---

## 11. 구현 단계 (상위 개요)

> **중요 — 이 spec 은 마스터 아키텍처 문서**입니다. 실제 구현 시 각 Phase 마다 `writing-plans` 로 **별도 구현 계획서**를 작성해야 합니다. 단일 implementation plan 으로 묶기엔 범위가 넓습니다.

이 spec 은 다음 하위 계획들로 분할 구현:

### Phase 1 — VPS 기반 + 서버 확장 (1~2주)
- VPS 프로비저닝 (Vultr Seoul)
- Ubuntu 22.04 + nginx + PostgreSQL + Python 설정
- 기존 FastAPI → VPS 이전
- 도메인 + TLS (Let's Encrypt)
- 배포 스크립트 (`deploy.sh`)
- DB 스키마 마이그레이션 (customer_id, server_config, users, execution_logs 추가)
- 어드민 UI 에 "배포" 버튼 + "일시정지" 버튼 추가

### Phase 2 — 워커 Windows 전환 (1주)
- Windows PC 1대에 hydra-worker 설치 스크립트 작성
- Task Scheduler 등록
- Tailscale 연동
- Mac ↔ Windows 호환성 이슈 수정 (인코딩, 경로)
- 상시 테스트 워커 확정

### Phase 3 — 관측성 (1주)
- `/api/logs/batch`, `/api/screenshots` 엔드포인트
- `RemoteLogHandler` 워커 측 구현
- 실패 시 자동 스크린샷
- 어드민 UI 의 "Live Worker" 뷰, 로그 필터, 타임라인 뷰
- Discord 웹훅 알림

### Phase 4 — 자동화 (1주)
- 카나리 배포 로직
- Drain timeout / 좀비 태스크 복구 크론
- DB 자동 백업 (S3)
- GitHub Actions CI (macOS + Windows pytest)
- 운영 플레이북 문서화

### Phase 5 — 워커 확장 (지속)
- 나머지 Windows 워커 순차 온보딩
- 계정 캠페인 실전 투입
- 관측성 데이터 기반 최적화

---

## 12. 열린 질문 / 후속 과제

- **VPS 백업 대상 S3 호환 서비스 선택** (AWS S3 / Backblaze B2 / Wasabi) — 비용/한국 지연 기반 결정 필요
- **Tailscale 유료 전환 시점** — 20 디바이스 초과 시점
- **로그 저장소 규모 추정** — 100태스크/일 × 10워커 × 30일 → 예상 GB 계산 후 디스크 크기 확정
- **AdsPower 요금제 업그레이드 시점** — 동시 브라우저 수 제한에 걸리는 시점
- **CI 빌드 시간 vs 자동 배포 딜레이** — GitHub Actions 가 배포 체인에 직접 들어가야 하나, 선택 배포 방식 유지하나

---

## 13. 성공 기준

이 아키텍처가 "완성" 되었다고 판단하는 기준:

1. ✅ Mac 에서 `git push` → 1~2분 내 전 워커 반영 (수동 개입 없이)
2. ✅ 워커 1대 임의 종료해도 자동 복구 (Task Scheduler + 좀비 태스크 처리)
3. ✅ 태스크 실패 시 3초 내 Discord 알림 + 30초 내 어드민 UI 에서 스크린샷 확인 가능
4. ✅ VPS 삭제되어도 30분 내 재구축 (스냅샷 + DB 덤프 + `.env` 복원)
5. ✅ Mac 에서 Tailscale 로 워커 PC 접근 가능 (RDP/SSH)
6. ✅ 크로스플랫폼 CI 통과 없이 배포 불가
7. ✅ 10~20대 워커로 일 1000태스크 이상 안정 처리

---
