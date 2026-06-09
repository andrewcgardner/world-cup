"""
scripts/seed_test_state.py
===========================
Injects synthetic match results into Supabase so you can browse the real UI
without waiting for live games.

Prerequisites (run once if not already done):
  python scripts/seed.py                              # users, teams, settings
  python scripts/seed_groups.py                       # group_letter + group_standings baseline
  python scripts/seed_matches.py --file scripts/data/games.json  # all 104 matches
  (run the draw via /admin/panel → "Run Draw" button, or via admin API)

Usage:
  python scripts/seed_test_state.py --stage group-md1    # matchday 1 only
  python scripts/seed_test_state.py --stage group-md2    # matchdays 1-2
  python scripts/seed_test_state.py --stage group        # full group stage
  python scripts/seed_test_state.py --stage r32          # group + Round of 32
  python scripts/seed_test_state.py --stage r16          # ... through Round of 16
  python scripts/seed_test_state.py --stage qf           # ... through QF
  python scripts/seed_test_state.py --stage sf           # ... through SF
  python scripts/seed_test_state.py --stage final        # full tournament
  python scripts/seed_test_state.py --reset              # revert everything to SCHEDULED

Scoring logic for synthetic results:
  Winner = team with lower pot_number (pot 1 beats pot 4, etc.)
  Same pot = home team wins
  Scores: large gap (2+ pots) → 3-0; 1 pot gap → 2-1; same pot → 1-0
  Introduces one intentional draw per group (between the 2 weakest teams)
  to exercise the tie-aware scoring logic.
"""

import sys
import os
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import admin_client
from scoring_engine import recompute_all_scores

# ── Stage ordering ─────────────────────────────────────────────────────────

STAGE_ORDER = ["group-md1", "group-md2", "group", "r32", "r16", "qf", "sf", "final"]
MATCHDAY_FOR_STAGE = {
    "group-md1": [1],
    "group-md2": [1, 2],
    "group":     [1, 2, 3],
}
KO_STAGES_FOR_STAGE = {
    "r32":   ["R32"],
    "r16":   ["R32", "R16"],
    "qf":    ["R32", "R16", "QF"],
    "sf":    ["R32", "R16", "QF", "SF"],
    "final": ["R32", "R16", "QF", "SF", "FINAL"],
}


# ── Synthetic score calculation ────────────────────────────────────────────

def _synthetic_result(home_pot: int, away_pot: int, match_index: int) -> tuple[int, int]:
    """
    Return (home_score, away_score).
    Winner = lower pot_number.  Same pot = home wins (1-0).
    Introduces one draw per match_index==0 if both teams have the same pot.
    """
    if home_pot == away_pot:
        # One draw per group between same-pot teams (index 0 in that group)
        if match_index % 3 == 2:
            return (1, 1)
        return (1, 0)  # home wins on default

    pot_diff = away_pot - home_pot  # positive = home team is better
    if pot_diff > 0:
        # Home is better
        if pot_diff >= 2:
            return (3, 0)
        return (2, 1)
    else:
        # Away is better
        if abs(pot_diff) >= 2:
            return (0, 3)
        return (1, 2)


# ── Group standings computation ─────────────────────────────────────────────

def _compute_standings(matches: list[dict]) -> dict[str, list[dict]]:
    """Replay finished group matches and return standings per group."""
    stats: dict[int, dict] = {}

    def _init(tid: int, grp: str) -> dict:
        return {"team_id": tid, "group_letter": grp,
                "MP": 0, "W": 0, "D": 0, "L": 0,
                "GF": 0, "GA": 0, "GD": 0, "Pts": 0}

    for m in matches:
        if m.get("status") != "FINISHED" or m.get("stage") != "GROUP":
            continue
        h, a = m["home_team_id"], m["away_team_id"]
        hs, as_ = m["home_score"], m["away_score"]
        grp = m.get("group_letter", "?")
        for tid, gf, ga in [(h, hs, as_), (a, as_, hs)]:
            s = stats.setdefault(tid, _init(tid, grp))
            s["MP"] += 1; s["GF"] += gf; s["GA"] += ga; s["GD"] = s["GF"] - s["GA"]
            if gf > ga:    s["W"] += 1; s["Pts"] += 3
            elif gf == ga: s["D"] += 1; s["Pts"] += 1
            else:          s["L"] += 1

    groups: dict[str, list[dict]] = defaultdict(list)
    for st in stats.values():
        groups[st["group_letter"]].append(st)
    for grp in groups:
        groups[grp].sort(key=lambda x: (x["Pts"], x["GD"], x["GF"]), reverse=True)
    return dict(groups)


