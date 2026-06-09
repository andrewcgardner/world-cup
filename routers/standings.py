"""
/standings  –  Group stage standings grid.

Shows all 12 groups with each team's W/D/L/GF/GA/GD/Pts stats,
current pool points, and the manager who drafted that team.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from scoring_engine import get_group_standings_page_data

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/standings", response_class=HTMLResponse)
async def standings_view(request: Request):
    groups = get_group_standings_page_data()
    return templates.TemplateResponse(request, "standings.html", context={
        "groups": groups,
    })
