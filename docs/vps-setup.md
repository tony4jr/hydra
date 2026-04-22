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

## 4. 다음 단계

- Task 3: 도메인 연결 + TLS (Let's Encrypt)
- Task 4: PostgreSQL + Python 설치
- Task 5: repo clone + 의존성
- ...
