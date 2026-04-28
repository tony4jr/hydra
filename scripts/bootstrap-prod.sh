#!/usr/bin/env bash
# Bootstrap script — Mac 에서 1회 실행. 이후 VPS 는 자동 sync.
#
# 하는 일:
#   1. VPS 에 최신 코드 pull
#   2. 새 systemd units 설치 (deploy + auto-pull timer)
#   3. 첫 deploy 실행 (frontend build 포함)
#   4. auto-pull timer 활성화 → 이후 push 만 하면 60초 내 자동 반영
#   5. 검증: 사이트 reachable + frontend version 확인
#
# Usage: ./scripts/bootstrap-prod.sh

set -euo pipefail

SSH_KEY="$HOME/.ssh/hydra_prod"
HOST="deployer@158.247.232.101"
REPO_DIR="/opt/hydra"

ssh_run() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$HOST" "$@"
}

echo "── 1. Pull latest on VPS ──"
ssh_run "cd $REPO_DIR && git fetch origin main && git reset --hard origin/main && git rev-parse --short HEAD"

echo
echo "── 2. Install systemd units ──"
ssh_run "set -e
cd $REPO_DIR
sudo cp deploy/hydra-deploy.service     /etc/systemd/system/
sudo cp deploy/hydra-auto-pull.service  /etc/systemd/system/
sudo cp deploy/hydra-auto-pull.timer    /etc/systemd/system/
sudo systemctl daemon-reload
echo '✅ units installed'
"

echo
echo "── 3. Run first deploy (frontend build, may take 2-3min on first run) ──"
ssh_run "sudo systemctl start hydra-deploy.service"
echo "deploy started — waiting up to 5min for completion…"

# Wait for deploy to finish (systemctl is-active returns 'inactive' when oneshot done)
START_TS=$(date +%s)
while true; do
    STATE=$(ssh_run "systemctl is-active hydra-deploy.service" 2>&1 || true)
    ELAPSED=$(( $(date +%s) - START_TS ))
    if [[ "$STATE" == "inactive" || "$STATE" == "failed" ]]; then
        break
    fi
    if [[ $ELAPSED -gt 300 ]]; then
        echo "⚠️  deploy still active after 5min — check log manually"
        break
    fi
    printf "."
    sleep 5
done
echo
echo
echo "── 4. Deploy result ──"
ssh_run "systemctl status hydra-deploy.service --no-pager -l | head -20"
echo
echo "── deploy.log tail ──"
ssh_run "sudo tail -50 /var/log/hydra/deploy.log"

echo
echo "── 5. Enable auto-pull timer (VPS will sync from GitHub every 60s from now on) ──"
ssh_run "sudo systemctl enable --now hydra-auto-pull.timer && systemctl list-timers hydra-auto-pull.timer --no-pager"

echo
echo "── 6. Verify site ──"
sleep 3
HTTP_CODE=$(curl -sI -o /dev/null -w "%{http_code}" https://hydra-prod.duckdns.org/)
CSS_FILE=$(curl -s https://hydra-prod.duckdns.org/ | grep -oE 'index-[A-Za-z0-9]+\.css' | head -1)
HAS_AURORA=$(curl -s "https://hydra-prod.duckdns.org/assets/$CSS_FILE" | grep -c "hydra-aurora" || true)

echo "site HTTP:    $HTTP_CODE"
echo "CSS file:     $CSS_FILE"
echo "aurora class: $HAS_AURORA matches"

if [[ "$HTTP_CODE" == "200" && "$HAS_AURORA" -gt 0 ]]; then
    echo
    echo "✅ ALL DONE — VPS now auto-pulls from GitHub every 60s"
    echo "   Push to main → automatic deploy in ~60s"
else
    echo
    echo "❌ Verification failed — check /var/log/hydra/deploy.log"
    exit 1
fi
