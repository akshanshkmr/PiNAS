import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..security import require_auth
from ..services import smart
from ..services.monitor import SAMPLE_INTERVAL, monitor

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_auth)])


@router.get("/stats")
async def stats():
    """One-shot snapshot. Kept for debugging and non-streaming clients."""
    return await asyncio.to_thread(monitor.snapshot)


def _collect_health_alerts() -> list[dict]:
    """Distil SMART reports into alerts the System tab can surface.

    A drive is 'crit' if smartctl's overall self-assessment failed; 'warn'
    if it passed but has any warnings we care about (reallocated / pending
    / uncorrectable sectors on ATA, low spare or media errors on NVMe).
    Drives that report cleanly produce nothing — the empty list is the
    happy path the banner hides on."""
    alerts: list[dict] = []
    for r in smart.smart_report():
        if not r.get("available"):
            # Missing smartctl or an unreadable drive is worth surfacing
            # once — it's the difference between "clean" and "unknown".
            alerts.append({
                "device": r["device"],
                "model": r.get("model"),
                "severity": "warn",
                "reason": r.get("error") or "SMART unavailable",
            })
            continue
        warnings = r.get("warnings") or []
        if r.get("health") == "failed":
            alerts.append({
                "device": r["device"],
                "model": r.get("model"),
                "severity": "crit",
                "reason": warnings[0] if warnings else "SMART self-assessment failed",
            })
        elif warnings:
            alerts.append({
                "device": r["device"],
                "model": r.get("model"),
                "severity": "warn",
                "reason": warnings[0],
            })
    return alerts


@router.get("/health")
async def health():
    """Aggregated drive-health alerts for the System-tab banner.

    Polled every few minutes by the frontend; SMART data itself doesn't
    change on a second-scale, so this stays off the per-second SSE stream."""
    return {"alerts": await asyncio.to_thread(_collect_health_alerts)}


@router.get("/stream")
async def stream(request: Request):
    """Server-Sent Events stream of telemetry, one frame per sample interval.

    The browser authenticates via the session cookie (EventSource sends it on
    same-origin requests), so the router-level require_auth dependency applies.
    """

    async def events():
        while True:
            if await request.is_disconnected():
                break
            snapshot = await asyncio.to_thread(monitor.snapshot)
            yield f"data: {json.dumps(snapshot)}\n\n"
            await asyncio.sleep(SAMPLE_INTERVAL)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering where honoured
        },
    )
