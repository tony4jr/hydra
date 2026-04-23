#!/usr/bin/env bash
# M2.1 — Mac 로컬 워커를 DRY-RUN 모드로 VPS 에 연결.
# 실 Gmail/AdsPower/브라우저 액션 없이 heartbeat/fetch/complete 루프만.
set -euo pipefail

cd "$(dirname "$0")/.."

SERVER_URL="${SERVER_URL:-https://hydra-prod.duckdns.org}"
ADMIN_EMAIL="${ADMIN_EMAIL:?ADMIN_EMAIL required}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:?ADMIN_PASSWORD required}"

echo "[1/4] admin login"
ADMIN_TOKEN=$(curl -s -X POST "$SERVER_URL/api/admin/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')

echo "[2/4] enrollment token"
ENROLL=$(curl -s -X POST "$SERVER_URL/api/admin/workers/enroll" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"worker_name":"mac-dryrun","ttl_hours":1}' \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["enrollment_token"])')

echo "[3/4] worker enroll"
WT=$(python3 -c "
import json, urllib.request
body=json.dumps({'enrollment_token':'$ENROLL','hostname':'mac-dryrun'}).encode()
req=urllib.request.Request('$SERVER_URL/api/workers/enroll', data=body, method='POST',
    headers={'Content-Type':'application/json'})
print(json.load(urllib.request.urlopen(req))['worker_token'])
")

echo "[4/4] launching worker (Ctrl+C to stop)"
# worker/secrets.py 가 SERVER_URL / WORKER_TOKEN 을 최우선으로 읽음.
# .env 의 localhost 값을 덮어쓰기 위해 양쪽 모두 export.
export HYDRA_WORKER_DRY_RUN=1
export SERVER_URL="$SERVER_URL"
export WORKER_TOKEN="$WT"
export HYDRA_SERVER_URL="$SERVER_URL"
export HYDRA_WORKER_TOKEN="$WT"
.venv/bin/python -m worker
