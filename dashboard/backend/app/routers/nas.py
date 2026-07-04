import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..security import require_auth
from ..services import nas, smart
from ..services.shell import CmdResult

router = APIRouter(prefix="/nas", tags=["nas"], dependencies=[Depends(require_auth)])


class CreateRaidRequest(BaseModel):
    disks: list[str]
    level: str
    mountpoint: str = nas.DEFAULT_MOUNTPOINT
    confirm: str


class MountRequest(BaseModel):
    mountpoint: str = nas.DEFAULT_MOUNTPOINT
    persist: bool = True


class SyncRequest(BaseModel):
    action: str = "repair"
    confirm: str


class ConfirmRequest(BaseModel):
    confirm: str


class ShareModel(BaseModel):
    name: str
    path: str
    allow_guest: bool = False
    read_only: bool = False


class SharesRequest(BaseModel):
    shares: list[ShareModel] = Field(default_factory=list)


class SambaUserRequest(BaseModel):
    username: str
    password: str


def _unwrap(res: CmdResult) -> dict:
    if not res.ok:
        raise HTTPException(status_code=500, detail=res.error or "Operation failed")
    return {"ok": True, "message": res.output}


def _check_confirm(given: str, expected: str):
    if given.strip().upper() != expected:
        raise HTTPException(status_code=400, detail=f"Type {expected} to confirm")


@router.get("/overview")
async def overview():
    return await asyncio.to_thread(nas.overview)


@router.get("/smart")
async def smart_health():
    return {"drives": await asyncio.to_thread(smart.smart_report)}


@router.post("/raid")
async def create_raid(body: CreateRaidRequest):
    _check_confirm(body.confirm, "CREATE")
    res = await asyncio.to_thread(nas.create_raid, body.disks, body.level, body.mountpoint)
    return _unwrap(res)


@router.post("/raid/assemble")
async def assemble():
    return _unwrap(await asyncio.to_thread(nas.assemble_arrays))


@router.get("/raid/{md_name}")
async def raid_detail(md_name: str):
    res = await asyncio.to_thread(nas.raid_detail, md_name)
    if not res.ok:
        raise HTTPException(status_code=500, detail=res.error)
    return {"ok": True, "detail": res.output}


@router.post("/raid/{md_name}/mount")
async def mount(md_name: str, body: MountRequest):
    return _unwrap(await asyncio.to_thread(nas.mount_array, md_name, body.mountpoint, body.persist))


@router.post("/raid/{md_name}/unmount")
async def unmount(md_name: str):
    return _unwrap(await asyncio.to_thread(nas.unmount_array, md_name))


@router.post("/raid/{md_name}/stop")
async def stop(md_name: str, body: ConfirmRequest):
    _check_confirm(body.confirm, "STOP")
    return _unwrap(await asyncio.to_thread(nas.stop_array, md_name))


@router.post("/raid/{md_name}/sync")
async def sync(md_name: str, body: SyncRequest):
    if body.action != "idle":
        _check_confirm(body.confirm, "REPAIR" if body.action == "repair" else "CHECK")
    return _unwrap(await asyncio.to_thread(nas.sync_array, md_name, body.action))


@router.put("/samba/shares")
async def set_shares(body: SharesRequest):
    shares = [s.model_dump() for s in body.shares]
    return _unwrap(await asyncio.to_thread(nas.configure_shares, shares))


@router.post("/samba/users")
async def add_user(body: SambaUserRequest):
    return _unwrap(await asyncio.to_thread(nas.add_samba_user, body.username, body.password))


@router.post("/samba/users/{username}/disable")
async def disable_user(username: str):
    return _unwrap(await asyncio.to_thread(nas.disable_samba_user, username))
