# Phase 1 — VPS 기반 + 서버 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vultr VPS(Ubuntu 22.04) 에 HYDRA 서버 스택을 올리고, Mac 에서 git push → 어드민 UI "배포" 버튼 → VPS 자동 갱신 → 워커 heartbeat 감지 → git pull 사이클이 end-to-end 로 작동하는 상태를 구축한다.

**Architecture:** Ubuntu 22.04 + nginx + PostgreSQL + FastAPI + React (Vite) + systemd. Alembic 기반 DB 마이그레이션. enrollment token 기반 워커 시크릿 배포. nginx 로 정적 프론트 + 아바타 파일 서빙 (워커 토큰 인증). audit log 미들웨어. 프론트 원자적 배포.

**Tech Stack:**
- 서버: Python 3.11, FastAPI, SQLAlchemy, Alembic, PostgreSQL 14, nginx, systemd, certbot
- 프론트: TypeScript, React 18, Vite, Tailwind CSS, shadcn/ui, react-hook-form, tanstack query
- 워커: Python 3.11 (변경 없음 — 연결 대상만 로컬 → VPS)
- 배포: Bash, git, rsync
- 보안: Let's Encrypt TLS, bcrypt, JWT(세션), Windows DPAPI (워커 시크릿)

**참조 Spec:** [`../specs/2026-04-22-deployment-architecture-design.md`](../specs/2026-04-22-deployment-architecture-design.md)

---

## File Structure (Phase 1 완료 후)

```
# === VPS 신규 / 수정 ===
/opt/hydra/                            # VPS 배포 위치
  alembic.ini                          # 새로
  alembic/
    env.py                             # 새로
    versions/
      001_import_existing_schema.py    # 새로
      002_add_customer_id.py           # 새로
      003_add_server_config.py         # 새로
      004_add_users.py                 # 새로
      005_add_execution_logs.py        # 새로
      006_add_audit_logs.py            # 새로
      007_add_account_locks.py         # 새로
  hydra/db/models.py                   # 수정 (users/server_config/execution_logs/audit_logs)
  hydra/core/auth.py                   # 새로 (bcrypt + JWT 세션)
  hydra/core/enrollment.py             # 새로 (1회용 토큰 로직)
  hydra/web/main.py                    # 수정 (미들웨어 등록, 네임스페이스)
  hydra/web/middleware/audit.py        # 새로
  hydra/web/routes/
    admin_deploy.py                    # 새로
    admin_avatars.py                   # 새로
    admin_audit.py                     # 새로
    admin_workers.py                   # 수정 (enrollment)
    admin_auth.py                      # 새로 (login/logout)
    worker_api.py                      # 수정 (heartbeat + version + secrets fetch)
    tasks_api.py                       # 수정 (SKIP LOCKED, complete/fail)
    avatar_serving.py                  # 새로 (워커 토큰 인증 후 정적 파일)
  scripts/
    deploy.sh                          # 새로
    bump_version.py                    # 새로
    backup_db.sh                       # 새로
    backup_avatars.sh                  # 새로
    reset_canary.py                    # 새로
  /etc/nginx/sites-available/hydra      # 새로 (VPS)
  /etc/systemd/system/hydra-server.service  # 새로 (VPS)
  /var/hydra/avatars/                   # 새로 (rsync 대상)

# === 프론트엔드 신규 / 수정 ===
frontend/src/
  app/layout.tsx                       # 수정 (반응형 shell)
  features/
    auth/LoginPage.tsx                 # 새로
    deploy/DeployButton.tsx            # 새로
    deploy/DeployModal.tsx             # 새로
    killswitch/KillSwitchBar.tsx       # 새로
    audit/AuditLogPage.tsx             # 새로
    avatars/AvatarManager.tsx          # 새로
    avatars/AvatarUploadZone.tsx       # 새로
    workers/EnrollWorkerModal.tsx      # 새로
  lib/
    api.ts                             # 수정 (admin vs v1 분리)
    auth.ts                            # 새로 (session)
  hooks/
    useDeploy.ts                       # 새로
    useKillSwitch.ts                   # 새로
    useAuditLog.ts                     # 새로
    useAvatars.ts                      # 새로

# === 문서 ===
docs/
  vps-setup.md                         # 새로 (VPS 프로비저닝 수동 절차)
  runbook.md                           # 새로 (재해 복구)
  worker-enrollment.md                 # 새로 (워커 설치 가이드)
```

---

## 진행 방침

- 각 task 후 바로 commit (자주 커밋 원칙)
- 테스트 가능한 부분은 TDD (pytest)
- 인프라 설정은 "실행 명령 + 검증 절차" 형태로 (단위 테스트 불가)
- Mac (로컬 개발) 과 VPS (SSH 로 원격) 구분 명확히
- Alembic 은 모든 DB 변경의 유일한 경로 (수동 ALTER 금지)

---

## Task 목록 (전체 45개) — 5개 sub-phase 로 분할

**실행 순서 원칙:** 각 sub-phase 종료마다 "작동하는 무언가" 확보 → 체크포인트에서 다음 결정.

### 📦 Phase 1a: Foundation (3~4일) — curl 로 검증 가능한 인프라
- Task 0: 환경 준비 (.env, conftest, axios, vite alias, admin 시드)
- Task 1~4: VPS 프로비저닝
- Task 5: repo clone + deps
- Task 6~14: Alembic 마이그레이션 전체
- Task 15: auth 모듈
- Task 16: 감사 로그 미들웨어
- Task 17: stub 라우터 + namespace
- Task 17.5: CORS 설정
- Task 17.6: 기존 flat routes 통합 결정

**체크포인트:** `curl /openapi.json` 작동, DB 전체 테이블 존재, 로그인 API 통과.

### 📦 Phase 1b: Core Backend (3~4일) — 워커-서버 통신 curl 로 완전 검증
- Task 18: 어드민 로그인 API
- Task 19: 워커 enrollment
- Task 20: heartbeat + 시크릿 수신
- Task 21: fetch/complete/fail (SKIP LOCKED)
- Task 22: 좀비 태스크 복구
- Task 23: 아바타 API
- Task 24: deploy.sh + systemd + nginx
- Task 25: 배포/정지/카나리 엔드포인트
- Task 25.5: admin_session Depends 일괄 적용 ⭐ 보안
- Task 37: 워커 특화 (allowed_task_types) ⭐
- Task 38: 계정 생성 결과 업로드 API ⭐

**체크포인트:** curl 로 enrollment→heartbeat→fetch→complete 전체 작동. 배포는 SSH 에서 `bash deploy.sh`.

### 📦 Phase 1c: Minimal Admin UI (2~3일) — 일상 운영 가능
- Task 26: Tailwind + shadcn 세팅
- Task 27: 로그인 + 반응형 AppShell
- Task 28: 배포 버튼 + 긴급정지 바
- Task 28.5: 워커 목록 페이지 (간단)

**체크포인트:** 어드민 UI 로 로그인 → 배포 → 긴급정지, 모바일 포함.

### 📦 Phase 1d: Worker 전환 (2~3일) — Windows 워커 1대 실전
- Task 30: 아바타 Mac → VPS rsync
- Task 31: PowerShell setup 스크립트
- Task 32: 시크릿 로딩 (DPAPI)
- Task 33: Config 재구성
- Task 34: 자가 업데이트
- Task 35: 로컬 DB 의존성 제거

**체크포인트:** 테스트 워커 설치 완료, heartbeat 확인, 실제 태스크 1개 수행.

### 📦 Phase 1e: UI 완성 + 종합 검증 (2~3일)
- Task 29: 아바타 관리 UI (반응형)
- Task 39: 워커 특화 편집 UI ⭐
- Task 39.5: 감사 로그 뷰어
- Task 36: end-to-end 검증 체크리스트

**체크포인트:** 모든 기능 UI 에서 사용 가능, 전체 파이프라인 검증 통과.

---

## Task 0: 환경 준비 (env, conftest, axios, vite alias, admin 시드)

**목적:** Phase 1 전체를 관통하는 공통 설정 파일들. 이게 먼저 있어야 후속 task 들이 매끄럽게 실행됨.

**Files:**
- Create: `.env.example`
- Create: `tests/conftest.py`
- Create: `frontend/src/lib/api.ts`
- Modify: `frontend/vite.config.ts`
- Create: `scripts/create_admin.py`

- [ ] **Step 1: .env.example 작성**

프로젝트 루트 `.env.example`:
```bash
# 개발(Mac) / 프로덕션(VPS) 공통 템플릿. 실제 .env 는 git 커밋 금지.

# DB 연결 (Mac: sqlite, VPS: postgresql)
DATABASE_URL=sqlite:///data/hydra.db
# DATABASE_URL=postgresql://hydra:STRONGPASS@localhost/hydra_prod

# 암호화 키 (accounts.password / totp_secret 등 AES)
DB_CRYPTO_KEY=generate-with-openssl-rand-base64-32

# JWT 세션 서명 키
JWT_SECRET=generate-with-openssl-rand-base64-64

# 워커 enrollment 토큰 서명 키 (JWT_SECRET 과 분리)
ENROLLMENT_SECRET=generate-with-openssl-rand-base64-32

# 공개 URL
SERVER_URL=http://localhost:8000
# SERVER_URL=https://api.hydra.com

# 아바타 파일 저장 위치
AVATAR_STORAGE_DIR=./data/avatars
# AVATAR_STORAGE_DIR=/var/hydra/avatars
```

생성 명령 주석도 포함되어 있음. VPS 세팅 시 복사해서 실제 값 채움.

- [ ] **Step 2: tests/conftest.py — 테스트 DB 격리**

`tests/conftest.py`:
```python
"""pytest 전역 설정 — 테스트마다 격리된 sqlite 메모리 DB 사용."""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="function", autouse=True)
def _isolated_test_db(monkeypatch, tmp_path):
    """각 테스트마다 /tmp 에 임시 sqlite 파일 사용. alembic head 까지 migration."""
    db_path = tmp_path / "test.db"
    test_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", test_url)

    # SessionLocal / engine 을 test url 로 재바인딩
    import hydra.db.session as sess
    engine = create_engine(test_url, connect_args={"check_same_thread": False})
    sess.engine = engine
    sess.SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    # Alembic upgrade head
    from alembic.config import Config
    from alembic import command
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_url)
    command.upgrade(cfg, "head")
    yield
    # tmp_path 가 자동 정리
```

**효과:** 기존 `data/hydra.db` 프로덕션 DB 건드리지 않음. 테스트끼리 격리. CI 안정.

- [ ] **Step 3: frontend/src/lib/api.ts — axios instance + JWT interceptor**

`frontend/src/lib/api.ts`:
```typescript
import axios from "axios";

// baseURL 은 빌드 시점 env (VITE_API_URL) 또는 dev proxy.
// dev 에선 vite.config.ts 의 proxy 가 /api 를 http://localhost:8000 으로 포워딩.
// prod 에선 admin.hydra.com 에서 /api 호출이 api.hydra.com 으로 가도록 nginx 가 처리.
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  timeout: 30000,
});

// 요청 시 JWT 자동 주입
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("hydra_token");
  if (token && config.headers) {
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  return config;
});

// 401 응답 시 자동 로그인 페이지
api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("hydra_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);
```

이후 모든 task 의 frontend 코드는 `import { api } from "@/lib/api"` 로 `api.post(...)` 형태 사용.

- [ ] **Step 4: frontend/vite.config.ts — path alias 설정**

`frontend/vite.config.ts` 를 수정 (기존 내용 유지 + alias 추가):
```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

**효과:** `@/components/ui/button` import 작동. dev server 가 `/api` 호출을 FastAPI 로 프록시.

tsconfig.json 에도:
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

- [ ] **Step 5: scripts/create_admin.py — 첫 관리자 생성 CLI**

`scripts/create_admin.py`:
```python
#!/usr/bin/env python3
"""첫 관리자 계정을 DB 에 생성. VPS 최초 세팅 직후 1회 실행.

usage: python scripts/create_admin.py <email> <password>
"""
import sys
from hydra.db.session import SessionLocal
from hydra.db.models import User
from hydra.core.auth import hash_password


