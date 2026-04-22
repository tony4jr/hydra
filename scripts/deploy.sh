#!/usr/bin/env bash
# HYDRA VPS 배포 스크립트 — /opt/hydra 에서 deployer 유저로 실행.
# Task 25 의 /api/admin/deploy 엔드포인트가 이 파일을 호출한다.
set -euo pipefail

cd /opt/hydra

# 1. 안전 가드: main 브랜치에서만 실행
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" != "main" ]]; then
    echo "[deploy] ABORT — not on main (current=$CURRENT_BRANCH)" >&2
    exit 1
fi

PREV_REV=$(git rev-parse --short HEAD)
echo "[deploy] starting — prev=$PREV_REV"

# 2. 최신 코드 pull
echo "[deploy] git fetch + reset..."
git fetch origin main --quiet
git reset --hard origin/main

NEW_REV=$(git rev-parse --short HEAD)
if [[ "$NEW_REV" == "$PREV_REV" ]]; then
    echo "[deploy] no new commits — skip restart"
    exit 0
fi

# 3. Python 의존성
echo "[deploy] pip install -e ."
.venv/bin/pip install -e . --quiet

# 4. DB 마이그레이션 (실패 시 중단)
echo "[deploy] alembic upgrade head..."
set -a
. ./.env
set +a
.venv/bin/alembic upgrade head

# 5. 프론트엔드 빌드 — frontend/package.json 있을 때만
if [[ -f frontend/package.json ]]; then
    echo "[deploy] frontend build..."
    cd frontend
    npm ci --silent
    npm run build
    cd /opt/hydra
else
    echo "[deploy] frontend skipped (no package.json)"
fi

# 6. 서버 재시작 (deployer 무비번 sudo 설정돼있어야 — Validation B Step 3)
echo "[deploy] restarting hydra-server..."
sudo systemctl restart hydra-server

# 7. 버전 갱신 — heartbeat/v2 응답에 반영됨
echo "[deploy] bumping version to $NEW_REV..."
.venv/bin/python scripts/bump_version.py "$NEW_REV"

echo "[deploy] done — was=$PREV_REV now=$NEW_REV"
