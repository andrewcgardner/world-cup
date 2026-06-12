"""
Scoring engine.

recompute_all_scores()
  Called as a background task after every match sync.
  - Handles GROUP stage: computes full standings (P, GD, GF) for each group,
    determines 1st/2nd/3rd/4th place, awards configured points.
  - Handles KNOCKOUT stages: awards round-win points to the owning manager
    for every FINISHED match.

build_leaderboard()
  Returns a sorted list of LeaderboardEntry for the dashboard view.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from database import admin_client, anon_client
from models import LeaderboardEntry, MatchStage, MatchStatus

logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────

def _get_settings_row(db) -> dict[str, Any]:
    return db.table("system_settings").select("*").eq("id", 1).single().execute().data


def _get_picks(db) -> dict[int, int]:
    """Returns {team_id: user_id}."""
    res = db.table("picks").select("user_id, team_id").execute()
    return {row["team_id"]: row["user_id"] for row in (res.data or [])}


def _get_finished_matches(db, stage: MatchStage | None = None):
    q = db.table("matches").select("*").eq("status", MatchStatus.FINISHED)
    if stage:
        q = q.eq("stage", stage)
    return q.execute().data or []


def _get_active_matches(db, stage: MatchStage | None = None):
    """Returns LIVE and FINISHED matches — i.e. every match that has kicked off."""
    q = db.table("matches").select("*").in_(
        "status", [MatchStatus.LIVE, MatchStatus.FINISHED]
    )
    if stage:
        q = q.eq("stage", stage)
    return q.execute().data or []


def _get_or_init_score(scores: dict[int, int], user_id: int) -> int:
    return scores.get(user_id, 0)


# ── Group Stage ────────────────────────────────────────────────────────────

def _standings_from_db(db) -> dict[str, list[dict]]:
    """
    Load group standings from the group_standings table (upserted by the
    sync worker from the live API).  Returns the same shape as
    _compute_group_standings_from_matches() so callers are interchangeable.

    {group_letter: [{"team_id":…, "Pts":…, "GD":…, "GF":…, "played":…}, …]}
    Rows are sorted by position (imputed during ingestion).
    """
    res = db.table("group_standings").select(
        "group_letter, team_id, position, points, goal_difference, goals_for, played"
    ).order("group_letter").order("position").execute()

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in (res.data or []):
        groups[row["group_letter"]].append({
            "team_id": row["team_id"],
            "Pts":     row["points"],
            "GD":      row["goal_difference"],
            "GF":      row["goals_for"],
            "played":  row["played"],       # ← needed for the played > 0 guard
        })
    return dict(groups)


def _compute_group_standings_from_matches(db) -> dict[str, list[dict]]:
    """
    Derive standings by replaying every active (LIVE + FINISHED) GROUP match.
    LIVE matches contribute their current score, so standings update in real time.
    Only teams that have kicked off at least one match appear in the result;
    the played > 0 gate in _apply_tie_aware_group_points handles the rest.
    """
    stats: dict[int, dict] = {}

    teams_res = db.table("teams").select("id, group_letter").execute()
    team_group: dict[int, str] = {
        t["id"]: t["group_letter"]
        for t in (teams_res.data or [])
        if t.get("group_letter")
    }

    def init_stat(team_id: int) -> dict:
        return {
            "team_id":     team_id,
            "group_letter": team_group.get(team_id, "?"),
            "MP": 0, "W": 0, "D": 0, "L": 0,
            "GF": 0, "GA": 0, "GD": 0, "Pts": 0,
        }

    for m in _get_active_matches(db, MatchStage.GROUP):
        if m["home_score"] is None or m["away_score"] is None:
            continue
        h_id, a_id = m["home_team_id"], m["away_team_id"]
        if not h_id or not a_id:
            continue
        hs, as_ = m["home_score"], m["away_score"]
        for t_id, gf, ga in [(h_id, hs, as_), (a_id, as_, hs)]:
            s = stats.setdefault(t_id, init_stat(t_id))
            s["MP"] += 1
            s["GF"] += gf; s["GA"] += ga; s["GD"] = s["GF"] - s["GA"]
            if gf > ga:   s["W"] += 1; s["Pts"] += 3
            elif gf == ga: s["D"] += 1; s["Pts"] += 1
            else:          s["L"] += 1

    groups: dict[str, list[dict]] = defaultdict(list)
    for st in stats.values():
        groups[st["group_letter"]].append(st)
    for letter in groups:
        groups[letter].sort(key=lambda x: (x["Pts"], x["GD"], x["GF"]), reverse=True)
    return dict(groups)


# ── Head-to-head tiebreaker ────────────────────────────────────────────────

def _compute_h2h(tied_team_ids: list[int], matches: list[dict]) -> dict[int, tuple]:
    """
    Compute head-to-head (pts, gd, gf) for a set of tied teams using only
    the matches played between those teams.

    Returns {team_id: (h2h_pts, h2h_gd, h2h_gf)}.
    """
    tied_set = set(tied_team_ids)
    h2h: dict[int, list[int]] = {tid: [0, 0, 0] for tid in tied_team_ids}

    for m in matches:
        h_id = m.get("home_team_id")
        a_id = m.get("away_team_id")
        hs   = m.get("home_score")
        as_  = m.get("away_score")
        if h_id not in tied_set or a_id not in tied_set:
            continue
        if hs is None or as_ is None:
            continue
        # Points
        if hs > as_:
            h2h[h_id][0] += 3
        elif as_ > hs:
            h2h[a_id][0] += 3
        else:
            h2h[h_id][0] += 1
            h2h[a_id][0] += 1
        # Goal difference
        h2h[h_id][1] += hs - as_
        h2h[a_id][1] += as_ - hs
        # Goals for
        h2h[h_id][2] += hs
        h2h[a_id][2] += as_

    return {tid: tuple(v) for tid, v in h2h.items()}  # type: ignore[return-value]


# Keep the old name as an alias used by breakdowns
def _compute_group_standings(matches: list[dict]) -> dict[str, list[dict]]:
    """
    Thin wrapper kept for callers that pass raw match rows.
    Prefer _standings_from_db() inside recompute_all_scores().
    """
    stats: dict[int, dict] = {}
    db = anon_client()
    teams_res = db.table("teams").select("id, group_letter").execute()
    team_group: dict[int, str] = {
        t["id"]: t["group_letter"]
        for t in (teams_res.data or [])
        if t.get("group_letter")
    }

    def init_stat(tid: int) -> dict:
        return {"team_id": tid, "group_letter": team_group.get(tid, "?"),
                "MP": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "GD": 0, "Pts": 0}

    for m in matches:
        if m["home_score"] is None or m["away_score"] is None:
            continue
        h_id, a_id = m.get("home_team_id"), m.get("away_team_id")
        if not h_id or not a_id:
            continue
        hs, as_ = m["home_score"], m["away_score"]
        for t_id, gf, ga in [(h_id, hs, as_), (a_id, as_, hs)]:
            s = stats.setdefault(t_id, init_stat(t_id))
            s["MP"] += 1; s["GF"] += gf; s["GA"] += ga; s["GD"] = s["GF"] - s["GA"]
            if gf > ga:    s["W"] += 1; s["Pts"] += 3
            elif gf == ga: s["D"] += 1; s["Pts"] += 1
            else:          s["L"] += 1

    groups: dict[str, list[dict]] = defaultdict(list)
    for st in stats.values():
        groups[st["group_letter"]].append(st)
    for letter in groups:
        groups[letter].sort(key=lambda x: (x["Pts"], x["GD"], x["GF"]), reverse=True)
    return dict(groups)


def _apply_tie_aware_group_points(
    standings: dict[str, list[dict]],
    picks: dict[int, int],
    place_pts: list[int],
    group_matches: list[dict] | None = None,
) -> dict[int, int]:
    """
    Award group-stage pool points using tie-aware rules with H2H tiebreaker.

    Tiebreaker order (all computed only for played teams):
      1. Points (Pts)
      2. Goal difference (GD)
      3. Goals for (GF)
      4. Head-to-head among tied teams (H2H Pts → H2H GD → H2H GF)

    played > 0 guard
    ────────────────
    A team must have played at least one match to receive any pool points.
    This prevents everyone from receiving pt_group_1st at tournament start
    when all teams are at (0pts, 0GD, 0GF).

    Examples with defaults 1st=15, 2nd=10, 3rd=5, 4th=0:
      Before any games (all played=0)  → 0  / 0  / 0  / 0
      Clear standings A>B>C>D          → 15 / 10 / 5  / 0
      A=B tied, H2H breaks it          → 15 / 10 / …  / …
      A=B still tied on H2H, C=D tied  → 15 / 15 / 5  / 5
    """
    scores: dict[int, int] = defaultdict(int)

    # Pre-bucket matches by group_letter for fast H2H lookup
    matches_by_letter: dict[str, list[dict]] = defaultdict(list)
    if group_matches:
        for m in group_matches:
            grp = m.get("group_letter")
            if grp:
                matches_by_letter[grp].append(m)

    for letter, team_list in standings.items():
        def _key(t: dict) -> tuple:
            return (t["Pts"], t["GD"], t["GF"])

        def _played(t: dict) -> int:
            return t.get("played") or t.get("MP") or 0

        sorted_teams = sorted(
            [t for t in team_list if _played(t) > 0],
            key=_key,
            reverse=True,
        )[:4]

        group_ms = matches_by_letter.get(letter, [])

        # Compute effective rank for each team, with H2H breaking outer ties.
        eff_ranks: dict[int, int] = {}
        processed: set[int] = set()

        for i, team in enumerate(sorted_teams):
            tid = team["team_id"]
            if tid in processed:
                continue

            # Outer tie cluster: all played teams sharing identical (Pts, GD, GF)
            outer_indices = [
                j for j in range(len(sorted_teams))
                if _key(sorted_teams[j]) == _key(team)
            ]
            base_rank = outer_indices[0]

            if len(outer_indices) == 1:
                eff_ranks[tid] = base_rank
            else:
                # Apply H2H tiebreaker within the outer cluster
                outer_cluster = [sorted_teams[j] for j in outer_indices]
                outer_ids = [t["team_id"] for t in outer_cluster]
                h2h = _compute_h2h(outer_ids, group_ms)

                h2h_sorted = sorted(
                    outer_cluster,
                    key=lambda t: h2h.get(t["team_id"], (0, 0, 0)),
                    reverse=True,
                )

                cur_rank = base_rank
                for k, ht in enumerate(h2h_sorted):
                    if k > 0:
                        prev_h2h = h2h.get(h2h_sorted[k - 1]["team_id"], (0, 0, 0))
                        this_h2h = h2h.get(ht["team_id"], (0, 0, 0))
                        if this_h2h < prev_h2h:
                            # This team's H2H is strictly worse → advance rank
                            cur_rank = base_rank + k
                    eff_ranks[ht["team_id"]] = cur_rank

            for j in outer_indices:
                processed.add(sorted_teams[j]["team_id"])

        # Award pool points
        for team in sorted_teams:
            tid = team["team_id"]
            rank = eff_ranks.get(tid, len(sorted_teams) - 1)
            if rank < len(place_pts):
                pts = place_pts[rank]
                user_id = picks.get(tid)
                if user_id is not None:
                    scores[user_id] += pts

    return scores


def _award_group_points(db, picks: dict[int, int], settings: dict) -> dict[int, int]:
    """
    Entry point for group-stage scoring.

    Always derives standings from active (LIVE + FINISHED) match data so that
    pool points update in real time as matches are played, including mid-game.
    """
    place_pts = [
        settings["pt_group_1st"],
        settings["pt_group_2nd"],
        settings["pt_group_3rd"],
        settings["pt_group_4th"],
    ]

    standings = _compute_group_standings_from_matches(db)

    # Active group matches for H2H tiebreaker
    group_matches = _get_active_matches(db, MatchStage.GROUP)

    return _apply_tie_aware_group_points(standings, picks, place_pts, group_matches)


# ── Knockout Stage ─────────────────────────────────────────────────────────

_KNOCKOUT_PTS_KEY: dict[MatchStage, str] = {
    MatchStage.R32:   "pt_r32_win",
    MatchStage.R16:   "pt_r16_win",
    MatchStage.QF:    "pt_qf_win",
    MatchStage.SF:    "pt_sf_win",
    MatchStage.FINAL: "pt_final_win",
}


def _award_knockout_points(db, picks: dict[int, int], settings: dict) -> dict[int, int]:
    scores: dict[int, int] = defaultdict(int)

    for stage, pts_key in _KNOCKOUT_PTS_KEY.items():
        pts = settings[pts_key]
        matches = _get_finished_matches(db, stage)
        for m in matches:
            hs, as_ = m.get("home_score"), m.get("away_score")
            if hs is None or as_ is None:
                continue
            if hs > as_:
                winner_id = m["home_team_id"]
            elif as_ > hs:
                winner_id = m["away_team_id"]
            else:
                continue  # Draw shouldn't happen in knockout; skip

            user_id = picks.get(winner_id)
            if user_id is not None:
                scores[user_id] += pts

    return scores


# ── Main recompute ─────────────────────────────────────────────────────────

def recompute_all_scores() -> None:
    """
    Recomputes all scores from scratch and persists them to a
    'scores' table (user_id, total_points).  If that table doesn't exist
    yet, the error is logged but not raised so the sync worker isn't blocked.
    """
    try:
        db = admin_client()
        settings = _get_settings_row(db)
        picks = _get_picks(db)

        group_pts   = _award_group_points(db, picks, settings)
        knockout_pts = _award_knockout_points(db, picks, settings)

        # Merge
        all_user_ids = set(picks.values())
        merged: dict[int, int] = {}
        for uid in all_user_ids:
            merged[uid] = group_pts.get(uid, 0) + knockout_pts.get(uid, 0)

        # Upsert into a lightweight scores cache table.
        # Schema: scores(user_id PK, total_points INT)
        rows = [{"user_id": uid, "total_points": pts} for uid, pts in merged.items()]
        if rows:
            db.table("scores").upsert(rows, on_conflict="user_id").execute()

        logger.info("recompute_all_scores: updated %d user scores.", len(rows))
    except Exception as exc:
        logger.error("recompute_all_scores failed: %s", exc)


# ── Leaderboard ────────────────────────────────────────────────────────────

def build_leaderboard() -> list[LeaderboardEntry]:
    """
    Pulls current scores + user names + team names and returns
    a ranked leaderboard list.
    """
    try:
        db = anon_client()

        # scores joined with users
        scores_res = db.table("scores").select("user_id, total_points").order("total_points", desc=True).execute()
        score_rows = scores_res.data or []

        if not score_rows:
            # Fall back to all users with 0 pts
            users_res = db.table("users").select("id, name").execute()
            score_rows = [{"user_id": u["id"], "total_points": 0} for u in (users_res.data or [])]

        # Build a name map
        user_ids = [r["user_id"] for r in score_rows]
        users_res = db.table("users").select("id, name").in_("id", user_ids).execute()
        name_map = {u["id"]: u["name"] for u in (users_res.data or [])}

        # Build a teams-per-user map
        picks_res = db.table("picks").select("user_id, team:teams(country_name)").in_("user_id", user_ids).execute()
        teams_map: dict[int, list[str]] = defaultdict(list)
        for p in (picks_res.data or []):
            if p.get("team"):
                teams_map[p["user_id"]].append(p["team"]["country_name"])

        leaderboard = []
        for rank, row in enumerate(score_rows, start=1):
            uid = row["user_id"]
            leaderboard.append(LeaderboardEntry(
                rank=rank,
                user_id=uid,
                user_name=name_map.get(uid, f"User {uid}"),
                total_points=row["total_points"],
                teams=sorted(teams_map.get(uid, [])),
            ))

        return leaderboard

    except Exception as exc:
        logger.error("build_leaderboard failed: %s", exc)
        return []


# ── Points timeline (for Chart.js trend line) ──────────────────────────────

def get_points_timeline() -> dict:
    """
    Returns a Chart.js-ready data structure:
    {
      "labels": ["Group MD1", "Group MD2", ..., "R32", "R16", "QF", "SF", "Final"],
      "datasets": [
        {"label": "Alice", "data": [0, 5, 20, ...], "borderColor": "#...", ...},
        ...
      ]
    }

    Strategy: bucket scoring events by stage × match-day, accumulate per user.
    If no matches exist yet, returns empty labels/datasets.
    """
    try:
        db = anon_client()
        settings = _get_settings_row(db)
        picks = _get_picks(db)                          # {team_id: user_id}
        all_user_ids = sorted(set(picks.values()))

        # User name map
        users_res = db.table("users").select("id, name").in_("id", all_user_ids).execute()
        name_map = {u["id"]: u["name"] for u in (users_res.data or [])}

        # Fetch all finished matches ordered chronologically
        matches_res = (
            db.table("matches")
            .select("*")
            .eq("status", MatchStatus.FINISHED)
            .order("kickoff_time")
            .execute()
        )
        matches = matches_res.data or []

        if not matches:
            return {"labels": [], "datasets": []}

        # ── Bucket matches into timeline labels ────────────────────────────
        # Group stage: bucket by calendar date (match day)
        # Knockout stages: one bucket per round
        from datetime import datetime, timezone

        # Each event: (label_str, points_delta per user_id)
        events: list[tuple[str, dict[int, int]]] = []

        # Separate group from knockout
        group_matches = [m for m in matches if m["stage"] == MatchStage.GROUP]
        knockout_matches = [m for m in matches if m["stage"] != MatchStage.GROUP]

        # Group matches → bucket by date
        from itertools import groupby

        def _date_key(m):
            kt = m.get("kickoff_time")
            if kt:
                try:
                    return datetime.fromisoformat(kt).date().isoformat()
                except ValueError:
                    pass
            return "Unknown"

        # Pre-compute group standings per match-day bucket
        # (we snapshot standings after each day's matches)
        place_pts = [
            settings["pt_group_1st"], settings["pt_group_2nd"],
            settings["pt_group_3rd"], settings["pt_group_4th"],
        ]

        # Build cumulative group matches per date, compute standing snapshot
        accumulated_group: list[dict] = []
        seen_dates: list[str] = []
        for date_str, day_matches in groupby(group_matches, key=_date_key):
            accumulated_group.extend(list(day_matches))
            standings = _compute_group_standings(accumulated_group)

            delta: dict[int, int] = defaultdict(int)
            for letter, teams in standings.items():
                for rank, ts in enumerate(teams[:4]):
                    uid = picks.get(ts["team_id"])
                    if uid is not None:
                        delta[uid] += place_pts[rank]

            seen_dates.append(date_str)
            events.append((f"Group {date_str}", dict(delta)))

        # Knockout matches → one bucket per stage
        stage_order = [MatchStage.R32, MatchStage.R16, MatchStage.QF,
                       MatchStage.SF, MatchStage.FINAL]
        stage_labels = {
            MatchStage.R32: "Round of 32", MatchStage.R16: "Round of 16",
            MatchStage.QF: "Quarter-Finals", MatchStage.SF: "Semi-Finals",
            MatchStage.FINAL: "Final",
        }
        pts_keys = _KNOCKOUT_PTS_KEY

        for stage in stage_order:
            stage_matches = [m for m in knockout_matches if m["stage"] == stage]
            if not stage_matches:
                continue
            delta: dict[int, int] = defaultdict(int)
            pts = settings[pts_keys[stage]]
            for m in stage_matches:
                hs, as_ = m.get("home_score"), m.get("away_score")
                if hs is None or as_ is None:
                    continue
                if hs > as_:
                    winner_id = m["home_team_id"]
                elif as_ > hs:
                    winner_id = m["away_team_id"]
                else:
                    continue
                uid = picks.get(winner_id)
                if uid is not None:
                    delta[uid] += pts
            events.append((stage_labels[stage], dict(delta)))

        if not events:
            return {"labels": [], "datasets": []}

        # ── Build cumulative series per user ───────────────────────────────
        labels = [e[0] for e in events]
        cumulative: dict[int, list[int]] = {uid: [] for uid in all_user_ids}
        running: dict[int, int] = {uid: 0 for uid in all_user_ids}

        for _, delta in events:
            for uid in all_user_ids:
                running[uid] += delta.get(uid, 0)
                cumulative[uid].append(running[uid])

        # Palette – 12 distinct colours
        palette = [
            "#f59e0b", "#3b82f6", "#10b981", "#ef4444",
            "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16",
            "#f97316", "#6366f1", "#14b8a6", "#e11d48",
        ]

        datasets = []
        for i, uid in enumerate(all_user_ids):
            color = palette[i % len(palette)]
            datasets.append({
                "label": name_map.get(uid, f"User {uid}"),
                "data": cumulative[uid],
                "borderColor": color,
                "backgroundColor": color + "22",
                "tension": 0.35,
                "pointRadius": 4,
                "pointHoverRadius": 6,
                "fill": False,
            })

        return {"labels": labels, "datasets": datasets}

    except Exception as exc:
        logger.error("get_points_timeline failed: %s", exc)
        return {"labels": [], "datasets": []}


# ── Per-user team breakdown (for HTMX drill-down drawer) ───────────────────

def get_user_breakdown(user_id: int) -> dict:
    """
    Returns the detailed point breakdown for one manager, structured as:
    {
      "user_id": ...,
      "user_name": ...,
      "total_points": ...,
      "teams": [
        {
          "team_id": ...,
          "country_name": ...,
          "pot_number": ...,
          "group_letter": ...,
          "reveal_sequence": ...,
          "points": {
            "group_stage": int,
            "r32": int, "r16": int, "qf": int, "sf": int, "final": int,
            "total": int,
          }
        },
        ...  (4 teams per user)
      ]
    }
    """
    try:
        db = anon_client()
        settings = _get_settings_row(db)

        # Fetch user
        user_res = db.table("users").select("id, name").eq("id", user_id).single().execute()
        user = user_res.data

        # Fetch this user's picks (team info queried separately — FK joins can
        # silently return None when the Supabase schema relationship isn't set up,
        # which would crash on attribute access downstream).
        picks_res = (
            db.table("picks")
            .select("team_id, reveal_sequence")
            .eq("user_id", user_id)
            .order("reveal_sequence")
            .execute()
        )
        user_picks = picks_res.data or []
        team_ids = [p["team_id"] for p in user_picks]

        # Fetch team details explicitly
        team_info: dict[int, dict] = {}
        if team_ids:
            tr = db.table("teams").select(
                "id, country_name, pot_number, group_letter"
            ).in_("id", team_ids).execute()
            team_info = {t["id"]: t for t in (tr.data or [])}

        # ── Group-stage points per team (canonical tie-aware logic) ────────
        place_pts = [
            settings["pt_group_1st"], settings["pt_group_2nd"],
            settings["pt_group_3rd"], settings["pt_group_4th"],
        ]

        standings = _standings_from_db(db)
        if not standings:
            standings = _compute_group_standings_from_matches(db)

        group_matches = _get_finished_matches(db, MatchStage.GROUP)

        # Temporarily map team_id → team_id as the "picks" dict so
        # _apply_tie_aware_group_points returns {team_id: pool_pts}
        all_team_ids_in_standings = {
            t["team_id"] for ts in standings.values() for t in ts
        }
        team_id_as_user = {tid: tid for tid in all_team_ids_in_standings}
        group_pts_per_team = _apply_tie_aware_group_points(
            standings, team_id_as_user, place_pts, group_matches
        )
        group_pts_by_team: dict[int, int] = {
            tid: group_pts_per_team.get(tid, 0) for tid in team_ids
        }

        # ── Knockout points per team ───────────────────────────────────────
        ko_pts_by_team: dict[int, dict[str, int]] = {
            tid: {"r32": 0, "r16": 0, "qf": 0, "sf": 0, "final": 0}
            for tid in team_ids
        }
        stage_key_map = {
            MatchStage.R32: "r32", MatchStage.R16: "r16",
            MatchStage.QF:  "qf",  MatchStage.SF:  "sf",
            MatchStage.FINAL: "final",
        }
        for stage, key in stage_key_map.items():
            pts = settings[_KNOCKOUT_PTS_KEY[stage]]
            for m in _get_finished_matches(db, stage):
                hs, as_ = m.get("home_score"), m.get("away_score")
                if hs is None or as_ is None:
                    continue
                if hs > as_:
                    winner_id = m["home_team_id"]
                elif as_ > hs:
                    winner_id = m["away_team_id"]
                else:
                    continue
                if winner_id in team_ids:
                    ko_pts_by_team[winner_id][key] += pts

        # ── Assemble output ────────────────────────────────────────────────
        teams_out = []
        total_pts = 0
        for p in user_picks:
            tid = p["team_id"]
            info = team_info.get(tid, {})
            gp = group_pts_by_team.get(tid, 0)
            ko = ko_pts_by_team.get(tid, {})
            team_total = gp + sum(ko.values())
            total_pts += team_total
            teams_out.append({
                "team_id": tid,
                "country_name": info.get("country_name", f"Team {tid}"),
                "pot_number": info.get("pot_number", 0),
                "group_letter": info.get("group_letter"),
                "reveal_sequence": p.get("reveal_sequence"),
                "points": {
                    "group_stage": gp,
                    "r32":   ko.get("r32", 0),
                    "r16":   ko.get("r16", 0),
                    "qf":    ko.get("qf", 0),
                    "sf":    ko.get("sf", 0),
                    "final": ko.get("final", 0),
                    "total": team_total,
                },
            })

        return {
            "user_id": user_id,
            "user_name": user["name"],
            "total_points": total_pts,
            "teams": teams_out,
        }

    except Exception as exc:
        logger.error("get_user_breakdown(%s) failed: %s", user_id, exc)
        return {}


# ── Teams & Owners Matrix data ─────────────────────────────────────────────

def get_teams_matrix() -> dict:
    """
    Returns all 48 teams grouped by group_letter, each annotated with
    their current group standing and the manager who drafted them.

    {
      "A": [ {team fields + standing + owner_name}, ... ],
      ...
    }
    Teams without a group_letter land in key "?".
    """
    try:
        db = anon_client()

        # All teams
        teams_res = db.table("teams").select("*").order("group_letter").order("country_name").execute()
        teams = teams_res.data or []

        # Picks: {team_id: {user_id, user_name}}
        picks_res = db.table("picks").select("team_id, user_id, user:users(name)").execute()
        owner_map: dict[int, str] = {}
        for p in (picks_res.data or []):
            uname = p.get("user", {}).get("name", "Unassigned") if p.get("user") else "Unassigned"
            owner_map[p["team_id"]] = uname

        # Derive standings from active (LIVE + FINISHED) group matches
        active_group_matches = _get_active_matches(db, MatchStage.GROUP)
        match_stats: dict[int, dict] = {}
        for m in active_group_matches:
            if m["home_score"] is None or m["away_score"] is None:
                continue
            h_id, a_id = m["home_team_id"], m["away_team_id"]
            if not h_id or not a_id:
                continue
            hs, as_ = m["home_score"], m["away_score"]
            for t_id, gf, ga in [(h_id, hs, as_), (a_id, as_, hs)]:
                s = match_stats.setdefault(t_id, {
                    "MP": 0, "W": 0, "D": 0, "L": 0,
                    "GF": 0, "GA": 0, "GD": 0, "Pts": 0,
                })
                s["MP"] += 1
                s["GF"] += gf; s["GA"] += ga; s["GD"] = s["GF"] - s["GA"]
                if gf > ga:    s["W"] += 1; s["Pts"] += 3
                elif gf == ga: s["D"] += 1; s["Pts"] += 1
                else:          s["L"] += 1

        # Compute positions per group
        group_buckets: dict[str, list[int]] = defaultdict(list)
        for t in teams:
            letter = t.get("group_letter")
            if letter and t["id"] in match_stats:
                group_buckets[letter].append(t["id"])

        position_map: dict[int, int] = {}
        for letter, tids in group_buckets.items():
            sorted_tids = sorted(
                tids,
                key=lambda tid: (
                    match_stats[tid]["Pts"],
                    match_stats[tid]["GD"],
                    match_stats[tid]["GF"],
                ),
                reverse=True,
            )
            for i, tid in enumerate(sorted_tids):
                position_map[tid] = i + 1

        standing_map: dict[int, dict] = {
            tid: {
                "rank": position_map.get(tid, 0),
                "MP": s["MP"],
                "W":  s["W"],
                "D":  s["D"],
                "L":  s["L"],
                "GF": s["GF"],
                "GA": s["GA"],
                "GD": s["GD"],
                "Pts": s["Pts"],
            }
            for tid, s in match_stats.items()
        }

        # Group teams by group_letter
        groups: dict[str, list[dict]] = defaultdict(list)
        for t in teams:
            letter = t.get("group_letter") or "?"
            standing = standing_map.get(t["id"], {})
            groups[letter].append({
                **t,
                "owner_name": owner_map.get(t["id"], "Unassigned"),
                "standing": standing,
            })

        # Sort groups A→L then ?
        sorted_groups = dict(
            sorted(groups.items(), key=lambda kv: (kv[0] == "?", kv[0]))
        )
        return sorted_groups

    except Exception as exc:
        logger.error("get_teams_matrix failed: %s", exc)
        return {}


# ── Group Standings Page data ───────────────────────────────────────────────

def get_group_standings_page_data() -> dict:
    """
    Returns all 12 groups with per-team stats, pool points, and owner names.
    Derived entirely from active (LIVE + FINISHED) matches so standings and
    pool points update in real time, including mid-game.

    {
      "A": [
        {
          "position": 1,
          "team_id": 3,
          "country_name": "France",
          "played": 3, "won": 2, "drawn": 1, "lost": 0,
          "goals_for": 5, "goals_against": 2, "goal_difference": 3,
          "points": 7,
          "pool_pts": 15,
          "owner_name": "Andrew",
        },
        ...
      ],
      ...
    }
    """
    try:
        db = anon_client()
        settings = _get_settings_row(db)

        # ── All teams (need every team, even those yet to play) ────────────
        teams_res = db.table("teams").select("id, country_name, group_letter").execute()
        all_teams = teams_res.data or []
        team_names: dict[int, str] = {t["id"]: t["country_name"] for t in all_teams}

        # ── Owner lookup ───────────────────────────────────────────────────
        picks_res = db.table("picks").select("team_id, user:users(name)").execute()
        owner_map: dict[int, str] = {}
        for p in (picks_res.data or []):
            uname = (p.get("user") or {}).get("name") or "Unassigned"
            owner_map[p["team_id"]] = uname

        # ── Compute stats from active (LIVE + FINISHED) group matches ──────
        active_matches = _get_active_matches(db, MatchStage.GROUP)
        stats: dict[int, dict] = {}
        for m in active_matches:
            if m["home_score"] is None or m["away_score"] is None:
                continue
            h_id, a_id = m["home_team_id"], m["away_team_id"]
            if not h_id or not a_id:
                continue
            hs, as_ = m["home_score"], m["away_score"]
            for t_id, gf, ga in [(h_id, hs, as_), (a_id, as_, hs)]:
                s = stats.setdefault(t_id, {
                    "MP": 0, "W": 0, "D": 0, "L": 0,
                    "GF": 0, "GA": 0, "GD": 0, "Pts": 0,
                })
                s["MP"] += 1
                s["GF"] += gf; s["GA"] += ga; s["GD"] = s["GF"] - s["GA"]
                if gf > ga:    s["W"] += 1; s["Pts"] += 3
                elif gf == ga: s["D"] += 1; s["Pts"] += 1
                else:          s["L"] += 1

        # ── Build groups: include ALL teams, zeroes for unplayed ───────────
        raw_groups: dict[str, list[dict]] = defaultdict(list)
        for t in all_teams:
            letter = t.get("group_letter")
            if not letter:
                continue
            s = stats.get(t["id"], {})
            raw_groups[letter].append({
                "team_id": t["id"],
                "Pts": s.get("Pts", 0),
                "GD":  s.get("GD",  0),
                "GF":  s.get("GF",  0),
                "MP":  s.get("MP",  0),
                "W":   s.get("W",   0),
                "D":   s.get("D",   0),
                "L":   s.get("L",   0),
                "GA":  s.get("GA",  0),
            })

        # Sort each group and assign positions
        for letter in raw_groups:
            raw_groups[letter].sort(
                key=lambda x: (x["Pts"], x["GD"], x["GF"]), reverse=True
            )
            for i, t in enumerate(raw_groups[letter]):
                t["position"] = i + 1

        # ── Per-team pool points (tie-aware with H2H) ──────────────────────
        place_pts = [
            settings["pt_group_1st"], settings["pt_group_2nd"],
            settings["pt_group_3rd"], settings["pt_group_4th"],
        ]
        standings_for_scoring: dict[str, list[dict]] = {
            letter: [
                {"team_id": t["team_id"], "Pts": t["Pts"], "GD": t["GD"],
                 "GF": t["GF"], "played": t["MP"]}
                for t in teams
            ]
            for letter, teams in raw_groups.items()
        }
        all_team_ids = {t["team_id"] for teams in raw_groups.values() for t in teams}
        team_id_as_user = {tid: tid for tid in all_team_ids}
        group_pts_per_team = _apply_tie_aware_group_points(
            standings_for_scoring, team_id_as_user, place_pts, active_matches
        )

        # ── Assemble output ────────────────────────────────────────────────
        groups: dict[str, list[dict]] = {}
        for letter in sorted(raw_groups.keys()):
            group_teams = []
            for row in raw_groups[letter]:
                tid = row["team_id"]
                group_teams.append({
                    "position":        row["position"],
                    "team_id":         tid,
                    "country_name":    team_names.get(tid, f"Team {tid}"),
                    "played":          row["MP"],
                    "won":             row["W"],
                    "drawn":           row["D"],
                    "lost":            row["L"],
                    "goals_for":       row["GF"],
                    "goals_against":   row["GA"],
                    "goal_difference": row["GD"],
                    "points":          row["Pts"],
                    "pool_pts":        group_pts_per_team.get(tid, 0),
                    "owner_name":      owner_map.get(tid, "Unassigned"),
                })
            groups[letter] = group_teams

        return groups

    except Exception as exc:
        logger.error("get_group_standings_page_data failed: %s", exc)
        return {}


# ── Bracket data ────────────────────────────────────────────────────────────

def get_bracket_data() -> dict:
    """
    Returns knockout matches grouped by stage, with resolved team names,
    winner/loser flags, and owner annotations.

    {
      "rounds": {
        "R32":   [ {match dict}, ... ],
        "R16":   [ ... ],
        "QF":    [ ... ],
        "SF":    [ ... ],
        "FINAL": [ ... ],
      },
      "stage_labels": { "R32": "Round of 32", ... }
    }

    Each match dict includes:
      home_name, away_name         – resolved country name or label/TBD
      home_score, away_score       – int or None
      home_eliminated, away_eliminated – bool (True = loser of finished match)
      home_owner, away_owner       – manager name or ""
      status, stage, kickoff_time  – pass-through from DB row
    """
    try:
        db = anon_client()

        # All knockout matches, chronological within each stage
        res = (
            db.table("matches")
            .select("*")
            .neq("stage", "GROUP")
            .order("stage")
            .order("kickoff_time")
            .execute()
        )
        matches = res.data or []

        # ── Resolve team names ─────────────────────────────────────────────
        team_ids = {
            m[col]
            for m in matches
            for col in ("home_team_id", "away_team_id")
            if m.get(col)
        }
        team_names: dict[int, str] = {}
        if team_ids:
            tr = db.table("teams").select("id, country_name").in_("id", list(team_ids)).execute()
            team_names = {t["id"]: t["country_name"] for t in (tr.data or [])}

        # ── Owner lookup ───────────────────────────────────────────────────
        picks_res = db.table("picks").select("team_id, user:users(name)").execute()
        owner_map: dict[int, str] = {}
        for p in (picks_res.data or []):
            uname = (p.get("user") or {}).get("name") or ""
            owner_map[p["team_id"]] = uname

        stage_order = ["R32", "R16", "QF", "SF", "FINAL"]
        stage_labels = {
            "R32":   "Round of 32",
            "R16":   "Round of 16",
            "QF":    "Quarter-Finals",
            "SF":    "Semi-Finals",
            "FINAL": "Final",
        }

        rounds: dict[str, list[dict]] = {s: [] for s in stage_order}

        for m in matches:
            stage = m.get("stage")
            if stage not in rounds:
                continue

            h_id = m.get("home_team_id")
            a_id = m.get("away_team_id")
            hs   = m.get("home_score")
            as_  = m.get("away_score")

            home_name = team_names.get(h_id) if h_id else (m.get("home_team_label") or "TBD")
            away_name = team_names.get(a_id) if a_id else (m.get("away_team_label") or "TBD")

            home_elim = False
            away_elim = False
            if m.get("status") == "FINISHED" and hs is not None and as_ is not None:
                if hs > as_:
                    away_elim = True
                elif as_ > hs:
                    home_elim = True

            rounds[stage].append({
                **m,
                "home_name":       home_name,
                "away_name":       away_name,
                "home_eliminated": home_elim,
                "away_eliminated": away_elim,
                "home_owner":      owner_map.get(h_id, "") if h_id else "",
                "away_owner":      owner_map.get(a_id, "") if a_id else "",
            })

        # Drop empty rounds so template can check truthiness cleanly
        rounds = {s: v for s, v in rounds.items() if v}

        return {"rounds": rounds, "stage_labels": stage_labels}

    except Exception as exc:
        logger.error("get_bracket_data failed: %s", exc)
        return {"rounds": {}, "stage_labels": {}}
