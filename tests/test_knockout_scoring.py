"""
Unit tests for knockout-stage scoring.

Covers:
  _award_knockout_points  — all five stages, unowned teams, draws, accumulation
"""

import pytest

from scoring_engine import _award_knockout_points
from tests.conftest import (
    PICKS_MAP, SETTINGS, make_db,
    R32_MATCHES, R16_MATCHES, QF_MATCHES, SF_MATCHES, FINAL_MATCHES,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _ko_match(match_id: int, home_id: int, away_id: int,
               home_score: int, away_score: int, stage: str) -> dict:
    return {
        "id": match_id,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_score": home_score,
        "away_score": away_score,
        "stage": stage,
        "status": "FINISHED",
        "kickoff_time": "2026-07-01T18:00:00",
    }


# ── Individual stage tests ─────────────────────────────────────────────────

class TestKnockoutBasics:

    def test_home_win_awards_correct_points(self):
        """Home team wins → home team's owner gets the stage points."""
        # T1 (Alice) beats T2 (Bob) in R32
        db = make_db(extra_matches=[_ko_match(200, 1, 2, 2, 0, "R32")])
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)

        assert scores[1] == 5    # Alice: pt_r32_win=5
        assert scores.get(2, 0) == 0

    def test_away_win_awards_correct_points(self):
        """Away team wins → away team's owner gets the stage points."""
        # T2 (Bob) beats T1 (Alice) — Bob is away team
        db = make_db(extra_matches=[_ko_match(200, 1, 2, 0, 1, "R32")])
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)

        assert scores[2] == 5    # Bob: pt_r32_win=5
        assert scores.get(1, 0) == 0

    def test_draw_awards_no_points(self):
        """Draws in knockout (shouldn't happen in real play, but code should skip)."""
        db = make_db(extra_matches=[_ko_match(200, 1, 2, 1, 1, "R32")])
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)

        assert scores.get(1, 0) == 0
        assert scores.get(2, 0) == 0

    def test_unowned_winner_no_points(self):
        """T99 (no pick) wins → nobody gets points."""
        db = make_db(extra_matches=[_ko_match(200, 99, 1, 2, 0, "R32")])
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)

        # Alice (owns T1, which lost) gets nothing
        assert scores.get(1, 0) == 0
        assert sum(scores.values()) == 0

    def test_no_knockout_matches_returns_empty(self):
        """DB has no knockout matches → zero scores."""
        db = make_db()  # only group matches
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)

        assert sum(scores.values()) == 0

    def test_match_without_score_is_skipped(self):
        """Match with None scores (scheduled/live) must not affect points."""
        db = make_db(extra_matches=[{
            "id": 200, "home_team_id": 1, "away_team_id": 2,
            "home_score": None, "away_score": None,
            "stage": "R32", "status": "SCHEDULED",
            "kickoff_time": "2026-07-01T18:00:00",
        }])
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)
        assert sum(scores.values()) == 0


# ── Point values per stage ─────────────────────────────────────────────────

class TestStagePointValues:

    @pytest.mark.parametrize("stage,expected_pts", [
        ("R32",   5),
        ("R16",   10),
        ("QF",    15),
        ("SF",    20),
        ("FINAL", 30),
    ])
    def test_correct_points_per_stage(self, stage: str, expected_pts: int):
        """Each stage awards the configured number of points to the winner's owner."""
        # T1 (Alice) beats T99 (unowned) at the given stage
        db = make_db(extra_matches=[_ko_match(200, 1, 99, 1, 0, stage)])
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)

        assert scores[1] == expected_pts, (
            f"Stage {stage}: expected {expected_pts}, got {scores[1]}"
        )


# ── Multi-match accumulation ───────────────────────────────────────────────

class TestAccumulation:

    def test_multiple_r32_wins_same_user(self):
        """Alice wins two R32 matches → doubles her R32 points."""
        db = make_db(extra_matches=[
            _ko_match(200, 1, 7,  2, 0, "R32"),   # T1/Alice beats T7/Dave
            _ko_match(201, 8, 99, 1, 0, "R32"),   # T8/Alice beats T99
        ])
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)
        assert scores[1] == 10   # 5 + 5

    def test_different_users_win_at_same_stage(self):
        """Alice and Bob each win a R32 match."""
        db = make_db(extra_matches=[
            _ko_match(200, 1, 99, 2, 0, "R32"),   # T1/Alice
            _ko_match(201, 5, 99, 1, 0, "R32"),   # T5/Bob
        ])
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)
        assert scores[1] == 5    # Alice
        assert scores[2] == 5    # Bob

    def test_full_r32_bracket_from_fixture(self, db):
        """R32 fixture: Alice+5, Bob+5, Carol+10, Dave+0."""
        db.add_rows("matches", R32_MATCHES)
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)

        assert scores[1] == 5    # Alice: T1 wins
        assert scores[2] == 5    # Bob:   T5 wins
        assert scores[3] == 10   # Carol: T3 AND T6 win
        assert scores.get(4, 0) == 0  # Dave: both T4 and T7 lose

    def test_accumulates_across_all_stages(self):
        """
        One win per stage for Alice (T1 always wins) → sum of all stage pts.
        5 + 10 + 15 + 20 + 30 = 80
        """
        matches = [
            _ko_match(200, 1, 99, 1, 0, "R32"),
            _ko_match(201, 1, 99, 1, 0, "R16"),
            _ko_match(202, 1, 99, 1, 0, "QF"),
            _ko_match(203, 1, 99, 1, 0, "SF"),
            _ko_match(204, 1, 99, 1, 0, "FINAL"),
        ]
        db = make_db(extra_matches=matches)
        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)

        assert scores[1] == 80   # 5+10+15+20+30

    def test_full_knockout_run_from_fixtures(self, db):
        """
        Use the full fixture match set.
        Expected per stage:
          R32:   Alice+5,  Bob+5,  Carol+10
          R16:   Alice+10, Bob+10
          QF:    Alice+15
          SF:    Alice+20
          Final: Alice+30
        Totals: Alice=80, Bob=15, Carol=10, Dave=0
        """
        for m in R32_MATCHES + R16_MATCHES + QF_MATCHES + SF_MATCHES + FINAL_MATCHES:
            db.add_rows("matches", [m])

        scores = _award_knockout_points(db, PICKS_MAP, SETTINGS)

        assert scores[1] == 80   # Alice: 5+10+15+20+30
        assert scores[2] == 15   # Bob:   5+10
        assert scores[3] == 10   # Carol: 10 (R32 only)
        assert scores.get(4, 0) == 0
