"""
Shared fixtures and MockDB for tournament scoring tests.

Scenario (8 teams, 4 users, 2 groups):
  Alice (user 1):  Argentina T1 (Group A), Hungary T8 (Group B)
  Bob   (user 2):  Brazil    T2 (Group A), England  T5 (Group B)
  Carol (user 3):  Chile     T3 (Group A), France   T6 (Group B)
  Dave  (user 4):  Denmark   T4 (Group A), Germany  T7 (Group B)

Group A final standing:  T1/Alice 1st (15), T3/Carol 2nd (10), T2/Bob 3rd (5), T4/Dave 4th (0)
Group B final standing:  T5/Bob   1st (15), T6/Carol 2nd (10), T8/Alice 3rd (5), T7/Dave 4th (0)

Group totals:  Alice 20, Bob 20, Carol 20, Dave 0

Knockout bracket (winners only):
  R32:  T1/Alice, T5/Bob, T3/Carol, T6/Carol         → Alice+5, Bob+5, Carol+10
  R16:  T1/Alice beats T6/Carol, T5/Bob beats T3/Carol → Alice+10, Bob+10
  QF:   T1/Alice beats T5/Bob                          → Alice+15
  SF:   T1/Alice beats unowned T99                     → Alice+20
  Final: T1/Alice beats unowned T100                   → Alice+30

Running totals:
  Alice: 20+5+10+15+20+30 = 100
  Bob:   20+5+10          = 35
  Carol: 20+10            = 30   (eliminated in R16)
  Dave:  0
"""

import pytest
from typing import Any


# ── MockDB ─────────────────────────────────────────────────────────────────

class MockResult:
    """Mimics the APIResponse returned by Supabase .execute()."""
    def __init__(self, data: Any):
        self.data = data
        self.count = len(data) if isinstance(data, list) else (1 if data else 0)


class MockQueryBuilder:
    """Chainable query builder that filters an in-memory list."""

    def __init__(self, data: list, table_name: str, db: "MockDB"):
        self._data = list(data)
        self._table_name = table_name
        self._db = db
        self._single = False
        self._orders: list[tuple[str, bool]] = []

    # ── Column selection (no-op — we return full rows) ──────────────────────
    def select(self, *args, **kwargs):
        return self

    # ── Filters ─────────────────────────────────────────────────────────────
    def eq(self, col: str, val: Any):
        self._data = [r for r in self._data if r.get(col) == val]
        return self

    def neq(self, col: str, val: Any):
        self._data = [r for r in self._data if r.get(col) != val]
        return self

    def in_(self, col: str, vals):
        vals_set = set(vals) if not isinstance(vals, set) else vals
        self._data = [r for r in self._data if r.get(col) in vals_set]
        return self

    # ── Ordering ─────────────────────────────────────────────────────────────
    def order(self, col: str, desc: bool = False, **kwargs):
        self._orders.append((col, desc))
        return self

    # ── Single-row helpers ───────────────────────────────────────────────────
    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._single = True
        return self

    # ── Writes ───────────────────────────────────────────────────────────────
    def upsert(self, rows: Any, on_conflict: str = "id", **kwargs):
        if isinstance(rows, dict):
            rows = [rows]
        conflict_keys = [k.strip() for k in on_conflict.split(",")]
        table = self._db._tables.setdefault(self._table_name, [])
        for row in rows:
            for i, existing in enumerate(table):
                if all(existing.get(k) == row.get(k) for k in conflict_keys):
                    table[i] = {**existing, **row}
                    break
            else:
                table.append(row)
        self._data = list(table)
        return self

    def insert(self, row: dict):
        self._db._tables.setdefault(self._table_name, []).append(row)
        return self

    def delete(self):
        # Mark for deletion on execute (keep a sentinel so .neq still works)
        self._db._tables[self._table_name] = [
            r for r in self._db._tables.get(self._table_name, [])
            if r not in self._data
        ]
        self._data = []
        return self

    # ── Execute ──────────────────────────────────────────────────────────────
    def execute(self) -> MockResult:
        result = list(self._data)

        # Apply ordering: most-recently-appended order = least significant key
        # (stable sort from least-significant → most-significant)
        for col, desc in reversed(self._orders):
            result.sort(
                key=lambda r, c=col: (r.get(c) is None, r.get(c) or ""),
                reverse=desc,
            )

        if self._single:
            return MockResult(result[0] if result else None)
        return MockResult(result)


