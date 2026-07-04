import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..security import require_auth
from ..services import system_services, tailscale

router = APIRouter(prefix="/services", tags=["services"], dependencies=[Depends(require_auth)])


# -------------------- systemd --------------------

@router.get("")
async def list_services():
    return {"units": await asyncio.to_thread(system_services.list_services)}


@router.post("/units/{unit}/{action}")
async def control_unit(unit: str, action: str):
    res = await asyncio.to_thread(system_services.control, unit, action)
    if not res.ok:
        raise HTTPException(status_code=400 if "Unknown" in res.error or "Invalid" in res.error else 500, detail=res.error)
    return {"ok": True, "message": f"{unit}: {action} issued."}


@router.get("/units/{unit}/logs")
async def unit_logs(unit: str, lines: int = 200):
    res = await asyncio.to_thread(system_services.logs, unit, lines)
    if not res.ok:
        raise HTTPException(status_code=400 if "Unknown" in res.error else 500, detail=res.error)
    return {"ok": True, "logs": res.output or "(no log output)"}


# -------------------- tailscale --------------------

class ConnectionRequest(BaseModel):
    connect: bool


@router.get("/tailscale")
async def tailscale_status():
    return await asyncio.to_thread(tailscale.status)


@router.put("/tailscale/connection")
async def tailscale_connection(body: ConnectionRequest):
    res = await asyncio.to_thread(tailscale.set_connection, body.connect)
    if not res.ok:
        raise HTTPException(status_code=500, detail=res.error)
    return {"ok": True, "message": "Tailscale connected." if body.connect else "Tailscale disconnected."}
