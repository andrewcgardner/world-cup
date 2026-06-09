"""
Pydantic models mirroring the public schema tables plus request/response shapes.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DraftStatus(str, Enum):
    PRE_DRAFT = "PRE_DRAFT"
    REVEALING = "REVEALING"
    COMPLETE = "COMPLETE"


class MatchStage(str, Enum):
    GROUP = "GROUP"
    R32 = "R32"
    R16 = "R16"
    QF = "QF"
    SF = "SF"
    THIRD = "THIRD"
    FINAL = "FINAL"


class MatchStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    FINISHED = "FINISHED"


# ---------------------------------------------------------------------------
# DB row models (returned by Supabase selects)
# ---------------------------------------------------------------------------

class SystemSettings(BaseModel):
    id: int = 1
    draft_status: DraftStatus = DraftStatus.PRE_DRAFT
    pt_group_1st: int = 15
    pt_group_2nd: int = 10
    pt_group_3rd: int = 5
    pt_group_4th: int = 0
    pt_r32_win: int = 5
    pt_r16_win: int = 10
    pt_qf_win: int = 15
    pt_sf_win: int = 20
    pt_final_win: int = 30


class User(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    is_admin: bool = False
    is_bot: bool = False


class Team(BaseModel):
    id: int
    country_name: str
    pot_number: int          # 1-4
    fifa_rank: Optional[int] = None
    group_letter: Optional[str] = None  # A-L, set after group draw


class Pick(BaseModel):
    id: int
    user_id: int
    team_id: int
    reveal_sequence: int     # 1-48


class Match(BaseModel):
    id: int
    home_team_id: Optional[int] = None
    away_team_id: Optional[int] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    kickoff_time: Optional[datetime] = None
    stage: MatchStage
    status: MatchStatus = MatchStatus.SCHEDULED


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class PotUpdateRequest(BaseModel):
    team_id: int
    pot_number: int


class MatchUpsertPayload(BaseModel):
    external_id: str
    home_team_id: int
    away_team_id: int
    home_score: Optional[int]
    away_score: Optional[int]
    kickoff_time: Optional[datetime]
    stage: MatchStage
    status: MatchStatus


# ---------------------------------------------------------------------------
# Scoring / leaderboard
# ---------------------------------------------------------------------------

class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    user_name: str
    total_points: int
    teams: list[str] = []
