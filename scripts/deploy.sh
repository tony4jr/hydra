#!/usr/bin/env bash
# HYDRA VPS 배포 스크립트 — /opt/hydra 에서 deployer 유저로 실행.
# Task 25 의 /api/admin/deploy 엔드포인트가 이 파일을 호출한다.
#
# 설계 원칙:
#   1. 모든 단계는 시작/끝 + 결과 로그를 남긴다 (silence-by-default 금지).
#   2. 실패하면 명확한 메시지 + 종료 코드. systemd가 failed 로 표시.
#   3. frontend dist 가 없거나 stale 이면 강제 빌드 (no-new-commits 가드 무시).
#   4. 모든 npm/pip/git 출력은 그대로 흘려보낸다 (--silent 금지).
set -euo pipefail

# 모든 명령 trace + timestamp (systemd journal 에 한 줄씩 시간이 박힘)
ts() { date '+%H:%M:%S'; }
log() { echo "[$(ts)] $*"; }
fail() { log "❌ FAIL — $*"; exit 1; }

cd /opt/hydra

# 1. 안전 가드
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
[[ "$CURRENT_BRANCH" == "main" ]] || fail "not on main (current=$CURRENT_BRANCH)"

PREV_REV=$(git rev-parse --short HEAD)
log "starting — prev=$PREV_REV  user=$(whoami)  cwd=$(pwd)"

# 2. 최신 코드 pull
log "git fetch + reset…"
git fetch origin main
git reset --hard origin/main
NEW_REV=$(git rev-parse --short HEAD)
log "git HEAD → $NEW_REV"

CODE_CHANGED=true
if [[ "$NEW_REV" == "$PREV_REV" ]]; then
    CODE_CHANGED=false
    log "no new commits — backend skip, frontend will rebuild only if dist missing"
fi

# 3. Backend (only if code changed)
if [[ "$CODE_CHANGED" == "true" ]]; then
    log "pip install -e . …"
    .venv/bin/pip install -e .

    log "alembic upgrade head…"
    set -a
    . ./.env
    set +a
    .venv/bin/alembic upgrade head
fi

# 4. Frontend — 정책:
#    - npm 없음 = 명시적 ABORT (운영 환경 문제이므로 조용히 skip 금지)
#    - dist 폴더 없음 → 무조건 build (commit 안 바뀌어도)
#    - dist 있음 + 코드 안바뀜 → skip (안전하게 재사용)
#    - 코드 바뀜 → 무조건 build
if [[ ! -f frontend/package.json ]]; then
    log "frontend/package.json 없음 — frontend deploy skip (저장소 이상 가능)"
elif ! command -v npm >/dev/null 2>&1; then
    fail "npm not installed on VPS — cannot build frontend (apt install nodejs)"
else
    NEED_BUILD=false
    if [[ "$CODE_CHANGED" == "true" ]]; then
        NEED_BUILD=true
        log "frontend: code changed → rebuild"
    elif [[ ! -f /var/www/hydra/index.html ]]; then
        NEED_BUILD=true
        log "frontend: /var/www/hydra/index.html 없음 → rebuild"
    else
        log "frontend: skip (code unchanged + dist present)"
    fi

    if [[ "$NEED_BUILD" == "true" ]]; then
        log "frontend: node=$(node -v 2>&1) npm=$(npm -v 2>&1)"
        log "frontend: npm ci…"
        # --silent 금지 — 에러 즉시 보이게. set -e 로 실패 시 자동 abort.
        (cd frontend && npm ci) || fail "npm ci failed"
        log "frontend: npm run build…"
        (cd frontend && npm run build) || fail "npm run build failed"
        log "frontend: rsync → /var/www/hydra…"
        sudo mkdir -p /var/www/hydra
        sudo rsync -a --delete frontend/dist/ /var/www/hydra/
        sudo chown -R www-data:www-data /var/www/hydra
        log "frontend: ✅ deployed"
    fi
fi

# 5. nginx config sync (변경된 경우에만)
if [[ -f deploy/nginx-hydra.conf ]] && command -v nginx >/dev/null 2>&1; then
    NGINX_TARGET="/etc/nginx/sites-available/hydra"
    if ! sudo cmp -s deploy/nginx-hydra.conf "$NGINX_TARGET" 2>/dev/null; then
        log "nginx config changed — applying…"
        sudo cp deploy/nginx-hydra.conf "$NGINX_TARGET"
        sudo ln -sf "$NGINX_TARGET" /etc/nginx/sites-enabled/hydra
        if sudo nginx -t; then
            sudo systemctl reload nginx
            log "nginx reloaded"
        else
            fail "nginx -t failed — config NOT applied"
        fi
    fi
fi

# 6. backend restart + version bump (only if code changed)
if [[ "$CODE_CHANGED" == "true" ]]; then
    log "restarting hydra-server…"
    sudo systemctl restart hydra-server
    log "bumping version to $NEW_REV…"
    .venv/bin/python scripts/bump_version.py "$NEW_REV"
fi

log "✅ done — was=$PREV_REV now=$NEW_REV  code_changed=$CODE_CHANGED"
