"""
Tournament simulation script — manual UI validation.

Run from the project root:
  python scripts/simulate_tournament.py

Prints a step-by-step progression of the leaderboard at each tournament
stage so you can compare it against what the UI shows.

Uses the same MockDB and fixture data as the pytest suite, so the numbers
are guaranteed to agree with the automated tests.
"""

import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

from conftest import (
    MockDB, SETTINGS, PICKS_MAP, PICKS, USERS, TEAMS,
    ALL_GROUP_MATCHES, GROUP_STANDINGS,
    R32_MATCHES, R16_MATCHES, QF_MATCHES, SF_MATCHES, FINAL_MATCHES,
    make_db,
)
from scoring_engine import (
    _award_group_points,
    _award_knockout_points,
)


# ── Display helpers ────────────────────────────────────────────────────────

USER_NAMES = {u["id"]: u["name"] for u in USERS}
TEAM_NAMES = {t["id"]: t["country_name"] for t in TEAMS}
TEAM_TO_USER = {p["team_id"]: p["user_id"] for p in PICKS}

# Each user's picks grouped
USER_PICKS: dict[int, list[int]] = {}
for p in PICKS:
    USER_PICKS.setdefault(p["user_id"], []).append(p["team_id"])


def _bar(pts: int, max_pts: int, width: int = 30) -> str:
    filled = int((pts / max_pts) * width) if max_pts > 0 else 0
    return "█" * filled + "░" * (width - filled)


def print_header(title: str):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_leaderboard(group_scores: dict, ko_scores: dict, stage_label: str):
    all_ids = set(PICKS_MAP.values())
    totals = {uid: group_scores.get(uid, 0) + ko_scores.get(uid, 0) for uid in all_ids}
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    max_pts = ranked[0][1] if ranked else 1

    print(f"\n  {'Rank':<5} {'Manager':<10} {'Pts':>5}  {'Group':>6}  {'KO':>5}  Bar")
    print(f"  {'-'*4}  {'-'*9}  {'-'*5}  {'-'*6}  {'-'*5}  {'-'*30}")

    prev_pts = None
    rank = 0
    for i, (uid, pts) in enumerate(ranked):
        if pts != prev_pts:
            rank = i + 1
        prev_pts = pts
        gp = group_scores.get(uid, 0)
        kp = ko_scores.get(uid, 0)
        bar = _bar(pts, max_pts) if max_pts > 0 else "░" * 30
        print(f"  {rank:<5} {USER_NAMES[uid]:<10} {pts:>5}  {gp:>6}  {kp:>5}  {bar}")


def print_team_breakdown(group_scores: dict, ko_scores: dict):
    """Show which teams each user owns and what their current standing is."""
    all_ids = set(PICKS_MAP.values())
    totals = {uid: group_scores.get(uid, 0) + ko_scores.get(uid, 0) for uid in all_ids}

    for uid in sorted(totals, key=lambda x: totals[x], reverse=True):
        teams = USER_PICKS.get(uid, [])
        team_strs = [f"{TEAM_NAMES.get(t, f'T{t}')}" for t in teams]
        print(f"\n  {USER_NAMES[uid]} ({totals[uid]} pts)  —  teams: {', '.join(team_strs)}")


def print_match_results(matches: list[dict], label: str):
    if not matches:
        return
    print(f"\n  {label}:")
    for m in matches:
        h = TEAM_NAMES.get(m["home_team_id"], f"T{m['home_team_id']}")
        a = TEAM_NAMES.get(m["away_team_id"], f"T{m['away_team_id']}")
        hs, as_ = m["home_score"], m["away_score"]
        winner_note = ""
        if hs is not None and as_ is not None:
            if hs > as_:
                owner = USER_NAMES.get(TEAM_TO_USER.get(m["home_team_id"]), "—")
                winner_note = f"  ✓ {h} wins  ({owner})"
            elif as_ > hs:
                owner = USER_NAMES.get(TEAM_TO_USER.get(m["away_team_id"]), "—")
                winner_note = f"  ✓ {a} wins  ({owner})"
            else:
                winner_note = "  draw"
        print(f"    {h:>12}  {hs}-{as_}  {a:<12}{winner_note}")


# ── Simulation stages ─────────────────────────────────────────────────────

