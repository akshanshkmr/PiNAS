import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..security import require_auth
from ..services import controls

router = APIRouter(prefix="/controls", tags=["controls"], dependencies=[Depends(require_auth)])


class PowerRequest(BaseModel):
    action: str  # "reboot" | "shutdown"
    confirm: str


class CpuFanRequest(BaseModel):
    on: bool


class PironmanRequest(BaseModel):
    rgb_enable: bool | None = None
    rgb_color: str | None = None
    rgb_brightness: int | None = None
    rgb_style: str | None = None
    rgb_speed: int | None = None
    gpio_fan_mode: int | None = None
    oled_enable: bool | None = None
    oled_rotation: int | None = None
    oled_disk: str | None = None
    oled_network_interface: str | None = None
    oled_sleep_timeout: int | None = None


@router.post("/power")
async def power(body: PowerRequest):
    expected = {"reboot": "REBOOT", "shutdown": "SHUTDOWN"}.get(body.action)
    if not expected:
        raise HTTPException(status_code=400, detail="Unknown power action")
    if body.confirm.strip().upper() != expected:
        raise HTTPException(status_code=400, detail=f"Type {expected} to confirm")
    fn = controls.reboot if body.action == "reboot" else controls.shutdown
    res = await asyncio.to_thread(fn)
    if not res.ok:
        raise HTTPException(status_code=500, detail=res.error)
    return {"ok": True, "message": f"{body.action.capitalize()} command issued."}


class ConfirmRequest(BaseModel):
    confirm: str


@router.get("/updates")
async def updates():
    return await asyncio.to_thread(controls.check_updates)


@router.post("/updates/apply")
async def apply_updates(body: ConfirmRequest):
    if body.confirm.strip().upper() != "UPGRADE":
        raise HTTPException(status_code=400, detail="Type UPGRADE to confirm")
    return StreamingResponse(
        controls.apply_updates_stream(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/pironman")
async def pironman_config():
    return await asyncio.to_thread(controls.get_pironman_config)


@router.put("/pironman")
async def apply_pironman(body: PironmanRequest):
    settings = {k: v for k, v in body.model_dump().items() if v is not None}
    if "rgb_style" in settings and settings["rgb_style"] not in controls.RGB_STYLES:
        raise HTTPException(status_code=400, detail="Unknown RGB style")
    if "gpio_fan_mode" in settings and not 0 <= settings["gpio_fan_mode"] <= 4:
        raise HTTPException(status_code=400, detail="Fan mode must be 0-4")
    if "rgb_color" in settings:
        color = settings["rgb_color"].lstrip("#").lower()
        if len(color) != 6 or any(c not in "0123456789abcdef" for c in color):
            raise HTTPException(status_code=400, detail="RGB color must be a hex value like 60a5fa")
        settings["rgb_color"] = color
    res = await asyncio.to_thread(controls.apply_pironman_config, settings)
    if not res.ok:
        raise HTTPException(status_code=500, detail=res.error)
    return {"ok": True, "message": "Settings applied, pironman5 restarted."}


@router.get("/cpu-fan")
async def cpu_fan():
    return await asyncio.to_thread(controls.get_cpu_fan)


@router.put("/cpu-fan")
async def set_cpu_fan(body: CpuFanRequest):
    res = await asyncio.to_thread(controls.set_cpu_fan, body.on)
    if not res.ok:
        raise HTTPException(status_code=500, detail=res.error)
    return {"ok": True, "on": body.on}