# ── Simulate group matches ─────────────────────────────────────────────────

def _simulate_group_matches(
    db, matchdays: list[int], pot_map: dict[int, int]
) -> list[dict]:
    """
    Load group matches for the given matchdays, assign synthetic results,
    upsert to DB, and return the updated rows.
    """
    res = db.table("matches").select("*").eq("stage", "GROUP").execute()
    all_group = res.data or []

    updated = []
    group_match_counter: dict[str, int] = defaultdict(int)  # group → match count

    for m in sorted(all_group, key=lambda x: (x.get("matchday") or 0, x.get("id") or 0)):
        md = m.get("matchday") or 0
        grp = m.get("group_letter") or "?"
        h_id = m.get("home_team_id")
        a_id = m.get("away_team_id")

        if md not in matchdays or not h_id or not a_id:
            continue

        idx = group_match_counter[grp]
        group_match_counter[grp] += 1

        h_pot = pot_map.get(h_id, 4)
        a_pot = pot_map.get(a_id, 4)
        hs, as_ = _synthetic_result(h_pot, a_pot, idx)

        db.table("matches").update({
            "home_score": hs,
            "away_score": as_,
            "status": "FINISHED",
        }).eq("id", m["id"]).execute()

        updated.append({**m, "home_score": hs, "away_score": as_,
                        "status": "FINISHED"})

    return updated


# ── Update group_standings ─────────────────────────────────────────────────

def _upsert_standings(db, standings: dict[str, list[dict]]) -> None:
    """Write computed group standings back to the group_standings table."""
    rows = []
    for grp, teams in standings.items():
        for pos, t in enumerate(teams, start=1):
            rows.append({
                "group_letter":    grp,
                "team_id":         t["team_id"],
                "position":        pos,
                "points":          t["Pts"],
                "goal_difference": t["GD"],
                "goals_for":       t["GF"],
                "goals_against":   t["GA"],
                "played":          t["MP"],
                "won":             t["W"],
                "drawn":           t["D"],
                "lost":            t["L"],
            })
    if rows:
        db.table("group_standings").upsert(
            rows, on_conflict="group_letter,team_id"
        ).execute()
        print(f"  ✓ Upserted {len(rows)} group_standings rows")


# ── Knockout simulation ────────────────────────────────────────────────────

