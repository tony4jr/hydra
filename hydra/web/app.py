"""FastAPI web dashboard.

Spec Part 12.2: dashboard pages.
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware

from hydra.db.session import init_db
from hydra.web.routes import accounts, brands, campaigns, dashboard, keywords, videos, settings, pools, logs, system, export, creator, recovery, campaign_videos
from hydra.web.routes import (
    admin_auth, admin_workers, admin_avatars, admin_deploy, admin_audit,
    admin_accounts, admin_tasks, admin_adspower, admin_collection,
    avatar_serving, worker_api, tasks_api,
    analytics,
)
from hydra.api.workers import router as workers_router
from hydra.api.tasks import router as tasks_router
from hydra.api.presets import router as presets_router
from hydra.api.websocket import router as ws_router
from hydra.api.profile_locks import router as profile_locks_router
from hydra.api.version import router as version_router
from hydra.api.ai import router as ai_router

# Task 25.5 — 모든 어드민 성격 라우터에 세션 JWT 강제
from hydra.web.routes.admin_auth import admin_session
_ADMIN_DEPS = [Depends(admin_session)]

@asynccontextmanager
async def lifespan(app):
    from hydra.services.background import scheduler
    init_db()
    # Start background scheduler
    task = asyncio.create_task(scheduler.start())
    yield
    scheduler.stop()
    task.cancel()

app = FastAPI(title="HYDRA Dashboard", version="1.0", lifespan=lifespan)

# CORS — 운영 도메인 + 로컬 dev. env 로 override 가능.
# allow_credentials=True 이므로 "*" 금지 — 명시적 origin 리스트만.
_cors_env = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:80,http://localhost",
)
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Task 39.5: /api/admin/* 쓰기 감사 로그 자동 기록
from hydra.web.middleware.audit_middleware import AuditLogMiddleware
app.add_middleware(AuditLogMiddleware)

# Static & templates
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# API routes — 어드민 성격 전부 admin_session 강제 (Task 25.5)
# 예외: dashboard (HTML 템플릿 루트) 는 Phase 1c 재설계 전까지 공개 유지
# 예외: workers_router/tasks_router (legacy 워커 API, X-Worker-Token 자체 인증)
app.include_router(dashboard.router, prefix="", tags=["dashboard"])
app.include_router(accounts.router, prefix="/accounts", tags=["accounts"], dependencies=_ADMIN_DEPS)
app.include_router(brands.router, prefix="/brands", tags=["brands"], dependencies=_ADMIN_DEPS)
app.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"], dependencies=_ADMIN_DEPS)
app.include_router(campaign_videos.router, prefix="/api/campaigns", tags=["campaign-videos"], dependencies=_ADMIN_DEPS)
app.include_router(keywords.router, prefix="/keywords", tags=["keywords"], dependencies=_ADMIN_DEPS)
app.include_router(videos.router, prefix="/videos", tags=["videos"], dependencies=_ADMIN_DEPS)
app.include_router(settings.router, prefix="/settings", tags=["settings"], dependencies=_ADMIN_DEPS)
app.include_router(pools.router, prefix="/pools", tags=["pools"], dependencies=_ADMIN_DEPS)
app.include_router(logs.router, prefix="/logs", tags=["logs"], dependencies=_ADMIN_DEPS)
app.include_router(system.router, prefix="/system", tags=["system"], dependencies=_ADMIN_DEPS)
app.include_router(export.router, prefix="/export", tags=["export"], dependencies=_ADMIN_DEPS)
app.include_router(creator.router, prefix="/creator", tags=["creator"], dependencies=_ADMIN_DEPS)
app.include_router(recovery.router, prefix="/recovery", tags=["recovery"], dependencies=_ADMIN_DEPS)
# Legacy workers/tasks — 워커 X-Worker-Token 인증 유지 (admin 아님)
app.include_router(workers_router)
app.include_router(tasks_router)
# Admin 성격 — 세션 필수
app.include_router(presets_router, dependencies=_ADMIN_DEPS)
app.include_router(profile_locks_router, dependencies=_ADMIN_DEPS)
app.include_router(version_router, dependencies=_ADMIN_DEPS)
app.include_router(ai_router)  # 개별 라우트가 worker_auth 로 보호 (M1-9)
# WebSocket — Starlette dependencies 미지원, 별도 인증 핸들러 추후
app.include_router(ws_router)

# --- 신규 /api/admin/* + /api/workers, /api/tasks 네임스페이스 (Task 17 stub) ---
# 실제 엔드포인트는 후속 task 에서 채워짐. 기존 flat routes 는 유지 (Task 17.6 에서 통합).
# admin_auth 는 login/logout 공개 (로그인 자체는 토큰 없이)
app.include_router(admin_auth.router,    prefix="/api/admin/auth",    tags=["admin-auth"])
# 나머지 /api/admin/* 는 router-level dependencies 로 세션 강제 (defense in depth —
# 라우트 내부 Depends 와 이중 검증이지만 비용 미미)
app.include_router(admin_workers.router, prefix="/api/admin/workers", tags=["admin-workers"], dependencies=_ADMIN_DEPS)
app.include_router(admin_avatars.router, prefix="/api/admin/avatars", tags=["admin-avatars"], dependencies=_ADMIN_DEPS)
app.include_router(admin_deploy.router,  prefix="/api/admin",         tags=["admin-deploy"],  dependencies=_ADMIN_DEPS)
app.include_router(admin_audit.router,   prefix="/api/admin/audit",   tags=["admin-audit"],   dependencies=_ADMIN_DEPS)
app.include_router(admin_adspower.router, prefix="/api/admin/adspower", tags=["admin-adspower"], dependencies=_ADMIN_DEPS)
app.include_router(admin_accounts.router, prefix="/api/admin/accounts",
                   tags=["admin-accounts"], dependencies=_ADMIN_DEPS)
app.include_router(admin_tasks.router, prefix="/api/admin/tasks",
                   tags=["admin-tasks"], dependencies=_ADMIN_DEPS)
app.include_router(admin_collection.router, prefix="/api/admin/collection",
                   tags=["admin-collection"], dependencies=_ADMIN_DEPS)
app.include_router(avatar_serving.router, prefix="/api/avatars",      tags=["avatar-static"])
# Task 20: 신규 워커 프로토콜 (/enroll, /heartbeat/v2). legacy /api/workers/register,
# /heartbeat 는 hydra.api.workers 에 공존 유지 (Phase 1d 전환 완료 후 제거 예정).
app.include_router(worker_api.router,    prefix="/api/workers",       tags=["worker-v2"])
# Task 21: 신규 태스크 큐 (/api/tasks/v2/*) — SKIP LOCKED + ProfileLock.
app.include_router(tasks_api.router,     prefix="/api/tasks/v2",      tags=["tasks-v2"])
app.include_router(analytics.router,                                  tags=["analytics"], dependencies=_ADMIN_DEPS)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


def run(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
