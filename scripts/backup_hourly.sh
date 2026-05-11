#!/bin/bash
# PR-M: Hourly pg_dump backup with 7-day retention.
# Invoked by hydra-backup.service (systemd timer).

set -euo pipefail

BACKUP_DIR="${HYDRA_BACKUP_DIR:-/opt/hydra/data/backup}"
RETAIN_DAYS="${HYDRA_RETAIN_DAYS:-7}"
HYDRA_DIR="${HYDRA_DIR:-/opt/hydra}"

mkdir -p "$BACKUP_DIR"

ENV_FILE="$HYDRA_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "ENV file not found: $ENV_FILE" >&2
  exit 1
fi

# postgresql+psycopg2://user:pass@host:port/db  형식을 sed 로 파싱.
DB_LINE=$(grep '^DATABASE_URL=' "$ENV_FILE" | head -n1 | cut -d= -f2-)
if [ -z "$DB_LINE" ]; then
  echo "DATABASE_URL not set" >&2
  exit 2
fi
# Strip "+psycopg2" if present
DB_URL="${DB_LINE/+psycopg2/}"
# Pattern: postgresql://USER:PASS@HOST:PORT/DB
URL_BODY="${DB_URL#postgresql://}"
USERPASS="${URL_BODY%@*}"
HOSTDB="${URL_BODY#*@}"
export PGUSER="${USERPASS%:*}"
export PGPASSWORD="${USERPASS#*:}"
HOSTPORT="${HOSTDB%%/*}"
export PGHOST="${HOSTPORT%:*}"
export PGPORT="${HOSTPORT#*:}"
export PGDATABASE="${HOSTDB#*/}"

STAMP=$(date '+%Y%m%d-%H%M%S')
OUT="$BACKUP_DIR/hydra-$STAMP.dump"

pg_dump -Fc -f "$OUT"

if [ ! -s "$OUT" ]; then
  echo "pg_dump produced empty file: $OUT" >&2
  rm -f "$OUT"
  exit 3
fi

SIZE=$(du -h "$OUT" | cut -f1)
echo "backup OK: $OUT ($SIZE)"

# Retention.
find "$BACKUP_DIR" -maxdepth 1 -name 'hydra-*.dump' -type f -mtime +"$RETAIN_DAYS" -print -delete

# Telegram alert (best-effort).
if [ -n "${HYDRA_TELEGRAM_BACKUP_ALERT:-}" ]; then
  cd "$HYDRA_DIR" && .venv/bin/python -c "
from hydra.infra import telegram
telegram.info(f'백업 완료: $STAMP ($SIZE)')
" 2>/dev/null || true
fi
