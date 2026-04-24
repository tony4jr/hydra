#!/usr/bin/env bash
# Mac/dev 머신에서 frontend 빌드 → VPS /var/www/hydra/ 로 rsync.
# VPS 에 node 설치 불필요.
#
# 사용:
#   bash scripts/build_and_deploy_frontend.sh
set -euo pipefail

SSH_KEY="${SSH_KEY:-$HOME/.ssh/hydra_prod}"
SSH_TARGET="${SSH_TARGET:-deployer@158.247.232.101}"
REMOTE_DIR="${REMOTE_DIR:-/var/www/hydra}"

cd "$(dirname "$0")/.."

echo "[1/3] frontend build..."
(cd frontend && [ -d node_modules ] || npm ci --silent; npm run build)

DIST_DIR="frontend/dist"
if [[ ! -d "$DIST_DIR" ]]; then
    echo "[deploy-fe] ERROR: $DIST_DIR not found after build" >&2
    exit 1
fi

echo "[2/3] rsync $DIST_DIR/ → $SSH_TARGET:$REMOTE_DIR/..."
rsync -az --delete \
    --exclude 'screenshots/' \
    -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new" \
    "$DIST_DIR/" "$SSH_TARGET:$REMOTE_DIR/"

echo "[3/3] reloading nginx (no-op if static only)..."
ssh -i "$SSH_KEY" "$SSH_TARGET" 'sudo nginx -t && sudo systemctl reload nginx'

echo "[deploy-fe] done — https://hydra-prod.duckdns.org/"
