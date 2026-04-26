# HYDRA Staging 환경 셋업 가이드

prod 와 staging 을 같은 VPS 에서 운영. 격리는 4-layer:
- 프로세스 (port 8000 vs 8001)
- DB (`hydra` vs `hydra_staging`)
- 디렉터리 (`/opt/hydra` vs `/opt/hydra-staging`, `/var/www/hydra` vs `/var/www/hydra-staging`)
- 도메인 (`hydra-prod.duckdns.org` vs `hydra-stg-prod.duckdns.org`)

## 1단계 — DNS

duckdns.org 에서 `hydra-stg-prod` 서브도메인 추가 → 같은 IP (158.247.232.101).

## 2단계 — DB 생성

```bash
sudo -u postgres psql -c "CREATE DATABASE hydra_staging OWNER deployer;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE hydra_staging TO deployer;"
```

prod 스키마 복제 (선택):
```bash
sudo -u postgres pg_dump --schema-only hydra > /tmp/schema.sql
sudo -u postgres psql hydra_staging < /tmp/schema.sql
```

## 3단계 — 코드 클론

```bash
sudo mkdir -p /opt/hydra-staging
sudo chown deployer:deployer /opt/hydra-staging
sudo -u deployer git clone https://github.com/tony4jr/hydra.git /opt/hydra-staging
cd /opt/hydra-staging
sudo -u deployer python3 -m venv .venv
sudo -u deployer .venv/bin/pip install -e .
```

## 4단계 — .env

`/opt/hydra-staging/.env` (prod .env 복사 후 아래만 변경):
```
HYDRA_ENV=staging
DATABASE_URL=postgresql://deployer:<pw>@127.0.0.1:5432/hydra_staging
SERVER_URL=https://hydra-stg-prod.duckdns.org
SERVER_PORT=8001
# (Telegram 토큰 / API 키 별도 — 알림 혼동 방지)
TELEGRAM_BOT_TOKEN=<staging-bot-or-empty>
TELEGRAM_CHAT_ID=<staging-chat-or-empty>
```

## 5단계 — Alembic 마이그레이션

```bash
cd /opt/hydra-staging
sudo -u deployer .venv/bin/alembic upgrade head
```

## 6단계 — systemd

```bash
sudo cp /opt/hydra-staging/deploy/hydra-server-staging.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hydra-server-staging
```

## 7단계 — nginx + TLS

```bash
sudo cp /opt/hydra-staging/deploy/nginx-hydra-staging.conf /etc/nginx/sites-available/hydra-staging
sudo ln -s /etc/nginx/sites-available/hydra-staging /etc/nginx/sites-enabled/
sudo certbot --nginx -d hydra-stg-prod.duckdns.org
sudo nginx -t && sudo systemctl reload nginx
```

## 8단계 — 프론트엔드 배포

`scripts/build_and_deploy_frontend.sh` 응용 — REMOTE_DIR 변경:
```bash
REMOTE_DIR=/var/www/hydra-staging \
  bash /opt/hydra-staging/scripts/build_and_deploy_frontend.sh
```

(또는 `/opt/hydra-staging/scripts/deploy.sh` 만들어 staging-specific 배포 자동화)

## 9단계 — 검증

```bash
curl https://hydra-stg-prod.duckdns.org/healthz
# → "hydra-staging ok"
```

브라우저에서 `https://hydra-stg-prod.duckdns.org/` 접속해 어드민 로그인.

## 운영 룰

- **워커는 staging 에 별도 token 발급** — prod worker 가 staging task 잡으면 안 됨
- **AdsPower 프로필 분리** — staging 전용 그룹/프로필 사용 (실 계정과 섞이면 위험)
- **모니터링 분리** — Telegram 봇 다른 거 (혹은 chat_id 만 다른 같은 봇)
- **백업 cron 도 staging 별도** — 리텐션 짧게 (3일) 설정
