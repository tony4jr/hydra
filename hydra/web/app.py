"""FastAPI web dashboard.

Spec Part 12.2: dashboard pages.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from hydra.db.session import init_db
from hydra.web.routes import accounts, brands, campaigns, dashboard, keywords, videos, settings, pools, logs, system, export

app = FastAPI(title="HYDRA Dashboard", version="1.0")

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


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.on_event("startup")
def startup():
    init_db()


def run(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
