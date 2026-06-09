"""
/teams  –  Pre-Draft team maintenance view.

- Public GET: lists all 48 teams grouped by pot.
- Admin POST (HTMX): updates a single team's pot_number when draft_status == PRE_DRAFT.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from database import admin_client, anon_client
from models import DraftStatus, PotUpdateRequest
from auth import require_admin

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _get_draft_status() -> DraftStatus:
    res = anon_client().table("system_settings").select("draft_status").eq("id", 1).single().execute()
    return DraftStatus(res.data["draft_status"])


@router.get("/teams", response_class=HTMLResponse)
async def teams_view(request: Request):
    draft_status = _get_draft_status()
    res = anon_client().table("teams").select("*").order("pot_number").order("fifa_rank").execute()
    teams = res.data or []

    # Group by pot
    pots: dict[int, list] = {1: [], 2: [], 3: [], 4: []}
    for t in teams:
        pots.setdefault(t["pot_number"], []).append(t)

    return templates.TemplateResponse(request, "teams.html", context={
        "pots": pots,
        "draft_status": draft_status,
        "editable": draft_status == DraftStatus.PRE_DRAFT,
    })


@router.post("/teams/{team_id}/pot", response_class=HTMLResponse)
async def update_team_pot(
    request: Request,
    team_id: int,
    pot_number: int = Form(...),
    _: None = Depends(require_admin),
):
    draft_status = _get_draft_status()
    if draft_status != DraftStatus.PRE_DRAFT:
        raise HTTPException(status_code=403, detail="Draft has already started – teams are locked.")

    if pot_number not in (1, 2, 3, 4):
        raise HTTPException(status_code=422, detail="pot_number must be 1-4.")

    admin_client().table("teams").update({"pot_number": pot_number}).eq("id", team_id).execute()

    # Return the updated row as an HTMX fragment
    row = anon_client().table("teams").select("*").eq("id", team_id).single().execute().data
    return templates.TemplateResponse(request, "fragments/team_row.html", context={
        "team": row,
        "editable": True,
    })
