"""
World Cup 2026 Pool Application
================================
Entry point – mounts all routers and configures Jinja2 + static files.

Run with:
    uvicorn main:app --reload
"""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from routers import admin, bracket, dashboard, matches, reveal, standings, teams, worker

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="World Cup 2026 Pool",
    description="Snake-draft tournament pool with live scoring.",
    version="0.1.0",
)

# ── Static files & templates ───────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Routers ────────────────────────────────────────────────────────────────
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
