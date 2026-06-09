"""
World Cup 2026 Pool Application
================================
Entry point – mounts all routers and configures Jinja2 + static files.

Run with:
    uvicorn main:app --reload
"""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from routers import admin, bracket, dashboard, matches, reveal, standings, teams, worker
from routers import pool_auth

logging.basicConfig(level=logging.INFO)

# ── Pool password gate ─────────────────────────────────────────────────────
_GATE_TEMPLATE = Path("templates/password_gate.html").read_text()

# Routes that bypass the password gate entirely.
_PUBLIC_PREFIXES = (
    "/auth",    # login route itself
    "/static",  # CSS, JS, images
)


class PoolAuthMiddleware(BaseHTTPMiddleware):
    """
    Intercepts every request and checks for the pool_authenticated cookie.
    Unauthenticated requests receive the password gate HTML instead of the
    normal application response.
    """

    async def dispatch(self, request: Request, call_next):
        # Always allow public routes through
        if any(request.url.path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        authenticated = request.cookies.get("pool_authenticated") == "true"
        if not authenticated:
            return HTMLResponse(content=_GATE_TEMPLATE, status_code=200)

        return await call_next(request)


app = FastAPI(
    title="World Cup 2026 Pool",
    description="Snake-draft tournament pool with live scoring.",
    version="0.1.0",
)

app.add_middleware(PoolAuthMiddleware)

# ── Static files & templates ───────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(pool_auth.router)
app.include_router(teams.router)
app.include_router(matches.router)
app.include_router(standings.router)
app.include_router(bracket.router)
app.include_router(reveal.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(worker.router)


@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")
