import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from ..security import require_auth
from ..services.monitor import SAMPLE_INTERVAL, monitor

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_auth)])


@router.get("/stats")
async def stats():
    """One-shot snapshot. Kept for debugging and non-streaming clients."""
    return await asyncio.to_thread(monitor.snapshot)


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
