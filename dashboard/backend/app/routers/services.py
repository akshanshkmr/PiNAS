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


class ToggleRequest(BaseModel):
    enabled: bool


@router.put("/tailscale/exit-node")
async def tailscale_exit_node(body: ToggleRequest):
    res = await asyncio.to_thread(tailscale.set_exit_node, body.enabled)
    if not res.ok:
        raise HTTPException(status_code=500, detail=res.error)
    msg = ("This Pi is now advertising as an exit node. Approve it in the "
           "tailnet admin console to let devices route through it.") if body.enabled \
          else "Exit-node advertisement disabled."
    return {"ok": True, "message": msg}


@router.put("/tailscale/funnel")
async def tailscale_funnel(body: ToggleRequest):
    res = await asyncio.to_thread(tailscale.set_funnel, body.enabled)
    if not res.ok:
        raise HTTPException(status_code=500, detail=res.error)
    return {
        "ok": True,
        "message": "Funnel exposing /s/ to the public internet."
                   if body.enabled else "Funnel for /s/ turned off.",
    }


@router.put("/tailscale/serve")
async def tailscale_serve(body: ToggleRequest):
    res = await asyncio.to_thread(tailscale.set_serve, body.enabled)
    if not res.ok:
        raise HTTPException(status_code=500, detail=res.error)
    return {
        "ok": True,
        "message": "Dashboard is now reachable at https://<host>.ts.net/."
                   if body.enabled else res.output or "Dashboard serve disabled.",
    }


@router.post("/tailscale/login")
async def tailscale_login():
    """Kick off the interactive login flow and return the auth URL to open."""
    url, err = await asyncio.to_thread(tailscale.start_login)
    if err:
        raise HTTPException(status_code=500, detail=err)
    if not url:
        # Already logged in and Running — nothing to do.
        return {"ok": True, "auth_url": None, "message": "Tailscale is already logged in."}
    return {"ok": True, "auth_url": url,
            "message": "Open the auth URL to complete login. Status will refresh automatically."}
