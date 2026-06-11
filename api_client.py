"""
api_client.py
=============
Data ingestion from worldcup26.ir — a free, open-source World Cup 2026 API.
  https://github.com/rezarahiminia/worldcup2026
  https://worldcup26.ir/api-docs/

Endpoints used
──────────────
  GET  /get/games   → all 104 match fixtures
  GET  /get/groups  → all 12 group standings
  POST /auth/authenticate → JWT token (valid 84 days)

Authentication
──────────────
The API's read endpoints work without auth in practice, but sends a JWT
in the Authorization header when one is available.  Two configuration modes:
  1. Set WORLDCUP_API_TOKEN in .env (pre-obtained, good for 84 days).
  2. Leave TOKEN blank and set EMAIL + PASSWORD — the module auto-obtains
     a token on first use and caches it for the process lifetime.

Field mapping — games → public.matches
──────────────────────────────────────
  id              → external_id    (INT 1-104)
  home_team_id    → home_team_id   (external ID → translated to internal in worker._sync_fixtures; "0" → NULL for TBD)
  away_team_id    → away_team_id   (same translation)
  home_team_name_en / home_team_label → home_team_label
  away_team_name_en / away_team_label → away_team_label
  home_score      → home_score     (NULL when SCHEDULED)
  away_score      → away_score
  local_date      → kickoff_time   ("MM/DD/YYYY HH:MM" → UTC ISO-8601)
  matchday        → matchday
  group           → group_letter   (only for type=="group")
  type            → stage          ("group"→GROUP, "r32"→R32, …)
  finished + time_elapsed → status

Field mapping — groups → public.group_standings
───────────────────────────────────────────────
  name            → group_letter
  teams[].team_id → team_id       (external ID — translated to internal in worker._sync_standings)
  teams[].mp      → played
  teams[].w/l/d   → won/lost/drawn
  teams[].pts     → points
  teams[].gf/ga/gd → goals_for/goals_against/goal_difference
  position        → imputed by sorting (pts desc, gd desc, gf desc)
"""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

# ── Stage mapping ──────────────────────────────────────────────────────────
_TYPE_TO_STAGE: dict[str, str] = {
    "group":  "GROUP",
    "r32":    "R32",
    "r16":    "R16",
    "qf":     "QF",
    "sf":     "SF",
    "third":  "THIRD",
    "final":  "FINAL",
}

# ── In-process JWT cache ───────────────────────────────────────────────────
_cached_token: str | None = None


async def _get_token() -> str | None:
    """
    Return a valid JWT, sourcing it in this priority order:
      1. WORLDCUP_API_TOKEN env var (pre-configured)
      2. In-process cache from a previous auto-login
      3. Auto-login using WORLDCUP_API_EMAIL + WORLDCUP_API_PASSWORD
    Returns None if no credentials are configured (public read still works).
    """
    global _cached_token

    s = get_settings()

    if s.worldcup_api_token:
        return s.worldcup_api_token

    if _cached_token:
        return _cached_token

    if s.worldcup_api_email and s.worldcup_api_password:
        logger.info("api_client: auto-logging in to worldcup26.ir …")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{s.worldcup_api_url}/auth/authenticate",
                    json={"email": s.worldcup_api_email, "password": s.worldcup_api_password},
                )
                resp.raise_for_status()
                _cached_token = resp.json().get("token")
                logger.info("api_client: JWT obtained, valid 84 days.")
                return _cached_token
        except Exception as exc:
            logger.warning("api_client: auto-login failed: %s", exc)

    return None


async def _get(path: str) -> Any:
    """Authenticated GET against the worldcup26.ir base URL."""
    s = get_settings()
    token = await _get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = f"{s.worldcup_api_url}{path}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


# ── Shared field converters ────────────────────────────────────────────────

