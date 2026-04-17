"""FastAPI web dashboard.

Spec Part 12.2: dashboard pages.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware

from hydra.db.session import init_db
from hydra.web.routes import accounts, brands, campaigns, dashboard, keywords, videos, settings, pools, logs, system, export, creator, recovery
from hydra.api.workers import router as workers_router
from hydra.api.tasks import router as tasks_router
from hydra.api.presets import router as presets_router
from hydra.api.websocket import router as ws_router
from hydra.api.profile_locks import router as profile_locks_router
from hydra.api.version import router as version_router
from hydra.api.ai import router as ai_router

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

# CORS middleware for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:80", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & templates
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# API routes
app.include_router(dashboard.router, prefix="", tags=["dashboard"])
app.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
app.include_router(brands.router, prefix="/brands", tags=["brands"])
app.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
app.include_router(keywords.router, prefix="/keywords", tags=["keywords"])
app.include_router(videos.router, prefix="/videos", tags=["videos"])
app.include_router(settings.router, prefix="/settings", tags=["settings"])
app.include_router(pools.router, prefix="/pools", tags=["pools"])
app.include_router(logs.router, prefix="/logs", tags=["logs"])
app.include_router(system.router, prefix="/system", tags=["system"])
app.include_router(export.router, prefix="/export", tags=["export"])
app.include_router(creator.router, prefix="/creator", tags=["creator"])
app.include_router(recovery.router, prefix="/recovery", tags=["recovery"])
app.include_router(workers_router)
app.include_router(tasks_router)
app.include_router(presets_router)
app.include_router(ws_router)
app.include_router(profile_locks_router)
app.include_router(version_router)
app.include_router(ai_router)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


def run(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
