"""FastAPI application for QuitSmoking Home Assistant add-on."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .scheduler import _notification_scheduler
from .ws_listener import _ws_event_listener
from .routes import status, history, config, catchup, health, cravings, actions, debug

INGRESS_PATH = os.environ.get("INGRESS_PATH", "")

_scheduler_task: Optional[asyncio.Task] = None
_ws_listener_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background scheduler and websocket listener on app startup."""
    global _scheduler_task, _ws_listener_task
    _scheduler_task = asyncio.create_task(_notification_scheduler())
    _ws_listener_task = asyncio.create_task(_ws_event_listener())
    yield
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    if _ws_listener_task:
        _ws_listener_task.cancel()
        try:
            await _ws_listener_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="QuitSmoking", root_path=INGRESS_PATH, lifespan=lifespan)

# Include all route modules
app.include_router(status.router)
app.include_router(history.router)
app.include_router(config.router)
app.include_router(catchup.router)
app.include_router(health.router)
app.include_router(cravings.router)
app.include_router(actions.router)
app.include_router(debug.router)

# ---------------------------------------------------------------------------
# Static files (frontend)
# ---------------------------------------------------------------------------

FRONTEND_DIR = "/app/frontend/dist"
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
