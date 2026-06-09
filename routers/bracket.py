"""
/bracket  –  Knockout stage bracket view.

Displays all post-group matches (R32 → Final) grouped by round,
with scores, TBD labels for undecided slots, and strikethrough on eliminated teams.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from scoring_engine import get_bracket_data

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/bracket", response_class=HTMLResponse)
async def bracket_view(request: Request):
    data = get_bracket_data()
    return templates.TemplateResponse(request, "bracket.html", context={
        "rounds":       data["rounds"],
        "stage_labels": data["stage_labels"],
    })
