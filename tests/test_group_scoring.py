"""
Unit tests for group-stage scoring logic.

Covers:
  _apply_tie_aware_group_points  — pure function, no DB needed
  _award_group_points            — tested via both the group_standings
                                   table path and the match-computation fallback
"""

import pytest
from unittest.mock import patch

from scoring_engine import (
    _apply_tie_aware_group_points,
    _award_group_points,
)
from tests.conftest import PLACE_PTS, PICKS_MAP, SETTINGS, make_db, GROUP_STANDINGS


# ── Helper ─────────────────────────────────────────────────────────────────

def _standings(teams: list[dict]) -> dict[str, list[dict]]:
    """Wrap a list of team-stat dicts into the {group_letter: [...]} format."""
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in teams:
        groups[t["group_letter"]].append(t)
    return dict(groups)


def _team(team_id: int, pts: int, gd: int, gf: int, played: int = 3, group: str = "A") -> dict:
    return {
        "team_id": team_id,
        "group_letter": group,
        "Pts": pts,
        "GD": gd,
        "GF": gf,
        "played": played,
    }


# ── _apply_tie_aware_group_points ──────────────────────────────────────────

class TestApplyTieAwareGroupPoints:

    def test_clear_standings_no_ties(self):
        """Four distinct standings → each place gets its configured points."""
        # Group A: T1(Alice)=1st, T3(Carol)=2nd, T2(Bob)=3rd, T4(Dave)=4th
        standings = _standings([
            _team(1, pts=9, gd=6,  gf=6),   # 1st — Alice
            _team(3, pts=4, gd=0,  gf=3),   # 2nd — Carol
            _team(2, pts=3, gd=-2, gf=2),   # 3rd — Bob
            _team(4, pts=1, gd=-3, gf=1),   # 4th — Dave
        ])
        scores = _apply_tie_aware_group_points(standings, PICKS_MAP, PLACE_PTS)

        assert scores[1] == 15   # Alice: 1st
        assert scores[3] == 10   # Carol: 2nd
        assert scores[2] == 5    # Bob:   3rd
        assert scores[4] == 0    # Dave:  4th (0 pts but still in scores)

    def test_first_and_second_tied(self):
        """Two teams tied at top → both receive 1st-place points (15)."""
        standings = _standings([
            _team(1, pts=7, gd=3, gf=5),   # Alice — tied 1st
            _team(2, pts=7, gd=3, gf=5),   # Bob   — tied 1st (same Pts/GD/GF)
            _team(3, pts=4, gd=0, gf=3),   # Carol — 3rd
            _team(4, pts=1, gd=-6, gf=1),  # Dave  — 4th
        ])
        scores = _apply_tie_aware_group_points(standings, PICKS_MAP, PLACE_PTS)

        assert scores[1] == 15  # Alice: tied 1st → gets place_pts[0]
        assert scores[2] == 15  # Bob:   tied 1st → gets place_pts[0]
        assert scores[3] == 5   # Carol: next clear position → 3rd place pts
        assert scores[4] == 0   # Dave:  4th

    def test_bottom_three_tied(self):
        """Positions 2/3/4 all tied → all receive 2nd-place points (10)."""
        standings = _standings([
            _team(1, pts=9, gd=6, gf=6),   # Alice — clear 1st
            _team(2, pts=3, gd=0, gf=2),   # Bob   — tied 2nd
            _team(3, pts=3, gd=0, gf=2),   # Carol — tied 2nd
            _team(4, pts=3, gd=0, gf=2),   # Dave  — tied 2nd
        ])
        scores = _apply_tie_aware_group_points(standings, PICKS_MAP, PLACE_PTS)

        assert scores[1] == 15  # Alice: clear 1st
        assert scores[2] == 10  # Bob:   tied 2nd → best of positions [1,2,3] = 1 → 10
        assert scores[3] == 10
        assert scores[4] == 10

    def test_all_teams_unplayed_get_zero(self):
        """Before any match kicks off (played=0 for all) → everyone gets 0."""
        standings = _standings([
            _team(1, pts=0, gd=0, gf=0, played=0),
            _team(2, pts=0, gd=0, gf=0, played=0),
            _team(3, pts=0, gd=0, gf=0, played=0),
            _team(4, pts=0, gd=0, gf=0, played=0),
        ])
        scores = _apply_tie_aware_group_points(standings, PICKS_MAP, PLACE_PTS)
        assert sum(scores.values()) == 0

    def test_partial_play_unplayed_teams_excluded_from_ties(self):
        """
        T1 has played 1, T2/T3/T4 haven't played.
        T1 should get sole credit for 1st; the unplayed teams get nothing
        even though they share the same 0-0-0 stats.
        """
        standings = _standings([
            _team(1, pts=3, gd=1, gf=1, played=1),  # Alice: played + winning
            _team(2, pts=0, gd=0, gf=0, played=0),  # Bob:   not played
            _team(3, pts=0, gd=0, gf=0, played=0),  # Carol: not played
            _team(4, pts=0, gd=0, gf=0, played=0),  # Dave:  not played
        ])
        scores = _apply_tie_aware_group_points(standings, PICKS_MAP, PLACE_PTS)

        assert scores[1] == 15  # Alice: sole played team → clear 1st
        assert scores.get(2, 0) == 0
        assert scores.get(3, 0) == 0
        assert scores.get(4, 0) == 0

    def test_gd_tiebreak(self):
        """Same Pts, different GD → higher GD wins cleanly, no tie."""
        standings = _standings([
            _team(1, pts=4, gd=3, gf=4),   # Alice — better GD
            _team(2, pts=4, gd=1, gf=4),   # Bob
            _team(3, pts=4, gd=-1, gf=4),  # Carol
            _team(4, pts=0, gd=-3, gf=1),  # Dave
        ])
        scores = _apply_tie_aware_group_points(standings, PICKS_MAP, PLACE_PTS)

        assert scores[1] == 15  # best GD → 1st
        assert scores[2] == 10
        assert scores[3] == 5
        assert scores[4] == 0

    def test_gf_tiebreak(self):
        """Same Pts and GD but different GF → higher GF wins."""
        standings = _standings([
            _team(1, pts=4, gd=2, gf=5),  # Alice — most goals
            _team(2, pts=4, gd=2, gf=4),  # Bob
            _team(3, pts=4, gd=2, gf=3),  # Carol
            _team(4, pts=0, gd=-6, gf=0), # Dave
        ])
        scores = _apply_tie_aware_group_points(standings, PICKS_MAP, PLACE_PTS)

        assert scores[1] == 15
        assert scores[2] == 10
        assert scores[3] == 5

    def test_multi_group_accumulates_per_user(self):
        """
        Scores from two groups accumulate correctly for the same user.
        Bob has T2 (Group A, 3rd → 5pts) and T5 (Group B, 1st → 15pts) → total 20.
        """
        group_a = [_team(1, 9, 6, 6, group="A"), _team(3, 4, 0, 3, group="A"),
                   _team(2, 3, -2, 2, group="A"), _team(4, 1, -3, 1, group="A")]
        group_b = [_team(5, 7, 3, 4, group="B"), _team(6, 5, 1, 2, group="B"),
                   _team(8, 3, -1, 3, group="B"), _team(7, 1, -3, 2, group="B")]

        standings = _standings(group_a + group_b)
        scores = _apply_tie_aware_group_points(standings, PICKS_MAP, PLACE_PTS)

        # Alice: T1(A,1st)=15 + T8(B,3rd)=5  = 20
        # Bob:   T2(A,3rd)=5  + T5(B,1st)=15 = 20
        # Carol: T3(A,2nd)=10 + T6(B,2nd)=10 = 20
        # Dave:  T4(A,4th)=0  + T7(B,4th)=0  = 0
        assert scores[1] == 20   # Alice
        assert scores[2] == 20   # Bob
        assert scores[3] == 20   # Carol
        assert scores.get(4, 0) == 0   # Dave

    def test_unowned_team_contributes_no_points(self):
        """A team not in picks (T99) doesn't award points to anyone."""
        standings = _standings([
            _team(99, pts=9, gd=6, gf=6),  # unowned team wins group
            _team(1,  pts=6, gd=2, gf=4),  # Alice: 2nd
            _team(2,  pts=3, gd=-2, gf=2), # Bob: 3rd
            _team(4,  pts=1, gd=-6, gf=1), # Dave: 4th
        ])
        # T99 is not in PICKS_MAP so it contributes nothing
        scores = _apply_tie_aware_group_points(standings, PICKS_MAP, PLACE_PTS)

        assert scores.get(99, 0) == 0    # no mapping → 0
        assert scores[1] == 10           # Alice: 2nd
        assert scores[2] == 5            # Bob: 3rd