class MockDB:
    """In-memory Supabase-like client."""

    def __init__(self, tables: dict[str, list[dict]] | None = None):
        self._tables: dict[str, list[dict]] = {
            k: list(v) for k, v in (tables or {}).items()
        }

    def table(self, name: str) -> MockQueryBuilder:
        return MockQueryBuilder(self._tables.get(name, []), name, self)

    def snapshot(self) -> dict[str, list[dict]]:
        """Deep-copy of current table state (useful for debugging)."""
        return {k: list(v) for k, v in self._tables.items()}

    def add_rows(self, table_name: str, rows: list[dict]):
        """Helper to append rows during a test."""
        self._tables.setdefault(table_name, []).extend(rows)


# ── Static test data ───────────────────────────────────────────────────────

SETTINGS = {
    "id": 1,
    "draft_status": "COMPLETE",
    "pt_group_1st": 15,
    "pt_group_2nd": 10,
    "pt_group_3rd": 5,
    "pt_group_4th": 0,
    "pt_r32_win":   5,
    "pt_r16_win":   10,
    "pt_qf_win":    15,
    "pt_sf_win":    20,
    "pt_final_win": 30,
}

USERS = [
    {"id": 1, "name": "Alice", "is_bot": False},
    {"id": 2, "name": "Bob",   "is_bot": False},
    {"id": 3, "name": "Carol", "is_bot": False},
    {"id": 4, "name": "Dave",  "is_bot": False},
]

# 8 teams across 2 groups (teams 99/100 are unowned placeholders for late KO rounds)
TEAMS = [
    {"id": 1,  "country_name": "Argentina", "group_letter": "A", "pot_number": 1},
    {"id": 2,  "country_name": "Brazil",    "group_letter": "A", "pot_number": 2},
    {"id": 3,  "country_name": "Chile",     "group_letter": "A", "pot_number": 3},
    {"id": 4,  "country_name": "Denmark",   "group_letter": "A", "pot_number": 4},
    {"id": 5,  "country_name": "England",   "group_letter": "B", "pot_number": 1},
    {"id": 6,  "country_name": "France",    "group_letter": "B", "pot_number": 2},
    {"id": 7,  "country_name": "Germany",   "group_letter": "B", "pot_number": 3},
    {"id": 8,  "country_name": "Hungary",   "group_letter": "B", "pot_number": 4},
    {"id": 99, "country_name": "Team99",    "group_letter": None, "pot_number": 1},
    {"id": 100,"country_name": "Team100",   "group_letter": None, "pot_number": 1},
]

# Alice: T1, T8 | Bob: T2, T5 | Carol: T3, T6 | Dave: T4, T7
PICKS = [
    {"id": 1, "user_id": 1, "team_id": 1, "reveal_sequence": 1},
    {"id": 2, "user_id": 2, "team_id": 2, "reveal_sequence": 2},
    {"id": 3, "user_id": 3, "team_id": 3, "reveal_sequence": 3},
    {"id": 4, "user_id": 4, "team_id": 4, "reveal_sequence": 4},
    {"id": 5, "user_id": 2, "team_id": 5, "reveal_sequence": 5},
    {"id": 6, "user_id": 3, "team_id": 6, "reveal_sequence": 6},
    {"id": 7, "user_id": 4, "team_id": 7, "reveal_sequence": 7},
    {"id": 8, "user_id": 1, "team_id": 8, "reveal_sequence": 8},
]

# picks dict shorthand: {team_id: user_id}
PICKS_MAP = {p["team_id"]: p["user_id"] for p in PICKS}

PLACE_PTS = [
    SETTINGS["pt_group_1st"],
    SETTINGS["pt_group_2nd"],
    SETTINGS["pt_group_3rd"],
    SETTINGS["pt_group_4th"],
]