def _int_or_none(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _team_id(val) -> int | None:
    """String/int "0" → NULL (TBD).  Positive int → that id."""
    v = _int_or_none(val)
    return v if v and v > 0 else None


def _kickoff(raw_str: str | None) -> str | None:
    """Parse "MM/DD/YYYY HH:MM" → UTC ISO-8601. Returns None on failure."""
    if not raw_str:
        return None
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw_str.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    logger.warning("api_client: could not parse kickoff %r", raw_str)
    return None


def _derive_status(raw: dict) -> str:
    if str(raw.get("finished", "FALSE")).upper() == "TRUE":
        return "FINISHED"
    if str(raw.get("time_elapsed", "notstarted")).lower() != "notstarted":
        return "LIVE"
    return "SCHEDULED"


# ── Fixtures ───────────────────────────────────────────────────────────────

def _map_fixture(raw: dict) -> dict | None:
    """Map one raw game object → matches row dict. Returns None to skip."""
    type_str = str(raw.get("type", "")).strip().lower()
    stage = _TYPE_TO_STAGE.get(type_str)
    if not stage:
        logger.warning("api_client: unknown type %r in game id=%s", type_str, raw.get("id"))
        return None

    home_id = _team_id(raw.get("home_team_id"))
    away_id = _team_id(raw.get("away_team_id"))
    if home_id is not None and away_id is not None and home_id == away_id:
        logger.warning("api_client: home_team_id == away_team_id in game id=%s", raw.get("id"))
        return None

    status = _derive_status(raw)
    home_score = _int_or_none(raw.get("home_score")) if status != "SCHEDULED" else None
    away_score = _int_or_none(raw.get("away_score")) if status != "SCHEDULED" else None

    # group_letter only meaningful for group-stage rows
    group_val = raw.get("group")
    group_letter = group_val if stage == "GROUP" and group_val else None

    # Labels: explicit label field wins, then fall back to team name
    home_label = raw.get("home_team_label") or raw.get("home_team_name_en") or None
    away_label = raw.get("away_team_label") or raw.get("away_team_name_en") or None

    return {
        "external_id":     int(raw["id"]),
        "home_team_id":    home_id,
        "away_team_id":    away_id,
        "home_team_label": home_label,
        "away_team_label": away_label,
        "home_score":      home_score,
        "away_score":      away_score,
        "kickoff_time":    _kickoff(raw.get("local_date")),
        "matchday":        _int_or_none(raw.get("matchday")),
        "group_letter":    group_letter,
        "stage":           stage,
        "status":          status,
    }


async def fetch_fixtures() -> list[dict[str, Any]]:
    """
    Fetch all 104 fixtures from GET /get/games.
    Returns a list of dicts ready for UPSERT into public.matches.
    """
    data = await _get("/get/games")

    # Response is {"games": [...]} or a bare list
    raw_list = data.get("games", data) if isinstance(data, dict) else data
    if not isinstance(raw_list, list):
        logger.warning("fetch_fixtures: unexpected response shape")
        return []

    rows, skipped = [], 0
    for item in raw_list:
        row = _map_fixture(item)
        if row:
            rows.append(row)
        else:
            skipped += 1

    tbd = sum(1 for r in rows if r["home_team_id"] is None or r["away_team_id"] is None)
    logger.info("fetch_fixtures: %d rows mapped (%d TBD, %d skipped)", len(rows), tbd, skipped)
    return rows


# ── Group standings ────────────────────────────────────────────────────────

def _map_group(raw: dict) -> list[dict]:
    """
    Map one raw group object → list of group_standings rows.

    raw shape:
      {"name": "A", "teams": [{"team_id":"1","mp":"0","w":"0","l":"0",
                                "d":"0","pts":"0","gf":"0","ga":"0","gd":"0"}, ...]}

    Position is imputed by sorting (pts desc, gd desc, gf desc).
    team_id values here are external API IDs — callers must translate to
    internal DB IDs before upserting (see worker._sync_standings).
    """
    group_letter = str(raw.get("name", "")).strip().upper()
    if not group_letter or len(group_letter) != 1:
        logger.warning("_map_group: unrecognised group name %r", raw.get("name"))
        return []

    teams_raw = raw.get("teams", [])

    # Parse each team entry
    parsed = []
    for t in teams_raw:
        tid = _int_or_none(t.get("team_id"))
        if not tid:
            continue
        gf = _int_or_none(t.get("gf")) or 0
        ga = _int_or_none(t.get("ga")) or 0
        parsed.append({
            "group_letter":    group_letter,
            "team_id":         tid,
            "played":          _int_or_none(t.get("mp")) or 0,
            "won":             _int_or_none(t.get("w"))  or 0,
            "drawn":           _int_or_none(t.get("d"))  or 0,
            "lost":            _int_or_none(t.get("l"))  or 0,
            "goals_for":       gf,
            "goals_against":   ga,
            "goal_difference": _int_or_none(t.get("gd")) or (gf - ga),
            "points":          _int_or_none(t.get("pts")) or 0,
        })

    # Impute position by sorting: pts desc → gd desc → gf desc
    parsed.sort(key=lambda x: (x["points"], x["goal_difference"], x["goals_for"]), reverse=True)
    for i, row in enumerate(parsed):
        row["position"] = i + 1   # 1-indexed

    return parsed


async def fetch_standings() -> list[dict[str, Any]]:
    """
    Fetch group standings from GET /get/groups.
    Returns a flat list of dicts for UPSERT into public.group_standings.
    """
    data = await _get("/get/groups")

    raw_list = data.get("groups", data) if isinstance(data, dict) else data
    if not isinstance(raw_list, list):
        logger.warning("fetch_standings: unexpected response shape")
        return []

    rows: list[dict] = []
    for item in raw_list:
        rows.extend(_map_group(item))

    logger.info("fetch_standings: %d group-standing rows mapped across %d groups",
                len(rows), len(raw_list))
    return rows
