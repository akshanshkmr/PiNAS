import asyncio
import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..security import require_auth
from ..services import smart
from ..services.monitor import SAMPLE_INTERVAL, monitor
from ..services.shell import run

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_auth)])


_REPO_ROOT = Path(__file__).resolve().parents[3].parent  # /home/akshansh/homeserver


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


def _version_info() -> dict:
    """Short git SHA + commit date so the popup can identify what's running.

    Falls back to placeholders in case the repo has no git metadata
    (e.g., someone unpacked a tarball)."""
    root = str(_REPO_ROOT)
    sha = run("git", "-C", root, "rev-parse", "--short", "HEAD", timeout=5)
    when = run("git", "-C", root, "log", "-1", "--format=%cI", "HEAD", timeout=5)
    return {
        "commit": sha.output.strip() if sha.ok else "unknown",
        "committed_at": when.output.strip() if when.ok else None,
        "repo_url": "https://github.com/akshanshkmr/PiNAS",
    }


@router.get("/version")
async def version():
    return await asyncio.to_thread(_version_info)


@router.post("/restart")
async def restart_dashboard():
    """Restart the `dashboard.service` unit from inside itself.

    We detach with start_new_session so systemd can stop the current
    process without the child dying with us. The client will see the
    connection drop, then reconnect once uvicorn is back."""
    try:
        subprocess.Popen(
            ["sudo", "-n", "systemctl", "restart", "dashboard"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "message": "Restart queued — the dashboard will be back in a few seconds."}


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
