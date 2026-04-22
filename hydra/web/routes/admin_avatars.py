"""어드민 — 아바타 업로드/목록/삭제 (admin_session 보호).

저장 루트는 AVATAR_STORAGE_DIR env. 모든 경로는 resolve() 로 symlink/traversal 방어.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from hydra.web.routes.admin_auth import admin_session

router = APIRouter()
log = logging.getLogger("hydra.admin_avatars")

MAX_IMAGE_DIM = 800
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _storage_root() -> Path:
    return Path(os.getenv("AVATAR_STORAGE_DIR", "/var/hydra/avatars")).resolve()


def _safe_join(category: str, name: str | None = None) -> Path:
    """category + name 이 STORAGE 루트 밖으로 나가지 않도록 검증 후 Path 반환."""
    if "\x00" in category or category.startswith("/") or ".." in category.split("/"):
        raise HTTPException(400, "invalid category")
    if name is not None:
        if "/" in name or name in ("", ".", ".."):
            raise HTTPException(400, "invalid filename")

    root = _storage_root()
    target = (root / category / (name or "")).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(400, "path escape")
    return target


def _resize_if_needed(path: Path) -> None:
    try:
        from PIL import Image  # lazy import — 설치 없어도 서버는 살게
    except ImportError:
        log.warning("Pillow not installed — skipping resize")
        return
    try:
        img = Image.open(path)
        if max(img.size) > MAX_IMAGE_DIM:
            img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM))
            img.save(path, optimize=True)
    except Exception as e:
        log.warning("resize failed for %s: %s", path, e)


@router.get("/list")
def list_avatars(_session: dict = Depends(admin_session)) -> dict:
    root = _storage_root()
    if not root.exists():
        return {}
    tree: dict = {}
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        rel = p.relative_to(root)
        node = tree
        for part in rel.parts[:-1]:
            node = node.setdefault(part, {})
        node.setdefault("__files__", []).append(rel.name)
    return tree


@router.post("/upload")
async def upload_avatar(
    category: str = Form(...),
    file: UploadFile = File(...),
    _session: dict = Depends(admin_session),
) -> dict:
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(400, "filename missing")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"unsupported extension: {suffix}")

    dest = _safe_join(category, filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    _resize_if_needed(dest)
    return {"saved": str(dest.relative_to(_storage_root()))}


@router.post("/upload-zip")
async def upload_zip(
    category: str = Form(...),
    file: UploadFile = File(...),
    _session: dict = Depends(admin_session),
) -> dict:
    data = await file.read()
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(400, "not a zip file")

    root = _storage_root()
    saved: list[str] = []
    for name in z.namelist():
        if name.endswith("/") or ".." in Path(name).parts or Path(name).is_absolute():
            continue
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            continue
        dest = (root / category / name).resolve()
        try:
            dest.relative_to(root)
        except ValueError:
            continue  # escape 시도는 skip
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(name))
        _resize_if_needed(dest)
        saved.append(str(dest.relative_to(root)))
    return {"saved_count": len(saved), "saved": saved}


@router.delete("/{path:path}")
def delete_avatar(path: str, _session: dict = Depends(admin_session)) -> dict:
    root = _storage_root()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(400, "invalid path")
    if target.exists() and target.is_file():
        target.unlink()
        return {"ok": True, "deleted": path}
    raise HTTPException(404, "not found")
