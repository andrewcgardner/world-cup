"""
Full tournament simulation tests.

Walks through the tournament stage by stage, verifying leaderboard scores
at each checkpoint.  Patches scoring_engine.admin_client so recompute_all_scores()
uses in-memory data instead of Supabase.

Expected final totals:
  Alice: group(20) + R32(5) + R16(10) + QF(15) + SF(20) + Final(30) = 100
  Bob:   group(20) + R32(5) + R16(10)                                 = 35
  Carol: group(20) + R32(10)                                           = 30
  Dave:  0
"""

import pytest
from unittest.mock import patch

from scoring_engine import (
    _award_group_points,
    _award_knockout_points,
    recompute_all_scores,
)
from tests.conftest import (
    PICKS_MAP, SETTINGS, make_db,
    ALL_GROUP_MATCHES,
    R32_MATCHES, R16_MATCHES, QF_MATCHES, SF_MATCHES, FINAL_MATCHES,
)


# ── Stage-by-stage checkpoint tests ───────────────────────────────────────

class TestTournamentProgression:

    def _total(self, db, extra_ko: list | None = None) -> dict[int, int]:
        """
        Compute merged total scores (group + knockout) for the given DB state.
        """
        db.add_rows("matches", extra_ko or [])
        group_scores = _award_group_points(db, PICKS_MAP, SETTINGS)
        ko_scores    = _award_knockout_points(db, PICKS_MAP, SETTINGS)
        all_user_ids = set(PICKS_MAP.values())
        return {uid: group_scores.get(uid, 0) + ko_scores.get(uid, 0)
                for uid in all_user_ids}

    def test_before_tournament_all_zeros(self):
        """
        Before any matches, group_standings table is empty and no finished
        matches exist → everyone scores 0.
        """
        db = make_db(extra_matches=[], use_standings_table=False)
        # Remove all match data to simulate pre-tournament state
        db._tables["matches"] = []

        group_scores = _award_group_points(db, PICKS_MAP, SETTINGS)
        ko_scores    = _award_knockout_points(db, PICKS_MAP, SETTINGS)

        assert sum(group_scores.values()) == 0
        assert sum(ko_scores.values()) == 0

    def test_after_first_group_match_day(self):
        """
        After MD1 (T1 beat T2, T3-T4 drew, T8 beat T7, T5-T6 drew):
        standings are provisional but scoring reflects current positions.
        Scores should be non-negative and total > 0.
        """
        # Only MD1 matches (ids 1, 2, 7, 8)
        md1 = [m for m in ALL_GROUP_MATCHES if m["id"] in {1, 2, 7, 8}]
        db = make_db(extra_matches=[], use_standings_table=False)
        db._tables["matches"] = md1

        scores = _award_group_points(db, PICKS_MAP, SETTINGS)

        assert sum(scores.values()) > 0          # some points awarded
        for uid, pts in scores.items():
            assert pts >= 0, f"User {uid} has negative points after MD1"

    def test_after_group_stage_complete(self):
        """
        After all group matches, group totals should be:
          Alice 20, Bob 20, Carol 20, Dave 0
        """
        db = make_db(use_standings_table=False)  # has all group matches
        scores = _award_group_points(db, PICKS_MAP, SETTINGS)

        assert scores[1] == 20   # Alice
        assert scores[2] == 20   # Bob
        assert scores[3] == 20   # Carol
        assert scores.get(4, 0) == 0  # Dave

    def test_after_group_stage_via_standings_table(self):
        """Same checkpoint but through the group_standings table path."""
        db = make_db(use_standings_table=True)
        scores = _award_group_points(db, PICKS_MAP, SETTINGS)

        assert scores[1] == 20
        assert scores[2] == 20
        assert scores[3] == 20
        assert scores.get(4, 0) == 0

    def test_after_r32(self):
        """
        After R32:
          Group: Alice 20, Bob 20, Carol 20, Dave 0
          R32:   Alice +5, Bob +5, Carol +10, Dave 0
          Total: Alice 25, Bob 25, Carol 30, Dave 0
        """
        db = make_db(use_standings_table=True)
        scores = self._total(db, R32_MATCHES)

        assert scores[1] == 25   # Alice
        assert scores[2] == 25   # Bob
        assert scores[3] == 30   # Carol (two teams win)
        assert scores[4] == 0    # Dave

    def test_after_r16(self):
        """
        After R16 (Alice beats Carol's T6, Bob beats Carol's T3):
          Group: Alice 20, Bob 20, Carol 20, Dave 0
          R32:   Alice +5, Bob +5, Carol +10
          R16:   Alice +10, Bob +10
          Total: Alice 35, Bob 35, Carol 30, Dave 0
        """
        db = make_db(use_standings_table=True)
        scores = self._total(db, R32_MATCHES + R16_MATCHES)

        assert scores[1] == 35
        assert scores[2] == 35
        assert scores[3] == 30
        assert scores[4] == 0

    def test_after_qf(self):
        """
        After QF (Alice's T1 beats Bob's T5):
          Total: Alice 50, Bob 35, Carol 30, Dave 0
        """
        db = make_db(use_standings_table=True)
        scores = self._total(db, R32_MATCHES + R16_MATCHES + QF_MATCHES)

        assert scores[1] == 50
        assert scores[2] == 35
        assert scores[3] == 30
        assert scores[4] == 0

    def test_after_sf(self):
        """
        After SF (Alice's T1 beats unowned T99):
          Total: Alice 70, Bob 35, Carol 30, Dave 0
        """
        db = make_db(use_standings_table=True)
        scores = self._total(db, R32_MATCHES + R16_MATCHES + QF_MATCHES + SF_MATCHES)

        assert scores[1] == 70
        assert scores[2] == 35
        assert scores[3] == 30
        assert scores[4] == 0

    def test_final_scores(self):
        """
        Complete tournament:
          Alice 100, Bob 35, Carol 30, Dave 0
        """
        db = make_db(use_standings_table=True)
        all_ko = R32_MATCHES + R16_MATCHES + QF_MATCHES + SF_MATCHES + FINAL_MATCHES
        scores = self._total(db, all_ko)

        assert scores[1] == 100
        assert scores[2] == 35
        assert scores[3] == 30
        assert scores[4] == 0

    def test_scores_monotonically_increase(self):
        """
        Each stage can only add points, never remove them.
        Verify the leaderboard never decreases between stages.
        """
        stages = [
            [],
            R32_MATCHES,
            R32_MATCHES + R16_MATCHES,
            R32_MATCHES + R16_MATCHES + QF_MATCHES,
            R32_MATCHES + R16_MATCHES + QF_MATCHES + SF_MATCHES,
            R32_MATCHES + R16_MATCHES + QF_MATCHES + SF_MATCHES + FINAL_MATCHES,
        ]

        prev_totals = {uid: 0 for uid in [1, 2, 3, 4]}
        for stage_matches in stages:
            db = make_db(use_standings_table=True)
            g = _award_group_points(db, PICKS_MAP, SETTINGS)
            db.add_rows("matches", stage_matches)
            k = _award_knockout_points(db, PICKS_MAP, SETTINGS)
            totals = {uid: g.get(uid, 0) + k.get(uid, 0) for uid in [1, 2, 3, 4]}

            for uid in [1, 2, 3, 4]:
                assert totals[uid] >= prev_totals[uid], (
                    f"User {uid} score decreased! {prev_totals[uid]} → {totals[uid]}"
                )
            prev_totals = totals