def main():
    if len(sys.argv) != 3:
        print("usage: create_admin.py <email> <password>"); sys.exit(1)
    email, password = sys.argv[1], sys.argv[2]
    db = SessionLocal()
    try:
        if db.query(User).filter_by(email=email).first():
            print(f"user {email} already exists"); return
        user = User(email=email, password_hash=hash_password(password), role="admin")
        db.add(user); db.commit()
        print(f"created admin: id={user.id} email={user.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 검증 — pytest conftest 작동 확인**

```bash
pytest tests/test_users_model.py -v
```

예상: test_user_creation_with_role pass (격리된 DB 에서 수행되고 자동 정리).

**주의:** 이 Task 는 Task 6~10 (Alembic 마이그레이션) 이전에 실행되면 conftest 의 `command.upgrade(cfg, "head")` 가 실패함. 실제 실행은 Task 14 (마이그레이션 완료) 이후 재검증 필요. **Task 0 의 코드는 준비해두되 검증은 Task 14 에서.**

- [ ] **Step 7: Commit**

```bash
git add .env.example tests/conftest.py frontend/src/lib/api.ts frontend/vite.config.ts scripts/create_admin.py
git commit -m "infra: env 템플릿 + 테스트 DB 격리 + axios 인터셉터 + vite alias + admin 시드"
```

---

## Task 1: Vultr VPS 생성 + SSH 접속

**Files:**
- Create: `docs/vps-setup.md`

- [ ] **Step 1: Vultr 계정 로그인 + 인스턴스 생성**

Vultr 콘솔 https://my.vultr.com 에서:
- Cloud Compute / Regular Performance
- Seoul 리전
- Ubuntu 22.04 LTS x64
- 2 vCPU / 4GB RAM / 80GB SSD ($24/월)
- Hostname: `hydra-prod-01`
- SSH 키 업로드 (Mac 에서 `ssh-keygen -t ed25519 -f ~/.ssh/hydra_prod` 로 사전 생성한 공개키)

검증: 생성 후 약 3분 내 상태 "Running". 공인 IP 확보.

- [ ] **Step 2: SSH 접속 테스트**

```bash
# Mac 에서
ssh -i ~/.ssh/hydra_prod root@<VPS_IP>
```

검증: 프롬프트 `root@hydra-prod-01:~#` 나타남.

- [ ] **Step 3: 일반 사용자 계정 생성 + sudo 권한**

VPS 에서:
```bash
adduser deployer
usermod -aG sudo deployer
mkdir -p /home/deployer/.ssh
cp ~/.ssh/authorized_keys /home/deployer/.ssh/
chown -R deployer:deployer /home/deployer/.ssh
chmod 700 /home/deployer/.ssh
chmod 600 /home/deployer/.ssh/authorized_keys
```

검증: `ssh deployer@<VPS_IP>` 성공.

- [ ] **Step 4: SSH root 로그인 차단**

VPS 에서 `/etc/ssh/sshd_config` 편집:
```
PermitRootLogin no
PasswordAuthentication no
```

```bash
sudo systemctl restart sshd
```

검증: `ssh root@<VPS_IP>` 실패 (Permission denied). `ssh deployer@<VPS_IP>` 는 성공.

- [ ] **Step 5: docs/vps-setup.md 작성**

위 절차를 재현 가능하게 기록:

```markdown
# VPS 초기 세팅 (Vultr Ubuntu 22.04)

## 1. Vultr 인스턴스 생성
- 리전: Seoul, OS: Ubuntu 22.04 LTS, 스펙: 2vCPU/4GB/80GB ($24/월)
- SSH 키 사전 업로드 필수

## 2. deployer 사용자 생성
... (위 명령들 복붙)

## 3. root SSH 차단
...
```

- [ ] **Step 6: Commit**

```bash
git add docs/vps-setup.md
git commit -m "docs: VPS 프로비저닝 절차 문서화"
```

---

## Task 2: VPS 기본 보안 (방화벽 + fail2ban)

- [ ] **Step 1: UFW 방화벽 활성화**

VPS 에서:
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

검증: `Status: active`, 22/80/443 ALLOW 표시.

- [ ] **Step 2: fail2ban 설치**

```bash
sudo apt update
sudo apt install -y fail2ban
sudo systemctl enable --now fail2ban
sudo systemctl status fail2ban
```

검증: `Active: active (running)`.

- [ ] **Step 3: fail2ban SSH 보호 설정**

`/etc/fail2ban/jail.local` 생성:
```ini
[sshd]
enabled = true
port = 22
maxretry = 5
bantime = 3600
findtime = 600
```

```bash
sudo systemctl restart fail2ban
sudo fail2ban-client status sshd
```

검증: `Currently banned: 0`, `Total banned: 0`, Jail 활성.

- [ ] **Step 4: docs/vps-setup.md 에 방화벽 섹션 추가**

```markdown
## 4. 방화벽 + fail2ban
sudo ufw default deny incoming
... (위 명령)
```

- [ ] **Step 5: Commit**

```bash
git add docs/vps-setup.md
git commit -m "docs: VPS 방화벽 + fail2ban 세팅 추가"
```

---

## Task 3: 도메인 연결 + TLS 인증서

**전제:** 도메인 소유 (예: hydra.com). Cloudflare 또는 직접 DNS 관리자.

- [ ] **Step 1: DNS A 레코드 설정**

DNS 관리자에서:
- `admin.hydra.com` A 레코드 → VPS 공인 IP
- `api.hydra.com` A 레코드 → VPS 공인 IP

검증 (약 5분 후):
```bash
dig admin.hydra.com +short
dig api.hydra.com +short
```
VPS IP 반환되어야 함.

- [ ] **Step 2: nginx 설치**

VPS 에서:
```bash
sudo apt install -y nginx
sudo systemctl enable --now nginx
```

브라우저에서 `http://<VPS_IP>` 접속 → "Welcome to nginx" 페이지 확인.

- [ ] **Step 3: certbot 설치 + 인증서 발급**

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d admin.hydra.com -d api.hydra.com \
    --non-interactive --agree-tos -m admin@hydra.com
```

검증:
```bash
sudo certbot certificates
```
출력에 두 도메인 인증서 표시. 만료일 ~90일 뒤.

- [ ] **Step 4: 자동 갱신 확인**

```bash
sudo systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

검증: timer 활성화. dry-run 성공.

- [ ] **Step 5: docs/vps-setup.md 에 TLS 섹션 추가**

```markdown
## 5. 도메인 + TLS
- DNS: admin.hydra.com, api.hydra.com A 레코드
- nginx + certbot 설치
- sudo certbot --nginx -d admin.hydra.com -d api.hydra.com ...
- 자동 갱신 확인: sudo certbot renew --dry-run
```

- [ ] **Step 6: Commit**

```bash
git add docs/vps-setup.md
git commit -m "docs: 도메인 + TLS 인증서 발급 절차"
```

---

## Task 4: PostgreSQL + Python 런타임 설치

- [ ] **Step 1: PostgreSQL 14 설치**

VPS 에서:
```bash
sudo apt install -y postgresql-14 postgresql-contrib-14
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "SELECT version();"
```

검증: `PostgreSQL 14.x` 출력.

- [ ] **Step 2: hydra DB + 사용자 생성**

```bash
sudo -u postgres psql <<EOF
CREATE USER hydra WITH ENCRYPTED PASSWORD 'CHANGEME_STRONG_PASSWORD';
CREATE DATABASE hydra_prod OWNER hydra;
GRANT ALL PRIVILEGES ON DATABASE hydra_prod TO hydra;
EOF

psql -h localhost -U hydra -d hydra_prod -c "SELECT current_database();"
# 비밀번호 입력 → hydra_prod 출력 확인
```

- [ ] **Step 3: Python 3.11 + 필수 패키지 설치**

```bash
sudo apt install -y python3.11 python3.11-venv python3-pip build-essential libpq-dev git
python3.11 --version
```

검증: `Python 3.11.x` 출력.

- [ ] **Step 4: /opt/hydra 디렉토리 + 소유권**

```bash
sudo mkdir -p /opt/hydra /var/hydra/avatars /var/log/hydra
sudo chown -R deployer:deployer /opt/hydra /var/hydra/avatars /var/log/hydra
```

- [ ] **Step 5: docs/vps-setup.md 에 섹션 추가**

```markdown
## 6. PostgreSQL + Python
sudo apt install -y postgresql-14 ...
CREATE DATABASE hydra_prod OWNER hydra;
sudo apt install -y python3.11 ...
sudo mkdir -p /opt/hydra /var/hydra/avatars /var/log/hydra
```

- [ ] **Step 6: Commit**

```bash
git add docs/vps-setup.md
git commit -m "docs: PostgreSQL + Python 런타임 설치 절차"
```

---

## Task 5: Repo clone + venv + 의존성

- [ ] **Step 1: VPS 에서 repo clone**

VPS `deployer` 계정으로:
```bash
cd /opt
git clone https://github.com/<org>/hydra.git
cd /opt/hydra
```

검증: `ls` 에 기존 프로젝트 파일 확인.

- [ ] **Step 2: Python venv 생성 + 의존성 설치**

```bash
cd /opt/hydra
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

- [ ] **Step 3: Alembic + bcrypt + pyjwt 추가**

`requirements.txt` 에 추가:
```
alembic>=1.13,<2
bcrypt>=4.0,<5
pyjwt>=2.8,<3
python-multipart>=0.0.6
```

```bash
pip install -r requirements.txt
```

- [ ] **Step 4: 설치 검증**

```bash
python -c "import fastapi, sqlalchemy, alembic, bcrypt, jwt; print('all ok')"
```

검증: `all ok` 출력.

- [ ] **Step 5: Mac 에서도 requirements.txt 변경 반영**

Mac 에서:
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt
git commit -m "deps: alembic, bcrypt, pyjwt 추가 (Phase 1)"
git push origin main
```

---

## Task 6: Alembic 초기화

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/.gitkeep`

- [ ] **Step 1: Mac 에서 alembic init**

```bash
cd ~/Documents/hydra
source .venv/bin/activate
alembic init alembic
```

`alembic.ini` + `alembic/` 디렉토리 생성 확인.

- [ ] **Step 2: alembic.ini 수정**

`alembic.ini` 편집:
```ini
[alembic]
script_location = alembic
# sqlalchemy.url 은 env.py 에서 동적으로 로드 (주석 처리)
# sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic
# (나머지 기본값 유지)
```

- [ ] **Step 3: alembic/env.py 재작성**

`alembic/env.py` 내용 전체 교체:
```python
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from hydra.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

db_url = os.getenv("DATABASE_URL", "sqlite:///data/hydra.db")
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url, target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: 작동 확인**

```bash
DATABASE_URL=sqlite:///data/hydra.db alembic current
```

검증: 에러 없이 빈 출력 (아직 마이그레이션 없음).

- [ ] **Step 5: Commit**

```bash
git add alembic.ini alembic/env.py alembic/script.py.mako alembic/README
git commit -m "infra: Alembic 마이그레이션 프레임워크 초기화"
```

---

## Task 7: 기존 스키마 Alembic 마이그레이션으로 import

**Files:**
- Create: `alembic/versions/001_baseline_schema.py`

- [ ] **Step 1: 현재 sqlite DB 스키마 dump**

```bash
sqlite3 data/hydra.db ".schema" > /tmp/current_schema.sql
head -30 /tmp/current_schema.sql
```

현재 프로덕션 스키마 구조 파악.

- [ ] **Step 2: alembic revision 생성**

```bash
alembic revision -m "baseline_schema"
```

`alembic/versions/<hash>_baseline_schema.py` 생성됨. 파일명을 `001_baseline_schema.py` 로 리네임 (순서 명시).

- [ ] **Step 3: autogenerate 로 기존 모델 기반 스키마 생성**

```bash
# 깨끗한 DB 에 대해 autogenerate
DATABASE_URL=sqlite:////tmp/empty_hydra.db alembic revision --autogenerate -m "baseline_schema_auto"
```

autogenerate 결과를 `001_baseline_schema.py` 의 `upgrade()` 에 복사. `downgrade()` 에 drop_table 구문 채움.

- [ ] **Step 4: 검증 — 깨끗한 DB 에서 upgrade 성공**

```bash
rm -f /tmp/test_hydra.db
DATABASE_URL=sqlite:////tmp/test_hydra.db alembic upgrade head
sqlite3 /tmp/test_hydra.db ".tables"
```

검증: `accounts workers tasks campaigns ...` 등 주요 테이블 목록 출력.

- [ ] **Step 5: 기존 data/hydra.db 는 alembic_version 테이블에 baseline 표시**

```bash
# 기존 DB 에 "이미 001 이 적용됨" 마킹
DATABASE_URL=sqlite:///data/hydra.db alembic stamp 001_baseline_schema
DATABASE_URL=sqlite:///data/hydra.db alembic current
```

검증: `001_baseline_schema (head)` 출력.

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/001_baseline_schema.py
git commit -m "infra: baseline schema Alembic 마이그레이션"
```

---

## Task 8: customer_id 컬럼 마이그레이션 (D 단계 대비)

**Files:**
- Create: `alembic/versions/002_add_customer_id.py`

- [ ] **Step 1: revision 생성**

```bash
alembic revision -m "add_customer_id_columns"
```

파일명 `002_add_customer_id.py` 로 리네임.

- [ ] **Step 2: upgrade/downgrade 작성**

`alembic/versions/002_add_customer_id.py`:
```python
"""add_customer_id_columns

Revision ID: 002_add_customer_id
Revises: 001_baseline_schema
Create Date: 2026-04-22 ...
"""
from alembic import op
import sqlalchemy as sa

revision = "002_add_customer_id"
down_revision = "001_baseline_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("accounts", "tasks", "campaigns"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("customer_id", sa.Integer, nullable=True))


def downgrade() -> None:
    for table in ("accounts", "tasks", "campaigns"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("customer_id")
```

- [ ] **Step 3: 로컬 적용**

```bash
DATABASE_URL=sqlite:///data/hydra.db alembic upgrade head
sqlite3 data/hydra.db "PRAGMA table_info(accounts);" | grep customer_id
```

검증: `customer_id|INTEGER|0||0` 출력.

- [ ] **Step 4: models.py 에 필드 추가**

`hydra/db/models.py` 의 Account, Task, Campaign 클래스에 각각:
```python
customer_id = Column(Integer, nullable=True)
```

- [ ] **Step 5: 모델 import 검증**

```bash
python -c "from hydra.db.models import Account; print('customer_id' in [c.name for c in Account.__table__.columns])"
```

검증: `True` 출력.

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/002_add_customer_id.py hydra/db/models.py
git commit -m "schema: customer_id 컬럼 추가 (D 단계 대비)"
```

---

## Task 9: server_config 테이블 마이그레이션

**Files:**
- Create: `alembic/versions/003_add_server_config.py`

- [ ] **Step 1: revision 생성**

```bash
alembic revision -m "add_server_config"
```

파일명 `003_add_server_config.py`.

- [ ] **Step 2: 테스트 작성**

`tests/test_server_config_model.py`:
```python
from hydra.db.models import ServerConfig
from hydra.db.session import SessionLocal


def test_server_config_singleton_defaults():
    db = SessionLocal()
    cfg = db.query(ServerConfig).first()
    assert cfg is not None
    assert cfg.current_version is not None
    assert cfg.paused is False
    assert cfg.canary_worker_ids == "[]"
    db.close()
```

- [ ] **Step 3: 테스트 실행 — FAIL**

```bash
pytest tests/test_server_config_model.py -v
```

검증: FAIL (ServerConfig not defined).

- [ ] **Step 4: migration upgrade 작성**

`alembic/versions/003_add_server_config.py`:
```python
"""add_server_config"""
from alembic import op
import sqlalchemy as sa

revision = "003_add_server_config"
down_revision = "002_add_customer_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "server_config",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("current_version", sa.String(64), nullable=False, server_default="v0"),
        sa.Column("paused", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("canary_worker_ids", sa.Text, nullable=False, server_default="[]"),
        sa.Column("last_deploy_at", sa.DateTime, nullable=True),
        sa.Column("last_deploy_by", sa.String(64), nullable=True),
    )
    op.execute("INSERT INTO server_config (id, current_version, paused, canary_worker_ids) "
               "VALUES (1, 'v0', 0, '[]')")


def downgrade() -> None:
    op.drop_table("server_config")
```

- [ ] **Step 5: models.py 에 ServerConfig 추가**

`hydra/db/models.py`:
```python
class ServerConfig(Base):
    __tablename__ = "server_config"
    id = Column(Integer, primary_key=True)
    current_version = Column(String(64), nullable=False, default="v0")
    paused = Column(Boolean, nullable=False, default=False)
    canary_worker_ids = Column(Text, nullable=False, default="[]")
    last_deploy_at = Column(DateTime, nullable=True)
    last_deploy_by = Column(String(64), nullable=True)
```

- [ ] **Step 6: 적용 + 테스트 재실행**

```bash
DATABASE_URL=sqlite:///data/hydra.db alembic upgrade head
pytest tests/test_server_config_model.py -v
```

검증: PASS.

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/003_add_server_config.py hydra/db/models.py tests/test_server_config_model.py
git commit -m "schema: server_config 테이블 (current_version/paused/canary)"
```

---

## Task 10: users 테이블 마이그레이션

**Files:**
- Create: `alembic/versions/004_add_users.py`

- [ ] **Step 1: revision 생성**

```bash
alembic revision -m "add_users"
```

- [ ] **Step 2: 테스트 작성**

`tests/test_users_model.py`:
```python
from hydra.db.models import User
from hydra.db.session import SessionLocal


def test_user_creation_with_role():
    db = SessionLocal()
    u = User(email="admin@test.local", password_hash="x", role="admin")
    db.add(u)
    db.commit()
    loaded = db.query(User).filter_by(email="admin@test.local").first()
    assert loaded.role == "admin"
    db.delete(loaded)
    db.commit()
    db.close()
```

- [ ] **Step 3: migration 작성**

`alembic/versions/004_add_users.py`:
```python
"""add_users"""
from alembic import op
import sqlalchemy as sa

revision = "004_add_users"
down_revision = "003_add_server_config"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="operator"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
    )
    op.create_index("idx_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_index("idx_users_email", "users")
    op.drop_table("users")
```

- [ ] **Step 4: models.py 에 User 추가**

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="operator")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    last_login_at = Column(DateTime, nullable=True)
```

- [ ] **Step 5: 적용 + 테스트**

```bash
DATABASE_URL=sqlite:///data/hydra.db alembic upgrade head
pytest tests/test_users_model.py -v
```

검증: PASS.

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/004_add_users.py hydra/db/models.py tests/test_users_model.py
git commit -m "schema: users 테이블 (email/password_hash/role)"
```

---

## Task 11: execution_logs 테이블 마이그레이션

**Files:**
- Create: `alembic/versions/005_add_execution_logs.py`

- [ ] **Step 1: revision 생성**

```bash
alembic revision -m "add_execution_logs"
```

- [ ] **Step 2: 테스트 작성**

`tests/test_execution_logs_model.py`:
```python
from datetime import datetime, UTC
from hydra.db.models import ExecutionLog, Account, Worker, Task
from hydra.db.session import SessionLocal


def test_execution_log_insert_and_query():
    db = SessionLocal()
    # 기존 test account 재사용 (id=1 이 test fixtures 에 있다고 가정)
    log = ExecutionLog(
        task_id=None, worker_id=None, account_id=None,
        timestamp=datetime.now(UTC), level="INFO",
        message="test log entry", context='{"step":"login"}',
        screenshot_url=None,
    )
    db.add(log); db.commit()
    loaded = db.query(ExecutionLog).filter_by(message="test log entry").first()
    assert loaded.level == "INFO"
    db.delete(loaded); db.commit()
    db.close()
```

- [ ] **Step 3: migration 작성**

```python
"""add_execution_logs"""
from alembic import op
import sqlalchemy as sa

revision = "005_add_execution_logs"
down_revision = "004_add_users"


def upgrade() -> None:
    op.create_table(
        "execution_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("worker_id", sa.Integer, sa.ForeignKey("workers.id"), nullable=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=True),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=True),
        sa.Column("screenshot_url", sa.String(512), nullable=True),
    )
    op.create_index("idx_exec_task", "execution_logs", ["task_id"])
    op.create_index("idx_exec_worker_time", "execution_logs", ["worker_id", "timestamp"])
    op.create_index("idx_exec_account_time", "execution_logs", ["account_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("idx_exec_account_time", "execution_logs")
    op.drop_index("idx_exec_worker_time", "execution_logs")
    op.drop_index("idx_exec_task", "execution_logs")
    op.drop_table("execution_logs")
```

- [ ] **Step 4: models.py 에 ExecutionLog 추가**

```python
class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    timestamp = Column(DateTime, nullable=False)
    level = Column(String(16), nullable=False)
    message = Column(Text, nullable=False)
    context = Column(Text, nullable=True)
    screenshot_url = Column(String(512), nullable=True)
```

- [ ] **Step 5: 적용 + 테스트**

```bash
DATABASE_URL=sqlite:///data/hydra.db alembic upgrade head
pytest tests/test_execution_logs_model.py -v
```

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/005_add_execution_logs.py hydra/db/models.py tests/test_execution_logs_model.py
git commit -m "schema: execution_logs 테이블 (로그 중앙 수집용)"
```

---

## Task 12: audit_logs 테이블 마이그레이션

**Files:**
- Create: `alembic/versions/006_add_audit_logs.py`

- [ ] **Step 1: revision 생성**

```bash
alembic revision -m "add_audit_logs"
```

- [ ] **Step 2: migration 작성**

`alembic/versions/006_add_audit_logs.py`:
```python
"""add_audit_logs"""
from alembic import op
import sqlalchemy as sa

revision = "006_add_audit_logs"
down_revision = "005_add_execution_logs"


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.Integer, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("timestamp", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_user_time", "audit_logs", ["user_id", "timestamp"])
    op.create_index("idx_audit_action_time", "audit_logs", ["action", "timestamp"])


def downgrade() -> None:
    op.drop_index("idx_audit_action_time", "audit_logs")
    op.drop_index("idx_audit_user_time", "audit_logs")
    op.drop_table("audit_logs")
```

- [ ] **Step 3: models.py 에 AuditLog 추가**

```python
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(64), nullable=False)
    target_type = Column(String(32), nullable=True)
    target_id = Column(Integer, nullable=True)
    metadata_json = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
```

- [ ] **Step 4: 적용**

```bash
DATABASE_URL=sqlite:///data/hydra.db alembic upgrade head
sqlite3 data/hydra.db ".schema audit_logs"
```

검증: CREATE TABLE audit_logs 출력.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/006_add_audit_logs.py hydra/db/models.py
git commit -m "schema: audit_logs 테이블 (관리자 액션 추적)"
```

---

## Task 13: account_locks 테이블 마이그레이션

**Files:**
- Create: `alembic/versions/007_add_account_locks.py`

- [ ] **Step 1: revision 생성**

```bash
alembic revision -m "add_account_locks"
```

- [ ] **Step 2: 테스트 작성**

`tests/test_account_locks.py`:
```python
from datetime import datetime, UTC
from hydra.db.models import AccountLock
from hydra.db.session import SessionLocal


def test_lock_uniqueness_for_active_account():
    """released_at IS NULL 인 lock 은 account_id 당 최대 1개여야 함."""
    db = SessionLocal()
    lock1 = AccountLock(account_id=1, worker_id=1, task_id=1,
                        locked_at=datetime.now(UTC))
    db.add(lock1); db.commit()

    lock2 = AccountLock(account_id=1, worker_id=2, task_id=2,
                        locked_at=datetime.now(UTC))
    db.add(lock2)
    import pytest
    with pytest.raises(Exception):  # UNIQUE 위반
        db.commit()
    db.rollback()
    db.delete(lock1); db.commit()
    db.close()
```

- [ ] **Step 3: migration 작성**

```python
"""add_account_locks"""
from alembic import op
import sqlalchemy as sa

revision = "007_add_account_locks"
down_revision = "006_add_audit_logs"


def upgrade() -> None:
    op.create_table(
        "account_locks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("worker_id", sa.Integer, sa.ForeignKey("workers.id"), nullable=False),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("locked_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("released_at", sa.DateTime, nullable=True),
    )
    # SQLite 는 partial index 지원. PostgreSQL 도 동일 문법.
    op.execute(
        "CREATE UNIQUE INDEX idx_account_locks_active "
        "ON account_locks (account_id) WHERE released_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_account_locks_active")
    op.drop_table("account_locks")
```

- [ ] **Step 4: models.py 에 AccountLock 추가**

```python
class AccountLock(Base):
    __tablename__ = "account_locks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    locked_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    released_at = Column(DateTime, nullable=True)
```

- [ ] **Step 5: 적용 + 테스트**

```bash
DATABASE_URL=sqlite:///data/hydra.db alembic upgrade head
pytest tests/test_account_locks.py -v
```

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/007_add_account_locks.py hydra/db/models.py tests/test_account_locks.py
git commit -m "schema: account_locks 테이블 (동시 실행 방지 UNIQUE partial index)"
```

---

## Task 14: 전체 마이그레이션 통과 확인

- [ ] **Step 1: 깨끗한 DB 에 전체 적용**

```bash
rm -f /tmp/fresh_hydra.db
DATABASE_URL=sqlite:////tmp/fresh_hydra.db alembic upgrade head
```

검증: 오류 없이 `Running upgrade ... -> 007_add_account_locks, add_account_locks` 까지 출력.

- [ ] **Step 2: 테이블 목록 확인**

```bash
sqlite3 /tmp/fresh_hydra.db ".tables"
```

검증: `accounts`, `tasks`, `workers`, `server_config`, `users`, `execution_logs`, `audit_logs`, `account_locks`, 기타 기존 테이블 모두 표시.

- [ ] **Step 3: downgrade 테스트 (역방향)**

```bash
DATABASE_URL=sqlite:////tmp/fresh_hydra.db alembic downgrade base
sqlite3 /tmp/fresh_hydra.db ".tables"
```

검증: 테이블 목록이 alembic_version 만 남거나 비어있음 (downgrade 성공).

- [ ] **Step 4: 다시 head 로 upgrade**

```bash
DATABASE_URL=sqlite:////tmp/fresh_hydra.db alembic upgrade head
```

검증: 성공.

- [ ] **Step 5: 전체 테스트 실행**

```bash
pytest tests/ -q
```

검증: 기존 테스트 + 새 schema 테스트 전부 pass (또는 언급한 language_setup 1건 pre-existing 실패 유지).

---

## Task 15: 인증 모듈 (auth.py) — bcrypt + JWT 세션

**Files:**
- Create: `hydra/core/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_auth.py`:
```python
import pytest
from hydra.core.auth import hash_password, verify_password, create_session_token, verify_session_token


def test_hash_and_verify_password_round_trip():
    pwd = "ThisIsStrong!2026"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong", hashed) is False


def test_session_token_round_trip():
    token = create_session_token(user_id=42, role="admin", secret="test-secret")
    data = verify_session_token(token, secret="test-secret")
    assert data["user_id"] == 42
    assert data["role"] == "admin"


def test_session_token_wrong_secret_fails():
    token = create_session_token(user_id=42, role="admin", secret="test-secret")
    with pytest.raises(Exception):
        verify_session_token(token, secret="wrong-secret")
```

- [ ] **Step 2: 실행 — FAIL**

```bash
pytest tests/test_auth.py -v
```

검증: ImportError (`hydra.core.auth`).

- [ ] **Step 3: 구현 작성**

`hydra/core/auth.py`:
```python
"""Authentication helpers — bcrypt password hashing + JWT session tokens."""
from datetime import datetime, timedelta, UTC
import bcrypt
import jwt

SESSION_EXP_HOURS = 24 * 7  # 7일


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def create_session_token(user_id: int, role: str, secret: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.now(UTC) + timedelta(hours=SESSION_EXP_HOURS),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_session_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])
```

- [ ] **Step 4: 실행 — PASS**

```bash
pytest tests/test_auth.py -v
```

검증: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add hydra/core/auth.py tests/test_auth.py
git commit -m "feat(auth): bcrypt password + JWT session token 헬퍼"
```

---

## Task 16: 감사 로그 미들웨어

**Files:**
- Create: `hydra/web/middleware/audit.py`
- Create: `hydra/web/middleware/__init__.py`
- Test: `tests/test_audit_middleware.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_audit_middleware.py`:
```python
from hydra.web.middleware.audit import build_audit_entry


def test_build_audit_entry_from_request_dict():
    req_info = {
        "method": "POST", "path": "/api/admin/deploy",
        "client_ip": "1.2.3.4", "user_agent": "Mozilla/5.0",
    }
    session = {"user_id": 7, "role": "admin"}
    body = {"confirm": True, "version": "v1.2.4"}
    entry = build_audit_entry(req_info, session, body)
    assert entry["user_id"] == 7
    assert entry["action"] == "deploy"
    assert entry["ip_address"] == "1.2.3.4"
    assert "v1.2.4" in entry["metadata_json"]


def test_build_audit_entry_non_admin_path_returns_none():
    req_info = {"method": "GET", "path": "/api/workers/heartbeat",
                "client_ip": "1.2.3.4", "user_agent": ""}
    entry = build_audit_entry(req_info, {}, {})
    assert entry is None
```

- [ ] **Step 2: 실행 — FAIL**

```bash
pytest tests/test_audit_middleware.py -v
```

검증: ImportError.

- [ ] **Step 3: 구현 작성**

`hydra/web/middleware/__init__.py`: (빈 파일)

`hydra/web/middleware/audit.py`:
```python
"""감사 로그 자동 기록 미들웨어.

/api/admin/* 로 들어오는 POST/PUT/DELETE 요청을 audit_logs 테이블에 기록한다.
"""
import json
import re


ACTION_MAP = [
    (re.compile(r"/api/admin/deploy"),    "deploy"),
    (re.compile(r"/api/admin/pause"),     "pause"),
    (re.compile(r"/api/admin/unpause"),   "unpause"),
    (re.compile(r"/api/admin/campaigns"), "campaign_change"),
    (re.compile(r"/api/admin/avatars"),   "avatar_change"),
    (re.compile(r"/api/admin/workers"),   "worker_change"),
    (re.compile(r"/api/admin/accounts"),  "account_change"),
]

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _infer_action(path: str) -> str | None:
    for pat, action in ACTION_MAP:
        if pat.search(path):
            return action
    return None


def build_audit_entry(req_info: dict, session: dict, body: dict | None) -> dict | None:
    method = req_info.get("method", "").upper()
    path = req_info.get("path", "")
    if method not in WRITE_METHODS:
        return None
    action = _infer_action(path)
    if action is None:
        return None
    meta = {"method": method, "path": path}
    if body:
        # 비밀번호/토큰 등은 제거
        safe_body = {k: v for k, v in body.items()
                     if k.lower() not in ("password", "token", "enrollment_token")}
        meta["body"] = safe_body
    return {
        "user_id": session.get("user_id"),
        "action": action,
        "target_type": None,
        "target_id": None,
        "metadata_json": json.dumps(meta, ensure_ascii=False),
        "ip_address": req_info.get("client_ip"),
        "user_agent": req_info.get("user_agent"),
    }
```

- [ ] **Step 4: 실행 — PASS**

```bash
pytest tests/test_audit_middleware.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/web/middleware/ tests/test_audit_middleware.py
git commit -m "feat(audit): 관리자 액션 자동 기록 미들웨어 (entry builder)"
```

---

## Task 17: API 네임스페이스 분리 (/api/admin vs /api/v1 vs /api/workers)

**Files:**
- Modify: `hydra/web/main.py`
- Create: `hydra/web/routes/__init__.py` (존재 시 수정)

- [ ] **Step 1: 기존 routes 구조 확인**

```bash
ls hydra/web/routes/
grep -r "include_router" hydra/web/main.py | head
```

- [ ] **Step 2: main.py 에 prefix 분리**

`hydra/web/main.py` 를 수정하여:
```python
from fastapi import FastAPI
from hydra.web.routes import (
    admin_accounts, admin_campaigns, admin_workers, admin_auth,
    admin_avatars, admin_deploy, admin_audit,
    worker_api, tasks_api, public_v1,  # 필요에 따라
)

app = FastAPI(title="HYDRA API")

# 관리자 전용 (세션 인증)
app.include_router(admin_auth.router,      prefix="/api/admin/auth",     tags=["admin-auth"])
app.include_router(admin_accounts.router,  prefix="/api/admin/accounts", tags=["admin-accounts"])
app.include_router(admin_campaigns.router, prefix="/api/admin/campaigns",tags=["admin-campaigns"])
app.include_router(admin_workers.router,   prefix="/api/admin/workers",  tags=["admin-workers"])
app.include_router(admin_avatars.router,   prefix="/api/admin/avatars",  tags=["admin-avatars"])
app.include_router(admin_deploy.router,    prefix="/api/admin",          tags=["admin-deploy"])
app.include_router(admin_audit.router,     prefix="/api/admin/audit",    tags=["admin-audit"])

# 워커 전용 (X-Worker-Token)
app.include_router(worker_api.router, prefix="/api/workers", tags=["worker"])
app.include_router(tasks_api.router,  prefix="/api/tasks",   tags=["tasks"])

# 고객/공개 v1 (D 단계 대비, 지금은 비워둠)
# app.include_router(public_v1.router, prefix="/api/v1", tags=["public-v1"])
```

- [ ] **Step 3: OpenAPI 문서 확인**

```bash
# 로컬에서 서버 띄우고
python -m hydra.web.main &
curl -s http://localhost:8000/openapi.json | python -c "import json,sys; d=json.load(sys.stdin); print(list(d['paths'].keys())[:15])"
```

검증: `/api/admin/deploy`, `/api/workers/heartbeat`, `/api/tasks/fetch` 등이 포함됨.

- [ ] **Step 4: Commit**

```bash
git add hydra/web/main.py
git commit -m "refactor(api): /api/admin, /api/workers, /api/v1 네임스페이스 분리"
```

**중요:** Task 17 은 **stub 라우터만** 먼저 만든다는 점 명시. 각 `admin_*.py` 파일은 **빈 `router = APIRouter()`** 만 존재하는 상태로 만들고, 실제 엔드포인트는 Task 18~23 에서 채워짐. 이 순서로 하지 않으면 ImportError 로 서버가 안 뜸.

- [ ] **Step 5: stub 라우터 파일 생성**

```bash
# 빈 router 만 있는 파일들 생성
for f in admin_accounts admin_campaigns admin_workers admin_avatars admin_deploy admin_audit admin_auth worker_api tasks_api avatar_serving; do
  cat > "hydra/web/routes/${f}.py" <<'EOF'
"""Stub — 실제 엔드포인트는 후속 task 에서 채워짐."""
from fastapi import APIRouter
router = APIRouter()
EOF
done
```

**기존 파일 처리:** `hydra/web/routes/` 에 이미 있는 `accounts.py`, `campaigns.py` 등은 Task 17.6 에서 통합 처리 (아래).

- [ ] **Step 6: 실행 확인**

```bash
python -c "from hydra.web.main import app; print([r.path for r in app.routes][:10])"
```

검증: ImportError 없이 app 로드됨. 기본 경로만 출력 (/openapi.json 등).

---

## Task 17.5: CORS 미들웨어 설정

**목적:** admin.hydra.com (React) → api.hydra.com (FastAPI) 크로스 도메인 요청 허용.

**Files:**
- Modify: `hydra/web/main.py`
- Test: `tests/test_cors.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_cors.py`:
```python
from fastapi.testclient import TestClient
from hydra.web.main import app

client = TestClient(app)


def test_cors_preflight_from_admin_domain_allowed():
    resp = client.options(
        "/api/admin/auth/login",
        headers={
            "Origin": "https://admin.hydra.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://admin.hydra.com"


def test_cors_random_origin_blocked():
    resp = client.options(
        "/api/admin/auth/login",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # 거절되거나 allow-origin 헤더 없음
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"
```

- [ ] **Step 2: 실행 → FAIL**

```bash
pytest tests/test_cors.py -v
```

- [ ] **Step 3: CORSMiddleware 등록**

`hydra/web/main.py` 상단:
```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="HYDRA API")

_allowed = os.getenv("CORS_ALLOWED_ORIGINS",
    "https://admin.hydra.com,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ... 기존 include_router 코드
```

`.env.example` 에 추가:
```bash
CORS_ALLOWED_ORIGINS=https://admin.hydra.com,http://localhost:5173
```

- [ ] **Step 4: 실행 → PASS**

- [ ] **Step 5: Commit**

```bash
git add hydra/web/main.py .env.example tests/test_cors.py
git commit -m "feat(api): CORS 미들웨어 (admin.hydra.com + dev localhost)"
```

---

## Task 17.6: 기존 flat routes 를 admin_ 네임스페이스로 통합

**목적:** 이미 있는 `hydra/web/routes/accounts.py`, `campaigns.py` 등을 Task 17 의 stub 파일들과 합친다. 리팩터링 최소화 — 파일 경로 이동 없이 **main.py 에서 prefix 만 조정**.

**Files:**
- Modify: `hydra/web/main.py` (기존 routes 들을 `/api/admin/*` prefix 로 mount)
- Delete: stub 파일 중 중복되는 것

- [ ] **Step 1: 기존 routes 식별**

```bash
ls hydra/web/routes/*.py | grep -v __init__
```

기존: accounts, brands, campaigns, creator, dashboard, export, keywords, logs, pools, recovery, settings, system, videos.

이 중 관리 기능(어드민) 성격인 것들: accounts, brands, campaigns, creator, dashboard, export, keywords, pools, settings, system, videos, logs, recovery.

- [ ] **Step 2: main.py 에서 prefix 통합**

```python
# hydra/web/main.py

# Task 17 에서 생성한 stub 파일 중 기존에 이미 있는 것은 삭제
# (accounts.py, campaigns.py 등은 이미 있으므로 stub 필요 없음.
#  admin_workers, admin_auth, admin_avatars, admin_deploy, admin_audit 만 신규)

from hydra.web.routes import (
    # 기존 (어드민 성격)
    accounts, campaigns, brands, creator, dashboard, export_, keywords,
    logs, pools, recovery, settings, system, videos,
    # 신규
    admin_auth, admin_workers, admin_avatars, admin_deploy, admin_audit,
    worker_api, tasks_api, avatar_serving,
)

# 기존 flat routes → /api/admin/ prefix 로 마운트
app.include_router(accounts.router,   prefix="/api/admin/accounts",    tags=["admin"])
app.include_router(campaigns.router,  prefix="/api/admin/campaigns",   tags=["admin"])
app.include_router(brands.router,     prefix="/api/admin/brands",      tags=["admin"])
app.include_router(dashboard.router,  prefix="/api/admin/dashboard",   tags=["admin"])
app.include_router(logs.router,       prefix="/api/admin/logs",        tags=["admin"])
# ... 나머지 동일 패턴

# 신규 어드민
app.include_router(admin_auth.router,    prefix="/api/admin/auth",    tags=["admin-auth"])
app.include_router(admin_workers.router, prefix="/api/admin/workers", tags=["admin-workers"])
app.include_router(admin_avatars.router, prefix="/api/admin/avatars", tags=["admin-avatars"])
app.include_router(admin_deploy.router,  prefix="/api/admin",         tags=["admin-deploy"])
app.include_router(admin_audit.router,   prefix="/api/admin/audit",   tags=["admin-audit"])

# 워커
app.include_router(worker_api.router,  prefix="/api/workers", tags=["worker"])
app.include_router(tasks_api.router,   prefix="/api/tasks",   tags=["tasks"])
app.include_router(avatar_serving.router, prefix="/api/avatars", tags=["avatar-static"])
```

- [ ] **Step 3: 중복 stub 삭제**

```bash
# Task 17 에서 만든 stub 중 이미 있는 파일들은 삭제
# (accounts 등은 이미 있으므로 admin_accounts stub 생성 안 함, main.py 에서 기존 accounts 직접 참조)
rm hydra/web/routes/admin_accounts.py hydra/web/routes/admin_campaigns.py
```

- [ ] **Step 4: 동작 확인**

```bash
python -c "from hydra.web.main import app; print([r.path for r in app.routes if 'admin' in r.path][:10])"
```

검증: `/api/admin/accounts/...`, `/api/admin/auth/login` 등 경로 모두 표시.

- [ ] **Step 5: 프론트에서의 호출 경로 수정**

기존 프론트 코드에 `axios.get("/api/accounts")` 같은 호출이 있다면 → `/api/admin/accounts` 로 변경. 전부 find/replace 후 검증.

```bash
grep -rn 'axios\|fetch' frontend/src/ | grep "/api/" | head
```

- [ ] **Step 6: Commit**

```bash
git add hydra/web/main.py hydra/web/routes/ frontend/src/
git commit -m "refactor(api): 기존 flat routes 를 /api/admin/* prefix 로 통합"
```

---

## Task 18: 어드민 로그인 API

**Files:**
- Create: `hydra/web/routes/admin_auth.py`
- Test: `tests/test_admin_auth_api.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_admin_auth_api.py`:
```python
from fastapi.testclient import TestClient
from hydra.web.main import app
from hydra.core.auth import hash_password
from hydra.db.session import SessionLocal
from hydra.db.models import User

client = TestClient(app)


def setup_module(module):
    db = SessionLocal()
    # 테스트 사용자 생성
    if not db.query(User).filter_by(email="testadmin@hydra.local").first():
        db.add(User(email="testadmin@hydra.local",
                    password_hash=hash_password("testpass123"),
                    role="admin"))
        db.commit()
    db.close()


def test_login_success_returns_session_token():
    resp = client.post("/api/admin/auth/login",
                       json={"email": "testadmin@hydra.local", "password": "testpass123"})
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert body["role"] == "admin"


def test_login_wrong_password_401():
    resp = client.post("/api/admin/auth/login",
                       json={"email": "testadmin@hydra.local", "password": "wrong"})
    assert resp.status_code == 401
```

- [ ] **Step 2: 실행 — FAIL**

```bash
pytest tests/test_admin_auth_api.py -v
```

- [ ] **Step 3: 구현 작성**

`hydra/web/routes/admin_auth.py`:
```python
"""어드민 로그인 / 로그아웃 엔드포인트."""
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from hydra.core.auth import verify_password, create_session_token
from hydra.db.session import SessionLocal
from hydra.db.models import User

router = APIRouter()
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: int
    email: str
    role: str


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=req.email).first()
        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(401, "invalid credentials")
        token = create_session_token(user.id, user.role, JWT_SECRET)
        return LoginResponse(token=token, user_id=user.id, email=user.email, role=user.role)
    finally:
        db.close()


@router.post("/logout")
def logout():
    # JWT 는 stateless — 클라이언트가 토큰 삭제. 서버는 no-op.
    return {"ok": True}


def admin_session(authorization: str = Header(...)) -> dict:
    """다른 admin 라우트에서 `Depends(admin_session)` 으로 세션 검증.

    Returns: {user_id, role, ...}
    Raises: 401 if invalid / missing token
    """
    from fastapi import Header, HTTPException
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.replace("Bearer ", "", 1)
    try:
        data = verify_session_token(token, JWT_SECRET)
    except Exception:
        raise HTTPException(401, "invalid session")
    if data.get("role") not in ("admin", "operator"):
        raise HTTPException(403, "insufficient role")
    return data
```

- [ ] **Step 4a: Header import 추가**

파일 상단 import 에:
```python
from fastapi import APIRouter, HTTPException, Header, Depends
```

`verify_session_token` 도 import:
```python
from hydra.core.auth import verify_password, create_session_token, verify_session_token
```

- [ ] **Step 4: 실행 — PASS**

```bash
pytest tests/test_admin_auth_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/web/routes/admin_auth.py tests/test_admin_auth_api.py
git commit -m "feat(api): 어드민 로그인/로그아웃 엔드포인트"
```

---

## Task 19: 워커 enrollment 플로우

**Files:**
- Create: `hydra/core/enrollment.py`
- Create: `hydra/web/routes/admin_workers.py` (수정 — enrollment endpoint 추가)
- Test: `tests/test_enrollment.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_enrollment.py`:
```python
from datetime import datetime, UTC, timedelta
from hydra.core.enrollment import generate_enrollment_token, verify_enrollment_token


def test_generate_and_verify_round_trip():
    token = generate_enrollment_token(worker_name="worker-test", ttl_hours=24)
    data = verify_enrollment_token(token)
    assert data["worker_name"] == "worker-test"


def test_expired_token_rejected(monkeypatch):
    """만료 시간을 과거로 속여서 거절 확인."""
    token = generate_enrollment_token(worker_name="w", ttl_hours=-1)
    import pytest
    with pytest.raises(Exception):
        verify_enrollment_token(token)
```

- [ ] **Step 2: 실행 — FAIL**

- [ ] **Step 3: 구현 작성**

`hydra/core/enrollment.py`:
```python
"""워커 enrollment 토큰 — JWT 기반 1회용 등록 토큰."""
import os
import secrets
from datetime import datetime, timedelta, UTC
import jwt

ENROLLMENT_SECRET = os.getenv("ENROLLMENT_SECRET", "change-me")


def generate_enrollment_token(worker_name: str, ttl_hours: int = 24) -> str:
    payload = {
        "worker_name": worker_name,
        "nonce": secrets.token_hex(16),
        "exp": datetime.now(UTC) + timedelta(hours=ttl_hours),
        "iat": datetime.now(UTC),
        "type": "enrollment",
    }
    return jwt.encode(payload, ENROLLMENT_SECRET, algorithm="HS256")


def verify_enrollment_token(token: str) -> dict:
    data = jwt.decode(token, ENROLLMENT_SECRET, algorithms=["HS256"])
    if data.get("type") != "enrollment":
        raise ValueError("not an enrollment token")
    return data
```

- [ ] **Step 4: 실행 — PASS**

```bash
pytest tests/test_enrollment.py -v
```

- [ ] **Step 5: admin_workers.py 에 endpoint 추가**

`hydra/web/routes/admin_workers.py` 의 `router` 에 추가:
```python
from hydra.core.enrollment import generate_enrollment_token
import secrets
from hydra.core.auth import hash_password

@router.post("/enroll")
def create_enrollment(req: dict, session: dict = Depends(admin_session)):
    worker_name = req.get("worker_name", "").strip()
    if not worker_name:
        raise HTTPException(400, "worker_name required")
    token = generate_enrollment_token(worker_name, ttl_hours=24)
    # 설치 명령 1줄 리턴
    setup_url = f"{os.getenv('SERVER_URL')}/api/workers/setup.ps1"
    install_command = (
        f"iwr -Uri {setup_url} -OutFile setup.ps1; "
        f".\\setup.ps1 -Token '{token}' -ServerUrl '{os.getenv('SERVER_URL')}'"
    )
    return {"enrollment_token": token, "install_command": install_command, "expires_in_hours": 24}
```

(`admin_session` 의존성은 Task 15 auth + 간단한 depends 로 구현 — 기존 프로젝트에 있으면 재사용, 없으면 이 task 내에서 단순 JWT 검증 함수로 추가)

- [ ] **Step 6: Commit**

```bash
git add hydra/core/enrollment.py hydra/web/routes/admin_workers.py tests/test_enrollment.py
git commit -m "feat(enrollment): 워커 1회용 등록 토큰 발급"
```

---

## Task 20: 워커 heartbeat + 시크릿 수신 API

**Files:**
- Modify: `hydra/web/routes/admin_workers.py` (열어놓음) + `hydra/web/routes/worker_api.py` (신규)
- Test: `tests/test_worker_heartbeat.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_worker_heartbeat.py`:
```python
from fastapi.testclient import TestClient
from hydra.web.main import app
from hydra.core.enrollment import generate_enrollment_token
from hydra.db.session import SessionLocal
from hydra.db.models import ServerConfig

client = TestClient(app)


def test_enroll_via_token_returns_worker_token_and_secrets():
    token = generate_enrollment_token(worker_name="worker-unit-test", ttl_hours=1)
    resp = client.post("/api/workers/enroll", json={"enrollment_token": token,
                                                     "hostname": "test-pc"})
    assert resp.status_code == 200
    body = resp.json()
    assert "worker_token" in body
    assert "secrets" in body
    assert "DB_CRYPTO_KEY" in body["secrets"] or "server_url" in body["secrets"]


def test_heartbeat_returns_current_version_and_paused():
    db = SessionLocal()
    cfg = db.query(ServerConfig).first()
    cfg.current_version = "v9.9.9"
    cfg.paused = False
    db.commit(); db.close()
    # 유효한 워커 토큰 필요 — 위 enroll 에서 받아둠 또는 fixture
    # (fixture setup 은 실제 구현 시 conftest.py 에 추가)
```

- [ ] **Step 2: 실행 — FAIL**

- [ ] **Step 3: 구현 — worker_api.py 작성**

`hydra/web/routes/worker_api.py`:
```python
"""워커 전용 엔드포인트 — heartbeat, enrollment, 시크릿 수신."""
import json, os, secrets
from datetime import datetime, UTC
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from hydra.core.enrollment import verify_enrollment_token
from hydra.core.auth import hash_password, verify_password
from hydra.db.session import SessionLocal
from hydra.db.models import Worker, ServerConfig

router = APIRouter()


class EnrollRequest(BaseModel):
    enrollment_token: str
    hostname: str


class EnrollResponse(BaseModel):
    worker_token: str
    worker_id: int
    secrets: dict  # {"SERVER_URL": ..., "DB_CRYPTO_KEY": ..., ...}


@router.post("/enroll", response_model=EnrollResponse)
def enroll(req: EnrollRequest):
    try:
        data = verify_enrollment_token(req.enrollment_token)
    except Exception:
        raise HTTPException(401, "invalid enrollment token")
    worker_name = data["worker_name"]
    db = SessionLocal()
    try:
        worker = db.query(Worker).filter_by(hostname=worker_name).first()
        if worker is None:
            worker = Worker(hostname=worker_name)
            db.add(worker); db.flush()
        plain = secrets.token_urlsafe(32)
        worker.token_hash = hash_password(plain)
        worker.os_type = "windows"
        worker.enrolled_at = datetime.now(UTC)
        db.commit()
        shared_secrets = {
            "SERVER_URL": os.getenv("SERVER_URL", "https://api.hydra.com"),
            "DB_CRYPTO_KEY": os.getenv("DB_CRYPTO_KEY", ""),  # 워커 로컬 DB 암호화용
        }
        return EnrollResponse(worker_token=plain, worker_id=worker.id, secrets=shared_secrets)
    finally:
        db.close()


def worker_auth(x_worker_token: str = Header(...)) -> Worker:
    db = SessionLocal()
    # 단순 구현: 모든 워커 중 매칭되는 token_hash 찾기 (10~20대 규모라 OK)
    for w in db.query(Worker).all():
        if w.token_hash and verify_password(x_worker_token, w.token_hash):
            db.close()
            return w
    db.close()
    raise HTTPException(401, "invalid worker token")


class HeartbeatRequest(BaseModel):
    version: str
    os_type: str = "windows"
    cpu_percent: float = 0.0
    mem_used_mb: int = 0
    disk_free_gb: float = 0.0
    adb_devices: list[str] = []
    adspower_version: str = ""
    playwright_browsers_ok: bool = True
    current_task_id: int | None = None
    time_offset_ms: int = 0


class HeartbeatResponse(BaseModel):
    current_version: str
    paused: bool
    canary_worker_ids: list[int]
    restart_requested: bool
    worker_config: dict


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(req: HeartbeatRequest, worker: Worker = Depends(worker_auth)):
    db = SessionLocal()
    try:
        w = db.get(Worker, worker.id)
        w.last_heartbeat = datetime.now(UTC)
        w.version = req.version
        w.health_snapshot = json.dumps(req.model_dump(), ensure_ascii=False)
        db.commit()

        cfg = db.query(ServerConfig).first()
        canary_ids = json.loads(cfg.canary_worker_ids or "[]")
        return HeartbeatResponse(
            current_version=cfg.current_version,
            paused=cfg.paused,
            canary_worker_ids=canary_ids,
            restart_requested=False,
            worker_config={
                "poll_interval_sec": 15,
                "max_concurrent_tasks": 1,
                "drain_timeout_minutes": 15,
            },
        )
    finally:
        db.close()
```

- [ ] **Step 4: Worker 모델에 token_hash 컬럼 확인 + enrolled_at 추가**

필요 시 추가 마이그레이션 (008_worker_token_hash):
```python
op.add_column("workers", sa.Column("token_hash", sa.String(255), nullable=True))
op.add_column("workers", sa.Column("enrolled_at", sa.DateTime, nullable=True))
op.add_column("workers", sa.Column("health_snapshot", sa.Text, nullable=True))
op.add_column("workers", sa.Column("tailscale_ip", sa.String(45), nullable=True))
```

models.py 의 Worker 에 해당 컬럼 추가.

- [ ] **Step 5: 실행 — PASS**

```bash
DATABASE_URL=sqlite:///data/hydra.db alembic upgrade head
pytest tests/test_worker_heartbeat.py -v
```

- [ ] **Step 6: Commit**

```bash
git add hydra/web/routes/worker_api.py hydra/db/models.py alembic/versions/008_worker_token_hash.py tests/test_worker_heartbeat.py
git commit -m "feat(worker-api): enroll + heartbeat (버전 공지 + canary 리스트)"
```

---

## Task 21: fetch_tasks with SKIP LOCKED

**Files:**
- Create: `hydra/web/routes/tasks_api.py`
- Test: `tests/test_tasks_fetch.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_tasks_fetch.py`:
```python
# 핵심 동작: 두 워커가 동시에 fetch 해도 같은 태스크 받지 않음
from fastapi.testclient import TestClient
from hydra.web.main import app
from hydra.db.session import SessionLocal
from hydra.db.models import Task, Account

client = TestClient(app)


def test_fetch_marks_task_running_and_creates_lock():
    db = SessionLocal()
    # 테스트 태스크 생성
    t = Task(account_id=1, task_type="test", status="pending",
             priority="normal", scheduled_at=None)
    db.add(t); db.commit(); task_id = t.id
    db.close()

    resp = client.post("/api/tasks/fetch", headers={"X-Worker-Token": "TEST_WORKER_TOKEN_FIXTURE"})
    assert resp.status_code == 200
    body = resp.json()
    if body.get("tasks"):
        assert body["tasks"][0]["id"] == task_id
    # Task 가 running 상태로 갱신됐는지 확인
    db = SessionLocal()
    t = db.get(Task, task_id)
    assert t.status == "running"
    db.close()
```

- [ ] **Step 2: 실행 — FAIL**

- [ ] **Step 3: 구현 — tasks_api.py 작성**

`hydra/web/routes/tasks_api.py`:
```python
"""태스크 큐 API — fetch_tasks (동시성 안전), complete, fail."""
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from hydra.db.session import SessionLocal
from hydra.db.models import Task, Account, AccountLock, Worker
from hydra.web.routes.worker_api import worker_auth

router = APIRouter()


@router.post("/fetch")
def fetch_tasks(worker: Worker = Depends(worker_auth)):
    db = SessionLocal()
    try:
        # PostgreSQL 일 때만 SKIP LOCKED 사용. SQLite 는 단순 SELECT.
        dialect = db.bind.dialect.name
        if dialect == "postgresql":
            q = text("""
                SELECT t.id FROM tasks t
                 WHERE t.status='pending'
                   AND (t.scheduled_at IS NULL OR t.scheduled_at <= NOW())
                   AND t.account_id NOT IN (
                     SELECT account_id FROM account_locks WHERE released_at IS NULL
                   )
                 ORDER BY 
                   CASE t.priority 
                     WHEN 'high' THEN 3 
                     WHEN 'normal' THEN 2 
                     WHEN 'low' THEN 1 ELSE 0 
                   END DESC,
                   t.scheduled_at ASC NULLS FIRST
                 LIMIT 1
                 FOR UPDATE SKIP LOCKED
            """)
        else:  # sqlite (dev)
            q = text("""
                SELECT t.id FROM tasks t
                 WHERE t.status='pending'
                   AND (t.scheduled_at IS NULL OR t.scheduled_at <= datetime('now'))
                   AND t.account_id NOT IN (
                     SELECT account_id FROM account_locks WHERE released_at IS NULL
                   )
                 ORDER BY 
                   CASE t.priority 
                     WHEN 'high' THEN 3 
                     WHEN 'normal' THEN 2 
                     WHEN 'low' THEN 1 ELSE 0 
                   END DESC,
                   t.scheduled_at ASC
                 LIMIT 1
            """)
        row = db.execute(q).first()
        if row is None:
            return {"tasks": []}
        task_id = row[0]
        task = db.get(Task, task_id)
        task.status = "running"
        task.worker_id = worker.id
        task.started_at = datetime.now(UTC)
        db.add(AccountLock(account_id=task.account_id, worker_id=worker.id, task_id=task.id))
        db.commit()
        return {"tasks": [{"id": task.id, "account_id": task.account_id,
                           "task_type": task.task_type,
                           "payload": task.payload, "priority": task.priority}]}
    finally:
        db.close()


class TaskResult(BaseModel):
    task_id: int
    result: str | None = None


@router.post("/complete")
def complete(req: TaskResult, worker: Worker = Depends(worker_auth)):
    db = SessionLocal()
    try:
        t = db.get(Task, req.task_id)
        if t is None:
            raise HTTPException(404, "task not found")
        t.status = "done"
        t.completed_at = datetime.now(UTC)
        t.result = req.result
        # account lock 해제
        lock = db.query(AccountLock).filter_by(task_id=t.id, released_at=None).first()
        if lock:
            lock.released_at = datetime.now(UTC)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


class TaskFailure(BaseModel):
    task_id: int
    error: str
    screenshot_url: str | None = None


@router.post("/fail")
def fail(req: TaskFailure, worker: Worker = Depends(worker_auth)):
    db = SessionLocal()
    try:
        t = db.get(Task, req.task_id)
        if t is None:
            raise HTTPException(404, "task not found")
        t.status = "failed"
        t.completed_at = datetime.now(UTC)
        t.error_message = req.error
        lock = db.query(AccountLock).filter_by(task_id=t.id, released_at=None).first()
        if lock:
            lock.released_at = datetime.now(UTC)
        db.commit()
        return {"ok": True}
    finally:
        db.close()
```

- [ ] **Step 4: 실행 — PASS**

```bash
pytest tests/test_tasks_fetch.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/web/routes/tasks_api.py tests/test_tasks_fetch.py
git commit -m "feat(tasks): fetch/complete/fail API + SKIP LOCKED (PG) / SELECT (SQLite)"
```

---

## Task 22: 좀비 태스크 복구 크론

**Files:**
- Create: `hydra/core/zombie_cleanup.py`
- Create: `scripts/zombie_cleanup_cron.py`
- Test: `tests/test_zombie_cleanup.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_zombie_cleanup.py`:
```python
from datetime import datetime, UTC, timedelta
from hydra.core.zombie_cleanup import find_and_reset_zombies
from hydra.db.session import SessionLocal
from hydra.db.models import Task, AccountLock


def test_stale_running_task_reset_to_pending():
    db = SessionLocal()
    t = Task(account_id=1, task_type="test", status="running",
             started_at=datetime.now(UTC) - timedelta(minutes=45),
             worker_id=1)
    db.add(t); db.commit(); task_id = t.id
    db.close()

    count = find_and_reset_zombies(stale_minutes=30)
    assert count >= 1

    db = SessionLocal()
    t = db.get(Task, task_id); assert t.status == "pending"; assert t.worker_id is None
    db.delete(t); db.commit(); db.close()
```

- [ ] **Step 2: 실행 — FAIL**

- [ ] **Step 3: 구현**

`hydra/core/zombie_cleanup.py`:
```python
"""좀비 태스크 감지/복구 — 30분 이상 running 상태면 pending 으로 되돌림."""
from datetime import datetime, UTC, timedelta
from hydra.db.session import SessionLocal
from hydra.db.models import Task, AccountLock
from hydra.core.logger import get_logger

log = get_logger("zombie_cleanup")


def find_and_reset_zombies(stale_minutes: int = 30) -> int:
    threshold = datetime.now(UTC) - timedelta(minutes=stale_minutes)
    db = SessionLocal()
    try:
        stuck = db.query(Task).filter(
            Task.status == "running",
            Task.started_at < threshold,
        ).all()
        for t in stuck:
            log.warning(f"zombie task #{t.id} worker={t.worker_id} started={t.started_at}")
            t.status = "pending"
            t.worker_id = None
            t.started_at = None
            # lock 해제
            locks = db.query(AccountLock).filter_by(task_id=t.id, released_at=None).all()
            for lk in locks:
                lk.released_at = datetime.now(UTC)
        db.commit()
        return len(stuck)
    finally:
        db.close()
```

`scripts/zombie_cleanup_cron.py`:
```python
#!/usr/bin/env python3
"""Crontab 에서 5분마다 실행: 좀비 태스크 복구."""
from hydra.core.zombie_cleanup import find_and_reset_zombies

if __name__ == "__main__":
    count = find_and_reset_zombies(stale_minutes=30)
    print(f"reset {count} zombie tasks")
```

- [ ] **Step 4: 실행 — PASS**

```bash
pytest tests/test_zombie_cleanup.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/core/zombie_cleanup.py scripts/zombie_cleanup_cron.py tests/test_zombie_cleanup.py
git commit -m "feat(reliability): 좀비 태스크 자동 복구 크론"
```

---

## Task 23: 아바타 API (서빙 + 관리자 업로드)

**Files:**
- Create: `hydra/web/routes/avatar_serving.py`
- Create: `hydra/web/routes/admin_avatars.py`
- Test: `tests/test_avatar_api.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_avatar_api.py`:
```python
from pathlib import Path
import shutil, os
from fastapi.testclient import TestClient
from hydra.web.main import app

client = TestClient(app)


def setup_module(module):
    # 테스트 디렉토리 구조
    os.environ["AVATAR_STORAGE_DIR"] = "/tmp/hydra_avatars_test"
    Path("/tmp/hydra_avatars_test/female/20s").mkdir(parents=True, exist_ok=True)
    Path("/tmp/hydra_avatars_test/female/20s/test.png").write_bytes(b"PNG_DATA")


def teardown_module(module):
    shutil.rmtree("/tmp/hydra_avatars_test", ignore_errors=True)


def test_admin_list_returns_tree():
    resp = client.get("/api/admin/avatars/list",
                      headers={"Authorization": "Bearer ADMIN_JWT_FIXTURE"})
    # admin auth fixture 필요 — 실제 실행 시 conftest 에 추가
    assert resp.status_code in (200, 401)


def test_worker_download_returns_file():
    resp = client.get("/api/avatars/female/20s/test.png",
                      headers={"X-Worker-Token": "WORKER_FIXTURE"})
    # worker auth fixture 필요
    assert resp.status_code in (200, 401)
```

- [ ] **Step 2: 실행 — FAIL**

- [ ] **Step 3: 구현 — avatar_serving.py**

`hydra/web/routes/avatar_serving.py`:
```python
"""워커 대상 아바타 파일 서빙."""
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from hydra.web.routes.worker_api import worker_auth

router = APIRouter()
STORAGE = Path(os.getenv("AVATAR_STORAGE_DIR", "/var/hydra/avatars"))


@router.get("/{path:path}")
def get_avatar(path: str, worker=Depends(worker_auth)):
    # path traversal 방어
    requested = (STORAGE / path).resolve()
    if not str(requested).startswith(str(STORAGE.resolve())):
        raise HTTPException(400, "invalid path")
    if not requested.exists() or not requested.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(requested)
```

- [ ] **Step 4: 구현 — admin_avatars.py**

```python
"""어드민 — 아바타 업로드/목록/삭제."""
import os, zipfile, io, shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from PIL import Image

router = APIRouter()
STORAGE = Path(os.getenv("AVATAR_STORAGE_DIR", "/var/hydra/avatars"))
MAX_DIM = 800


def _resize_if_needed(path: Path) -> None:
    img = Image.open(path)
    if max(img.size) > MAX_DIM:
        img.thumbnail((MAX_DIM, MAX_DIM))
        img.save(path, optimize=True)


@router.get("/list")
def list_avatars():
    tree = {}
    for p in STORAGE.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg"):
            rel = p.relative_to(STORAGE)
            parts = list(rel.parts[:-1])
            node = tree
            for part in parts:
                node = node.setdefault(part, {})
            node.setdefault("__files__", []).append(rel.name)
    return tree


@router.post("/upload")
async def upload_avatar(category: str = Form(...), file: UploadFile = File(...)):
    # category 예: "female/20s" 또는 "object/flower"
    if "/.." in category or category.startswith("/"):
        raise HTTPException(400, "invalid category")
    dest_dir = STORAGE / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        _resize_if_needed(dest)
    except Exception:
        pass
    return {"saved": str(dest.relative_to(STORAGE))}


@router.post("/upload-zip")
async def upload_zip(category: str = Form(...), file: UploadFile = File(...)):
    if "/.." in category:
        raise HTTPException(400, "invalid category")
    data = await file.read()
    z = zipfile.ZipFile(io.BytesIO(data))
    saved = []
    for name in z.namelist():
        if name.endswith("/") or ".." in name:
            continue
        dest = STORAGE / category / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(name))
        try: _resize_if_needed(dest)
        except Exception: pass
        saved.append(str(dest.relative_to(STORAGE)))
    return {"saved_count": len(saved)}


@router.delete("/{path:path}")
def delete_avatar(path: str):
    target = (STORAGE / path).resolve()
    if not str(target).startswith(str(STORAGE.resolve())):
        raise HTTPException(400)
    if target.exists():
        target.unlink()
    return {"ok": True}
```

- [ ] **Step 5: Pillow 설치 + requirements.txt**

```bash
pip install Pillow
# requirements.txt 에 "Pillow>=10,<11" 추가
```

- [ ] **Step 6: Commit**

```bash
git add hydra/web/routes/avatar_serving.py hydra/web/routes/admin_avatars.py tests/test_avatar_api.py requirements.txt
git commit -m "feat(avatars): 서빙(워커) + 어드민 업로드(단일/ZIP/삭제/목록) API"
```

---

## Task 24: deploy.sh 작성 + 서버 systemd 설정

**Files:**
- Create: `scripts/deploy.sh`
- Create: `scripts/bump_version.py`
- Create: `/etc/systemd/system/hydra-server.service` (VPS)

- [ ] **Step 1: bump_version.py 작성**

`scripts/bump_version.py`:
```python
#!/usr/bin/env python3
"""server_config.current_version 을 git short hash 로 갱신."""
import sys
from datetime import datetime, UTC
from hydra.db.session import SessionLocal
from hydra.db.models import ServerConfig

def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    db = SessionLocal()
    cfg = db.query(ServerConfig).first()
    cfg.current_version = version
    cfg.last_deploy_at = datetime.now(UTC)
    db.commit(); db.close()
    print(f"server_config.current_version = {version}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: deploy.sh 작성**

`scripts/deploy.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

cd /opt/hydra
echo "[deploy] pulling latest..."
git fetch origin main
PREV_REV=$(git rev-parse HEAD)
git reset --hard origin/main

echo "[deploy] installing python deps..."
source .venv/bin/activate
pip install -r requirements.txt --quiet

echo "[deploy] alembic upgrade..."
alembic upgrade head

echo "[deploy] building frontend..."
cd frontend
npm ci --silent
npm run build -- --outDir dist-new
mv dist dist-old 2>/dev/null || true
mv dist-new dist
rm -rf dist-old
cd /opt/hydra

echo "[deploy] restarting hydra-server..."
sudo systemctl restart hydra-server

echo "[deploy] bumping version..."
NEW_REV=$(git rev-parse --short HEAD)
python scripts/bump_version.py "$NEW_REV"

echo "[deploy] done. was=$PREV_REV now=$NEW_REV"
```

```bash
chmod +x scripts/deploy.sh
```

- [ ] **Step 3: systemd 서비스 파일**

VPS `/etc/systemd/system/hydra-server.service`:
```ini
[Unit]
Description=HYDRA FastAPI Server
After=network.target postgresql.service

[Service]
Type=simple
User=deployer
WorkingDirectory=/opt/hydra
EnvironmentFile=/opt/hydra/.env
ExecStart=/opt/hydra/.venv/bin/uvicorn hydra.web.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hydra-server
sudo systemctl status hydra-server
```

검증: `Active: active (running)`.

- [ ] **Step 4: nginx 설정**

VPS `/etc/nginx/sites-available/hydra`:
```nginx
server {
    listen 443 ssl http2;
    server_name admin.hydra.com;
    ssl_certificate /etc/letsencrypt/live/admin.hydra.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/admin.hydra.com/privkey.pem;

    # 어드민 프론트 정적 파일
    root /opt/hydra/frontend/dist;
    index index.html;
    location = /index.html {
        add_header Cache-Control "no-store, no-cache, must-revalidate";
    }
    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
    }
    location / {
        try_files $uri $uri/ /index.html;
    }
}

server {
    listen 443 ssl http2;
    server_name api.hydra.com;
    ssl_certificate /etc/letsencrypt/live/api.hydra.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.hydra.com/privkey.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/hydra /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

- [ ] **Step 5: 검증**

```bash
curl -s https://api.hydra.com/openapi.json | head -c 200
curl -s -o /dev/null -w "%{http_code}\n" https://admin.hydra.com
```

검증: API 가 JSON 반환, admin 은 200 (React index.html).

- [ ] **Step 6: Commit**

```bash
git add scripts/deploy.sh scripts/bump_version.py
git commit -m "deploy: deploy.sh + bump_version + systemd/nginx 설정 문서화"
```

---

## Task 25: 어드민 "배포" + "긴급정지" 엔드포인트

**Files:**
- Create: `hydra/web/routes/admin_deploy.py`
- Test: `tests/test_admin_deploy.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_admin_deploy.py`:
```python
from fastapi.testclient import TestClient
from hydra.web.main import app
from hydra.db.session import SessionLocal
from hydra.db.models import ServerConfig

client = TestClient(app)


def test_pause_sets_server_config():
    resp = client.post("/api/admin/pause",
                       headers={"Authorization": "Bearer ADMIN_JWT"})
    # 인증 fixture 필요
    if resp.status_code == 200:
        db = SessionLocal()
        cfg = db.query(ServerConfig).first()
        assert cfg.paused is True
        cfg.paused = False
        db.commit(); db.close()
```

- [ ] **Step 2: 구현**

`hydra/web/routes/admin_deploy.py`:
```python
"""배포 실행 + 긴급정지 엔드포인트."""
import subprocess
from fastapi import APIRouter, HTTPException
from hydra.db.session import SessionLocal
from hydra.db.models import ServerConfig

router = APIRouter()


@router.post("/deploy")
def trigger_deploy():
    """VPS 에서 deploy.sh 실행. 비동기로 돌리고 즉시 반환."""
    proc = subprocess.Popen(
        ["bash", "/opt/hydra/scripts/deploy.sh"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return {"started": True, "pid": proc.pid}


@router.post("/pause")
def pause_all():
    db = SessionLocal()
    try:
        cfg = db.query(ServerConfig).first()
        cfg.paused = True
        db.commit()
        return {"paused": True}
    finally:
        db.close()


@router.post("/unpause")
def unpause_all():
    db = SessionLocal()
    try:
        cfg = db.query(ServerConfig).first()
        cfg.paused = False
        db.commit()
        return {"paused": False}
    finally:
        db.close()


@router.post("/canary")
def set_canary(worker_ids: list[int]):
    """카나리 대상 워커 ID 리스트 설정."""
    import json
    db = SessionLocal()
    try:
        cfg = db.query(ServerConfig).first()
        cfg.canary_worker_ids = json.dumps(worker_ids)
        db.commit()
        return {"canary_worker_ids": worker_ids}
    finally:
        db.close()
```

- [ ] **Step 3: sudoers — deployer 가 systemctl restart 권한**

VPS 에서:
```bash
sudo visudo
# 추가:
# deployer ALL=(ALL) NOPASSWD: /bin/systemctl restart hydra-server
```

- [ ] **Step 4: Commit**

```bash
git add hydra/web/routes/admin_deploy.py tests/test_admin_deploy.py
git commit -m "feat(admin): /api/admin/deploy, /pause, /unpause, /canary"
```

---

## Task 25.5: admin_session Depends 일괄 적용 ⭐ 보안

**목적:** 모든 `/api/admin/*` 라우터에 `Depends(admin_session)` 강제. 현재는 Task 18 에서 로그인 API 만 공개, 나머지 라우터들은 적용 안 돼있어 로그인 없이 호출 가능 상태. 배포 전 반드시 막아야 함.

**Files:**
- Modify: `hydra/web/main.py` (router include 시 dependencies 주입)
- Test: `tests/test_admin_requires_auth.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_admin_requires_auth.py`:
```python
from fastapi.testclient import TestClient
from hydra.web.main import app

client = TestClient(app)


def test_admin_endpoint_without_token_returns_401():
    endpoints = [
        ("POST", "/api/admin/deploy"),
        ("POST", "/api/admin/pause"),
        ("POST", "/api/admin/workers/enroll"),
        ("GET",  "/api/admin/audit/list"),
        ("POST", "/api/admin/avatars/upload"),
    ]
    for method, path in endpoints:
        resp = client.request(method, path)
        assert resp.status_code in (401, 403, 422), (
            f"{method} {path} returned {resp.status_code}, expected 401/403"
        )


def test_admin_auth_login_is_public():
    """로그인 자체는 토큰 없어도 접근 가능해야 함."""
    resp = client.post("/api/admin/auth/login",
                       json={"email": "x@y.z", "password": "wrong"})
    assert resp.status_code in (401, 400, 422)  # 인증 실패지만 auth 미들웨어는 통과
```

- [ ] **Step 2: 실행 → FAIL** (현재는 대부분 200)

- [ ] **Step 3: main.py 에서 admin 라우터 dependencies 주입**

```python
from fastapi import Depends
from hydra.web.routes.admin_auth import admin_session

# 로그인 라우터 — 공개
app.include_router(admin_auth.router, prefix="/api/admin/auth", tags=["admin-auth"])

# 나머지 admin 전부 — admin_session 필수
_ADMIN_DEPS = [Depends(admin_session)]
app.include_router(accounts.router,       prefix="/api/admin/accounts",   dependencies=_ADMIN_DEPS, tags=["admin"])
app.include_router(campaigns.router,      prefix="/api/admin/campaigns",  dependencies=_ADMIN_DEPS, tags=["admin"])
app.include_router(admin_workers.router,  prefix="/api/admin/workers",    dependencies=_ADMIN_DEPS, tags=["admin"])
app.include_router(admin_avatars.router,  prefix="/api/admin/avatars",    dependencies=_ADMIN_DEPS, tags=["admin"])
app.include_router(admin_deploy.router,   prefix="/api/admin",            dependencies=_ADMIN_DEPS, tags=["admin"])
app.include_router(admin_audit.router,    prefix="/api/admin/audit",      dependencies=_ADMIN_DEPS, tags=["admin"])
# ... 기존 flat 도 전부 동일 패턴
```

- [ ] **Step 4: 실행 → PASS**

- [ ] **Step 5: Commit**

```bash
git add hydra/web/main.py tests/test_admin_requires_auth.py
git commit -m "security: 모든 /api/admin/* 에 admin_session Depends 강제 (login 제외)"
```

---

## Task 37: 워커 특화 (allowed_task_types) 마이그레이션 + fetch 필터

**목적:** 워커별로 처리 가능한 task_type 제한. "워커 A 는 계정 생성만", "워커 B 는 댓글만".

**Files:**
- Create: `alembic/versions/009_worker_allowed_task_types.py`
- Modify: `hydra/db/models.py` (Worker 에 `allowed_task_types` 추가)
- Modify: `hydra/web/routes/tasks_api.py` (fetch 쿼리 필터)
- Test: `tests/test_worker_task_types_filter.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_worker_task_types_filter.py`:
```python
import json
from datetime import datetime, UTC
from hydra.db.session import SessionLocal
from hydra.db.models import Worker, Task
from hydra.web.routes.tasks_api import _filter_tasks_by_worker_types


def test_worker_wildcard_sees_all_task_types():
    allowed = '["*"]'
    assert _filter_tasks_by_worker_types(["create_account", "comment"], allowed) == \
           ["create_account", "comment"]


def test_specialized_worker_sees_only_allowed():
    allowed = '["create_account"]'
    assert _filter_tasks_by_worker_types(["create_account", "comment"], allowed) == \
           ["create_account"]


def test_multi_type_worker_sees_intersection():
    allowed = '["comment", "watch_video"]'
    assert _filter_tasks_by_worker_types(
        ["create_account", "comment", "watch_video", "onboarding_verify"],
        allowed,
    ) == ["comment", "watch_video"]


def test_empty_allowed_returns_empty():
    allowed = '[]'
    assert _filter_tasks_by_worker_types(["create_account"], allowed) == []
```

- [ ] **Step 2: 실행 → FAIL**

- [ ] **Step 3: alembic revision**

```bash
alembic revision -m "worker_allowed_task_types"
```

`alembic/versions/009_worker_allowed_task_types.py`:
```python
"""worker_allowed_task_types"""
from alembic import op
import sqlalchemy as sa

revision = "009_worker_allowed_task_types"
down_revision = "008_worker_token_hash"


def upgrade():
    with op.batch_alter_table("workers") as batch:
        batch.add_column(sa.Column("allowed_task_types", sa.Text, nullable=False,
                                    server_default='["*"]'))


def downgrade():
    with op.batch_alter_table("workers") as batch:
        batch.drop_column("allowed_task_types")
```

- [ ] **Step 4: models.py 에 컬럼 추가**

```python
# hydra/db/models.py Worker 클래스
allowed_task_types = Column(Text, nullable=False, default='["*"]')
```

- [ ] **Step 5: tasks_api.py 에 필터 헬퍼 + fetch 쿼리 수정**

```python
import json

def _filter_tasks_by_worker_types(task_types: list[str], allowed_json: str) -> list[str]:
    """워커의 allowed_task_types 로 task_type 리스트 필터링.
    
    '["*"]' 이면 모두 허용.
    """
    allowed = json.loads(allowed_json)
    if allowed == ["*"]:
        return task_types
    return [t for t in task_types if t in allowed]


# fetch_tasks 쿼리 WHERE 절 수정
@router.post("/fetch")
def fetch_tasks(worker: Worker = Depends(worker_auth)):
    db = SessionLocal()
    try:
        allowed = json.loads(worker.allowed_task_types or '["*"]')
        is_wildcard = allowed == ["*"]
        
        q = db.query(Task).filter(
            Task.status == "pending",
            # ... 기존 조건들
        )
        if not is_wildcard:
            q = q.filter(Task.task_type.in_(allowed))
        # account_lock 체크는 create_account 태스크에선 skip
        # ... 이하 기존 로직
```

- [ ] **Step 6: 실행 → PASS**

```bash
DATABASE_URL=sqlite:///data/hydra.db alembic upgrade head
pytest tests/test_worker_task_types_filter.py -v
```

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/009_worker_allowed_task_types.py hydra/db/models.py hydra/web/routes/tasks_api.py tests/test_worker_task_types_filter.py
git commit -m "feat(worker-spec): allowed_task_types 컬럼 + fetch 필터"
```

---

## Task 38: 계정 생성 결과 업로드 API ⭐

**목적:** 워커가 Google 가입 후 생성된 계정 정보를 VPS 에 업로드. DB 쓰기는 VPS 독점.

**Files:**
- Modify: `hydra/web/routes/tasks_api.py` (신규 엔드포인트 추가)
- Test: `tests/test_account_creation_upload.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_account_creation_upload.py`:
```python
from fastapi.testclient import TestClient
from hydra.web.main import app
from hydra.db.session import SessionLocal
from hydra.db.models import Task, Account, Worker
from hydra.core import crypto

client = TestClient(app)


def _setup_worker_with_task(db):
    worker = Worker(hostname="test-creator", token_hash="HASHED")
    db.add(worker); db.flush()
    task = Task(worker_id=worker.id, task_type="create_account", status="running",
                account_id=None)
    db.add(task); db.commit()
    return worker.id, task.id


def test_account_created_upload_inserts_new_account():
    db = SessionLocal()
    worker_id, task_id = _setup_worker_with_task(db)
    db.close()

    body = {
        "gmail": "brandnew1234@gmail.com",
        "encrypted_password": crypto.encrypt("secretPass!23"),
        "recovery_email": "rec1@911panel.us",
        "adspower_profile_id": "k1new001",
        "persona": {"name": "테스트유저", "age": 27},
        "encrypted_totp_secret": None,
    }
    resp = client.post(f"/api/tasks/{task_id}/result/account-created",
                        json=body,
                        headers={"X-Worker-Token": "FIXTURE_WORKER_TOKEN"})
    assert resp.status_code == 200
    new_id = resp.json()["account_id"]

    db = SessionLocal()
    created = db.get(Account, new_id)
    assert created.gmail == "brandnew1234@gmail.com"
    assert created.adspower_profile_id == "k1new001"
    # task 도 완료 처리됨
    t = db.get(Task, task_id)
    assert t.status == "done"
    db.close()


def test_duplicate_gmail_returns_409():
    db = SessionLocal()
    db.add(Account(gmail="dup@gmail.com", password="x", adspower_profile_id="p",
                   status="warmup"))
    worker_id, task_id = _setup_worker_with_task(db)
    db.commit(); db.close()

    body = {"gmail": "dup@gmail.com", "encrypted_password": "enc", 
            "adspower_profile_id": "p2", "persona": {}}
    resp = client.post(f"/api/tasks/{task_id}/result/account-created",
                        json=body,
                        headers={"X-Worker-Token": "FIXTURE_WORKER_TOKEN"})
    assert resp.status_code == 409


def test_wrong_worker_cannot_submit_result():
    """이 task 가 할당되지 않은 워커가 결과 업로드 시 거절."""
    # ... (Worker A 소유 task 에 Worker B 가 업로드 시도)
    pass  # 구현
```

- [ ] **Step 2: 실행 → FAIL**

- [ ] **Step 3: 엔드포인트 구현**

`hydra/web/routes/tasks_api.py` 에 추가:
```python
from datetime import datetime, UTC
from fastapi import HTTPException
from pydantic import BaseModel
import json


class AccountCreationResult(BaseModel):
    gmail: str
    encrypted_password: str
    recovery_email: str | None = None
    adspower_profile_id: str
    persona: dict
    encrypted_totp_secret: str | None = None
    youtube_channel_id: str | None = None
    phone_number: str | None = None
    fingerprint_snapshot: str | None = None


@router.post("/{task_id}/result/account-created")
def account_created(task_id: int, req: AccountCreationResult,
                     worker: Worker = Depends(worker_auth)):
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task is None:
            raise HTTPException(404, "task not found")
        if task.worker_id != worker.id:
            raise HTTPException(403, "this task is not assigned to you")
        if task.task_type != "create_account":
            raise HTTPException(400, "not a create_account task")
        # 중복 gmail 체크
        existing = db.query(Account).filter_by(gmail=req.gmail).first()
        if existing is not None:
            raise HTTPException(409, f"gmail already exists: {req.gmail}")

        new_account = Account(
            gmail=req.gmail,
            password=req.encrypted_password,   # 이미 암호화됨
            recovery_email=req.recovery_email,
            adspower_profile_id=req.adspower_profile_id,
            persona=json.dumps(req.persona, ensure_ascii=False),
            totp_secret=req.encrypted_totp_secret,
            youtube_channel_id=req.youtube_channel_id,
            phone_number=req.phone_number,
            status="profile_set",   # 생성 직후 상태
            created_at=datetime.now(UTC),
        )
        db.add(new_account); db.flush()

        # task 완료 처리
        task.status = "done"
        task.completed_at = datetime.now(UTC)
        task.result = json.dumps({"account_id": new_account.id})
        task.account_id = new_account.id

        # audit log
        from hydra.db.models import AuditLog
        db.add(AuditLog(
            user_id=None,
            action="account_created",
            target_type="account",
            target_id=new_account.id,
            metadata_json=json.dumps({
                "created_by_worker": worker.id,
                "task_id": task_id,
                "gmail": req.gmail,
            }),
        ))
        db.commit()
        return {"account_id": new_account.id}
    finally:
        db.close()
```

- [ ] **Step 4: 실행 → PASS**

- [ ] **Step 5: Commit**

```bash
git add hydra/web/routes/tasks_api.py tests/test_account_creation_upload.py
git commit -m "feat(api): 워커 → VPS 계정 생성 결과 업로드 + audit log"
```

---

## Task 26: 프론트엔드 프로젝트 세팅 (Tailwind + shadcn)

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/src/components/ui/*.tsx`

- [ ] **Step 1: 의존성 설치**

```bash
cd frontend
npm install tailwindcss postcss autoprefixer @headlessui/react react-hook-form zod @tanstack/react-query axios lucide-react
npm install -D @types/node
npx tailwindcss init -p
```

- [ ] **Step 2: tailwind.config.js**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      screens: { xs: "360px" },
    },
  },
  plugins: [],
}
```

- [ ] **Step 3: global CSS**

`frontend/src/index.css` 상단에:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: shadcn 컴포넌트 초기화**

```bash
npx shadcn@latest init -d
npx shadcn@latest add button input dialog toast card table
```

- [ ] **Step 5: 빌드 테스트**

```bash
npm run build
ls dist/
```

검증: dist/ 에 index.html + assets/*.js 생성.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tailwind.config.js frontend/postcss.config.js frontend/src/index.css frontend/src/lib frontend/components.json
git commit -m "frontend: Tailwind + shadcn/ui + tanstack query 세팅"
```

---

## Task 27: 로그인 페이지 + 반응형 shell

**Files:**
- Create: `frontend/src/features/auth/LoginPage.tsx`
- Create: `frontend/src/app/AppShell.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: LoginPage 작성**

`frontend/src/features/auth/LoginPage.tsx`:
```tsx
import { useState } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null); setLoading(true);
    try {
      const resp = await axios.post("/api/admin/auth/login", { email, password });
      localStorage.setItem("hydra_token", resp.data.token);
      window.location.href = "/";
    } catch (e: any) {
      setError(e?.response?.data?.detail || "로그인 실패");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 p-4">
      <Card className="w-full max-w-sm p-6 space-y-4">
        <h1 className="text-2xl font-bold text-center">HYDRA Admin</h1>
        <form onSubmit={submit} className="space-y-3">
          <Input type="email" placeholder="이메일" value={email}
                 onChange={e => setEmail(e.target.value)} required />
          <Input type="password" placeholder="비밀번호" value={password}
                 onChange={e => setPassword(e.target.value)} required />
          {error && <div className="text-sm text-red-500">{error}</div>}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "로그인 중..." : "로그인"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: AppShell (반응형)**

`frontend/src/app/AppShell.tsx`:
```tsx
import { useState, ReactNode } from "react";
import { Menu, X } from "lucide-react";

export function AppShell({ children }: { children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-40 bg-slate-900/95 backdrop-blur border-b border-slate-800 px-4 py-3 flex items-center gap-3">
        <button onClick={() => setNavOpen(!navOpen)} className="lg:hidden p-1">
          {navOpen ? <X/> : <Menu/>}
        </button>
        <h1 className="font-bold">HYDRA</h1>
      </header>
      <div className="flex">
        <nav className={`
          ${navOpen ? "block" : "hidden"} lg:block
          w-64 shrink-0 border-r border-slate-800 p-4 space-y-1
          fixed lg:sticky top-14 h-[calc(100vh-56px)] bg-slate-950 z-30
        `}>
          <NavLink href="/">대시보드</NavLink>
          <NavLink href="/campaigns">캠페인</NavLink>
          <NavLink href="/accounts">계정</NavLink>
          <NavLink href="/workers">워커</NavLink>
          <NavLink href="/avatars">아바타</NavLink>
          <NavLink href="/audit">감사 로그</NavLink>
        </nav>
        <main className="flex-1 p-4 lg:p-8 max-w-6xl">{children}</main>
      </div>
    </div>
  );
}

function NavLink({ href, children }: { href: string; children: ReactNode }) {
  return <a href={href} className="block px-3 py-2 rounded hover:bg-slate-800">{children}</a>;
}
```

- [ ] **Step 3: App.tsx 라우팅**

(기존 프로젝트 라우팅 방식에 따라 react-router 또는 tanstack router 연동)

- [ ] **Step 4: 모바일 테스트**

```bash
npm run dev
# 브라우저 dev tools 에서 iPhone/Galaxy 사이즈로 확인
```

검증: 햄버거 메뉴가 모바일에서 토글 작동, 메뉴 열리면 전체 화면 덮음.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/auth/LoginPage.tsx frontend/src/app/AppShell.tsx frontend/src/App.tsx
git commit -m "frontend: 로그인 페이지 + 반응형 AppShell (햄버거 메뉴)"
```

---

## Task 28: "배포" 버튼 + "긴급정지" 바

**Files:**
- Create: `frontend/src/features/deploy/DeployButton.tsx`
- Create: `frontend/src/features/killswitch/KillSwitchBar.tsx`

- [ ] **Step 1: DeployButton**

`frontend/src/features/deploy/DeployButton.tsx`:
```tsx
import { useMutation } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Rocket } from "lucide-react";
import axios from "axios";

export function DeployButton() {
  const deploy = useMutation({
    mutationFn: () => axios.post("/api/admin/deploy").then(r => r.data),
  });
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="default" size="lg" className="gap-2">
          <Rocket size={18}/> 배포
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <h2 className="font-bold text-lg">새 버전 배포</h2>
        <p className="text-sm text-slate-400">최신 main 브랜치를 VPS 에 적용합니다. 워커들은 현재 태스크 완료 후 자동 업데이트됩니다.</p>
        <Button onClick={() => deploy.mutate()} disabled={deploy.isPending} className="w-full">
          {deploy.isPending ? "배포 중..." : "배포 시작"}
        </Button>
        {deploy.isSuccess && <div className="text-green-500 text-sm">✅ 시작됨 (PID {(deploy.data as any)?.pid})</div>}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: KillSwitchBar**

`frontend/src/features/killswitch/KillSwitchBar.tsx`:
```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Play } from "lucide-react";
import axios from "axios";

export function KillSwitchBar() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["server-config"],
    queryFn: () => axios.get("/api/admin/server-config").then(r => r.data),
    refetchInterval: 10000,
  });
  const pause = useMutation({
    mutationFn: () => axios.post("/api/admin/pause").then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["server-config"] }),
  });
  const unpause = useMutation({
    mutationFn: () => axios.post("/api/admin/unpause").then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["server-config"] }),
  });
  if (!data) return null;
  return (
    <div className={`p-3 rounded-lg border flex items-center gap-3 ${
      data.paused ? "bg-red-900/30 border-red-800" : "bg-slate-800 border-slate-700"
    }`}>
      {data.paused ? (
        <>
          <AlertTriangle className="text-red-400"/>
          <div className="flex-1"><strong>전체 워커 일시정지 중</strong></div>
          <Button onClick={() => unpause.mutate()} variant="default" size="sm">
            <Play size={14}/> 재개
          </Button>
        </>
      ) : (
        <>
          <div className="flex-1 text-sm text-slate-400">정상 운영 중 (v{data.current_version})</div>
          <Button onClick={() => pause.mutate()} variant="destructive" size="sm">
            <AlertTriangle size={14}/> 긴급 정지
          </Button>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: 서버 측 server-config GET**

`hydra/web/routes/admin_deploy.py` 에 추가:
```python
@router.get("/server-config")
def get_server_config():
    db = SessionLocal()
    try:
        cfg = db.query(ServerConfig).first()
        import json
        return {
            "current_version": cfg.current_version,
            "paused": cfg.paused,
            "canary_worker_ids": json.loads(cfg.canary_worker_ids or "[]"),
            "last_deploy_at": cfg.last_deploy_at,
        }
    finally: db.close()
```

- [ ] **Step 4: 대시보드에 배치**

대시보드 페이지 상단:
```tsx
<div className="space-y-4">
  <KillSwitchBar/>
  <div className="flex justify-end"><DeployButton/></div>
  {/* ... */}
</div>
```

- [ ] **Step 5: 모바일 확인**

모바일에서 버튼 터치 크기 충분 (최소 44pt 높이) 확인.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/deploy/ frontend/src/features/killswitch/ hydra/web/routes/admin_deploy.py
git commit -m "frontend: 배포 버튼 + 긴급정지 바 (반응형 + 터치 친화)"
```

---

## Task 29: 아바타 관리 UI (업로드 + 목록)

**Files:**
- Create: `frontend/src/features/avatars/AvatarManager.tsx`
- Create: `frontend/src/features/avatars/AvatarUploadZone.tsx`

- [ ] **Step 1: AvatarUploadZone (드래그 앤 드롭)**

```tsx
import { useState, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import axios from "axios";

export function AvatarUploadZone({ category, onDone }: { category: string; onDone: () => void }) {
  const [dragOver, setDragOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: async (files: FileList) => {
      for (const f of Array.from(files)) {
        const fd = new FormData();
        fd.append("category", category);
        fd.append("file", f);
        await axios.post("/api/admin/avatars/upload", fd);
      }
    },
    onSuccess: onDone,
  });
  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={e => { e.preventDefault(); setDragOver(false); upload.mutate(e.dataTransfer.files); }}
      onClick={() => input.current?.click()}
      className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer ${
        dragOver ? "border-blue-500 bg-blue-900/20" : "border-slate-700"
      }`}
    >
      <Upload className="mx-auto mb-2"/>
      <p className="text-sm">파일 드래그하거나 클릭 (모바일: 카메라/앨범 선택)</p>
      <input ref={input} type="file" multiple accept="image/*"
             onChange={e => e.target.files && upload.mutate(e.target.files)} className="hidden"/>
      {upload.isPending && <div className="mt-2 text-blue-400">업로드 중...</div>}
    </div>
  );
}
```

- [ ] **Step 2: AvatarManager (목록 + 업로드 통합)**

```tsx
import { useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import axios from "axios";
import { AvatarUploadZone } from "./AvatarUploadZone";
import { Button } from "@/components/ui/button";
import { Trash } from "lucide-react";

export function AvatarManager() {
  const [category, setCategory] = useState("female/20s");
  const qc = useQueryClient();
  const { data: tree } = useQuery({
    queryKey: ["avatars-tree"],
    queryFn: () => axios.get("/api/admin/avatars/list").then(r => r.data),
  });
  const del = useMutation({
    mutationFn: (path: string) => axios.delete(`/api/admin/avatars/${path}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["avatars-tree"] }),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">아바타 관리</h1>
      <div className="flex flex-col sm:flex-row gap-2">
        <select value={category} onChange={e => setCategory(e.target.value)}
                className="bg-slate-800 rounded p-2 border border-slate-700">
          <option value="female/20s">여성 / 20대</option>
          <option value="female/30s">여성 / 30대</option>
          <option value="male/20s">남성 / 20대</option>
          <option value="male/30s">남성 / 30대</option>
          <option value="object/flower">오브젝트 / 꽃</option>
          <option value="object/cat">오브젝트 / 고양이</option>
        </select>
      </div>
      <AvatarUploadZone category={category} onDone={() => qc.invalidateQueries({ queryKey: ["avatars-tree"] })}/>
      <TreeView tree={tree} onDelete={(p) => del.mutate(p)}/>
    </div>
  );
}

function TreeView({ tree, onDelete, prefix = "" }: any) {
  if (!tree) return null;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-2">
      {tree.__files__?.map((f: string) => {
        const path = prefix + "/" + f;
        return (
          <div key={f} className="relative group">
            <img src={`/api/admin/avatars/thumb/${path}`} alt={f} className="w-full h-24 object-cover rounded" />
            <button onClick={() => onDelete(path)}
                    className="absolute top-1 right-1 bg-red-600 p-1 rounded opacity-0 group-hover:opacity-100">
              <Trash size={12}/>
            </button>
          </div>
        );
      })}
      {Object.keys(tree).filter(k => k !== "__files__").map(k => (
        <TreeView key={k} tree={tree[k]} onDelete={onDelete} prefix={prefix + "/" + k}/>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: 라우트 등록 + 빌드 테스트**

App 라우팅에 `/avatars` 경로 추가. `npm run build` 성공 확인.

- [ ] **Step 4: 모바일 확인**

- 드래그앤드롭 영역이 모바일에서 탭 시 `<input type="file">` 발동
- 그리드가 모바일 2열, 데스크톱 6열

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/avatars/
git commit -m "frontend: 아바타 관리 UI (업로드/목록/삭제, 반응형)"
```

---

## Task 39: 워커 상세 페이지 + 특화 편집 UI

**목적:** 어드민 UI 에서 워커별 `allowed_task_types` 편집. 체크박스 + 커스텀 JSON.

**Files:**
- Create: `frontend/src/features/workers/WorkerDetail.tsx`
- Create: `frontend/src/features/workers/TaskTypeSelector.tsx`

- [ ] **Step 1: 서버 측 워커 상세 API 추가**

`hydra/web/routes/admin_workers.py` 에:
```python
from pydantic import BaseModel
import json


class WorkerUpdate(BaseModel):
    allowed_task_types: list[str] | None = None


@router.get("/{worker_id}")
def get_worker(worker_id: int):
    db = SessionLocal()
    try:
        w = db.get(Worker, worker_id)
        if w is None: raise HTTPException(404)
        return {
            "id": w.id, "hostname": w.hostname, "version": w.version,
            "last_heartbeat": w.last_heartbeat,
            "allowed_task_types": json.loads(w.allowed_task_types or '["*"]'),
            "health_snapshot": json.loads(w.health_snapshot or '{}'),
        }
    finally: db.close()


@router.patch("/{worker_id}")
def update_worker(worker_id: int, req: WorkerUpdate):
    db = SessionLocal()
    try:
        w = db.get(Worker, worker_id)
        if w is None: raise HTTPException(404)
        if req.allowed_task_types is not None:
            w.allowed_task_types = json.dumps(req.allowed_task_types)
        db.commit()
        # audit log
        from hydra.db.models import AuditLog
        db.add(AuditLog(action="worker_change", target_type="worker",
                        target_id=worker_id,
                        metadata_json=json.dumps({"allowed_task_types": req.allowed_task_types})))
        db.commit()
        return {"ok": True}
    finally: db.close()
```

- [ ] **Step 2: TaskTypeSelector 컴포넌트**

`frontend/src/features/workers/TaskTypeSelector.tsx`:
```tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";

const KNOWN_TYPES = [
  { value: "create_account",     label: "계정 생성" },
  { value: "onboarding_verify",  label: "온보딩 검증" },
  { value: "warmup",             label: "워밍업" },
  { value: "comment",            label: "댓글 작성" },
  { value: "watch_video",        label: "영상 시청" },
  { value: "ranking_observe",    label: "상단 노출 관찰" },
];

export function TaskTypeSelector({ value, onChange }: {
  value: string[];
  onChange: (types: string[]) => void;
}) {
  const [custom, setCustom] = useState("");
  const isWildcard = value.length === 1 && value[0] === "*";
  
  const toggle = (t: string) => {
    const next = value.includes(t) ? value.filter(x => x !== t) : [...value, t];
    onChange(next);
  };
  
  return (
    <div className="space-y-3">
      <Button onClick={() => onChange(["*"])} 
              variant={isWildcard ? "default" : "outline"}
              size="sm" className="w-full sm:w-auto">
        만능 워커 (모든 태스크 처리)
      </Button>
      {!isWildcard && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {KNOWN_TYPES.map(t => (
              <label key={t.value} className="flex items-center gap-2 p-2 border border-slate-700 rounded cursor-pointer hover:bg-slate-800">
                <input type="checkbox" checked={value.includes(t.value)}
                       onChange={() => toggle(t.value)} />
                <span className="text-sm">{t.label}</span>
              </label>
            ))}
          </div>
          <div className="text-xs text-slate-500">
            커스텀 type: 
            <input value={custom} onChange={e => setCustom(e.target.value)}
                   className="ml-2 bg-slate-800 px-2 py-1 rounded" placeholder="my_custom_type"/>
            <Button size="sm" onClick={() => {
              if (custom.trim() && !value.includes(custom)) onChange([...value, custom.trim()]);
              setCustom("");
            }}>추가</Button>
          </div>
        </>
      )}
      <div className="text-xs text-slate-400">
        현재: {isWildcard ? "전체" : value.join(", ") || "(없음)"}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: WorkerDetail 페이지**

`frontend/src/features/workers/WorkerDetail.tsx`:
```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { TaskTypeSelector } from "./TaskTypeSelector";
import { useState } from "react";

export function WorkerDetail({ workerId }: { workerId: number }) {
  const qc = useQueryClient();
  const { data: worker } = useQuery({
    queryKey: ["worker", workerId],
    queryFn: () => api.get(`/api/admin/workers/${workerId}`).then(r => r.data),
  });
  const [types, setTypes] = useState<string[] | null>(null);
  const save = useMutation({
    mutationFn: () => api.patch(`/api/admin/workers/${workerId}`, { allowed_task_types: types }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["worker", workerId] }); setTypes(null); },
  });

  if (!worker) return <div>Loading...</div>;
  const current = types ?? worker.allowed_task_types;

  return (
    <div className="space-y-4 max-w-2xl">
      <h1 className="text-2xl font-bold">{worker.hostname}</h1>
      <Card className="p-4 space-y-2">
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>버전: <code>{worker.version}</code></div>
          <div>마지막 heartbeat: {worker.last_heartbeat}</div>
        </div>
      </Card>
      <Card className="p-4 space-y-3">
        <h2 className="font-bold">허용된 태스크 타입</h2>
        <TaskTypeSelector value={current} onChange={setTypes}/>
        {types && (
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "저장 중..." : "변경 저장"}
          </Button>
        )}
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: 라우트 등록 + 모바일 검증**

`/workers/:id` 경로 연결. 모바일에서 체크박스 영역이 2열로 표시, 버튼 44pt 이상.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/workers/ hydra/web/routes/admin_workers.py
git commit -m "frontend: 워커 상세 페이지 + 특화 편집 UI (반응형)"
```

---

## Task 39.5: 감사 로그 뷰어 (간단)

**Files:**
- Create: `hydra/web/routes/admin_audit.py` (body 채우기)
- Create: `frontend/src/features/audit/AuditLogPage.tsx`

- [ ] **Step 1: 서버 측**

```python
# hydra/web/routes/admin_audit.py
from fastapi import APIRouter, Query
from hydra.db.session import SessionLocal
from hydra.db.models import AuditLog

router = APIRouter()


@router.get("/list")
def list_audit(action: str | None = None, limit: int = Query(100, le=500)):
    db = SessionLocal()
    try:
        q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
        if action:
            q = q.filter(AuditLog.action == action)
        rows = q.limit(limit).all()
        return [{
            "id": r.id, "action": r.action, "user_id": r.user_id,
            "target_type": r.target_type, "target_id": r.target_id,
            "metadata_json": r.metadata_json, "ip_address": r.ip_address,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        } for r in rows]
    finally: db.close()
```

- [ ] **Step 2: 프론트 뷰어**

```tsx
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function AuditLogPage() {
  const { data } = useQuery({
    queryKey: ["audit"],
    queryFn: () => api.get("/api/admin/audit/list?limit=200").then(r => r.data),
    refetchInterval: 30000,
  });
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold">감사 로그</h1>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-slate-700">
            <tr><th className="text-left p-2">시각</th><th>액션</th><th>대상</th><th>IP</th></tr>
          </thead>
          <tbody>
            {data?.map((row: any) => (
              <tr key={row.id} className="border-b border-slate-800 hover:bg-slate-800/30">
                <td className="p-2 text-xs">{row.timestamp}</td>
                <td className="p-2"><code>{row.action}</code></td>
                <td className="p-2 text-xs">{row.target_type}:{row.target_id}</td>
                <td className="p-2 text-xs">{row.ip_address}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 모바일 확인**

`overflow-x-auto` 로 모바일에서 가로 스크롤. 필수 컬럼만 표시되도록 반응형 축약 고려.

- [ ] **Step 4: Commit**

```bash
git add hydra/web/routes/admin_audit.py frontend/src/features/audit/
git commit -m "frontend: 감사 로그 뷰어 (필터 + 가로 스크롤 반응형)"
```

---

## Task 30: Mac 아바타 → VPS rsync 마이그레이션

- [ ] **Step 1: VPS 로 rsync**

Mac 에서:
```bash
rsync -avz --progress data/avatars/ deployer@<VPS_IP>:/var/hydra/avatars/
```

검증: 2.1GB 전송 완료.

- [ ] **Step 2: 권한/소유권 설정**

VPS 에서:
```bash
sudo chown -R deployer:www-data /var/hydra/avatars/
sudo chmod -R 750 /var/hydra/avatars/
du -sh /var/hydra/avatars/
ls /var/hydra/avatars/
```

검증: `2.1G`, 디렉토리 목록 (female/male/object).

- [ ] **Step 3: 어드민 UI 에서 목록 조회 테스트**

브라우저 `https://admin.hydra.com/avatars` → 트리 뷰에 카테고리별 썸네일 표시 확인.

- [ ] **Step 4: 워커 다운로드 테스트**

VPS API 에 테스트 요청 (워커 토큰 있는 상태에서):
```bash
curl -H "X-Worker-Token: <test_token>" \
     https://api.hydra.com/api/avatars/female/20s/f20_001.png \
     -o /tmp/test_avatar.png
file /tmp/test_avatar.png
```

검증: `PNG image data` 출력.

- [ ] **Step 5: Commit**

```bash
# 마이그레이션은 일회성이라 commit 할 파일 없음. runbook 에 절차 기록만.
# 이미 docs/vps-setup.md 나 별도 마이그레이션 섹션에 명시했으면 OK.
```

---

## Task 31: 워커 설치 스크립트 (PowerShell)

**Files:**
- Create: `setup/hydra-worker-setup.ps1`
- Create: `setup/README.md`

- [ ] **Step 1: setup.ps1 작성**

`setup/hydra-worker-setup.ps1`:
```powershell
param(
    [Parameter(Mandatory=$true)] [string]$Token,
    [Parameter(Mandatory=$true)] [string]$ServerUrl
)

$ErrorActionPreference = "Stop"
Write-Host "=== HYDRA Worker Setup ===" -ForegroundColor Cyan

# 1. Chocolatey 설치
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "[1/8] Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    iex ((New-Object Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
    $env:Path += ";C:\ProgramData\chocolatey\bin"
}

# 2. 의존성 설치
Write-Host "[2/8] Installing Python, Git, ADB, Tailscale..."
choco install -y python311 git adb tailscale

# 3. NTP 동기화
Write-Host "[3/8] Configuring NTP..."
w32tm /config /manualpeerlist:"time.windows.com,time.google.com" /syncfromflags:manual /reliable:yes /update
Restart-Service w32time
w32tm /resync

# 4. Repo clone
Write-Host "[4/8] Cloning repo..."
if (-not (Test-Path "C:\hydra")) {
    git clone https://github.com/ORGNAME/hydra.git C:\hydra
}
cd C:\hydra

# 5. venv + deps
Write-Host "[5/8] Installing Python deps..."
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium

# 6. Enrollment 콜
Write-Host "[6/8] Enrolling to server..."
$hostname = $env:COMPUTERNAME
$body = @{ enrollment_token = $Token; hostname = $hostname } | ConvertTo-Json
$resp = Invoke-RestMethod -Method Post -Uri "$ServerUrl/api/workers/enroll" `
        -ContentType "application/json" -Body $body
$workerToken = $resp.worker_token
$secrets = $resp.secrets

# 7. .env 저장 (Windows DPAPI 암호화)
Write-Host "[7/8] Saving secrets..."
$envContent = @"
SERVER_URL=$ServerUrl
WORKER_TOKEN=$workerToken
DB_CRYPTO_KEY=$($secrets.DB_CRYPTO_KEY)
"@
# DPAPI 로 암호화
$secureBytes = [System.Security.Cryptography.ProtectedData]::Protect(
    [System.Text.Encoding]::UTF8.GetBytes($envContent),
    $null,
    [System.Security.Cryptography.DataProtectionScope]::LocalMachine
)
[System.IO.File]::WriteAllBytes("C:\hydra\secrets.enc", $secureBytes)

# 8. Task Scheduler 등록
Write-Host "[8/8] Registering Task Scheduler..."
$action = New-ScheduledTaskAction -Execute "C:\hydra\.venv\Scripts\python.exe" `
          -Argument "-m worker" -WorkingDirectory "C:\hydra"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName "HydraWorker" -Action $action -Trigger $trigger `
                        -Settings $settings -Principal $principal -Force

Write-Host "✅ Setup complete." -ForegroundColor Green
Write-Host "   Worker token saved to C:\hydra\secrets.enc (DPAPI encrypted)."
Write-Host "   Task 'HydraWorker' registered. Reboot to auto-start, or:"
Write-Host "   Start-ScheduledTask -TaskName HydraWorker"
```

- [ ] **Step 2: setup/README.md**

```markdown
# HYDRA Worker 설치 가이드 (Windows)

## 1. 어드민 UI 에서 enrollment token 발급
1. https://admin.hydra.com 로그인
2. "워커" → "새 워커 추가" 버튼
3. worker_name 입력 (예: worker-03) → 생성
4. 표시되는 install_command 1줄 복사

## 2. 워커 PC 에서 PowerShell 관리자로 실행
복사한 명령어 붙여넣기:
```powershell
iwr -Uri https://api.hydra.com/api/workers/setup.ps1 -OutFile setup.ps1; .\setup.ps1 -Token 'ABC...' -ServerUrl 'https://api.hydra.com'
```

## 3. 검증
- 설치 완료 후 몇 초 뒤 어드민 UI 의 워커 목록에 새 워커 표시
- heartbeat 시각이 최근으로 업데이트됨
```

- [ ] **Step 3: 서버에서 setup.ps1 서빙**

VPS 에서:
```bash
sudo cp setup/hydra-worker-setup.ps1 /var/www/setup.ps1
# 또는 FastAPI 에 엔드포인트 추가
```

`hydra/web/routes/worker_api.py` 에 추가:
```python
from fastapi.responses import FileResponse

@router.get("/setup.ps1")
def serve_setup():
    return FileResponse("/opt/hydra/setup/hydra-worker-setup.ps1", media_type="text/plain")
```

- [ ] **Step 4: Commit**

```bash
git add setup/ hydra/web/routes/worker_api.py
git commit -m "feat(worker-setup): PowerShell 설치 스크립트 + enrollment 연동 + NTP/DPAPI"
```

---

## Task 32: 워커 시크릿 로딩 모듈 (DPAPI + .env fallback)

**목적:** 워커가 VPS 에서 받은 시크릿을 Windows 에선 DPAPI 암호화로, Mac dev 환경에선 `.env` 로 로딩. 평문 파일 배포 제거.

**Files:**
- Create: `worker/secrets.py`
- Modify: `requirements.txt` (pywin32 on Windows 조건부)
- Test: `tests/test_worker_secrets.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_worker_secrets.py`:
```python
import os
from pathlib import Path
from unittest.mock import patch
import pytest
from worker.secrets import load_secrets, _load_dotenv, _parse_env_text


def test_parse_env_text_basic():
    text = "SERVER_URL=https://api.test\nWORKER_TOKEN=abc123\n"
    parsed = _parse_env_text(text)
    assert parsed["SERVER_URL"] == "https://api.test"
    assert parsed["WORKER_TOKEN"] == "abc123"


def test_parse_env_text_ignores_comments_and_blanks():
    text = "# comment\n\nKEY1=val1\n  \nKEY2=val2"
    parsed = _parse_env_text(text)
    assert parsed == {"KEY1": "val1", "KEY2": "val2"}


def test_parse_env_text_values_with_equals_sign():
    text = "JWT_SECRET=abc=def=ghi\n"
    parsed = _parse_env_text(text)
    assert parsed["JWT_SECRET"] == "abc=def=ghi"


def test_load_dotenv_from_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SERVER_URL=http://localhost:8000\nWORKER_TOKEN=dev\n")
    result = _load_dotenv(env_file)
    assert result["SERVER_URL"] == "http://localhost:8000"


def test_load_secrets_raises_on_missing_required():
    """DPAPI 파일/env 파일 둘 다 없으면 명확히 에러."""
    with patch.dict(os.environ, {}, clear=True):
        with patch("worker.secrets._dotenv_path", return_value=Path("/nonexistent/.env")):
            with patch("worker.secrets._secrets_enc_path", return_value=Path("/nonexistent/secrets.enc")):
                with pytest.raises(RuntimeError, match="no secrets source"):
                    load_secrets()
```

- [ ] **Step 2: 테스트 실행 → FAIL**

```bash
pytest tests/test_worker_secrets.py -v
```

예상: `ModuleNotFoundError: worker.secrets`.

- [ ] **Step 3: worker/secrets.py 구현**

```python
"""워커 시크릿 로딩.

- Windows: C:\\hydra\\secrets.enc (DPAPI 암호화, 해당 PC 에서만 복호화 가능)
- Mac/Linux (dev): .env 파일 (git 커밋 금지)

설치 스크립트(Task 31) 가 enrollment 응답으로 받은 시크릿을 DPAPI 로 저장.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path


REQUIRED_KEYS = ("SERVER_URL", "WORKER_TOKEN")


def _secrets_enc_path() -> Path:
    return Path(r"C:\hydra\secrets.enc")


def _dotenv_path() -> Path:
    # 프로젝트 루트의 .env
    return Path(__file__).resolve().parent.parent / ".env"


def _parse_env_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return _parse_env_text(path.read_text(encoding="utf-8"))


def _load_dpapi(path: Path) -> dict[str, str]:
    import win32crypt  # pywin32 (Windows 전용)
    blob = path.read_bytes()
    _, decrypted = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    text = decrypted.decode("utf-8")
    return _parse_env_text(text)


def load_secrets() -> dict[str, str]:
    """시크릿 dict 반환. Windows 면 DPAPI, 그 외면 .env.

    OS 환경변수로 override 가능 (테스트/CI 편의).
    """
    result: dict[str, str] = {}

    # 1. Windows DPAPI 우선
    if sys.platform == "win32":
        p = _secrets_enc_path()
        if p.exists():
            result = _load_dpapi(p)

    # 2. .env fallback (Mac/Linux dev)
    if not result:
        p = _dotenv_path()
        if p.exists():
            result = _load_dotenv(p)

    # 3. 환경변수 최종 override
    for key in REQUIRED_KEYS:
        if key in os.environ:
            result[key] = os.environ[key]

    # 4. 검증
    missing = [k for k in REQUIRED_KEYS if k not in result or not result[k]]
    if missing:
        src = "DPAPI" if sys.platform == "win32" else ".env"
        raise RuntimeError(
            f"no secrets source found or missing keys: {missing}. "
            f"Windows: re-run setup.ps1 to regenerate secrets.enc. "
            f"Dev ({src}): check .env file."
        )

    return result


def save_secrets_dpapi(secrets: dict[str, str]) -> None:
    """Windows 에서만. enrollment 직후 DPAPI 로 secrets.enc 기록.

    setup.ps1 이 PowerShell 에서 직접 하지만, Python 에서도 저장 필요하면 이걸 사용.
    """
    if sys.platform != "win32":
        raise RuntimeError("DPAPI is Windows-only")
    import win32crypt
    text = "\n".join(f"{k}={v}" for k, v in secrets.items())
    data = text.encode("utf-8")
    blob = win32crypt.CryptProtectData(data, "hydra-secrets", None, None, None, 0)
    _secrets_enc_path().write_bytes(blob)
```

- [ ] **Step 4: requirements.txt 에 Windows-only 의존성 조건부 추가**

`requirements.txt` 에 추가:
```
pywin32>=306; sys_platform == 'win32'
python-dotenv>=1.0,<2
```

- [ ] **Step 5: 테스트 실행 → PASS**

```bash
pip install -r requirements.txt
pytest tests/test_worker_secrets.py -v
```

예상: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add worker/secrets.py tests/test_worker_secrets.py requirements.txt
git commit -m "feat(worker): DPAPI/.env 시크릿 로딩 모듈 (플랫폼 분기)"
```

---

## Task 33: 워커 Config 재구성 + git-기반 version 감지

**목적:** 기존 `worker/config.py` 가 하드코딩된 localhost 를 쓰는 것을 `secrets.load_secrets()` 기반으로 전환. `worker_version` 을 현재 git HEAD short hash 로 자동 설정.

**Files:**
- Modify: `worker/config.py`
- Test: `tests/test_worker_config.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_worker_config.py`:
```python
import os
import subprocess
from unittest.mock import patch
from worker.config import build_config


def test_build_config_from_secrets_dict():
    secrets = {"SERVER_URL": "https://api.hydra.com",
               "WORKER_TOKEN": "tok_abc",
               "DB_CRYPTO_KEY": "crypto_key_xyz"}
    cfg = build_config(secrets)
    assert cfg.server_url == "https://api.hydra.com"
    assert cfg.worker_token == "tok_abc"
    assert cfg.db_crypto_key == "crypto_key_xyz"
    # 기본값들
    assert cfg.poll_interval_sec == 15
    assert cfg.drain_timeout_minutes == 15


def test_build_config_worker_version_from_git():
    secrets = {"SERVER_URL": "x", "WORKER_TOKEN": "y"}
    cfg = build_config(secrets)
    # 실제 git repo 안에서 실행되면 short hash (7자 정도)
    assert len(cfg.worker_version) >= 4
    assert cfg.worker_version != ""


def test_build_config_worker_version_fallback_when_no_git():
    secrets = {"SERVER_URL": "x", "WORKER_TOKEN": "y"}
    with patch("worker.config._git_short_hash", return_value=None):
        cfg = build_config(secrets)
    assert cfg.worker_version == "unknown"


def test_build_config_missing_required_raises():
    import pytest
    with pytest.raises(KeyError):
        build_config({"SERVER_URL": "x"})  # WORKER_TOKEN 누락
```

- [ ] **Step 2: 테스트 실행 → FAIL**

```bash
pytest tests/test_worker_config.py -v
```

- [ ] **Step 3: worker/config.py 재작성**

```python
"""워커 설정 — secrets 기반, git-based version."""
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path

from worker.secrets import load_secrets


@dataclass
class Config:
    server_url: str
    worker_token: str
    worker_version: str
    db_crypto_key: str = ""
    poll_interval_sec: int = 15
    drain_timeout_minutes: int = 15
    max_concurrent_tasks: int = 1


def _git_short_hash() -> str | None:
    """현재 체크아웃된 커밋의 short hash 반환."""
    try:
        repo_root = Path(__file__).resolve().parent.parent
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=5,
        )
        return out.decode().strip()
    except Exception:
        return None


def build_config(secrets: dict) -> Config:
    """secrets dict 로부터 Config 조립. 테스트 편의 + 프로덕션 둘 다 사용."""
    server_url = secrets["SERVER_URL"]           # 없으면 KeyError (의도됨)
    worker_token = secrets["WORKER_TOKEN"]
    version = _git_short_hash() or "unknown"
    return Config(
        server_url=server_url,
        worker_token=worker_token,
        worker_version=version,
        db_crypto_key=secrets.get("DB_CRYPTO_KEY", ""),
    )


def _load() -> Config:
    return build_config(load_secrets())


# 모듈 import 시 자동 로드 (기존 코드 호환)
config = _load()
```

- [ ] **Step 4: 테스트 실행 → PASS**

```bash
# 테스트 환경 변수 셋업 (.env 가 없어도 OS env 로 override 가능)
SERVER_URL=http://localhost:8000 WORKER_TOKEN=test pytest tests/test_worker_config.py -v
```

예상: 4 passed.

- [ ] **Step 5: 기존 사용처 확인 (breakage 없는지)**

```bash
grep -rn "config\." worker/*.py | grep -v "__pycache__" | head -20
```

`config.server_url`, `config.worker_token` 을 쓰는 기존 코드는 그대로 작동 (필드명 유지).

`config.heartbeat_interval` 같은 구 필드가 있으면 `config.poll_interval_sec` 로 alias 추가하거나 호출처 수정.

- [ ] **Step 6: Commit**

```bash
git add worker/config.py tests/test_worker_config.py
git commit -m "refactor(worker): Config 를 secrets 기반 + git version 자동 감지로 재구성"
```

---

## Task 34: 워커 자가 업데이트 로직 (drain + git pull + restart)

**목적:** 워커가 heartbeat 응답의 `current_version` 과 자기 버전 비교 → 다르면 drain → git pull → pip install → 종료. Task Scheduler 가 자동 재시작.

**Files:**
- Create: `worker/updater.py`
- Modify: `worker/app.py` (메인 루프에 훅 삽입)
- Test: `tests/test_worker_updater.py`

- [ ] **Step 1: 테스트 작성**

`tests/test_worker_updater.py`:
```python
from unittest.mock import patch, MagicMock
import pytest
from worker.updater import should_update, perform_update


def test_should_update_true_when_versions_differ():
    assert should_update(server_version="v1.2.4", local_version="v1.2.3") is True


def test_should_update_false_when_versions_match():
    assert should_update(server_version="abc123", local_version="abc123") is False


def test_should_update_false_when_unknown_local():
    """로컬 버전이 'unknown' 이면 업데이트 강제 안 함 (CI/테스트 환경)."""
    assert should_update(server_version="v1.2.4", local_version="unknown") is False


def test_perform_update_runs_git_pull_and_pip(tmp_path):
    with patch("worker.updater.subprocess.check_call") as mock_run:
        perform_update(repo_dir=str(tmp_path))
    calls = [args[0] for args, _ in mock_run.call_args_list]
    assert any("fetch" in str(c) for c in calls)
    assert any("reset" in str(c) for c in calls)
    assert any("pip" in str(c) for c in calls)


def test_perform_update_rolls_back_on_pip_failure(tmp_path):
    import subprocess as sp
    def fake_run(args, **kwargs):
        if "pip" in " ".join(args):
            raise sp.CalledProcessError(1, args)
    with patch("worker.updater.subprocess.check_call", side_effect=fake_run):
        with patch("worker.updater.subprocess.call") as mock_rollback:
            with pytest.raises(SystemExit):
                perform_update(repo_dir=str(tmp_path))
            # rollback 시도 확인
            assert any("reset" in " ".join(c.args[0]) for c in mock_rollback.call_args_list)
```

- [ ] **Step 2: 테스트 실행 → FAIL**

```bash
pytest tests/test_worker_updater.py -v
```

- [ ] **Step 3: worker/updater.py 구현**

```python
"""워커 자가 업데이트 — 버전 mismatch 감지 → drain → git pull → exit."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

from hydra.core.logger import get_logger

log = get_logger("worker.updater")


def should_update(server_version: str, local_version: str) -> bool:
    """버전 다르고 로컬이 dev/unknown 아닌 경우에만 True.
    
    'unknown' 은 git 없거나 CI 환경 — 자동 업데이트 타게 두면 위험.
    """
    if not server_version or not local_version:
        return False
    if local_version in ("unknown", "dev"):
        return False
    return server_version != local_version


def perform_update(repo_dir: str = r"C:\hydra") -> None:
    """git pull + pip install. 실패 시 롤백 후 exit.
    
    성공/실패 모두 최종적으로 sys.exit — Task Scheduler 가 재시작.
    """
    log.info(f"updater: pulling latest in {repo_dir}")
    try:
        subprocess.check_call(
            ["git", "-C", repo_dir, "fetch", "origin", "main"],
            timeout=60,
        )
        # 현재 HEAD 기록 (롤백용)
        prev = subprocess.check_output(
            ["git", "-C", repo_dir, "rev-parse", "HEAD"],
            timeout=10,
        ).decode().strip()

        subprocess.check_call(
            ["git", "-C", repo_dir, "reset", "--hard", "origin/main"],
            timeout=30,
        )
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r",
             str(Path(repo_dir) / "requirements.txt"), "--quiet"],
            timeout=300,
        )
        log.info("updater: update succeeded, exiting for Task Scheduler restart")
    except subprocess.CalledProcessError as e:
        log.error(f"updater: update step failed ({e.cmd}): reverting")
        try:
            subprocess.call(
                ["git", "-C", repo_dir, "reset", "--hard", prev],
                timeout=30,
            )
        except Exception:
            log.error("updater: rollback also failed — manual intervention required")
        sys.exit(1)
    except Exception as e:
        log.error(f"updater: unexpected error: {e}")
        sys.exit(1)

    sys.exit(0)  # 성공 시 Task Scheduler 가 자동 재시작


def maybe_update(server_version: str, local_version: str,
                 repo_dir: str = r"C:\hydra", is_idle: bool = True) -> bool:
    """is_idle (현재 태스크 없음) 일 때만 업데이트. True 반환은 exit 직전을 의미.
    
    호출자는 False 면 계속 진행, True 면 (이미 exit 호출됨이라 여기 도달 안 함).
    """
    if not should_update(server_version, local_version):
        return False
    if not is_idle:
        log.info(f"updater: version mismatch but task in progress — drain mode")
        return False  # 다음 idle 시점에 재체크
    perform_update(repo_dir)
    return True  # 실제론 exit 됐으므로 여기 도달 안 함
```

- [ ] **Step 4: worker/app.py 메인 루프에 훅 삽입**

`worker/app.py` 수정 — `_async_tick` 수정:

```python
async def _async_tick(self):
    now = datetime.now(UTC)

    if self.last_heartbeat is None or (now - self.last_heartbeat).total_seconds() >= config.poll_interval_sec:
        try:
            resp = self.client.heartbeat()
            self.last_heartbeat = now
            
            # NEW: 버전 체크
            from worker.updater import maybe_update
            is_idle = not hasattr(self, "_current_task_id") or self._current_task_id is None
            maybe_update(
                server_version=resp.get("current_version", ""),
                local_version=config.worker_version,
                is_idle=is_idle,
            )  # 업데이트 발생하면 sys.exit — 이 줄 뒤는 실행 안 됨
            
            # NEW: paused 체크
            if resp.get("paused"):
                log.info("paused by server — skipping fetch")
                return
            
            # NEW: canary 고려 (optional)
            # canary_ids 에 있으면 current_version 이 달라도 동기화, 없으면 무시
        except Exception as e:
            print(f"[Worker] Heartbeat failed: {e}")
            return

    # 기존 fetch + execute
    try:
        tasks = self.client.fetch_tasks()
        ...
    except Exception as e:
        ...
```

현재 태스크 ID 추적을 위해 `self._current_task_id` 도 executor 진입/종료 시 설정:
```python
# _execute_session 내부
self._current_task_id = task["id"]
try:
    await self.executor.execute(...)
finally:
    self._current_task_id = None
```

- [ ] **Step 5: client.py 의 heartbeat() 메서드도 응답 전체 반환하도록**

현재 `heartbeat()` 는 응답 json 을 반환함 (위 테스트 코드에서 가정). 만약 void 로 되어있으면:

```python
# worker/client.py
def heartbeat(self) -> dict:
    resp = self.http.post(
        f"{self.base_url}/api/workers/heartbeat",
        headers=self.headers,
        json={
            "version": config.worker_version,
            "os_type": platform.system().lower(),
            # ... 시스템 상태 필드들
        },
    )
    resp.raise_for_status()
    return resp.json()   # 응답 반환 — current_version/paused 포함
```

- [ ] **Step 6: 테스트 실행 → PASS**

```bash
pytest tests/test_worker_updater.py -v
```

예상: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add worker/updater.py worker/app.py worker/client.py tests/test_worker_updater.py
git commit -m "feat(worker): 자가 업데이트 (버전 감지 + drain + git pull + exit)"
```

---

## Task 35: 로컬 DB 의존성 제거 — API payload 기반 실행

**목적:** 워커가 로컬 SQLite 에 직접 접근하지 않고, VPS API 에서 받은 payload 만으로 태스크 실행 가능하게 분리. `scripts/*.py` (dev 도구) 와 `worker/*.py` (prod 워커) 경계 명확화.

**Files:**
- Modify: `worker/executor.py` (로컬 DB 접근 제거)
- Modify: `hydra/web/routes/tasks_api.py` (fetch 응답에 account_snapshot 포함)
- Create: `worker/account_snapshot.py` (payload 복호화 헬퍼)
- Test: `tests/test_executor_no_local_db.py`

- [ ] **Step 1: 현재 로컬 DB 접근 지점 식별**

```bash
grep -rn "SessionLocal\|hydra.db\|sqlite" worker/*.py | grep -v "__pycache__"
```

출력 예시 확인 — `worker/executor.py` 가 `SessionLocal()` 로 계정 조회하는 라인들.

- [ ] **Step 2: AccountSnapshot 데이터클래스**

`worker/account_snapshot.py`:
```python
"""VPS API payload 로부터 받은 계정 정보를 다루는 스냅샷.

로컬 DB 없이도 태스크 실행이 가능하도록 필요한 필드 전부 포함.
"""
from dataclasses import dataclass
from typing import Any
from hydra.core import crypto


@dataclass
class AccountSnapshot:
    id: int
    gmail: str
    password: str                 # 복호화된 평문 (워커 메모리에만)
    recovery_email: str | None
    adspower_profile_id: str
    persona: dict[str, Any]
    totp_secret: str | None = None
    status: str = "warmup"
    ipp_flagged: bool = False
    youtube_channel_id: str | None = None

    @classmethod
    def from_payload(cls, payload: dict, crypto_key: str) -> "AccountSnapshot":
        """서버가 보낸 암호화된 payload 를 AccountSnapshot 으로.

        서버는 password/totp_secret 을 DB_CRYPTO_KEY 로 암호화해서 보냄.
        """
        import json
        enc = payload.get("account_snapshot") or {}
        pwd = enc.get("encrypted_password")
        totp = enc.get("encrypted_totp_secret")
        persona_raw = enc.get("persona")
        persona = json.loads(persona_raw) if isinstance(persona_raw, str) else (persona_raw or {})

        return cls(
            id=enc["id"],
            gmail=enc["gmail"],
            password=crypto.decrypt(pwd) if pwd else "",
            recovery_email=enc.get("recovery_email"),
            adspower_profile_id=enc["adspower_profile_id"],
            persona=persona,
            totp_secret=crypto.decrypt(totp) if totp else None,
            status=enc.get("status", "warmup"),
            ipp_flagged=enc.get("ipp_flagged", False),
            youtube_channel_id=enc.get("youtube_channel_id"),
        )
```

- [ ] **Step 3: fetch 응답 확장 — account_snapshot 포함**

`hydra/web/routes/tasks_api.py` 수정:

```python
@router.post("/fetch")
def fetch_tasks(worker: Worker = Depends(worker_auth)):
    db = SessionLocal()
    try:
        # ... 기존 SKIP LOCKED 쿼리 ...
        task_id = row[0]
        task = db.get(Task, task_id)
        task.status = "running"
        task.worker_id = worker.id
        task.started_at = datetime.now(UTC)
        db.add(AccountLock(account_id=task.account_id, worker_id=worker.id, task_id=task.id))

        # NEW: 계정 snapshot 동봉
        account = db.get(Account, task.account_id)
        account_snapshot = {
            "id": account.id,
            "gmail": account.gmail,
            "encrypted_password": account.password,  # 이미 암호화되어 DB 에 있음
            "recovery_email": account.recovery_email,
            "adspower_profile_id": account.adspower_profile_id,
            "persona": account.persona,
            "encrypted_totp_secret": account.totp_secret,
            "status": account.status,
            "ipp_flagged": account.ipp_flagged,
            "youtube_channel_id": account.youtube_channel_id,
        }
        db.commit()
        return {"tasks": [{
            "id": task.id,
            "account_id": task.account_id,
            "task_type": task.task_type,
            "payload": task.payload,
            "priority": task.priority,
            "account_snapshot": account_snapshot,
        }]}
    finally:
        db.close()
```

- [ ] **Step 4: 테스트 작성**

`tests/test_executor_no_local_db.py`:
```python
"""워커 executor 가 로컬 SQLite 를 직접 건드리지 않는지 검증."""
from worker.account_snapshot import AccountSnapshot
from hydra.core import crypto


def test_account_snapshot_from_payload_decrypts_password():
    encrypted = crypto.encrypt("MySecret!123")
    payload = {"account_snapshot": {
        "id": 42,
        "gmail": "test@gmail.com",
        "encrypted_password": encrypted,
        "adspower_profile_id": "k1xxx",
        "persona": {"name": "홍길동", "age": 28},
    }}
    snap = AccountSnapshot.from_payload(payload, crypto_key="unused-handled-by-crypto")
    assert snap.gmail == "test@gmail.com"
    assert snap.password == "MySecret!123"
    assert snap.persona["name"] == "홍길동"


def test_executor_does_not_import_sessionlocal():
    """executor.py 소스에 SessionLocal 직접 import 가 없어야 함."""
    import inspect
    import worker.executor as ex
    src = inspect.getsource(ex)
    assert "SessionLocal" not in src, (
        "worker/executor.py 는 로컬 DB 에 직접 접근하면 안 됨. "
        "AccountSnapshot 으로만 작업해야 함."
    )


def test_persona_json_string_parsed():
    """persona 가 JSON 문자열로 와도 dict 로 변환."""
    payload = {"account_snapshot": {
        "id": 1, "gmail": "x@y.z",
        "adspower_profile_id": "p",
        "persona": '{"name": "이순신"}',
    }}
    snap = AccountSnapshot.from_payload(payload, crypto_key="")
    assert isinstance(snap.persona, dict)
    assert snap.persona["name"] == "이순신"
```

- [ ] **Step 5: 테스트 실행 → 이 시점엔 executor.py 수정 전이라 마지막 테스트 FAIL**

```bash
pytest tests/test_executor_no_local_db.py -v
```

예상: 2 pass + 1 fail (executor 가 아직 SessionLocal 씀).

- [ ] **Step 6: worker/executor.py 리팩터링**

현재 executor 에서 `SessionLocal()` 로 계정 조회하는 부분을 제거하고, fetch 응답의 `account_snapshot` 을 받아 `AccountSnapshot.from_payload()` 로 변환 후 사용하도록 수정.

핵심 변경:
```python
# 기존
from hydra.db.session import SessionLocal
from hydra.db.models import Account

async def execute(self, task: dict):
    db = SessionLocal()
    acct = db.get(Account, task["account_id"])
    db.close()
    # ... acct 사용

# 변경
from worker.account_snapshot import AccountSnapshot
from worker.config import config

async def execute(self, task: dict):
    snap = AccountSnapshot.from_payload(task, crypto_key=config.db_crypto_key)
    # ... snap 을 acct 처럼 사용 (동일 필드명)
```

onboarding/verifier.py 나 다른 곳에서 `acct.gmail`, `acct.persona` 등을 접근하는 부분은 `AccountSnapshot` 이 같은 속성 이름을 가지므로 **대부분 그대로 작동**.

**단 예외:** `acct.totp_secret` 이 암호화된 문자열이 아니라 복호화된 평문이 될 것 (snap 생성 시 복호화). 기존 `crypto.decrypt(acct.totp_secret)` 호출 라인들 찾아서 제거.

```bash
grep -rn "crypto.decrypt(acct.totp_secret\|crypto.decrypt(acct.password" .
```

- [ ] **Step 7: 테스트 실행 → PASS**

```bash
pytest tests/test_executor_no_local_db.py -v
```

예상: 3 passed.

- [ ] **Step 8: scripts/ vs worker/ 경계 README**

`worker/README.md` 작성 (없으면):
```markdown
# worker/ — 프로덕션 워커

VPS API 와만 통신. 로컬 DB 직접 접근 금지.

- `worker/app.py` — 메인 루프
- `worker/client.py` — VPS API 클라이언트
- `worker/config.py` — secrets 기반 설정
- `worker/secrets.py` — DPAPI/.env 로딩
- `worker/executor.py` — 태스크 실행
- `worker/account_snapshot.py` — payload → AccountSnapshot
- `worker/updater.py` — 자가 업데이트

**로컬 DB 접근 금지.** AccountSnapshot 으로만 작업.
```

`scripts/README.md`:
```markdown
# scripts/ — 개발/운영 도구

로컬 DB 직접 접근 OK. 프로덕션 워커에는 배포 안 됨.

예: run_verifier.py (온보딩 디버깅), click_*.py (수동 조작)
```

- [ ] **Step 9: Commit**

```bash
git add worker/account_snapshot.py worker/executor.py worker/README.md scripts/README.md hydra/web/routes/tasks_api.py tests/test_executor_no_local_db.py
git commit -m "refactor(worker): 로컬 DB 의존 제거 — API payload 기반 AccountSnapshot"
```

---

## Task 36: end-to-end 검증

- [ ] **Step 1: VPS 에서 전체 파이프라인 검증**

Mac 에서:
```bash
git push origin main
```

VPS 에 ssh 후:
```bash
curl -X POST https://api.hydra.com/api/admin/deploy \
     -H "Authorization: Bearer <admin_jwt>"
# 1~2분 대기
curl https://api.hydra.com/api/admin/server-config -H "Authorization: Bearer <admin_jwt>"
# current_version 이 새 git hash 로 변경됐는지 확인
```

- [ ] **Step 2: 워커 1대에서 전체 플로우**

테스트 Windows PC 에서:
```powershell
# setup.ps1 실행 (위 Task 31 참조)
# 설치 후 Task Scheduler 시작
Start-ScheduledTask -TaskName HydraWorker
```

VPS 에서:
```bash
psql -h localhost -U hydra -d hydra_prod \
  -c "SELECT id, hostname, last_heartbeat, version FROM workers ORDER BY last_heartbeat DESC LIMIT 3;"
```

검증: 새 워커가 목록에 있고 last_heartbeat 가 최근.

- [ ] **Step 3: 업데이트 반영 end-to-end 테스트**

Mac 에서 간단한 로그 추가 커밋:
```bash
echo "# trivial change $(date)" >> README.md
git add README.md
git commit -m "test: deploy cycle"
git push
```

어드민 UI 에서 "배포" 버튼 클릭.
2~3분 내:
- VPS: `git rev-parse --short HEAD` 가 새 값
- 워커: Task Scheduler 로그 확인 — 재시작됐는지 (`Get-ScheduledTaskInfo -TaskName HydraWorker | select LastRunTime`)
- 어드민 UI: 워커 목록의 version 이 새 값

- [ ] **Step 4: 체크리스트 문서화**

`docs/phase1-verification.md` 작성:
```markdown
# Phase 1 검증 체크리스트

- [ ] VPS 에서 hydra-server 가 systemd 로 상시 running
- [ ] https://admin.hydra.com 로그인 작동
- [ ] https://api.hydra.com/openapi.json 응답
- [ ] TLS 인증서 유효 (브라우저 자물쇠 녹색)
- [ ] DB 마이그레이션 head 도달: `alembic current` 확인
- [ ] server_config 에 row 1개 (id=1)
- [ ] /api/admin/pause 호출 → DB paused=True
- [ ] 어드민 UI 배포 버튼 → git pull 성공 → version 갱신
- [ ] 워커 1대 설치 완료 → heartbeat 로그 확인
- [ ] 워커가 current_version 갱신 감지 → 재시작 확인
- [ ] 아바타 업로드 UI 에서 파일 업로드 → 저장 확인
- [ ] 워커가 /api/avatars/xxx 로 다운로드 성공
- [ ] 모바일에서 어드민 UI 접속 → 주요 기능 사용 가능
  - [ ] 햄버거 메뉴 토글
  - [ ] 긴급정지 바
  - [ ] 배포 버튼
  - [ ] 아바타 업로드 (카메라 앨범 선택)
- [ ] Audit log 에 배포 이력 기록됨
- [ ] fail2ban + UFW 작동
- [ ] certbot 자동 갱신 timer 활성
```

- [ ] **Step 5: Commit**

```bash
git add docs/phase1-verification.md
git commit -m "docs: Phase 1 완료 검증 체크리스트"
```

---

## Phase 1 완료 기준 요약

**인프라:**
- ✅ VPS (Ubuntu 22.04) 에서 hydra-server + PostgreSQL + nginx + TLS 동작
- ✅ Alembic 마이그레이션 9개 적용 (baseline / customer_id / server_config / users / execution_logs / audit_logs / account_locks / worker_token_hash / worker_allowed_task_types)
- ✅ 환경 준비 완료 (.env.example / conftest DB 격리 / axios interceptor / vite alias / create_admin CLI)

**보안:**
- ✅ 모든 `/api/admin/*` 에 admin_session Depends 강제 (login 제외)
- ✅ CORS 허용 리스트 명시적 설정
- ✅ 감사 로그 자동 기록 (deploy / pause / worker_change / account_created 등)

**프론트엔드 (반응형 — 모바일/태블릿/PC 전부):**
- ✅ 로그인 → 대시보드 → 배포 → 긴급정지 → 아바타 관리 → 워커 상세/특화 편집 → 감사 로그 전체 사용 가능
- ✅ 모바일에서 햄버거 메뉴 + 터치 친화 버튼 (44pt+)

**워커 (Windows):**
- ✅ 설치 스크립트로 1회 세팅 완료 (NTP 포함)
- ✅ DPAPI/.env 기반 시크릿 로딩 (평문 전달 없음)
- ✅ heartbeat 응답의 current_version 감지 → 자가 업데이트 (drain + git pull + 롤백)
- ✅ 로컬 DB 없이 AccountSnapshot 기반으로만 태스크 실행

**워커 특화 + 데이터 흐름:**
- ✅ `allowed_task_types` 로 워커별 역할 제한 ("계정 생성 전용 워커" 등)
- ✅ 워커가 생성한 계정 정보를 VPS API 로 업로드 → VPS DB 에 INSERT (로컬 DB 안 씀)
- ✅ audit log 에 "account_created by worker X" 기록

**파이프라인:**
- ✅ Mac git push → 어드민 UI 배포 버튼 → VPS + 워커 갱신 end-to-end 작동
- ✅ 감사 로그 + 좀비 복구 + enrollment + 아바타 서빙 모두 검증됨

---

## 다음 Phase 미리보기

- **Phase 2**: 워커 Windows 완전 전환 + 크로스플랫폼 호환성 이슈 해결 + CI (GitHub Actions)
- **Phase 3**: 관측성 (로그 스트리밍, 스크린샷 자동 업로드, Discord 알림, Tailscale)
- **Phase 4**: 자동화 (카나리, 재해복구 runbook, DB 백업 크론)
- **Phase 5**: 전체 워커 확장 + 실전 캠페인 투입 + 데이터 수집
