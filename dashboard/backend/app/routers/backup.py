"""Configuration + SD image backup and restore endpoints."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..security import require_auth
from ..services import backups

router = APIRouter(prefix="/backup", tags=["backup"], dependencies=[Depends(require_auth)])


class RestoreBody(BaseModel):
    source: str
    confirm: str


class ConfirmBody(BaseModel):
    confirm: str


@router.get("/status")
async def status():
    """Everything the Backup panel needs in a single request."""
    detected = await asyncio.to_thread(backups.find_restore_source)
    return {
        "state": backups.state(),
        "restore_available": detected,
        "sd_backup": backups.current_sd_backup(),
        "sd_images": await asyncio.to_thread(backups.list_sd_backups),
    }


@router.post("/config")
async def run_config_backup():
    res = await asyncio.to_thread(backups.backup_config)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "backup failed"))
    return res


@router.post("/config/restore")
async def restore(body: RestoreBody):
    if body.confirm.strip().upper() != "RESTORE":
        raise HTTPException(status_code=400, detail="Type RESTORE to confirm")
    res = await asyncio.to_thread(backups.restore_config, body.source)
    if "error" in res and not res.get("restored"):
        raise HTTPException(status_code=400, detail=res.get("error", "restore failed"))
    return res


@router.post("/sd")
async def start_sd_backup(body: ConfirmBody):
    if body.confirm.strip().upper() != "BACKUP":
        raise HTTPException(status_code=400, detail="Type BACKUP to confirm")
    res = await backups.start_sd_backup()
    if not res.get("ok"):
        raise HTTPException(status_code=409, detail=res.get("error", "unable to start backup"))
    return res


@router.get("/sd")
async def sd_backup_status():
    return {"job": backups.current_sd_backup(), "images": await asyncio.to_thread(backups.list_sd_backups)}
