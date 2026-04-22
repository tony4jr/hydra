# HYDRA 배포 아키텍처 — 한 페이지 요약

> 이 문서는 IT 초급자도 이해할 수 있게 설명된 **1페이지 완결 레퍼런스**입니다. 기술적인 세부 명세는 [`2026-04-22-deployment-architecture-design.md`](./2026-04-22-deployment-architecture-design.md) 참조.

---

## 🎯 목적 (한 줄)

**"Mac 에서 코드 수정 → 1~2분 내 전 워커 PC 에 자동 반영 + 원격으로 모든 걸 관찰/제어할 수 있는 운영 체계"**

---

## 🗺️ 전체 그림

```
    [개발 Mac]                          [인터넷]                         [워커 PC × 10~20]
 ┌──────────────┐                    ┌──────────┐                     ┌──────────────────┐
 │  - 코드 작성  │   ① git push       │          │    ③ git pull      │  - 온보딩/댓글     │
 │  - 테스트     │ ────────────────► │  GitHub  │ ◄────────────────── │  - IP 로테이션     │
 │  - 배포버튼   │                    │          │                     │  - 태스크 실행     │
 └──────┬───────┘                    └──────────┘                     └─────────┬────────┘
        │                                                                       │
        │                            ┌──────────────┐                           │
        │  ② 어드민 UI 접속           │              │   ④ heartbeat/태스크 poll │
        └───────────────────────────►│   VPS 서버   │◄──────────────────────────┘
                                     │  (Vultr SG)  │
                                     │              │   ⑤ 로그 + 스크린샷 업로드
                                     │  FastAPI     │◄──────────────────────────┐
                                     │  PostgreSQL  │                           │
                                     │  nginx       │                           │
                                     │  React UI    │                           │
                                     └──────┬───────┘                           │
                                            │                                    │
                                            │   ⑥ Discord 알림                   │
                                            ▼                                    │
                                    ┌──────────────┐                            │
                                    │   Discord    │                            │
                                    │   (채팅방)     │                          │
                                    └──────────────┘                            │
                                                                                 │
    [Tailscale VPN: Mac ↔ 워커PC 직접 접근 가능 — 비상시 RDP/SSH]                │
    Mac ──────────────────────────────────────────────────────────────────────┘
```

**6가지 주요 신호:**
1. **git push** — Mac 에서 GitHub 로 코드 업로드
2. **어드민 UI** — Mac 에서 VPS 웹페이지 접속 (`admin.hydra.com`)
3. **git pull** — 워커가 GitHub 에서 새 코드 다운로드
4. **heartbeat/태스크 poll** — 워커가 VPS 에 15초마다 "일감 있나요?" 물어봄
5. **로그 + 스크린샷** — 워커가 실행 결과를 VPS 에 업로드
6. **Discord 알림** — 실패 발생 시 메신저로 바로 알림

---

## 🧱 어떤 컴포넌트가 뭘 하는지

### 🟢 개발 Mac (우리가 쓰는 것)
| 역할 | 사용 도구 |
|---|---|
| 코드 수정 | VSCode + Claude Code |
| 버전 관리 | git |
| 로컬 테스트 | Python 3.11 가상환경 (`.venv`) |
| Mac 에서도 Playwright 테스트 가능 (휴대폰 IP 로테이션만 없음) | Playwright |
| VPS 접근 | SSH, 브라우저 (어드민 UI) |
| 워커 원격 접근 | Tailscale (VPN) |

### 🟡 GitHub (무료)
- **역할:** 코드의 "진실의 원천" (single source of truth)
- 워커 20대가 동시에 pull 해도 부담 없음
- 브랜치 전략: `main` 만 배포 대상 (초기엔 단순화)

### 🔵 VPS — Vultr Seoul ($24/월)
**스펙:** 2 vCPU / 4GB RAM / 80GB SSD / 한국 리전