# ── Match data ─────────────────────────────────────────────────────────────
#
# Group A matches (all FINISHED).
# Final standings: T1(1st) > T3(2nd) > T2(3rd) > T4(4th)
#
GROUP_A_MATCHES = [
    # id, home, away, hs, as_, stage, status
    {"id": 1,  "home_team_id": 1, "away_team_id": 2, "home_score": 3, "away_score": 0,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-12T15:00:00"},
    {"id": 2,  "home_team_id": 3, "away_team_id": 4, "home_score": 1, "away_score": 1,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-12T18:00:00"},
    {"id": 3,  "home_team_id": 1, "away_team_id": 3, "home_score": 2, "away_score": 1,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-16T15:00:00"},
    {"id": 4,  "home_team_id": 2, "away_team_id": 4, "home_score": 2, "away_score": 0,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-16T18:00:00"},
    {"id": 5,  "home_team_id": 1, "away_team_id": 4, "home_score": 1, "away_score": 0,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-20T18:00:00"},
    {"id": 6,  "home_team_id": 2, "away_team_id": 3, "home_score": 0, "away_score": 1,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-20T18:00:00"},
]
# T1: 3W, GF=6, GA=0, GD=+6, Pts=9  → 1st  (Alice  +15 pool pts)
# T3: 1W1D1L, GF=3, GA=3, GD=0, Pts=4 → 2nd (Carol  +10)
# T2: 1W0D2L, GF=2, GA=4, GD=-2, Pts=3→ 3rd (Bob    +5)
# T4: 0W1D2L, GF=1, GA=4, GD=-3, Pts=1→ 4th (Dave   +0)

# Group B matches (all FINISHED).
# Final standings: T5(1st) > T6(2nd) > T8(3rd) > T7(4th)
#
GROUP_B_MATCHES = [
    {"id": 7,  "home_team_id": 5, "away_team_id": 6, "home_score": 0, "away_score": 0,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-13T15:00:00"},
    {"id": 8,  "home_team_id": 7, "away_team_id": 8, "home_score": 1, "away_score": 2,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-13T18:00:00"},
    {"id": 9,  "home_team_id": 5, "away_team_id": 7, "home_score": 3, "away_score": 1,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-17T15:00:00"},
    {"id": 10, "home_team_id": 6, "away_team_id": 8, "home_score": 2, "away_score": 1,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-17T18:00:00"},
    {"id": 11, "home_team_id": 5, "away_team_id": 8, "home_score": 1, "away_score": 0,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-21T18:00:00"},
    {"id": 12, "home_team_id": 6, "away_team_id": 7, "home_score": 0, "away_score": 0,
     "stage": "GROUP", "status": "FINISHED", "kickoff_time": "2026-06-21T18:00:00"},
]
# T5: 2W1D0L, GF=4, GA=1, GD=+3, Pts=7  → 1st (Bob   +15)
# T6: 1W2D0L, GF=2, GA=1, GD=+1, Pts=5  → 2nd (Carol +10)
# T8: 1W0D2L, GF=3, GA=4, GD=-1, Pts=3  → 3rd (Alice +5)
# T7: 0W1D2L, GF=2, GA=5, GD=-3, Pts=1  → 4th (Dave  +0)

ALL_GROUP_MATCHES = GROUP_A_MATCHES + GROUP_B_MATCHES

# Group standings as they would come from the API sync worker
GROUP_STANDINGS = [
    # Group A
    {"group_letter": "A", "team_id": 1, "position": 1, "points": 9,  "goal_difference": 6,  "goals_for": 6, "goals_against": 0, "played": 3, "won": 3, "drawn": 0, "lost": 0},
    {"group_letter": "A", "team_id": 3, "position": 2, "points": 4,  "goal_difference": 0,  "goals_for": 3, "goals_against": 3, "played": 3, "won": 1, "drawn": 1, "lost": 1},
    {"group_letter": "A", "team_id": 2, "position": 3, "points": 3,  "goal_difference": -2, "goals_for": 2, "goals_against": 4, "played": 3, "won": 1, "drawn": 0, "lost": 2},
    {"group_letter": "A", "team_id": 4, "position": 4, "points": 1,  "goal_difference": -3, "goals_for": 1, "goals_against": 4, "played": 3, "won": 0, "drawn": 1, "lost": 2},
    # Group B
    {"group_letter": "B", "team_id": 5, "position": 1, "points": 7,  "goal_difference": 3,  "goals_for": 4, "goals_against": 1, "played": 3, "won": 2, "drawn": 1, "lost": 0},
    {"group_letter": "B", "team_id": 6, "position": 2, "points": 5,  "goal_difference": 1,  "goals_for": 2, "goals_against": 1, "played": 3, "won": 1, "drawn": 2, "lost": 0},
    {"group_letter": "B", "team_id": 8, "position": 3, "points": 3,  "goal_difference": -1, "goals_for": 3, "goals_against": 4, "played": 3, "won": 1, "drawn": 0, "lost": 2},
    {"group_letter": "B", "team_id": 7, "position": 4, "points": 1,  "goal_difference": -3, "goals_for": 2, "goals_against": 5, "played": 3, "won": 0, "drawn": 1, "lost": 2},
]

# Knockout matches
R32_MATCHES = [
    # T1/Alice beats T7/Dave
    {"id": 101, "home_team_id": 1,  "away_team_id": 7,  "home_score": 2, "away_score": 0, "stage": "R32", "status": "FINISHED", "kickoff_time": "2026-06-29T18:00:00"},
    # T5/Bob beats T4/Dave
    {"id": 102, "home_team_id": 5,  "away_team_id": 4,  "home_score": 1, "away_score": 0, "stage": "R32", "status": "FINISHED", "kickoff_time": "2026-06-29T21:00:00"},
    # T3/Carol beats T8/Alice — Alice loses a team here
    {"id": 103, "home_team_id": 3,  "away_team_id": 8,  "home_score": 2, "away_score": 1, "stage": "R32", "status": "FINISHED", "kickoff_time": "2026-06-30T18:00:00"},
    # T6/Carol beats T2/Bob — Bob loses a team here
    {"id": 104, "home_team_id": 6,  "away_team_id": 2,  "home_score": 3, "away_score": 0, "stage": "R32", "status": "FINISHED", "kickoff_time": "2026-06-30T21:00:00"},
]
# After R32: Alice +5(T1), Bob +5(T5), Carol +5(T3)+5(T6)=+10, Dave 0

R16_MATCHES = [
    # T1/Alice beats T6/Carol
    {"id": 201, "home_team_id": 1, "away_team_id": 6, "home_score": 1, "away_score": 0, "stage": "R16", "status": "FINISHED", "kickoff_time": "2026-07-04T18:00:00"},
    # T5/Bob beats T3/Carol
    {"id": 202, "home_team_id": 5, "away_team_id": 3, "home_score": 2, "away_score": 1, "stage": "R16", "status": "FINISHED", "kickoff_time": "2026-07-04T21:00:00"},
]
# After R16: Alice +10(T1), Bob +10(T5), Carol 0 (all out)

QF_MATCHES = [
    # T1/Alice beats T5/Bob
    {"id": 301, "home_team_id": 1, "away_team_id": 5, "home_score": 1, "away_score": 0, "stage": "QF", "status": "FINISHED", "kickoff_time": "2026-07-08T21:00:00"},
]
# After QF: Alice +15(T1), Bob 0

SF_MATCHES = [
    # T1/Alice beats T99 (unowned)
    {"id": 401, "home_team_id": 1, "away_team_id": 99, "home_score": 2, "away_score": 1, "stage": "SF", "status": "FINISHED", "kickoff_time": "2026-07-12T21:00:00"},
]
# After SF: Alice +20(T1)

FINAL_MATCHES = [
    # T1/Alice beats T100 (unowned)
    {"id": 501, "home_team_id": 1, "away_team_id": 100, "home_score": 1, "away_score": 0, "stage": "FINAL", "status": "FINISHED", "kickoff_time": "2026-07-19T21:00:00"},
]
# After Final: Alice +30(T1)


# ── Fixtures ───────────────────────────────────────────────────────────────

def make_db(extra_matches: list[dict] | None = None, use_standings_table: bool = False) -> MockDB:
    """
    Create a MockDB pre-loaded with the standard fixture.

    extra_matches:     additional knockout matches to add
    use_standings_table: populate group_standings (API path); otherwise
                         scoring falls back to computing from match rows
    """
    all_matches = list(ALL_GROUP_MATCHES) + (extra_matches or [])
    tables: dict[str, list] = {
        "system_settings": [SETTINGS],
        "users":           list(USERS),
        "teams":           list(TEAMS),
        "picks":           list(PICKS),
        "matches":         all_matches,
        "scores":          [],
    }
    if use_standings_table:
        tables["group_standings"] = list(GROUP_STANDINGS)
    else:
        tables["group_standings"] = []  # force fallback path

    return MockDB(tables)


@pytest.fixture
def db():
    """Standard MockDB with only group matches, standings from match computation."""
    return make_db()


@pytest.fixture
def db_with_standings():
    """MockDB using the pre-populated group_standings table (API sync path)."""
    return make_db(use_standings_table=True)


@pytest.fixture
def full_tournament_db():
    """MockDB with all matches through the Final."""
    ko = R32_MATCHES + R16_MATCHES + QF_MATCHES + SF_MATCHES + FINAL_MATCHES
    return make_db(extra_matches=ko)
