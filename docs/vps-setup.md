# VPS 초기 세팅 (Vultr Ubuntu 22.04)

> **목적:** Phase 1 의 VPS 를 처음부터 재구축할 수 있는 절차. 재해 복구 / 스테이징 환경 구축 / 인수인계 시 사용.

---

## 1. Vultr 인스턴스 생성

**접속:** https://my.vultr.com

**설정:**
- Location: **Seoul, KR**
- Type: **Shared CPU**
- Plan: **vc2-2c-4gb** (2 vCPU / 4 GB RAM / 80 GB SSD / $20~24/월)
- Image: **Ubuntu 22.04 LTS x64**
- Server Hostname / Label: `hydra-prod-01`

**Additional Features — 전부 OFF**
- VPC Network ❌
- Automatic Backups ❌ (B2 백업으로 대체)
- DDoS Protection ❌ (Cloudflare 로 대체)
- Limited User Login ❌ (deployer 수동 생성)
- Cloud-Init User Data ❌

**SSH Keys:**
```bash
# Mac 에서 1회 실행
ssh-keygen -t ed25519 -f ~/.ssh/hydra_prod -N "" -C "hydra-prod"
cat ~/.ssh/hydra_prod.pub
```
출력된 공개키를 Vultr → Account → SSH Keys → Add SSH Key 에 등록 (Name: `hydra-mac`). 인스턴스 생성 시 이 키 선택.

**배포 후 확인:** 공인 IP 주소 획득 (예: `158.247.232.101`).

---

## 2. deployer 사용자 생성 + SSH 보안 강화

배포 직후 root 로 한 번 접속 후 아래 스크립트 실행 (또는 Mac 에서 SSH 로 원격 실행):

```bash
ssh -i ~/.ssh/hydra_prod root@<VPS_IP>
```

VPS 에서:

```bash
# deployer 사용자 생성 (비번 없이 SSH 키로만 접속)
adduser --disabled-password --gecos "HYDRA Deployer" deployer
usermod -aG sudo deployer

# 비밀번호 없이 sudo (배포 스크립트 편의)
echo "deployer ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deployer
chmod 440 /etc/sudoers.d/deployer

# SSH 키 복사 (root 의 것을 deployer 로)
mkdir -p /home/deployer/.ssh
cp /root/.ssh/authorized_keys /home/deployer/.ssh/authorized_keys
chown -R deployer:deployer /home/deployer/.ssh
chmod 700 /home/deployer/.ssh
chmod 600 /home/deployer/.ssh/authorized_keys
```

### SSH 서버 보안 강화

```bash
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.$(date +%Y%m%d)

sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config

# Ubuntu cloud-init 이 override 하는 파일도 수정
if [ -f /etc/ssh/sshd_config.d/50-cloud-init.conf ]; then
    sed -i 's/^PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config.d/50-cloud-init.conf
fi

sshd -t && systemctl restart ssh
```

### 검증

Mac 에서:

```bash
# root 접속 시도 → 실패해야 정상
ssh -i ~/.ssh/hydra_prod root@<VPS_IP>
# → Permission denied (publickey)

# deployer 접속 → 성공해야 정상
ssh -i ~/.ssh/hydra_prod deployer@<VPS_IP>
# → 정상 접속

# sudo 무비번 확인
ssh -i ~/.ssh/hydra_prod deployer@<VPS_IP> 'sudo whoami'
# → root
```

---

## 3. 방화벽 (UFW) + fail2ban

```bash
sudo apt-get update -qq
sudo apt-get install -y -qq ufw fail2ban

# UFW — 22/80/443 만 허용
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment "SSH"
sudo ufw allow 80/tcp comment "HTTP"
sudo ufw allow 443/tcp comment "HTTPS"
sudo ufw --force enable

# fail2ban — SSH 무차별 대입 공격 차단
sudo tee /etc/fail2ban/jail.local > /dev/null <<'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
banaction = ufw

[sshd]
enabled = true
port = 22
logpath = %(sshd_log)s
backend = %(sshd_backend)s
maxretry = 5
EOF

sudo systemctl enable --now fail2ban
sudo systemctl restart fail2ban
```

**정책:** 10분 동안 5회 실패 → 1시간 IP ban (ufw 를 통해 커널 레벨 차단).

**확인:**
```bash
sudo ufw status verbose
sudo fail2ban-client status sshd
```

---

## 4. 도메인 + TLS (Let's Encrypt)

### 도메인 세팅
**DuckDNS** (무료) 선택: https://www.duckdns.org
- 서브도메인: `hydra-prod` → `hydra-prod.duckdns.org`
- Current IP: 158.247.232.101 설정 후 "update ip"

### nginx 임시 설정 + TLS 발급

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx

