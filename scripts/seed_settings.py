"""
scripts/seed_settings.py
=========================
Ensures the singleton system_settings row (id=1) exists and applies
the default or custom point values.

You can call this standalone to reset point values without touching
other tables.

Run:
    python -m scripts.seed_settings
    python scripts/seed_settings.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import admin_client

# ---------------------------------------------------------------------------
# Default point configuration – edit to taste before the draft.
# ---------------------------------------------------------------------------

SETTINGS: dict = {
    "id":           1,
    "draft_status": "PRE_DRAFT",

    # Group stage placements (per group, per manager who owns that team)
    "pt_group_1st": 15,
    "pt_group_2nd": 10,
    "pt_group_3rd": 5,
    "pt_group_4th": 0,

    # Knockout round wins (awarded when a FINISHED knockout match is synced)
    "pt_r32_win":   5,
    "pt_r16_win":   10,
    "pt_qf_win":    15,
    "pt_sf_win":    20,
    "pt_final_win": 30,
}


def seed_settings() -> None:
    db = admin_client()
    result = db.table("system_settings").upsert(SETTINGS, on_conflict="id").execute()
    row = result.data[0]
    print("  ✓ system_settings upserted:")
    print(f"    draft_status : {row['draft_status']}")
    print(f"    Group pts    : 1st={row['pt_group_1st']}  2nd={row['pt_group_2nd']}  "
          f"3rd={row['pt_group_3rd']}  4th={row['pt_group_4th']}")
    print(f"    Knockout pts : R32={row['pt_r32_win']}  R16={row['pt_r16_win']}  "
          f"QF={row['pt_qf_win']}  SF={row['pt_sf_win']}  Final={row['pt_final_win']}")


if __name__ == "__main__":
    seed_settings()
