# Phase 1 구현 — 한눈에 보는 로드맵

> **1페이지 요약 문서.** 상세는 [`2026-04-22-phase1-vps-server-setup.md`](./2026-04-22-phase1-vps-server-setup.md) 참조.

---

## 🎯 Phase 1 의 최종 목표

```
 [현재 상태]                              [Phase 1 종료]
  ┌──────────────┐                      ┌──────────────────────────┐
  │ Mac 로컬 개발 │                      │ VPS + 1개 Windows 워커    │
  │ 로컬 sqlite  │        ───────►     │ PostgreSQL               │
  │ curl 테스트   │   (2~2.5주 작업)     │ 어드민 UI (반응형)         │
  │              │                      │ git push → 자동 반영       │
  └──────────────┘                      └──────────────────────────┘
```

**다섯 문장으로 끝:**
1. Mac 에서 `git push` 하면 1~2분 내 VPS + 워커 자동 반영
2. 어드민 UI 에서 배포/긴급정지/계정관리/아바타업로드 휴대폰으로도 가능
3. 윈도우 워커가 VPS 와 통신하며 태스크 수행 (DB 는 VPS 만 씀)
4. 워커별로 "계정 생성 전용 / 댓글 전용" 역할 분담 가능
5. 모든 관리자 액션이 감사 로그에 자동 기록

---

## 📅 5 sub-phase 타임라인

