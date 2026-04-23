#!/usr/bin/env bash
# M2.1 — Mac 로컬 대시보드 (Vite dev) 를 VPS API 와 연결해 기동.
set -euo pipefail

cd "$(dirname "$0")/.."

SERVER_URL="${SERVER_URL:-https://hydra-prod.duckdns.org}"

echo "[dashboard] VITE_API_BASE_URL=$SERVER_URL"
echo "[dashboard] Vite dev 시작 — 포트 알림 뜨면 브라우저로 열기"
cd frontend
VITE_API_BASE_URL="$SERVER_URL" npm run dev
