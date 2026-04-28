#!/usr/bin/env bash
# HYDRA VPS 배포 스크립트 — /opt/hydra 에서 deployer 유저로 실행.
# Task 25 의 /api/admin/deploy 엔드포인트가 이 파일을 호출한다.
#
# 설계 원칙:
#   1. 모든 단계는 시작/끝 + 결과 로그를 남긴다 (silence-by-default 금지).
#   2. 실패하면 명확한 메시지 + 종료 코드. systemd가 failed 로 표시.
#   3. 외부 명령(npm/pip)은 stdbuf 로 line-buffer 강제 — 죽어도 출력 안 잃음.
#   4. cd 는 subshell 대신 in-place — set -e propagation 보장.
#   5. 매번 환경 dump (df/free/git HEAD) — 사후 디버그 용.

set -euo pipefail

# 모든 stdout/stderr 를 line-buffer 로. systemd append: 모드와 결합해도 안 잃음.
export PYTHONUNBUFFERED=1
exec > >(stdbuf -oL -eL cat) 2>&1 || true

ts() { date '+%H:%M:%S'; }
log() { echo "[$(ts)] $*"; }
fail() { log "❌ FAIL — $*"; exit 1; }
run() {
    # 외부 명령을 line-buffered 로 실행 — 죽어도 stdout 보존.
    log "▶ $*"
    stdbuf -oL -eL "$@"
}

cd /opt/hydra

# ── 0. 환경 스냅샷 (사후 디버그용)
log "── ENV ──"
log "user=$(whoami)  cwd=$(pwd)  shell=$BASH_VERSION"
log "node=$(command -v node && node -v 2>&1 || echo 'NOT INSTALLED')"
log "npm=$(command -v npm  && npm -v  2>&1 || echo 'NOT INSTALLED')"
log "git HEAD=$(git rev-parse --short HEAD 2>&1)"
log "disk: $(df -h / 2>/dev/null | tail -1)"
log "mem:  $(free -h 2>/dev/null | grep Mem)"
log "─────────"

# ── 1. main 브랜치 가드
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
[[ "$CURRENT_BRANCH" == "main" ]] || fail "not on main (current=$CURRENT_BRANCH)"

PREV_REV=$(git rev-parse --short HEAD)
log "starting — prev=$PREV_REV"

# ── 2. git pull
log "git fetch + reset…"
run git fetch origin main
run git reset --hard origin/main
NEW_REV=$(git rev-parse --short HEAD)
log "git HEAD → $NEW_REV"

CODE_CHANGED=true
if [[ "$NEW_REV" == "$PREV_REV" ]]; then
    CODE_CHANGED=false
    log "no new commits — backend skip, frontend will rebuild only if dist missing"
fi

# ── 3. Backend (코드 변경 시에만)
if [[ "$CODE_CHANGED" == "true" ]]; then
    log "── BACKEND ──"
    run .venv/bin/pip install -e .
    set -a; . ./.env; set +a
    run .venv/bin/alembic upgrade head
fi

# ── 4. Frontend — fail-fast, no silent skip
log "── FRONTEND ──"
[[ -f frontend/package.json ]] || fail "frontend/package.json missing"
command -v npm >/dev/null 2>&1 || fail "npm not installed (run: sudo apt install nodejs)"

NEED_BUILD=false
if [[ "$CODE_CHANGED" == "true" ]]; then
    NEED_BUILD=true
    log "frontend: code changed → rebuild"
elif [[ ! -f /var/www/hydra/index.html ]]; then
    NEED_BUILD=true
    log "frontend: dist missing → rebuild"
else
    log "frontend: skip (code unchanged + dist present)"
fi

if [[ "$NEED_BUILD" == "true" ]]; then
    log "frontend: node=$(node -v) npm=$(npm -v)"

    # cd in-place — set -e propagation 확실.
    pushd frontend > /dev/null
    log "frontend: npm ci start (timeout=300s)…"
    # timeout 으로 hang 방지. 실패 시 stderr/stdout 둘다 잡힘.
    if ! timeout 300 stdbuf -oL -eL npm ci 2>&1; then
        rc=$?
        popd > /dev/null
        fail "npm ci failed (rc=$rc)"
    fi
    log "frontend: npm ci ✅"

    log "frontend: npm run build start (timeout=180s)…"
    if ! timeout 180 stdbuf -oL -eL npm run build 2>&1; then
        rc=$?
        popd > /dev/null
        fail "npm run build failed (rc=$rc)"
    fi
    log "frontend: build ✅"
    popd > /dev/null

    [[ -f frontend/dist/index.html ]] || fail "frontend/dist/index.html missing after build"

    log "frontend: rsync → /var/www/hydra…"
    run sudo mkdir -p /var/www/hydra
    run sudo rsync -a --delete frontend/dist/ /var/www/hydra/
    run sudo chown -R www-data:www-data /var/www/hydra
    log "frontend: deployed ✅"
fi

# ── 5. nginx config (변경 시에만)
if [[ -f deploy/nginx-hydra.conf ]] && command -v nginx >/dev/null 2>&1; then
    NGINX_TARGET="/etc/nginx/sites-available/hydra"
    if ! sudo cmp -s deploy/nginx-hydra.conf "$NGINX_TARGET" 2>/dev/null; then
        log "nginx config changed — applying…"
        run sudo cp deploy/nginx-hydra.conf "$NGINX_TARGET"
        run sudo ln -sf "$NGINX_TARGET" /etc/nginx/sites-enabled/hydra
        run sudo nginx -t || fail "nginx -t failed — config NOT applied"
        run sudo systemctl reload nginx
    fi
fi

# ── 6. backend restart + version bump
if [[ "$CODE_CHANGED" == "true" ]]; then
    log "── RESTART ──"
    run sudo systemctl restart hydra-server
    run .venv/bin/python scripts/bump_version.py "$NEW_REV"
fi

# ── 7. self-verification
log "── VERIFY ──"
sleep 2
if curl -sf -o /dev/null https://hydra-prod.duckdns.org/ ; then
    log "site reachable ✅"
else
    log "⚠️  site not reachable (may be transient)"
fi

log "✅ done — was=$PREV_REV now=$NEW_REV  code_changed=$CODE_CHANGED"