```
 Week 1                                Week 2
 ┌──────────────────┬──────────────────┬──────────────────┬──────────────────┬──────────────────┐
 │ Phase 1a         │ Phase 1b         │ Phase 1c         │ Phase 1d         │ Phase 1e         │
 │ Foundation       │ Core Backend     │ Minimal UI       │ Worker 전환       │ UI 완성 + 검증    │
 │ (3~4일)           │ (3~4일)           │ (2~3일)           │ (2~3일)           │ (2~3일)           │
 │                  │                  │                  │                  │                  │
 │ 14 tasks         │ 11 tasks         │ 4 tasks          │ 6 tasks          │ 4 tasks          │
 ├──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┤
 │ VPS + DB + auth  │ 핵심 API 전부     │ UI 일상 운영 가능  │ 윈도우 워커 실전   │ 기능 UI 완성      │
 │                  │ (curl 로 검증)     │                  │                  │ e2e 검증         │
 ├──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┤
 │ CHECKPOINT 🏁    │ CHECKPOINT 🏁    │ CHECKPOINT 🏁    │ CHECKPOINT 🏁    │ CHECKPOINT 🏁    │
 │ /openapi.json OK │ 워커↔서버 전체    │ 로그인→배포      │ 실제 워커 태스크  │ 모든 기능 사용    │
 │ 로그인 API 통과  │ curl 플로우 OK   │ 모바일 OK        │ 1개 성공 수행     │ 가능, 문서 완성   │
 └──────────────────┴──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

---

## 🧱 각 Phase 에서 만들어지는 것

### 📦 Phase 1a — Foundation (Task 0~17.6)
```
  Vultr VPS 생성 ─► Ubuntu 설정 ─► PostgreSQL ─► Python ─► repo
       │                                                      │
       ▼                                                      ▼
  도메인 + TLS (Let's Encrypt)                       Alembic 마이그레이션 9개
       │                                                      │
       ▼                                                      ▼
  firewall + fail2ban                               FastAPI 껍데기 + CORS
       │                                                      │
       └──────────────────────┬───────────────────────────────┘
                              ▼
                     [💡 이 시점: curl 로 /openapi.json 가능]
```

### 📦 Phase 1b — Core Backend (Task 18~25.5, 37, 38)
```
  로그인 API ─► 워커 enrollment ─► heartbeat ─► fetch/complete/fail
       │              │                │              │
       ▼              ▼                ▼              ▼
  감사 로그        1회용 토큰        버전 공지       SKIP LOCKED
       │              │                │              │
       └──────────────┴────────────────┴──────────────┘
                              │
                              ▼
                  [⭐ 워커 특화 + 계정생성 업로드 API 여기서 추가]
                              │
                              ▼
                  [💡 이 시점: 전체 파이프라인 curl 로 검증 가능]
```

### 📦 Phase 1c — Minimal UI (Task 26~28.5)
```
  Tailwind + shadcn/ui ─► 반응형 AppShell (햄버거 메뉴)
         │                        │
         ▼                        ▼
  로그인 페이지            배포 버튼 + 긴급정지 바
                                  │
                                  ▼
                       [💡 이 시점: 모바일에서 일상 운영 가능]
```

### 📦 Phase 1d — Worker 전환 (Task 30~35)
```
  Mac 아바타 → VPS rsync ─► PowerShell setup.exe ─► NTP + DPAPI
         │                          │                      │
         ▼                          ▼                      ▼
   /var/hydra/avatars     Chocolatey + Tailscale       secrets.enc
                                    │
                                    ▼
                         워커 Config 재구성 (secrets 기반)
                                    │
                                    ▼
                         자가 업데이트 (git pull + 롤백)
                                    │
                                    ▼
                         로컬 DB 제거 (AccountSnapshot)
                                    │
                                    ▼
                         [💡 이 시점: Windows 워커 1대 실제 태스크 수행]
```

### 📦 Phase 1e — UI 완성 + 검증 (Task 29, 39, 39.5, 36)
```
  아바타 관리 UI ─► 워커 특화 편집 UI ─► 감사 로그 뷰어
         │                 │                    │
         └─────────────────┴────────────────────┘
                           │
                           ▼
                   end-to-end 검증 체크리스트 (20 항목)
                           │
                           ▼
                   [💡 이 시점: Phase 1 완료]
```

---

## 🗺️ 45 tasks 의 의존 관계 (주요 경로)

```
                                    Task 0 (환경 준비)
                                        │
                                        ▼
                      Task 1~4 (VPS 프로비저닝)
                                        │
                                        ▼
                      Task 5 (repo + deps)
                                        │
                                        ▼
        ┌─────────────── Task 6~14 (Alembic 9개) ───────────────┐
        │                                                        │
        ▼                                                        ▼
   Task 15~16 (auth + audit)                        Task 17~17.6 (라우터 + CORS)
        │                                                        │
        └──────────────────────┬─────────────────────────────────┘
                               ▼
                  Task 18 (로그인 API)
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
        Task 19~20          Task 21~22     Task 23~24
        (enrollment)        (tasks API)    (아바타 + deploy.sh)
                │              │              │
                └──────────────┼──────────────┘
                               ▼
                  Task 25~25.5 (deploy + 보안)
                               │
                ┌──────────────┴──────────────┐
                ▼                              ▼
           Task 37 (특화)                Task 38 (계정생성 업로드)
                │                              │
                └──────────────┬───────────────┘
                               ▼
                     [Phase 1b 완료]
                               │
                               ▼
                  Task 26~28.5 (Minimal UI)
                               │
                               ▼
                  Task 30~35 (Worker 전환)
                               │
                               ▼
                  Task 29, 39, 39.5 (UI 완성)
                               │
                               ▼
                  Task 36 (e2e 검증)
```

---

## 🏁 Phase 끝 체크포인트 — "여기까지 되면 다음 단계 OK"

| Phase | 체크포인트 | 검증 명령 |
|---|---|---|
| **1a 끝** | VPS API 떠있고 DB 구조 완성 | `curl https://api.hydra.com/openapi.json` 성공 + alembic current = head |
| **1b 끝** | 워커↔서버 통신 전체 작동 | curl 로 enrollment→heartbeat→fetch→complete 한 사이클 성공 |
| **1c 끝** | 어드민 UI 기본 기능 | 모바일/PC 양쪽에서 로그인 → 배포 버튼 → 긴급정지 작동 |
| **1d 끝** | 실제 워커 1대 실전 | Windows PC 에서 설치 스크립트 실행 후 실제 태스크 1개 성공 |
| **1e 끝** | Phase 1 완전 완료 | 36번 검증 체크리스트 20항목 모두 ✅ |

---

## 🎛️ Sub-phase 별 "커밋될 산출물"

| Phase | 코드 | 문서 | 인프라 |
|---|---|---|---|
| **1a** | alembic/ (9 migration), hydra/core/auth.py, 미들웨어 | docs/vps-setup.md, .env.example | VPS Ubuntu 22.04, PostgreSQL 14, nginx+TLS |
| **1b** | hydra/web/routes/ (worker_api, tasks_api, admin_*), deploy.sh | (spec 갱신 불필요) | systemd hydra-server 등록 |
| **1c** | frontend/src/features/ (auth, deploy, killswitch) | — | Tailwind + shadcn 세팅 |
| **1d** | worker/ (secrets, config, updater, account_snapshot), setup.ps1 | docs/worker-enrollment.md | Windows 워커 1대 |
| **1e** | frontend/src/features/ (avatars, workers, audit) | docs/phase1-verification.md | — |

---

## 🚨 이거 꼭 기억 (실행 시 놓치기 쉬운 것)

### ① **Task 0 은 반드시 먼저**
`.env.example`, `conftest.py`, `api.ts`, `vite.config.ts`, `create_admin.py` — 이 5개는 Phase 1 전체를 관통하는 공통 기반. **Task 14 이후에 conftest 검증**도 까먹지 말기.

### ② **Task 17 (stub) → Task 17.6 (통합) → Task 18+ (내용 채우기)** 순서
17 에서 stub 만들고, 17.6 에서 기존 flat routes 와 합친 다음, 18 부터 실제 구현. 이 순서 꼬이면 ImportError 로 VPS 못 띄움.

### ③ **Task 25.5 (admin_session 일괄 적용) 은 배포 전 반드시**
이거 놓치면 **로그인 안 해도 아무나 배포 버튼 누를 수 있는 상태**. 보안 차원에서 Phase 1b 끝에 반드시 확인.

### ④ **Task 35 (로컬 DB 제거) 의 SessionLocal import 검증**
테스트에 `assert "SessionLocal" not in worker/executor.py` 있음. 이거 통과해야 함.

### ⑤ **Phase 1d 시작 전 Phase 1b 가 완전해야 함**
워커 전환 시점에 VPS API 가 완벽하게 돌아야 함. 1b 체크포인트 확실히 통과 후 1d 진입.

---

## 📊 예상 소요 시간 (실사용 기준)

```
 Phase 1a: ████████████▓▓ 3~4일   (14 tasks × 평균 30분 ~ 3시간)
 Phase 1b: ██████████▓▓▓  3~4일   (11 tasks × 평균 1~3시간)  
 Phase 1c: ███████        2~3일   (4 tasks × 평균 2~4시간)
 Phase 1d: ███████████    2~3일   (6 tasks × 평균 2~4시간)
 Phase 1e: ███████        2~3일   (4 tasks × 평균 1~3시간)
 ─────────────────────────────────
 합계:     2~2.5주 (solo dev 기준, AI 페어)
```

---

## 📁 관련 문서 (혼동하지 말기)

| 문서 | 역할 | 언제 봄 |
|---|---|---|
| `specs/2026-04-22-deployment-architecture-design.md` | **기술 명세** — 왜/어떻게 설계했는지 상세 | 설계 근거 확인할 때 |
| `specs/2026-04-22-deployment-architecture-overview.md` | **1페이지 요약** — 시스템 구조 시각화 | 빠른 참조, 새로운 팀원 오리엔테이션 |
| `plans/2026-04-22-phase1-vps-server-setup.md` | **상세 구현 계획** — 45 tasks step-by-step | 실제 구현할 때 |
| `plans/2026-04-22-phase1-overview.md` (이 문서) | **구현 로드맵** — 시각화 + 체크포인트 | 진척도 파악, 방향성 확인 |

---

## 🚀 다음 단계

이 문서 + 상세 plan 을 검토하고 이상 없으면:
- **옵션 A**: Subagent-Driven Development — fresh subagent 가 Phase 1a 부터 task-by-task 실행, 리뷰 후 다음 task
- **옵션 B**: Inline Execution — 이 세션에서 batch 단위로 실행, 중간 체크포인트

어느 쪽이든 **Phase 1a 부터 순차 실행** 권장.