# ── recompute_all_scores integration test ─────────────────────────────────

class TestRecomputeAllScores:
    """
    Tests recompute_all_scores() end-to-end by patching admin_client
    with a MockDB and verifying the scores table is written correctly.
    """

    def test_recompute_writes_correct_scores(self, full_tournament_db):
        """
        After a full tournament, recompute_all_scores() should upsert:
          Alice=100, Bob=35, Carol=30, Dave=0  into the scores table.
        """
        with patch("scoring_engine.admin_client", return_value=full_tournament_db):
            recompute_all_scores()

        scores_rows = full_tournament_db._tables.get("scores", [])
        scores_by_user = {r["user_id"]: r["total_points"] for r in scores_rows}

        assert scores_by_user[1] == 100  # Alice
        assert scores_by_user[2] == 35   # Bob
        assert scores_by_user[3] == 30   # Carol
        assert scores_by_user[4] == 0    # Dave

    def test_recompute_group_only(self):
        """recompute_all_scores() with only group data writes group-only scores."""
        db = make_db(use_standings_table=True)

        with patch("scoring_engine.admin_client", return_value=db):
            recompute_all_scores()

        scores_rows = db._tables.get("scores", [])
        scores_by_user = {r["user_id"]: r["total_points"] for r in scores_rows}

        assert scores_by_user[1] == 20
        assert scores_by_user[2] == 20
        assert scores_by_user[3] == 20
        assert scores_by_user[4] == 0

    def test_recompute_upserts_not_duplicates(self, full_tournament_db):
        """Calling recompute twice shouldn't double-count points."""
        with patch("scoring_engine.admin_client", return_value=full_tournament_db):
            recompute_all_scores()
            recompute_all_scores()  # second call

        scores_rows = full_tournament_db._tables.get("scores", [])
        # Each user_id should appear exactly once
        user_ids = [r["user_id"] for r in scores_rows]
        assert len(user_ids) == len(set(user_ids)), "Duplicate rows found in scores table"

        scores_by_user = {r["user_id"]: r["total_points"] for r in scores_rows}
        assert scores_by_user[1] == 100   # not doubled to 200
        assert scores_by_user[2] == 35


# ── Edge cases ─────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_user_with_no_picks_gets_no_points(self):
        """A user_id with zero picks never appears in scores."""
        scores = _award_group_points(make_db(use_standings_table=True), PICKS_MAP, SETTINGS)
        # PICKS_MAP only covers user ids 1-4; user 99 has no picks
        assert 99 not in scores

    def test_settings_custom_point_values(self):
        """Changing point values in settings correctly changes awarded totals."""
        custom_settings = {**SETTINGS, "pt_group_1st": 100, "pt_group_4th": 50}
        db = make_db(use_standings_table=True)

        scores = _award_group_points(db, PICKS_MAP, custom_settings)

        # Alice has both T1 (A, 1st → 100) and T8 (B, 3rd → unchanged 5)
        assert scores[1] == 100 + 5   # Alice
        # Dave has T4 (A, 4th → 50) and T7 (B, 4th → 50)
        assert scores[4] == 50 + 50   # Dave

    def test_group_and_knockout_points_are_independent(self):
        """
        Group points should be the same regardless of whether knockout
        matches exist, and vice versa.
        """
        db_group_only = make_db(use_standings_table=True)
        db_with_ko    = make_db(extra_matches=R32_MATCHES, use_standings_table=True)

        group_only = _award_group_points(db_group_only, PICKS_MAP, SETTINGS)
        group_with_ko = _award_group_points(db_with_ko, PICKS_MAP, SETTINGS)

        # Group scores must be identical
        assert group_only == group_with_ko