def simulate():

    # ── Stage 0: pre-tournament ─────────────────────────────────────────
    print_header("PRE-TOURNAMENT  (no matches played)")
    db = make_db(extra_matches=[], use_standings_table=False)
    db._tables["matches"] = []
    g = _award_group_points(db, PICKS_MAP, SETTINGS)
    k = _award_knockout_points(db, PICKS_MAP, SETTINGS)
    print_leaderboard(g, k, "Pre-tournament")
    print("\n  Expected UI: all managers at 0 pts, equal ranking")

    # ── Stage 1: after MD1 ──────────────────────────────────────────────
    print_header("AFTER MATCH DAY 1  (6 of 12 group matches played)")
    md1_ids = {1, 2, 7, 8}
    md1_matches = [m for m in ALL_GROUP_MATCHES if m["id"] in md1_ids]
    db = make_db(extra_matches=[], use_standings_table=False)
    db._tables["matches"] = md1_matches
    print_match_results(md1_matches, "Match Day 1 results")
    g = _award_group_points(db, PICKS_MAP, SETTINGS)
    k = _award_knockout_points(db, PICKS_MAP, SETTINGS)
    print_leaderboard(g, k, "After MD1")
    print("\n  Note: standings are provisional after only one round of fixtures.")
    print("  Check the UI standings page — group tables should show 1 game played.")

    # ── Stage 2: after MD2 ──────────────────────────────────────────────
    print_header("AFTER MATCH DAY 2  (8 of 12 group matches played)")
    md2_ids = {1, 2, 3, 4, 7, 8, 9, 10}
    md2_matches = [m for m in ALL_GROUP_MATCHES if m["id"] in md2_ids]
    db = make_db(extra_matches=[], use_standings_table=False)
    db._tables["matches"] = md2_matches
    print_match_results(
        [m for m in ALL_GROUP_MATCHES if m["id"] in {3, 4, 9, 10}],
        "Match Day 2 results"
    )
    g = _award_group_points(db, PICKS_MAP, SETTINGS)
    k = _award_knockout_points(db, PICKS_MAP, SETTINGS)
    print_leaderboard(g, k, "After MD2")

    # ── Stage 3: group stage complete ──────────────────────────────────
    print_header("GROUP STAGE COMPLETE  (all 12 group matches played)")
    print_match_results(
        [m for m in ALL_GROUP_MATCHES if m["id"] in {5, 6, 11, 12}],
        "Match Day 3 results"
    )

    db = make_db(use_standings_table=True)
    g = _award_group_points(db, PICKS_MAP, SETTINGS)
    k_empty = {}
    print_leaderboard(g, k_empty, "After Group Stage")
    print_team_breakdown(g, k_empty)

    print("""
  Final Group Standings:
    Group A:  Argentina 1st (Alice), Chile 2nd (Carol), Brazil 3rd (Bob), Denmark 4th (Dave)
    Group B:  England   1st (Bob),  France 2nd (Carol), Hungary 3rd (Alice), Germany 4th (Dave)

  Expected pool totals:
    Alice  = 15 (Argentina A-1st) + 5 (Hungary B-3rd)  = 20
    Bob    = 5  (Brazil   A-3rd)  + 15 (England B-1st) = 20
    Carol  = 10 (Chile    A-2nd)  + 10 (France  B-2nd) = 20
    Dave   = 0 + 0 = 0
    """)

    # ── Stage 4: Round of 32 ────────────────────────────────────────────
    print_header("AFTER ROUND OF 32")
    print_match_results(R32_MATCHES, "R32 results")
    db = make_db(extra_matches=R32_MATCHES, use_standings_table=True)
    g = _award_group_points(db, PICKS_MAP, SETTINGS)
    k = _award_knockout_points(db, PICKS_MAP, SETTINGS)
    print_leaderboard(g, k, "After R32")
    print("""
  Carol leads! She had TWO teams win in R32 (Chile T3 + France T6).
  Dave's teams Germany and Denmark both eliminated.
    """)

    # ── Stage 5: Round of 16 ────────────────────────────────────────────
    print_header("AFTER ROUND OF 16")
    print_match_results(R16_MATCHES, "R16 results")
    db = make_db(extra_matches=R32_MATCHES + R16_MATCHES, use_standings_table=True)
    g = _award_group_points(db, PICKS_MAP, SETTINGS)
    k = _award_knockout_points(db, PICKS_MAP, SETTINGS)
    print_leaderboard(g, k, "After R16")
    print("""
  Carol's last teams eliminated — she's locked in at 30.
  Alice and Bob both advanced with +10 each, tied at 35.
    """)

    # ── Stage 6: Quarter-Finals ─────────────────────────────────────────
    print_header("AFTER QUARTER-FINALS")
    print_match_results(QF_MATCHES, "QF results")
    db = make_db(extra_matches=R32_MATCHES + R16_MATCHES + QF_MATCHES, use_standings_table=True)
    g = _award_group_points(db, PICKS_MAP, SETTINGS)
    k = _award_knockout_points(db, PICKS_MAP, SETTINGS)
    print_leaderboard(g, k, "After QF")
    print("""
  Alice pulls ahead!  Argentina beat England (Alice beats Bob's last team).
  Bob is locked in at 35.
    """)

    # ── Stage 7: Semi-Finals ────────────────────────────────────────────
    print_header("AFTER SEMI-FINALS")
    print_match_results(SF_MATCHES, "SF results")
    db = make_db(extra_matches=R32_MATCHES + R16_MATCHES + QF_MATCHES + SF_MATCHES, use_standings_table=True)
    g = _award_group_points(db, PICKS_MAP, SETTINGS)
    k = _award_knockout_points(db, PICKS_MAP, SETTINGS)
    print_leaderboard(g, k, "After SF")
    print("  Argentina into the Final!  Alice now at 70.")

    # ── Stage 8: Final ──────────────────────────────────────────────────
    print_header("FINAL RESULT 🏆")
    print_match_results(FINAL_MATCHES, "Final")
    all_ko = R32_MATCHES + R16_MATCHES + QF_MATCHES + SF_MATCHES + FINAL_MATCHES
    db = make_db(extra_matches=all_ko, use_standings_table=True)
    g = _award_group_points(db, PICKS_MAP, SETTINGS)
    k = _award_knockout_points(db, PICKS_MAP, SETTINGS)
    print_leaderboard(g, k, "Final standings")

    print("""
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  FINAL SCORES (verify against UI leaderboard):
    1st  Alice  100  (Group:20  R32:5   R16:10  QF:15  SF:20  Final:30)
    2nd  Bob     35  (Group:20  R32:5   R16:10)
    3rd  Carol   30  (Group:20  R32:10)
    4th  Dave     0

  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)


if __name__ == "__main__":
    simulate()
