#!/bin/bash
# HYDRA v2 개발 환경 시작
# 백엔드 + 프론트엔드 동시 실행

echo "=== HYDRA v2 Development ==="
echo ""

# Backend
echo "[1/2] Starting backend (FastAPI)..."
cd "$(dirname "$0")/.."
.venv/bin/python -m uvicorn hydra.web.app:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Frontend
echo "[2/2] Starting frontend (Vite)..."
cd frontend
pnpm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
