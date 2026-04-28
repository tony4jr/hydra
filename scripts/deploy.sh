#!/usr/bin/env bash
# HYDRA VPS deploy — 단순화. 매번 풀+빌드+재시작. 가드 없음.
#
# Flow:
#   git pull → pip install → alembic → pnpm install → pnpm build → rsync → restart
#
# 모든 단계 verbose, 어느 한 줄 실패하면 즉시 abort with 명확한 메시지.

set -euo pipefail
export PYTHONUNBUFFERED=1

ts() { date '+%H:%M:%S'; }
log() { echo "[$(ts)] $*"; }
fail() { log "❌ FAIL — $*"; exit 1; }

cd /opt/hydra

log "── ENV ──"
log "git HEAD=$(git rev-parse --short HEAD)"
log "node=$(command -v node && node -v 2>&1 || echo MISSING)"
log "npm=$(command -v npm && npm -v 2>&1 || echo MISSING)"
log "disk: $(df -h / | tail -1)"
log "mem:  $(free -h | grep Mem)"

# ── 1. main 가드
[[ "$(git rev-parse --abbrev-ref HEAD)" == "main" ]] || fail "not on main"

# ── 2. git pull
log "── GIT PULL ──"
git fetch origin main
git reset --hard origin/main
NEW_REV=$(git rev-parse --short HEAD)
log "HEAD → $NEW_REV"

# ── 3. backend
log "── BACKEND ──"
.venv/bin/pip install -e . || fail "pip install failed"
set -a; . ./.env; set +a
.venv/bin/alembic upgrade head || fail "alembic failed"

# ── 4. pnpm 보장 (없으면 글로벌 설치, idempotent)
log "── PNPM ──"
command -v node >/dev/null || fail "node not installed"
if ! command -v pnpm >/dev/null 2>&1; then
    log "pnpm 없음 — sudo npm install -g pnpm…"
    sudo npm install -g pnpm 2>&1 || fail "pnpm 설치 실패"
fi
log "node=$(node -v)  pnpm=$(pnpm -v)"

# ── 5. frontend build
log "── FRONTEND ──"
[[ -f frontend/package.json ]] || fail "frontend/package.json 없음"
[[ -f frontend/pnpm-lock.yaml ]] || fail "frontend/pnpm-lock.yaml 없음"

cd frontend
log "pnpm install --frozen-lockfile…"
timeout 300 pnpm install --frozen-lockfile 2>&1 || fail "pnpm install 실패"

log "pnpm run build…"
timeout 180 pnpm run build 2>&1 || fail "pnpm build 실패"
cd ..

[[ -f frontend/dist/index.html ]] || fail "dist/index.html 없음 (빌드 결과 누락)"

log "rsync → /var/www/hydra/…"
sudo mkdir -p /var/www/hydra
sudo rsync -a --delete frontend/dist/ /var/www/hydra/
sudo chown -R www-data:www-data /var/www/hydra
log "frontend ✅"

# ── 6. nginx (변경 시에만)
if [[ -f deploy/nginx-hydra.conf ]] && command -v nginx >/dev/null 2>&1; then
    if ! sudo cmp -s deploy/nginx-hydra.conf /etc/nginx/sites-available/hydra 2>/dev/null; then
        log "nginx 설정 변경 감지 — 적용…"
        sudo cp deploy/nginx-hydra.conf /etc/nginx/sites-available/hydra
        sudo ln -sf /etc/nginx/sites-available/hydra /etc/nginx/sites-enabled/hydra
        sudo nginx -t || fail "nginx -t 실패"
        sudo systemctl reload nginx
    fi
fi

# ── 7. backend restart
log "── RESTART ──"
sudo systemctl restart hydra-server || fail "hydra-server restart 실패"
.venv/bin/python scripts/bump_version.py "$NEW_REV" || log "⚠️  version bump 실패 (non-fatal)"

# ── 8. verify
log "── VERIFY ──"
sleep 2
HTTP=$(curl -sf -o /dev/null -w "%{http_code}" https://hydra-prod.duckdns.org/ || echo "000")
if [[ "$HTTP" == "200" ]]; then
    log "site HTTP 200 ✅"
else
    log "⚠️  site HTTP=$HTTP"
fi

log "✅ deploy 완료 — HEAD=$NEW_REV"
