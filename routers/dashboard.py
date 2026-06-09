"""
/dashboard         – Central hub: trend chart + leaderboard + teams matrix.
/dashboard/chart-data       – JSON series for Chart.js.
/dashboard/user/{id}/breakdown – HTMX fragment: per-user drill-down drawer.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from scoring_engine import build_leaderboard, get_points_timeline, get_user_breakdown, get_teams_matrix

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    leaderboard = build_leaderboard()
    return templates.TemplateResponse(request, "dashboard.html", context={
        "leaderboard": leaderboard,
    })


@router.get("/dashboard/chart-data")
async def chart_data():
    """Returns Chart.js-compatible JSON for the points trend visualisation."""
    return JSONResponse(get_points_timeline())


@router.get("/dashboard/user/{user_id}/breakdown", response_class=HTMLResponse)
async def user_breakdown(request: Request, user_id: int):
    """
    HTMX fragment – replaces the clicked leaderboard row's breakdown drawer.
    Triggered by: hx-get="/dashboard/user/{user_id}/breakdown"
    """
    data = get_user_breakdown(user_id)
    return templates.TemplateResponse(request, "fragments/user_breakdown.html", context={
        "breakdown": data,
    })


@router.get("/dashboard/teams-matrix", response_class=HTMLResponse)
async def teams_matrix_fragment(request: Request):
    """
    HTMX fragment – the full Teams & Owners matrix swap target.
    Loaded lazily when the user clicks the [ ⚽ Teams & Owners Matrix ] toggle.
    """
    matrix = get_teams_matrix()
    return templates.TemplateResponse(request, "fragments/teams_matrix.html", context={
        "matrix": matrix,
    })