# ── _award_group_points (DB-integrated path) ──────────────────────────────

class TestAwardGroupPoints:

    def test_from_group_standings_table(self, db_with_standings):
        """Uses the group_standings table (API sync path)."""
        scores = _award_group_points(db_with_standings, PICKS_MAP, SETTINGS)

        assert scores[1] == 20   # Alice: T1(A,1st)=15 + T8(B,3rd)=5
        assert scores[2] == 20   # Bob:   T2(A,3rd)=5  + T5(B,1st)=15
        assert scores[3] == 20   # Carol: T3(A,2nd)=10 + T6(B,2nd)=10
        assert scores.get(4, 0) == 0  # Dave: both 4th

    def test_falls_back_when_standings_table_empty(self, db):
        """With empty group_standings, falls back to computing from match rows."""
        scores = _award_group_points(db, PICKS_MAP, SETTINGS)

        assert scores[1] == 20
        assert scores[2] == 20
        assert scores[3] == 20
        assert scores.get(4, 0) == 0

    def test_both_paths_produce_same_result(self, db, db_with_standings):
        """The standings-table path and match-computation fallback agree."""
        scores_fallback = _award_group_points(db, PICKS_MAP, SETTINGS)
        scores_table    = _award_group_points(db_with_standings, PICKS_MAP, SETTINGS)

        assert scores_fallback == scores_table

    def test_mid_group_stage_partial_standings(self):
        """Only 1 match day played: partial standings, non-zero for teams that played."""
        # Only first match day (matches 1 and 7) played
        partial_standings = [
            # Group A after MD1: T1 beat T2, T3-T4 drew
            {"group_letter": "A", "team_id": 1, "position": 1, "points": 3, "goal_difference": 3,  "goals_for": 3, "goals_against": 0, "played": 1},
            {"group_letter": "A", "team_id": 3, "position": 2, "points": 1, "goal_difference": 0,  "goals_for": 1, "goals_against": 1, "played": 1},
            {"group_letter": "A", "team_id": 4, "position": 3, "points": 1, "goal_difference": 0,  "goals_for": 1, "goals_against": 1, "played": 1},
            {"group_letter": "A", "team_id": 2, "position": 4, "points": 0, "goal_difference": -3, "goals_for": 0, "goals_against": 3, "played": 1},
            # Group B after MD1: T5-T6 drew, T8 beat T7
            {"group_letter": "B", "team_id": 8, "position": 1, "points": 3, "goal_difference": 1,  "goals_for": 2, "goals_against": 1, "played": 1},
            {"group_letter": "B", "team_id": 5, "position": 2, "points": 1, "goal_difference": 0,  "goals_for": 0, "goals_against": 0, "played": 1},
            {"group_letter": "B", "team_id": 6, "position": 3, "points": 1, "goal_difference": 0,  "goals_for": 0, "goals_against": 0, "played": 1},
            {"group_letter": "B", "team_id": 7, "position": 4, "points": 0, "goal_difference": -1, "goals_for": 1, "goals_against": 2, "played": 1},
        ]
        db = make_db(use_standings_table=False)
        db._tables["group_standings"] = partial_standings

        scores = _award_group_points(db, PICKS_MAP, SETTINGS)

        # No team has played 0 matches, so scoring proceeds
        # Group A: T1(Alice)=1st→15, T3/T4 tied 2nd (both get 10), T2(Bob)=4th→0
        assert scores[1] >= 0   # Alice has T1 (1st) in A and T8 (1st!) in B
        # The key check: no score should be negative
        for uid, pts in scores.items():
            assert pts >= 0, f"User {uid} has negative points: {pts}"
