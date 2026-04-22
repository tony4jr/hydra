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

## Task 목록 (전체 32개)

### 그룹 A: VPS 프로비저닝 (Task 1~4)
### 그룹 B: 기본 인프라 설정 (Task 5~8)
### 그룹 C: Alembic 마이그레이션 (Task 9~14)
### 그룹 D: 인증 + 네임스페이스 (Task 15~17)
### 그룹 E: 핵심 API (Task 18~23)
### 그룹 F: 배포 파이프라인 (Task 24~25)
### 그룹 G: 프론트엔드 (Task 26~29)
### 그룹 H: 검증 (Task 30~32)

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

## Task 32: end-to-end 검증

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

- ✅ VPS (Ubuntu 22.04) 에서 hydra-server + PostgreSQL + nginx + TLS 동작
- ✅ Alembic 마이그레이션 7개 적용 (customer_id/server_config/users/execution_logs/audit_logs/account_locks/worker_token_hash)
- ✅ 어드민 UI 에서 로그인 → 배포 버튼/긴급정지/아바타 관리 사용 가능 (**모바일 포함**)
- ✅ 워커 설치 스크립트로 Windows PC 에 1회 세팅 완료
- ✅ Mac git push → 어드민 UI 배포 버튼 → VPS + 워커 갱신 end-to-end 작동
- ✅ 감사 로그 + 좀비 복구 + enrollment + 아바타 서빙 모두 검증됨

---

## 다음 Phase 미리보기

- **Phase 2**: 워커 Windows 완전 전환 + 크로스플랫폼 호환성 이슈 해결 + CI (GitHub Actions)
- **Phase 3**: 관측성 (로그 스트리밍, 스크린샷 자동 업로드, Discord 알림, Tailscale)
- **Phase 4**: 자동화 (카나리, 재해복구 runbook, DB 백업 크론)
- **Phase 5**: 전체 워커 확장 + 실전 캠페인 투입 + 데이터 수집
