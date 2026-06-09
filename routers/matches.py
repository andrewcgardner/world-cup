"""
/matches  –  Public schedule & results dashboard.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from database import admin_client
from models import MatchStatus

router = APIRouter()
templates = Jinja2Templates(directory="templates")
log = logging.getLogger(__name__)


@router.get("/matches", response_class=HTMLResponse)
async def matches_view(request: Request):
    # ── Step 1: fetch all matches (flat columns, no join) ──────────────────
    # Uses the service-role client so RLS never interferes with this public
    # read. The matches schedule is non-sensitive tournament data, so
    # bypassing RLS here is intentional. If you add a public SELECT policy
    # (`CREATE POLICY … USING (TRUE)`) you can switch back to anon_client().
    res = admin_client().table("matches").select("*").order("kickoff_time").execute()
    all_matches = res.data or []

    if not all_matches:
        log.warning("matches_view: no rows returned from public.matches")

    # ── Step 2: resolve team names with one batched lookup ─────────────────
    team_ids = {
        m[col]
        for m in all_matches
        for col in ("home_team_id", "away_team_id")
        if m.get(col)
    }

    team_names: dict[int, str] = {}
    if team_ids:
        teams_res = (
            admin_client().table("teams")
            .select("id, country_name")
            .in_("id", list(team_ids))
            .execute()
        )
        team_names = {t["id"]: t["country_name"] for t in (teams_res.data or [])}

    # ── Step 3: attach resolved names so match_card.html stays unchanged ───
    for m in all_matches:
        h_id = m.get("home_team_id")
        a_id = m.get("away_team_id")
        m["home_team"] = {"country_name": team_names[h_id]} if h_id and h_id in team_names else None
        m["away_team"] = {"country_name": team_names[a_id]} if a_id and a_id in team_names else None

    upcoming = [m for m in all_matches if m["status"] == MatchStatus.SCHEDULED]
    live     = [m for m in all_matches if m["status"] == MatchStatus.LIVE]
    past     = [m for m in all_matches if m["status"] == MatchStatus.FINISHED]

    return templates.TemplateResponse(request, "matches.html", context={
        "upcoming": upcoming,
        "live": live,
        "past": past,
    })