# HTTP 80 임시 설정 (certbot 검증용)
sudo tee /etc/nginx/sites-available/hydra > /dev/null <<'NGINX'
server {
    listen 80;
    server_name hydra-prod.duckdns.org;
    location / {
        return 200 "hydra-prod ok\n";
        add_header Content-Type text/plain;
    }
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/hydra /etc/nginx/sites-enabled/hydra
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

# Let's Encrypt 인증서 발급 + 자동 HTTPS 리다이렉트
sudo certbot --nginx -d hydra-prod.duckdns.org \
    --non-interactive --agree-tos -m <ADMIN_EMAIL> --redirect
```

### 확인
```bash
curl https://hydra-prod.duckdns.org/     # HTTPS 정상 응답
sudo certbot certificates                # 만료일 확인 (90일)
sudo certbot renew --dry-run             # 자동 갱신 점검
```

certbot.timer 가 매일 점검 → 만료 30일 전부터 자동 갱신.

### 아키텍처 특성: 단일 도메인 / 경로 라우팅

DuckDNS 는 서브도메인 1개만 제공 → `admin.hydra-prod.*` 와 `api.hydra-prod.*` 분리 불가.
**단일 도메인 내 경로로 분리:**
- `https://hydra-prod.duckdns.org/api/...` → FastAPI
- `https://hydra-prod.duckdns.org/` (그 외) → React 정적 파일

유료 도메인 구매 후에는 `admin.hydra.com` / `api.hydra.com` 서브도메인 분리 가능.

---

## 5. PostgreSQL + Python + 기본 디렉토리

```bash
# PostgreSQL 14
sudo apt-get install -y postgresql postgresql-contrib libpq-dev
sudo systemctl enable --now postgresql

# hydra DB + 사용자 (비번은 자동 생성)
DB_PASS=$(openssl rand -base64 32 | tr -d "/+=" | head -c 24)
sudo -u postgres psql <<EOF
CREATE USER hydra WITH ENCRYPTED PASSWORD '$DB_PASS';
CREATE DATABASE hydra_prod OWNER hydra;
GRANT ALL PRIVILEGES ON DATABASE hydra_prod TO hydra;
EOF

# Python 3.11 (Ubuntu 22.04 기본은 3.10, deadsnakes PPA 필요)
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update -qq
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev \
    python3-pip build-essential git curl

# 디렉토리 + 권한
sudo mkdir -p /opt/hydra /var/hydra/avatars /var/log/hydra
sudo chown -R deployer:deployer /opt/hydra /var/hydra /var/log/hydra
```

### .env 파일 생성 (민감 정보 — 백업 필수!)

```bash
# 강력한 시크릿 자동 생성
JWT_SECRET=$(openssl rand -base64 64 | tr -d "\n")
ENROLLMENT_SECRET=$(openssl rand -base64 32 | tr -d "\n")
DB_CRYPTO_KEY=$(openssl rand -base64 32 | tr -d "\n")

sudo tee /opt/hydra/.env > /dev/null <<ENVFILE
DATABASE_URL=postgresql+psycopg2://hydra:$DB_PASS@localhost:5432/hydra_prod
DB_CRYPTO_KEY=$DB_CRYPTO_KEY
JWT_SECRET=$JWT_SECRET
ENROLLMENT_SECRET=$ENROLLMENT_SECRET
SERVER_URL=https://hydra-prod.duckdns.org
CORS_ALLOWED_ORIGINS=https://hydra-prod.duckdns.org,http://localhost:5173
AVATAR_STORAGE_DIR=/var/hydra/avatars
ENVFILE

sudo chown deployer:deployer /opt/hydra/.env
sudo chmod 600 /opt/hydra/.env
```

### ⚠️ `.env` 백업 필수

`DB_CRYPTO_KEY` 가 소실되면 DB 에 저장된 암호화 데이터 (계정 비번 / TOTP) **영구 복구 불가**.

**권장 백업:**
```bash
# VPS 에서 로컬 Mac 으로 복사 (초기 세팅 직후 1회 + 변경 시마다)
scp -i ~/.ssh/hydra_prod deployer@<VPS_IP>:/opt/hydra/.env ~/secure/hydra-prod.env.backup
```

복사 후 1Password / iCloud Keychain / 암호화된 USB 등 **로컬 안전 저장소** 에 보관.

---

## 6. DB 스키마 초기화 (중요 — `alembic upgrade head` 단독으로 불가)

기존 `56b9dedf1f5b_initial_schema` 마이그레이션이 `pass` 만 있어서 (히스토리 결함) 빈 DB 에 `alembic upgrade head` 돌리면 accounts 테이블이 생성되지 않고 이후 마이그레이션 실패함.

**반드시 아래 순서로 초기화:**

```bash
cd /opt/hydra
source .venv/bin/activate
set -a; source .env; set +a

# 1. SQLAlchemy 모델 기반으로 스키마 일괄 생성
python <<'PY'
from sqlalchemy import create_engine
from hydra.db.models import Base
import os
e = create_engine(os.environ["DB_URL"])
Base.metadata.create_all(e)
PY

# 2. Alembic 을 최신 head 로 stamp (마이그레이션 이미 반영됐다고 표시)
alembic stamp head

# 3. 이후 새 마이그레이션은 정상 증분 적용 가능
#    예: 나중에 개발자가 alembic revision 으로 만든 파일 →
#        git pull + alembic upgrade head
```

### 검증

```bash
alembic current                            # head revision 표시
python -c "from sqlalchemy import create_engine, inspect; import os; print(sorted(inspect(create_engine(os.environ['DB_URL'])).get_table_names()))"
```

accounts, workers, tasks, users, execution_logs, audit_logs, profile_locks 등 20+ 테이블 목록 출력되어야.

---

## 7. 다음 단계

- Task 15: auth 모듈 (bcrypt + JWT)
- Task 16: 감사 로그 미들웨어
- Task 17~17.6: stub routes + CORS + flat 통합
- Phase 1b: core backend APIs
- ...
# deploy.sh 검증용
