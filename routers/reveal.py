"""
/reveal                     – Cookie gatekeeper: stream or assignments redirect.
/reveal/stream/{id}         – HTMX-aware stream page (full page or fragment).
/teams/assignments          – Static 12-manager draft results grid.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from database import anon_client

router = APIRouter()
templates = Jinja2Templates(directory="templates")

MAX_SEQUENCE = 48
COOKIE_NAME  = "reveal_watched"


# ── Helpers ────────────────────────────────────────────────────────────────

def _snake_round(seq: int) -> int:
    """Return the 1-indexed snake round (1-4) for a given reveal_sequence."""
    return (seq - 1) // 12 + 1


def _fetch_pick(sequence_id: int) -> dict | None:
    db = anon_client()
    res = (
        db.table("picks")
        .select(
            "reveal_sequence, "
            "user:users(id, name), "
            "team:teams(id, country_name, pot_number, group_letter, fifa_rank)"
        )
        .eq("reveal_sequence", sequence_id)
        .maybe_single()
        .execute()
    )
    return res.data if res else None


def _fetch_all_picks_by_user() -> dict[int, dict]:
    """
    Returns {user_id: {name, teams: [ordered by reveal_sequence]}}
    for the assignments grid.
    """
    db = anon_client()
    res = (
        db.table("picks")
        .select("reveal_sequence, user_id, user:users(id, name), team:teams(country_name, pot_number)")
        .order("reveal_sequence")
        .execute()
    )
    users: dict[int, dict] = {}
    for p in (res.data or []):
        uid = p["user_id"]
        if uid not in users:
            users[uid] = {
                "id": uid,
                "name": p["user"]["name"] if p.get("user") else f"User {uid}",
                "teams": [],
            }
        users[uid]["teams"].append({
            "country_name":  p["team"]["country_name"]  if p.get("team") else "?",
            "pot_number":    p["team"]["pot_number"]     if p.get("team") else 0,
            "reveal_sequence": p["reveal_sequence"],
        })
    # Return ordered by first pick's reveal_sequence (draft order)
    return dict(sorted(users.items(), key=lambda kv: kv[1]["teams"][0]["reveal_sequence"]))


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/reveal", response_class=HTMLResponse)
async def reveal_gate(request: Request):
    """
    Gatekeeper: check for reveal_watched cookie.
      - Cookie missing → redirect to /reveal/stream/1 (live show)
      - Cookie present → redirect to /teams/assignments (permanent grid)
    """
    if request.cookies.get(COOKIE_NAME) == "true":
        return RedirectResponse(url="/teams/assignments", status_code=302)
    return RedirectResponse(url="/reveal/stream/1", status_code=302)


@router.get("/reveal/stream/{sequence_id}", response_class=HTMLResponse)
async def reveal_stream(request: Request, sequence_id: int):
    """
    HTMX-aware handler.

    HTMX request (HX-Request header present):
      Returns a pick-card fragment for the given sequence_id.
      The fragment contains:
        • The pick card (appended to #pick-grid via beforeend).
        • OOB elements that update #chain-trigger, #pick-counter,
          #progress-fill, and (on final pick) #completion-zone.

    Direct browser navigation (no HX-Request header):
      Returns the full reveal.html shell — terminal overlay + empty grid.
      The shell always starts from pick #1 via the chain-trigger mechanism,
      so sequence_id is ignored for full-page renders.
    """
    # For HTMX fragment requests, validate sequence bounds
    if request.headers.get("HX-Request"):
        if sequence_id < 1 or sequence_id > MAX_SEQUENCE:
            return HTMLResponse("")  # silent no-op; chain stops naturally

        pick          = _fetch_pick(sequence_id)
        next_sequence = sequence_id + 1 if sequence_id < MAX_SEQUENCE else None
        is_final      = sequence_id == MAX_SEQUENCE
        snake_round   = _snake_round(sequence_id)

        return templates.TemplateResponse(
            request,
            "fragments/pick_card.html",
            context={
                "pick":          pick,
                "sequence_id":   sequence_id,
                "next_sequence": next_sequence,
                "is_final":      is_final,
                "snake_round":   snake_round,
                "max_sequence":  MAX_SEQUENCE,
            },
        )

    # Full-page render: always serve the reveal shell.
    # The terminal plays first; HTMX loads picks starting from #1 afterward.
    # Redirect out-of-range direct URLs to the canonical entry point.
    if sequence_id != 1:
        return RedirectResponse(url="/reveal/stream/1", status_code=302)

    return templates.TemplateResponse(request, "reveal.html", context={
        "max_sequence": MAX_SEQUENCE,
    })


@router.get("/teams/assignments", response_class=HTMLResponse)
async def assignments_grid(request: Request):
    """
    Static permanent draft results grid – 12 manager columns × 4 teams.
    Shown when reveal_watched cookie is present.
    Includes a 'Replay Reveal Show' button that clears the cookie client-side.
    """
    users_by_id = _fetch_all_picks_by_user()
    return templates.TemplateResponse(request, "assignments.html", context={
        "users": list(users_by_id.values()),
    })
