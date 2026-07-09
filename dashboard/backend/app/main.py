"""PiNAS backend.

Serves the JSON API under /api and the built React SPA at the site root.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import auth, controls, files, nas, services, system, terminal
from .services.monitor import monitor

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor.start()
    yield
    monitor.stop()


app = FastAPI(title="PiNAS", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

for router in (
    auth.router,
    system.router,
    controls.router,
    nas.router,
    files.router,
    services.router,
    terminal.router,
):
    app.include_router(router, prefix="/api")


if FRONTEND_DIST.is_dir():
    # Serve real assets from disk first; anything that isn't a file falls back
    # to index.html so client-side routes like /storage or /files survive a
    # hard refresh. Registered LAST so /api/* routes still win.
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    if (FRONTEND_DIST / "fonts").is_dir():
        app.mount("/fonts", StaticFiles(directory=FRONTEND_DIST / "fonts"), name="fonts")

    _index = FRONTEND_DIST / "index.html"

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str, request: Request):
        # Try a real file at the requested path first (favicon.svg etc.)
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_index)
else:

    @app.get("/")
    def missing_frontend():
        return {"error": "Frontend not built. Run: npm --prefix dashboard/frontend run build"}
