"""
/api/worker/sync  –  Cron-triggered data pipeline.

Fetches live match data and group standings from worldcup26.ir, upserts both
into Supabase, then runs score recomputation synchronously.

Time-window gate
────────────────
Requests outside 12:00pm–3:00am US/Eastern are acknowledged with HTTP 200
but no API calls are made, keeping costs and rate limits low.
Active window covers the earliest possible kickoff (noon) through one hour
after the latest match could finish (~2am), with a 1-hour buffer.

Scheduling:
  Automated every 10 minutes via cron-job.org during the active window.
  Manual trigger available via GitHub Actions workflow_dispatch.

At 10-min intervals the time-window check yields:
  Active hours  = 15 h  → 90 calls/day  (fixtures)
                         + 90 calls/day  (standings)
                         = 180 API calls/day total

Upsert strategy
───────────────
Fixtures: all 104 rows upserted on external_id each cycle.
  104 rows × ~180 cycles/day is negligible for Supabase and avoids the
  complexity of change-detection state. The DB upsert only writes rows
  whose values actually changed, so it is efficient even at full scale.

Standings: all group rows (up to 48) upserted on (group_letter, team_id).
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from typing import Optional

from config import get_settings
from api_client import fetch_fixtures, fetch_standings
from scoring_engine import recompute_all_scores
from database import admin_client

router = APIRouter(prefix="/api/worker")
log = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")   # handles EST/EDT automatically


# ── Auth ───────────────────────────────────────────────────────────────────

def _verify_cron_token(authorization: Optional[str] = Header(default=None)):
    expected = f"Bearer {get_settings().cron_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid cron token.")


# ── Time window ────────────────────────────────────────────────────────────

def _in_active_window() -> bool:
    """
    Return True if the current US/Eastern time is within the active window:
      12:00pm (12) → midnight → 3:00am (3)
    i.e. hour >= 12  OR  hour < 3
    """
    hour = datetime.now(_ET).hour
    return hour >= 12 or hour < 3


# ── Sync helpers ───────────────────────────────────────────────────────────

def _build_ext_to_int_map(db) -> dict[int, int]:
    """Return {external_id: internal_id} for every team that has external_id set."""
    res = db.table("teams").select("id, external_id").execute()
    return {
        t["external_id"]: t["id"]
        for t in (res.data or [])
        if t.get("external_id") is not None
    }


async def _sync_fixtures(db, ext_to_int: dict[int, int]) -> int:
    """Fetch all fixtures and upsert into public.matches.

    The API returns external team IDs for home/away participants.
    We translate to internal DB IDs before upserting so that
    matches.home_team_id / away_team_id are valid FKs to teams.id.
    TBD fixtures (id == None) are left as NULL — no translation needed.
    """
    fixtures = await fetch_fixtures()
    if not fixtures:
        return 0

    translated = []
    for row in fixtures:
        h_ext = row.get("home_team_id")
        a_ext = row.get("away_team_id")
        h_int = ext_to_int.get(h_ext) if h_ext is not None else None
        a_int = ext_to_int.get(a_ext) if a_ext is not None else None
        if h_ext is not None and h_int is None:
            log.warning("_sync_fixtures: no internal ID for home_team_id=%s (fixture external_id=%s)", h_ext, row.get("external_id"))
        if a_ext is not None and a_int is None:
            log.warning("_sync_fixtures: no internal ID for away_team_id=%s (fixture external_id=%s)", a_ext, row.get("external_id"))
        translated.append({**row, "home_team_id": h_int, "away_team_id": a_int})

    for row in translated:
        db.table("matches").upsert(row, on_conflict="external_id").execute()
    log.info("_sync_fixtures: upserted %d rows", len(translated))
    return len(translated)


async def _sync_standings(db, ext_to_int: dict[int, int]) -> int:
    """Fetch group standings and upsert into public.group_standings.

    The API returns external team IDs. We translate to internal DB IDs before
    upserting so that group_standings.team_id is a valid FK to teams.id.
    """
    rows = await fetch_standings()
    if not rows:
        return 0

    translated = []
    for row in rows:
        ext_id = row.get("team_id")
        internal_id = ext_to_int.get(ext_id)
        if internal_id is None:
            log.warning("_sync_standings: no internal ID for external team_id=%s, skipping", ext_id)
            continue
        translated.append({**row, "team_id": internal_id})

    if not translated:
        log.warning("_sync_standings: no rows survived ID translation — check teams.external_id is populated")
        return 0

    db.table("group_standings").upsert(
        translated, on_conflict="group_letter,team_id"
    ).execute()
    log.info("_sync_standings: upserted %d rows", len(translated))
    return len(translated)


# ── Main endpoint ──────────────────────────────────────────────────────────

@router.post("/sync")
async def sync(_: None = Depends(_verify_cron_token)):
    """
    Main sync endpoint — call this from your cron job every 10 minutes.

    Fetches fixtures and standings, upserts to Supabase, then runs score
    recomputation synchronously before returning. This ensures scoring is
    always complete by the time the response goes out — important on
    serverless hosts (e.g. Vercel) where background tasks may be killed
    after the response is sent.
    """
    now_et = datetime.now(_ET)

    if not _in_active_window():
        return JSONResponse({
            "status": "skipped",
            "reason": "outside active window (12pm–3am ET)",
            "current_time_et": now_et.strftime("%H:%M %Z"),
        })

    db = admin_client()
    ext_to_int = _build_ext_to_int_map(db)

    fixtures_count  = await _sync_fixtures(db, ext_to_int)
    standings_count = await _sync_standings(db, ext_to_int)

    recompute_all_scores()

    return JSONResponse({
        "status":            "ok",
        "time_et":           now_et.strftime("%H:%M %Z"),
        "fixtures_upserted": fixtures_count,
        "standings_upserted": standings_count,
    })


# ── Legacy alias (backwards compat with any existing cron configs) ─────────

@router.post("/sync-matches")
async def sync_matches_legacy(_: None = Depends(_verify_cron_token)):
    """Deprecated alias → delegates to /sync."""
    return await sync(_)
