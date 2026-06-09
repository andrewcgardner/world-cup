"""
Admin routes:
  GET  /admin/panel      – Control panel: pool status + draw trigger.
  POST /admin/run-draw   – Execute the snake draft (HTMX-aware).
  GET  /admin/login      – Login form.
  POST /admin/login      – Validate token, set session cookie.
  GET  /admin/logout     – Clear session cookie.
"""

import random
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import get_settings
from database import admin_client
from models import DraftStatus
from auth import require_admin

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")

COOKIE_NAME = "admin_session"
COOKIE_MAX_AGE = 60 * 60 * 8  # 8 hours


# ── Login / logout ─────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "admin_login.html", context={
        "error": error,
    })


@router.post("/login")
async def login(request: Request, token: str = Form(...)):
    if token != get_settings().admin_token:
        return templates.TemplateResponse(request, "admin_login.html", context={
            "error": "Invalid admin token.",
        }, status_code=401)

    response = RedirectResponse(url="/admin/panel", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ── Admin control panel ────────────────────────────────────────────────────

def _panel_context(db) -> dict:
    """Collect all state needed to render the admin panel."""
    settings = db.table("system_settings").select("*").eq("id", 1).maybe_single().execute()
    settings_row = settings.data or {}

    users_res = db.table("users").select("id, name, is_bot").order("id").execute()
    users = users_res.data or []

    teams_res = db.table("teams").select("id, pot_number").execute()
    teams = teams_res.data or []
    pot_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for t in teams:
        pot_counts[t["pot_number"]] = pot_counts.get(t["pot_number"], 0) + 1

    picks_res = db.table("picks").select("id", count="exact").execute()
    picks_count = picks_res.count or 0

    draft_status = settings_row.get("draft_status", "PRE_DRAFT")

    # Readiness checks
    checks = {
        "teams_seeded":   len(teams) == 48,
        "pots_balanced":  all(v == 12 for v in pot_counts.values()),
        "users_ready":    len(users) == 12,
        "draft_pending":  draft_status == "PRE_DRAFT",
    }
    ready_to_draw = all(checks.values())

    return {
        "draft_status":  draft_status,
        "settings":      settings_row,
        "users":         users,
        "user_count":    len(users),
        "teams_count":   len(teams),
        "pot_counts":    pot_counts,
        "picks_count":   picks_count,
        "checks":        checks,
        "ready_to_draw": ready_to_draw,
    }


@router.get("/panel", response_class=HTMLResponse)
async def admin_panel(request: Request, _: None = Depends(require_admin)):
    db = admin_client()
    ctx = _panel_context(db)
    return templates.TemplateResponse(request, "admin_panel.html", context=ctx)


TOTAL_USERS = 12
TOTAL_POTS = 4


def _ensure_twelve_users(db) -> list[dict]:
    res = db.table("users").select("*").order("id").execute()
    users: list[dict] = res.data or []

    missing = TOTAL_USERS - len(users)
    if missing < 0:
        raise HTTPException(status_code=400, detail=f"More than {TOTAL_USERS} users exist ({len(users)}). Resolve manually.")

    for i in range(missing):
        bot_num = i + 1
        db.table("users").insert({
            "name": f"House Bot {bot_num}",
            "email": None,
            "is_admin": False,
            "is_bot": True,
        }).execute()

    # Re-fetch ordered list
    res = db.table("users").select("*").order("id").execute()
    return res.data


def _fetch_teams_by_pot(db) -> dict[int, list[dict]]:
    res = db.table("teams").select("*").execute()
    pots: dict[int, list[dict]] = {1: [], 2: [], 3: [], 4: []}
    for t in res.data or []:
        pots.setdefault(t["pot_number"], []).append(t)
    return pots


def _snake_order(users: list[dict], round_number: int) -> list[dict]:
    """Return users in snake order for the given round (1-indexed)."""
    # Odd rounds: 1→12; even rounds: 12→1
    return users if round_number % 2 == 1 else list(reversed(users))


@router.post("/run-draw", response_class=HTMLResponse)
async def run_draw(request: Request, _: None = Depends(require_admin)):
    db = admin_client()
    error: str | None = None
    picks_created = 0

    try:
        # 1. Purge existing picks
        db.table("picks").delete().neq("id", 0).execute()

        # 2. Ensure exactly 12 users exist
        users = _ensure_twelve_users(db)

        # 3. Shuffle draft order and persist it
        random.shuffle(users)
        draft_order = [u["id"] for u in users]
        db.table("system_settings").update(
            {"draft_order": draft_order}
        ).eq("id", 1).execute()

        # 4. Fetch & validate pot assignments, then shuffle within each pot
        pots = _fetch_teams_by_pot(db)
        for pot_num in range(1, TOTAL_POTS + 1):
            if len(pots.get(pot_num, [])) != TOTAL_USERS:
                raise ValueError(
                    f"Pot {pot_num} has {len(pots.get(pot_num, []))} teams — "
                    f"expected {TOTAL_USERS}. Adjust pot assignments on the Teams page."
                )
            random.shuffle(pots[pot_num])

        # 5. Execute 4-round snake draft in memory
        picks: list[dict] = []
        sequence = 1
        for round_num in range(1, TOTAL_POTS + 1):
            ordered_users = _snake_order(users, round_num)
            pot_teams = pots[round_num]
            for idx, user in enumerate(ordered_users):
                picks.append({
                    "user_id":        user["id"],
                    "team_id":        pot_teams[idx]["id"],
                    "reveal_sequence": sequence,
                })
                sequence += 1

        # 6. Bulk-insert picks
        db.table("picks").insert(picks).execute()
        picks_created = len(picks)

        # 7. Advance draft status → REVEALING
        db.table("system_settings").update(
            {"draft_status": DraftStatus.REVEALING}
        ).eq("id", 1).execute()

    except ValueError as exc:
        error = str(exc)
    except Exception as exc:
        error = f"Unexpected error: {exc}"

    # Re-fetch panel state for the response
    ctx = _panel_context(db)
    ctx["draw_error"]   = error
    ctx["picks_created"] = picks_created

    # HTMX request → return the full panel fragment so the page updates in place
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "fragments/draw_result.html", context=ctx)

    # Non-HTMX (e.g. direct curl call) → redirect back to panel
    return templates.TemplateResponse(request, "admin_panel.html", context=ctx)
