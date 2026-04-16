from fastapi import APIRouter

router = APIRouter(prefix="/api/version", tags=["version"])

CURRENT_VERSION = "0.1.0"

@router.get("/")
def get_version():
    return {"version": CURRENT_VERSION}

@router.get("/worker-latest")
def get_worker_latest_version():
    """Worker가 확인하는 최신 버전."""
    return {"version": CURRENT_VERSION, "download_url": None}