def _resolve_ko_bracket(
    db,
    standings: dict[str, list[dict]],
    ko_stages: list[str],
    pot_map: dict[int, int],
) -> None:
    """
    Resolve the knockout bracket based on group results, then simulate
    each requested KO stage and write results to the matches table.

    3rd-place bracket: uses the best 8 of the 12 3rd-place finishers,
    assigned to slots in the order they appear in the match labels.
    (This approximates the real 2026 rules well enough for UI testing.)
    """
    # ── Build qualified teams ───────────────────────────────────────────────
    group_winners: dict[str, int]    = {}
    group_runners: dict[str, int]    = {}
    third_place_teams: list[dict]    = []  # sorted best→worst

    for grp, teams in sorted(standings.items()):
        if len(teams) >= 1: group_winners[grp] = teams[0]["team_id"]
        if len(teams) >= 2: group_runners[grp] = teams[1]["team_id"]
        if len(teams) >= 3:
            t = teams[2]
            third_place_teams.append({
                "team_id": t["team_id"],
                "group": grp,
                "Pts": t["Pts"], "GD": t["GD"], "GF": t["GF"],
            })

    third_place_teams.sort(
        key=lambda x: (x["Pts"], x["GD"], x["GF"]), reverse=True
    )
    best_thirds_ids = [t["team_id"] for t in third_place_teams[:8]]
    third_iter = iter(best_thirds_ids)

    # ── Parse bracket labels from DB ────────────────────────────────────────
    def _resolve_label(label: str) -> int | None:
        """Map a match label like 'Winner Group A' to a team_id."""
        label = (label or "").strip()
        if label.startswith("Winner Group "):
            grp = label.split()[-1]
            return group_winners.get(grp)
        if label.startswith("Runner-up Group "):
            grp = label.split()[-1]
            return group_runners.get(grp)
        if label.startswith("3rd"):
            return next(third_iter, None)
        return None

    # ── Load all KO matches (stages R32 through FINAL) ─────────────────────
    res = (
        db.table("matches")
        .select("*")
        .neq("stage", "GROUP")
        .order("matchday")
        .execute()
    )
    ko_matches = {m["external_id"]: m for m in (res.data or [])}

    # Process stages in order; winners advance to the next round.
    # We track {match_id: winner_team_id} so "Winner Match X" labels resolve.
    match_winners: dict[int, int] = {}  # external_id → winning team_id

    stage_map = {"R32": "R32", "R16": "R16", "QF": "QF", "SF": "SF", "FINAL": "FINAL"}

    for ko_stage in ["R32", "R16", "QF", "SF", "FINAL"]:
        stage_matches = sorted(
            [m for m in ko_matches.values() if m.get("stage") == ko_stage],
            key=lambda x: x.get("external_id") or 0,
        )

        for m in stage_matches:
            ext_id = m["external_id"]
            home_label = m.get("home_team_label") or ""
            away_label = m.get("away_team_label") or ""

            # Try to resolve team IDs for this match
            # First check if already set (non-zero)
            h_id = m.get("home_team_id") or None
            a_id = m.get("away_team_id") or None

            # Resolve from labels if not already set
            if not h_id:
                if home_label.startswith("Winner Match "):
                    prev = int(home_label.split()[-1])
                    h_id = match_winners.get(prev)
                else:
                    h_id = _resolve_label(home_label)

            if not a_id:
                if away_label.startswith("Winner Match "):
                    prev = int(away_label.split()[-1])
                    a_id = match_winners.get(prev)
                else:
                    a_id = _resolve_label(away_label)

            if not h_id or not a_id:
                continue  # can't resolve participants yet

            # Assign synthetic result
            h_pot = pot_map.get(h_id, 4)
            a_pot = pot_map.get(a_id, 4)
            hs, as_ = _synthetic_result(h_pot, a_pot, ext_id)
            winner = h_id if hs > as_ else a_id
            match_winners[ext_id] = winner

            # Update DB
            update_payload = {
                "home_team_id": h_id,
                "away_team_id": a_id,
                "home_score":   hs,
                "away_score":   as_,
            }
            if ko_stage in ko_stages:
                update_payload["status"] = "FINISHED"

            db.table("matches").update(update_payload).eq("external_id", ext_id).execute()
            ko_matches[ext_id] = {**m, **update_payload}

        if ko_stage in ko_stages:
            finished = sum(
                1 for m in stage_matches
                if ko_matches.get(m["external_id"], {}).get("status") == "FINISHED"
            )
            print(f"  ✓ {ko_stage}: {finished}/{len(stage_matches)} matches marked FINISHED")

        if ko_stage not in ko_stages:
            break  # stop resolving beyond the requested stage


# ── Reset ──────────────────────────────────────────────────────────────────

def _reset(db) -> None:
    """Revert all matches to SCHEDULED (null scores), zero standings and scores."""
    # Reset all group matches
    db.table("matches").update({
        "home_score": None,
        "away_score": None,
        "status": "SCHEDULED",
    }).eq("stage", "GROUP").execute()

    # Reset all KO matches (also clear team IDs since they come from bracket resolution)
    for stage in ["R32", "R16", "QF", "SF", "FINAL"]:
        db.table("matches").update({
            "home_team_id": None,
            "away_team_id": None,
            "home_score": None,
            "away_score": None,
            "status": "SCHEDULED",
        }).eq("stage", stage).execute()

    # Zero out group_standings (reset to all zeros, keep the rows)
    standings_res = db.table("group_standings").select("group_letter, team_id").execute()
    for row in (standings_res.data or []):
        db.table("group_standings").update({
            "position": 1, "points": 0, "goal_difference": 0,
            "goals_for": 0, "goals_against": 0, "played": 0,
            "won": 0, "drawn": 0, "lost": 0,
        }).eq("group_letter", row["group_letter"]).eq("team_id", row["team_id"]).execute()

    # Clear scores
    db.table("scores").delete().neq("user_id", 0).execute()

    print("  ✓ All matches reset to SCHEDULED")
    print("  ✓ group_standings zeroed")
    print("  ✓ scores cleared")


# ── Prerequisite checks ────────────────────────────────────────────────────

