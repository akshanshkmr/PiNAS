"""AI tagging endpoints — config, per-file tagging, folder batch, and search."""

import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..security import require_auth
from ..services import ai, tag_queue, tags
from ..services.files import IMAGE_EXT, resolve

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(require_auth)])


class ConfigBody(BaseModel):
    base_url: str | None = None
    model: str | None = None


class PathBody(BaseModel):
    path: str


class FolderBody(BaseModel):
    path: str
    recursive: bool = False


@router.get("/status")
async def status():
    cfg = ai.get_config()
    h = await ai.health()
    return {"config": {"base_url": cfg.base_url, "model": cfg.model}, "health": h, "cache": tags.stats()}


@router.put("/config")
async def config(body: ConfigBody):
    cfg = ai.set_config(base_url=body.base_url, model=body.model)
    return {"ok": True, "config": {"base_url": cfg.base_url, "model": cfg.model}}


@router.post("/tag")
async def tag_one(body: PathBody):
    try:
        target = await asyncio.to_thread(resolve, body.path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not target.is_file() or target.suffix.lower() not in IMAGE_EXT:
        raise HTTPException(status_code=400, detail="Only image files can be tagged (for now).")
    try:
        result = await ai.describe_image(str(target))
    except (RuntimeError, FileNotFoundError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    st = await asyncio.to_thread(os.stat, str(target))
    await asyncio.to_thread(tags.put, str(target), st.st_mtime, result["caption"], result["tags"])
    return {"ok": True, "caption": result["caption"], "tags": result["tags"]}


@router.post("/tag-folder")
async def tag_folder(body: FolderBody):
    try:
        added = await tag_queue.enqueue_folder(body.path, recursive=body.recursive)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"ok": True, "queued": added}


@router.get("/queue")
async def queue():
    return await tag_queue.snapshot()


@router.post("/queue/clear")
async def queue_clear():
    await tag_queue.clear()
    return {"ok": True}


@router.get("/search")
async def search(q: str = Query(..., min_length=1), root: str | None = None, limit: int = 200):
    results = await asyncio.to_thread(tags.search, q, root, limit)
    return {"query": q, "results": results}
