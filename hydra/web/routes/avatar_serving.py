"""워커 대상 아바타 파일 서빙.

GET /api/avatars/{path} — X-Worker-Token 인증 필수. path traversal 방어.
저장 루트는 AVATAR_STORAGE_DIR env (기본 /var/hydra/avatars).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from hydra.db.models import Worker
from hydra.web.routes.worker_api import worker_auth

router = APIRouter()


def _storage_root() -> Path:
    return Path(os.getenv("AVATAR_STORAGE_DIR", "/var/hydra/avatars")).resolve()


@router.get("/{path:path}")
def get_avatar(path: str, _worker: Worker = Depends(worker_auth)) -> FileResponse:
    root = _storage_root()
    requested = (root / path).resolve()
    # symlink/traversal 방어 — 해석 후에도 root 안에 있어야 함
    try:
        requested.relative_to(root)
    except ValueError:
        raise HTTPException(400, "invalid path")
    if not requested.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(requested)
