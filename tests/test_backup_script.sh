#!/usr/bin/env bash
# scripts/backup_db.sh 의 정적 검증
set -euo pipefail
PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ✗ $1" >&2; }

# 1. 스크립트 존재 + 실행 가능
[[ -x scripts/backup_db.sh ]] && ok "script exists + executable" || fail "script missing"

# 2. shellcheck 가능하면 검사
if command -v shellcheck >/dev/null; then
    shellcheck scripts/backup_db.sh >/dev/null 2>&1 && ok "shellcheck pass" || fail "shellcheck warnings"
fi

# 3. 필수 명령어 참조
grep -q "pg_dump" scripts/backup_db.sh && ok "pg_dump invoked" || fail "missing pg_dump"
grep -q "rclone rcat" scripts/backup_db.sh && ok "rclone rcat (streaming)" || fail "missing rclone"
grep -q "min-age" scripts/backup_db.sh && ok "retention cleanup" || fail "no retention"

# 4. 환경변수 대응
grep -q "DATABASE_URL" scripts/backup_db.sh && ok "reads DATABASE_URL" || fail "no DATABASE_URL"

echo "PASS: $PASS  FAIL: $FAIL"
exit "$FAIL"
