"""Pi Admin Dashboard backend.

Serves the JSON API under /status/api and the built React SPA under /status,
matching the Apache reverse-proxy prefix.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .routers import ai, auth, controls, files, nas, services, system, terminal
from .services import tag_queue, tags
from .services.monitor import monitor

BASE_PATH = "/status"
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor.start()
    tags.init()
    tag_queue.start()
    yield
    monitor.stop()


app = FastAPI(title="Pi Admin Dashboard", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

for router in (
    auth.router,
    system.router,
    controls.router,
    nas.router,
    files.router,
    ai.router,
    services.router,
    terminal.router,
):
    app.include_router(router, prefix=f"{BASE_PATH}/api")


@app.get("/")
def root():
    return RedirectResponse(url=f"{BASE_PATH}/")


if FRONTEND_DIST.is_dir():
    app.mount(BASE_PATH, StaticFiles(directory=FRONTEND_DIST, html=True), name="spa")
else:

    @app.get(BASE_PATH)
    @app.get(f"{BASE_PATH}/")
    def missing_frontend():
        return {"error": "Frontend not built. Run: npm --prefix dashboard/frontend run build"}