| 컴포넌트 | 역할 | 언어/기술 |
|---|---|---|
| **FastAPI** | 워커 API + 어드민 API | Python 3.11 |
| **PostgreSQL** | 모든 데이터 저장 (계정/태스크/로그) | SQL |
| **nginx** | HTTPS 종단 + 정적 파일 서빙 + rate limit | C (설정만 만짐) |
| **React UI (반응형 PWA)** | 어드민 페이지 — **휴대폰/태블릿/PC 모두에서 모든 기능 완전 지원** | TypeScript + React + Vite + Tailwind |
| **systemd** | 서비스 자동 실행/재시작 | Linux 기본 |
| **Certbot** | TLS 인증서 자동 갱신 (Let's Encrypt) | Bash |

**도메인 예시:** `admin.hydra.com` (어드민 UI), `api.hydra.com` (API)

### 🔴 워커 PC (Windows 10/11, 10~20대)

**설치 방식: 하이브리드 (초기 1회 exe → 이후 git pull)**
- `hydra-worker-setup.exe` 실행 1회 → Python/Git/ADB/Tailscale 자동 설치 + 코드 clone + Task Scheduler 등록 + NTP 설정 + enrollment token 으로 환경변수 수신
- 업데이트는 배포 버튼 → heartbeat 감지 → git pull (PyInstaller 불필요)
| 컴포넌트 | 역할 | 언어/기술 |
|---|---|---|
| **hydra-worker.exe** | 메인 워커 프로세스 (HTTP poll + 태스크 실행) | Python 3.11 (PyInstaller 로 exe 패키징) |
| **AdsPower 앱** | 안티디텍트 브라우저 (프로필 클라우드에서 싱크) | 외부 앱 (설치만) |
| **Playwright** | AdsPower 브라우저 원격 제어 | Python (pip install) |
| **ADB** | 휴대폰 데이터 on/off 제어 (IP 로테이션) | Android SDK Platform Tools |
| **Tailscale** | VPN 클라이언트 — Mac 에서 원격 접근 | 설치만 |
| **Task Scheduler** | 부팅 시 hydra-worker 자동 시작 + 크래시 재시작 | Windows 기본 |
| **USB ↔ 휴대폰** | 모바일 IP 확보 (테더링) | 하드웨어 |

### 🟣 외부 서비스 (선택)
| 서비스 | 용도 | 비용 |
|---|---|---|
| **Tailscale** | Mac ↔ 워커 VPN 메시 | 무료 (20 디바이스까지) |
| **Discord** | 알림 수신 (웹훅) | 무료 |
| **Backblaze B2** | DB 백업 / 스크린샷 저장 | ~$6/월 (10GB) |
| **Cloudflare** | DDoS 방어 + CDN (나중에) | 무료 플랜 충분 |

---

## 🌊 "하루의 흐름" 시나리오

**🕘 09:00 — 일과 시작**

```
1. 개발자가 Mac 에서 어드민 UI 열음 (admin.hydra.com)
   → "어제 밤 워커 상태" 대시보드 확인
   → 3개 태스크 실패, 나머지 127개 성공

2. 실패 3개 클릭해서 스크린샷 확인
   → "아, 이건 Google 이 새 다이얼로그 추가했네"
   → 코드 수정 필요
```

**🕙 10:00 — 코드 수정 + 배포**

```
3. Mac 에서 VSCode 로 수정 (5분 작업)
4. git commit + git push  
5. 어드민 UI 에서 "배포 v1.2.4" 버튼 클릭
6. 15초 후 워커들이 heartbeat 하면서 새 버전 감지
7. 워커들이 각자 현재 태스크 완료 → git pull → 재시작
8. 5분 내 전 워커 v1.2.4 로 갱신 완료
```

**🕛 12:00 — 실시간 캠페인 실행 중**

```
9. 어드민에서 "영상 ABC123 에 댓글 10개 seed 프리셋" 캠페인 등록
10. VPS 가 태스크 10개 생성 → DB 저장 (worker_id=NULL, status=pending)
11. 놀고 있던 워커 5대가 heartbeat 시 순차적으로 태스크 가져감
12. 각 워커: ADB 로 IP 로테 → AdsPower 프로필 시작 → 영상 시청 → 댓글 작성
13. 평균 7분 소요 → 댓글 10개 1시간 내 완료
```

**🕒 15:00 — 문제 발생**

```
14. Discord 에 🚨 알림: "워커 3, 태스크 #247 실패"
15. 클릭하면 어드민 UI 로 이동 → 스크린샷 + 로그 타임라인 자동 표시
16. "아, 핸들 중복 에러네. 프로필 re-assign 필요"
17. "재시도" 버튼 클릭 → 다른 계정에 재배치 → 성공
```

**🕖 19:00 — 긴급 상황**

```
18. 워커 2대가 연달아 실패 — Google 이 뭔가 막는 중
19. 어드민 UI 에서 "전체 일시정지" 버튼 클릭 (kill switch)
20. 모든 워커 즉시 새 태스크 fetch 중단
21. 문제 분석 → 원인 파악 (예: Google API 일시적 이슈)
22. 30분 후 "재개" 버튼 → 자동 복귀
```

---

## 📡 신호가 어떻게 오가는지 (시간순)

### 🔄 평상시 (매 15초)

```
워커 ─POST /api/workers/heartbeat──► VPS
  "안녕, 나 워커2. v1.2.3 쓰는 중. CPU 20%, RAM 4GB"
        
VPS ─응답─► 워커
  "OK. 최신 버전은 v1.2.3, 일시정지 아님"
        ↓
워커 ─POST /api/tasks/fetch──► VPS
  "일감 주세요"
        
VPS ─응답─► 워커  
  [{task_id: 42, account_id: 7, task_type: "comment", payload: {...}}]
        ↓
워커 실행 시작...
        ↓ (태스크 실행 중 수시로)
        
워커 ─POST /api/logs/batch──► VPS
  [로그 100개 뭉치]
        
워커 ─POST /api/screenshots──► VPS
  (실패 시 캡처 이미지)
        ↓ (완료 후)

워커 ─POST /api/tasks/complete──► VPS
  "태스크 42 완료"
```

### 🚀 배포할 때

```
Mac ─git push──► GitHub

Mac ─어드민 UI "배포" 클릭──► VPS
VPS 가 백엔드에서 deploy.sh 실행:
  git pull
  pip install
  npm run build (프론트)
  systemctl restart hydra-server
  UPDATE server_config SET current_version = 'v1.2.4'
        ↓
(15초 후 워커들 heartbeat)
        
워커들 ─heartbeat──► VPS
VPS 응답: "최신 버전은 v1.2.4"
  ↓
워커: "내 버전은 v1.2.3 이네, 업데이트 필요"
        ↓
워커: 현재 태스크 완료 기다리기 (drain mode)
        ↓
워커: git pull + pip install + 자기 자신 종료
        ↓
Windows Task Scheduler: 워커 프로세스 자동 재시작 (새 버전으로)
```

### 🚨 에러 발생 시

```
워커 태스크 실행 중 예외 발생
        ↓
자동으로 page.screenshot() 캡처
        ↓
워커 ─POST /api/screenshots──► VPS
  [PNG 파일] → S3 or 로컬 저장 → URL 반환
        ↓
워커 ─POST /api/tasks/fail──► VPS
  {task_id: 42, error: "...", screenshot_url: "..."}
        ↓
VPS ─Discord Webhook──► Discord
  🚨 Task #42 failed
  Goal: channel_profile
  Error: auth_dialog_blocking
  [Screenshot] [View Admin] [Retry]
        ↓
개발자가 Discord 보고 → 어드민 UI 클릭 → 상세 페이지
```

---

## 🔑 시크릿/보안 관리 추가 사항

| 항목 | 방식 |
|---|---|
| 워커 .env 배포 | 어드민 UI 발급 1회용 enrollment token → VPS 에서 pull → Windows DPAPI 암호화 저장 |
| DB 스키마 변경 | Alembic 마이그레이션 (git 히스토리 + 롤백 가능) |
| 관리자 액션 추적 | audit_logs 테이블 (누가 언제 뭘) |
| 워커 시계 | NTP 자동 동기화 (w32tm) — TOTP/스케줄 안정성 |
| VPS 완전 삭제 대비 | `docs/runbook.md` 재해 복구 절차 + 월 1회 drill |

---

## 🔐 보안 구조

```
         인터넷
           │
           ▼
      ┌─────────────┐
      │ Cloudflare  │ ← (선택) DDoS 방어 + TLS
      └──────┬──────┘
             ▼
      ┌─────────────┐
      │   nginx     │ ← TLS 종단 + rate limit
      │   (VPS)     │
      └──────┬──────┘
             ▼
     ┌────────────────┐
     │  FastAPI       │ ← X-Worker-Token 검증 (워커)
     │                │   JWT 검증 (어드민)
     └──────┬─────────┘
            ▼
     ┌────────────────┐
     │  PostgreSQL    │ ← 내부 네트워크만 (localhost)
     └────────────────┘

• 워커 → VPS: HTTPS + 토큰 (token 은 워커별 개별, bcrypt 해시 DB 저장)
• 개발자 → VPS 어드민 UI: HTTPS + 이메일/비번 로그인
• Mac → 워커 PC: Tailscale VPN (암호화됨)
```

---

## 🛡️ 자동 안전장치

| 상황 | 자동 조치 |
|---|---|
| 워커 프로세스 크래시 | Task Scheduler 가 즉시 재시작 |
| 워커 PC 재부팅 | 부팅 시 hydra-worker 자동 실행 |
| 태스크가 30분 넘게 running 상태 | VPS 크론이 pending 으로 되돌림 + 알림 |
| 워커 30분 heartbeat 없음 | 상태 offline 처리 + 알림 |
| 배포 중 git pull 실패 | 이전 버전으로 자동 롤백 |
| 휴대폰 ADB 연결 끊김 | 태스크 시작 전 헬스체크 → 실패 시 skip + 알림 |
| 긴급 상황 | 어드민 UI "전체 일시정지" 버튼 |

---

## 📚 용어집 (IT 초급자용)

| 용어 | 쉬운 설명 |
|---|---|
| **VPS** | 인터넷에 항상 켜져 있는 임대 컴퓨터. Vultr/AWS 같은 회사가 제공 |
| **HTTP poll** | 워커가 서버에 "일 있나요?" 주기적으로 물어보는 방식. 반대는 "서버가 알아서 알려주는 push" |
| **heartbeat** | "나 살아있어요" 신호. 15초마다 워커가 보냄 |
| **drain mode** | 식당 마감처럼 "새 손님 안 받고 남은 손님만 처리" 하는 상태. 배포 전 워커가 이 모드로 전환 |
| **카나리 배포** | 광부가 탄광에 카나리아 먼저 보내듯, 워커 1대만 먼저 업데이트해서 문제 없는지 확인 후 나머지 배포 |
| **좀비 태스크** | 워커가 죽어서 "실행 중" 상태로 영원히 남아있는 태스크 |
| **kill switch** | 비상 정지 버튼. 누르면 모든 워커가 즉시 멈춤 |
| **Tailscale** | 회사 사무실 없이도 먼 곳의 컴퓨터끼리 같은 네트워크처럼 통신하게 해주는 무료 VPN |
| **webhook** | "어떤 일 생기면 이 URL 로 알려줘" 하는 약속. Discord 알림이 이 방식 |
| **nginx** | 요청을 중계하는 문지기 프로그램. HTTPS 처리 + 정적 파일 서빙 |
| **systemd** | Linux 의 서비스 관리자. "이 프로그램 항상 실행해 놔" 하는 역할 |
| **Task Scheduler** | Windows 버전 systemd |
| **drain timeout** | drain mode 에서 최대 기다리는 시간. 넘으면 강제 종료 |
| **SPOF** | Single Point Of Failure. 얘 하나 죽으면 전부 죽는 약한 고리 |
| **multi-tenant** | 한 서비스 안에 여러 고객 계정이 공존하는 구조. 상용화 시 필요 |

---

## 💰 월간 비용 견적 (초기 10~20 워커 운영 기준)

| 항목 | 비용 |
|---|---|
| VPS (Vultr Seoul 2vCPU/4GB) | **$24** |
| 도메인 (.com) | $1 (연간 $12) |
| Backblaze B2 (10GB 백업) | **$6** |
| Tailscale | **$0** (무료) |
| Discord | **$0** |
| GitHub | **$0** (public 레포면) |
| Cloudflare | **$0** (free tier) |
| **합계** | **약 $31/월** |

(워커 PC + 휴대폰 + 데이터 요금제는 별도 고정비)

---

## 🚦 지금 어디쯤?

```
 [개발 완료]       [spec 작성]        [시각화 설명]      [구현 계획서]     [Phase 1 구현]    [운영 시작]
 온보딩 자동화  ──► 배포 구조 설계 ──► 👉 지금 여기 ──► Phase 1-5 plan ──► VPS + 서버 ──► 워커 온보딩
 (✅ 완료)        (✅ 완료)         (✅ 완료)         (다음 단계)       (1~2주)       (지속)
```

---

## ❓ 자주 있는 오해

**Q. "워커 PC 에 코드 설치하고 USB 로 매번 업데이트해야 하나요?"**
A. 아뇨. 첫 세팅만 USB/수동. 이후는 Mac 에서 `git push` → VPS 배포 버튼 → 워커가 자동 pull. 대면 접근 불필요.

**Q. "워커가 서로 다른 계정 동시에 건드리지 않나요?"**
A. VPS DB 에 `account_locks` 로 강제. 한 계정은 절대 두 워커에서 동시에 실행 안 됨.

**Q. "VPS 가 죽으면 전체 다 죽나요?"**
A. 네 (SPOF). 대신 Vultr 스냅샷 매일 + DB 백업으로 30분 내 재구축 가능. 나중에 규모 커지면 슬레이브 추가.

**Q. "Mac 에서 개발한 게 Windows 에서 안 돌아가면요?"**
A. 상시 테스트 워커 1대가 모든 배포를 먼저 받음. 상용 10대에 가기 전에 걸러짐.

**Q. "어떤 언어로 코드 짜요?"**
A. 백엔드+워커: Python 3.11. 프론트: TypeScript + React. 스크립트: Bash + PowerShell. 인프라 설정: YAML/nginx conf.

**Q. "AdsPower 없이는 안 되나요?"**
A. 현재 설계는 AdsPower 중심. 대체재(Multilogin/Dolphin) 쓰려면 채널설정/프로필 관리 코드 재작성 필요. 지금은 AdsPower 전제.

**Q. "휴대폰으로 전체 조작 가능한가요?"**
A. 네. 어드민 UI 가 **반응형 PWA** 로 설계되어 있어서 휴대폰 브라우저에서 PC 와 **동일한 모든 기능** 사용 가능합니다. 홈 화면에 앱처럼 설치 가능하고 푸시 알림도 받을 수 있습니다. 복잡한 폼(캠페인 설정, persona 편집 등)도 모바일에선 다단계 위저드로 자동 재구성됩니다.

---

## 🖼️ 아바타 파일 관리 (프로필 사진)

```
[초기 마이그레이션 1회]
 Mac ─rsync──► VPS /var/hydra/avatars/ (2.1GB, 953 파일)

[운영 중 새 사진 추가]
 휴대폰/PC 어드민 UI
   └─ "아바타 업로드" 버튼 (카테고리 선택 + 드래그 앤 드롭 or ZIP)
         └─ POST /api/admin/avatars/upload
               └─ VPS 가 /var/hydra/avatars/<카테고리>/ 에 저장
                    (800×800px 초과 시 자동 리사이즈)

[워커가 태스크 실행 시]
 워커 ──GET /api/avatars/female/20s/f20_003.png──► VPS
  │                                (워커 토큰 인증)
  ▼
 임시 파일로 다운로드 → AdsPower 프로필 아바타 업로드
  │
  ▼
 완료 후 임시 파일 삭제 (로컬엔 24h LRU 캐시)
```

**저장 위치:**
- 주저장: VPS `/var/hydra/avatars/` (2.1GB, nginx + 인증 필수)
- 백업: Backblaze B2 일 1회 자동 rsync
- 향후: 10GB 넘어가면 B2 로 완전 이관 (API 레이어 교체만)

---

## 📱 모바일 기능 지원 상세

| 기능 | 모바일 지원 | 비고 |
|---|---|---|
| 워커 상태 대시보드 | ✅ 완전 | 카드 레이아웃으로 자동 재배치 |
| 계정 관리 (등록/편집/삭제) | ✅ 완전 | 상세 편집 전부 가능 |
| Persona 편집 (JSON 폼) | ✅ 완전 | 필드별 접이식 섹션 |
| 캠페인 생성 (영상 URL/프리셋/계정 선택) | ✅ 완전 | 다단계 위저드 |
| 프리셋 편집기 (스텝/분기/변수) | ✅ 완전 | 터치 드래그 지원 |
| 태스크 스크린샷 뷰어 | ✅ 완전 | 핀치 줌 지원 |
| 실행 로그 타임라인 | ✅ 완전 | 세로 스크롤 최적화 |
| 배포 버튼 / 카나리 / 롤백 | ✅ 완전 | 확인 다이얼로그 필수 |
| 긴급 정지 / 재개 | ✅ 완전 | 홈 화면 첫 버튼 배치 |
| 상단 노출 효과 차트 | ✅ 완전 | 가로 스크롤 or 단순화 뷰 |
| **아바타 파일 업로드/관리** | ✅ 완전 | 카메라/앨범 직접 선택, ZIP 업로드 |
| 로그 검색 / 필터 | ✅ 완전 | 모바일 검색바 우선 |
| 알림 수신 | ✅ 완전 | PWA 푸시 또는 Discord |

---

## 📎 관련 문서

- **기술 명세서 (상세):** [`2026-04-22-deployment-architecture-design.md`](./2026-04-22-deployment-architecture-design.md)
- **온보딩 구조:** [`2026-04-21-onboarding-verifier-design.md`](./2026-04-21-onboarding-verifier-design.md)
- **프로젝트 메모리:** `~/.claude/projects/-Users-seominjae-Documents-hydra/memory/`

---
