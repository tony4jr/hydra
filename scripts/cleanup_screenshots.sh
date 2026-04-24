#!/usr/bin/env bash
# 7일 이상 된 스크린샷 + 빈 날짜 디렉토리 삭제. cron 매일 03:30.
# /etc/cron.d/hydra-screenshot-cleanup 에 다음 줄:
#   30 3 * * * deployer /opt/hydra/scripts/cleanup_screenshots.sh
set -euo pipefail

DIR="${HYDRA_SCREENSHOT_DIR:-/var/www/hydra/screenshots}"
[ -d "$DIR" ] || exit 0

# 7일 지난 파일 삭제
find "$DIR" -type f -mtime +7 -delete
# 빈 디렉토리 정리
find "$DIR" -type d -empty -delete 2>/dev/null || true

echo "[cleanup_screenshots] $(date -Iseconds) done"
