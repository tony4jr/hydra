#!/usr/bin/env bash
# HYDRA backup — DB dump + .env (encrypted-key file) into /opt/hydra/backups
# Cron: 0 4 * * *  (daily 04:00 KST)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/hydra/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d_%H%M%S)

# 1. PostgreSQL dump
if command -v pg_dump >/dev/null 2>&1; then
    DB_FILE="$BACKUP_DIR/db_${TS}.sql.gz"
    sudo -u postgres pg_dump --clean --if-exists hydra 2>/dev/null \
        | gzip > "$DB_FILE"
    echo "[backup] db: $DB_FILE ($(du -h "$DB_FILE" | cut -f1))"
fi

# 2. .env (read-only copy — has Fernet key)
if [[ -f /opt/hydra/.env ]]; then
    ENV_FILE="$BACKUP_DIR/env_${TS}.txt"
    cp /opt/hydra/.env "$ENV_FILE"
    chmod 600 "$ENV_FILE"
fi

# 3. system_config keys (Telegram tokens, API keys via system_config)
SYS_FILE="$BACKUP_DIR/sysconfig_${TS}.json"
sudo -u deployer /opt/hydra/.venv/bin/python -c "
from hydra.db.session import SessionLocal
from hydra.db.models import SystemConfig
import json
db = SessionLocal()
out = {r.key: r.value for r in db.query(SystemConfig).all()}
db.close()
print(json.dumps(out, ensure_ascii=False, indent=2))
" > "$SYS_FILE" 2>/dev/null
chmod 600 "$SYS_FILE"

# 4. Retention — delete > RETENTION_DAYS old backups
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "env_*.txt" -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "sysconfig_*.json" -mtime +"$RETENTION_DAYS" -delete 2>/dev/null || true

# 5. List backups
echo "[backup] inventory:"
ls -la "$BACKUP_DIR" | tail -10

echo "[backup] done at $(date)"