def _check_prerequisites(db) -> dict[int, int]:
    """
    Verify the DB is ready for test seeding.
    Returns pot_map {team_id: pot_number}.
    Exits with a helpful message if prerequisites aren't met.
    """
    # Check teams exist
    teams_res = db.table("teams").select("id, pot_number, country_name").execute()
    if not teams_res.data:
        print("\n⛔  No teams found. Run: python scripts/seed.py")
        sys.exit(1)

    pot_map = {t["id"]: t["pot_number"] for t in teams_res.data}
    print(f"  ✓ {len(pot_map)} teams loaded")

    # Check matches exist
    matches_res = db.table("matches").select("id", count="exact").execute()
    match_count = matches_res.count or len(matches_res.data or [])
    if match_count < 72:
        print(f"\n⛔  Only {match_count} matches found (need ≥72).")
        print("    Run: python scripts/seed_matches.py --file scripts/data/games.json")
        sys.exit(1)
    print(f"  ✓ {match_count} matches in DB")

    # Check picks exist (draw was run)
    picks_res = db.table("picks").select("id", count="exact").execute()
    pick_count = picks_res.count or len(picks_res.data or [])
    if pick_count == 0:
        print("\n⚠  No picks found — scores won't be computed until the draw is run.")
        print("   → Go to /admin/panel and click 'Run Draw', then re-run this script.")
        print("   Continuing anyway (match results will still be visible in the UI).")
    else:
        print(f"  ✓ {pick_count} picks found (draw has been run)")

    return pot_map


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inject synthetic match results for UI testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
stages:
  group-md1   Matchday 1 results only
  group-md2   Matchdays 1-2 results
  group       Full group stage complete
  r32         Group complete + Round of 32
  r16         Through Round of 16
  qf          Through Quarter-Finals
  sf          Through Semi-Finals
  final       Full tournament complete
        """,
    )
    parser.add_argument(
        "--stage", choices=STAGE_ORDER,
        help="Tournament stage to simulate through."
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Revert all matches to SCHEDULED, clear scores."
    )
    args = parser.parse_args()

    if not args.stage and not args.reset:
        parser.print_help()
        sys.exit(1)

    db = admin_client()

    print("\n" + "=" * 60)
    if args.reset:
        print("  Resetting all match data …")
        print("=" * 60)
        _reset(db)
        print("\n✅  Reset complete. All matches are back to SCHEDULED.\n")
        return

    print(f"  Seeding test state: {args.stage}")
    print("=" * 60)

    pot_map = _check_prerequisites(db)

    # ── Determine which matchdays to simulate ──────────────────────────────
    is_ko_stage = args.stage in KO_STAGES_FOR_STAGE
    group_matchdays = MATCHDAY_FOR_STAGE.get(
        args.stage if not is_ko_stage else "group",
        [1, 2, 3],
    )

    # ── Simulate group matches ─────────────────────────────────────────────
    print(f"\n  Simulating group matchdays {group_matchdays} …")
    finished_matches = _simulate_group_matches(db, group_matchdays, pot_map)
    print(f"  ✓ {len(finished_matches)} group matches marked FINISHED")

    # ── Compute and upsert standings ───────────────────────────────────────
    # Re-load all group matches (finished + scheduled) for standings computation
    all_group_res = db.table("matches").select("*").eq("stage", "GROUP").execute()
    standings = _compute_standings(all_group_res.data or [])
    _upsert_standings(db, standings)

    # Print standings summary
    print("\n  Group standings summary:")
    for grp in sorted(standings.keys()):
        teams = standings[grp]
        line = f"    Group {grp}: "
        for i, t in enumerate(teams[:4], 1):
            suffix = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}[i]
            line += f"T{t['team_id']}({suffix},{t['Pts']}pts)  "
        print(line)

    # ── Simulate knockout stages (if requested) ────────────────────────────
    if is_ko_stage and len(standings) == 12:  # only if full group stage available
        ko_stages = KO_STAGES_FOR_STAGE[args.stage]
        print(f"\n  Resolving knockout bracket through {ko_stages[-1]} …")
        _resolve_ko_bracket(db, standings, ko_stages, pot_map)
    elif is_ko_stage:
        print(f"\n  ⚠  Only {len(standings)} of 12 groups have results — skipping knockout.")
        print("     Use --stage group first to complete the group stage.")

    # ── Recompute pool scores ──────────────────────────────────────────────
    print("\n  Recomputing pool scores …")
    try:
        recompute_all_scores()
        print("  ✓ Scores updated")
    except Exception as e:
        print(f"  ⚠  Score recompute failed: {e}")
        print("     This is OK if picks haven't been created yet.")

    print(f"\n✅  Done. Start the app and browse to / to see the results.\n")


if __name__ == "__main__":
    main()
