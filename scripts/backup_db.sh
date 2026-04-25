#!/usr/bin/env bash
# DB 일일 백업 → Backblaze B2 (또는 다른 rclone remote)
#
# 사전 조건:
#   - rclone 설치 (apt install rclone)
#   - rclone config: remote 이름 'hydra-b2' (아래 RCLONE_REMOTE 변경 가능)
#   - PG 접속 가능 (DATABASE_URL 또는 .env)
#
# cron 설치:
#   sudo crontab -u deployer -e
#   0 4 * * * /opt/hydra/scripts/backup_db.sh >> /var/log/hydra/backup.log 2>&1
#
# 결과: 성공/실패 모두 worker_errors kind=diagnostic 로 서버 자체 보고
set -euo pipefail

REPO_DIR="${HYDRA_REPO:-/opt/hydra}"
RCLONE_REMOTE="${RCLONE_REMOTE:-hydra-b2}"
BUCKET="${B2_BUCKET:-hydra-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

cd "$REPO_DIR"

# .env 로드 (DB_URL)
if [[ -f "$REPO_DIR/.env" ]]; then
    set -a
    . "$REPO_DIR/.env"
    set +a
fi

# DATABASE_URL 또는 DB_URL 우선
DBURL="${DATABASE_URL:-${DB_URL:-}}"
if [[ -z "$DBURL" ]] || [[ "$DBURL" == sqlite* ]]; then
    echo "[backup] DB_URL must be PostgreSQL (got: ${DBURL:0:30}...)" >&2
    exit 1
fi

TIMESTAMP=$(date -u +%Y%m%d-%H%M)
DUMP_NAME="hydra-prod-${TIMESTAMP}.sql.gz"
TARGET="${RCLONE_REMOTE}:${BUCKET}/${DUMP_NAME}"

echo "[backup] $(date -Iseconds) start → $TARGET"

# pg_dump → gzip → B2 (스트리밍, 디스크 임시파일 X)
DUMP_SIZE=$(pg_dump "$DBURL" --no-owner --no-acl | gzip -9 | rclone rcat "$TARGET" --quiet 2>&1 \
    && rclone size "$TARGET" --json 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("bytes",0))' || echo 0)

if [[ "$DUMP_SIZE" -lt 1024 ]]; then
    MSG="backup uploaded but size suspicious: ${DUMP_SIZE} bytes"
    EXIT_CODE=1
else
    MSG="backup ok: ${DUMP_SIZE} bytes → ${DUMP_NAME}"
    EXIT_CODE=0
fi

echo "[backup] $MSG"

# 7일 초과분 정리
echo "[backup] cleanup older than ${RETENTION_DAYS}d..."
rclone delete "${RCLONE_REMOTE}:${BUCKET}" --min-age "${RETENTION_DAYS}d" --quiet || true

# 서버에 결과 보고 (worker_errors kind=diagnostic)
# 워커 토큰이 있으면 보고, 없으면 로컬 로그만
WT_FILE="${REPO_DIR}/.backup_worker_token"
if [[ -f "$WT_FILE" ]]; then
    WORKER_TOKEN=$(cat "$WT_FILE")
    SERVER_URL="${SERVER_URL:-https://hydra-prod.duckdns.org}"
    curl -sS --max-time 15 -X POST "${SERVER_URL}/api/workers/report-error" \
        -H "X-Worker-Token: ${WORKER_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$(python3 -c "
import json
print(json.dumps({
    'kind': 'diagnostic',
    'message': 'db backup ${MSG}',
    'context': {'dump': '${DUMP_NAME}', 'size': ${DUMP_SIZE}, 'remote': '${TARGET}'},
}))
")" > /dev/null 2>&1 || true
fi

exit "$EXIT_CODE"
