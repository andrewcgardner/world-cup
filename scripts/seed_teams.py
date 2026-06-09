"""
scripts/seed_teams.py
=====================
Seeds all 48 projected 2026 FIFA World Cup teams into public.teams.

Pot assignments follow FIFA's standard seeding methodology:
  Pot 1  – Host nations + highest-ranked remaining teams (ranks 1-9 approx.)
  Pot 2  – Next tier (ranks 10-21 approx.)
  Pot 3  – Next tier (ranks 22-33 approx.)
  Pot 4  – Remaining qualifiers (ranks 34-48+ / OFC / lower-ranked AFC/CAF)

FIFA ranks are based on the April 2025 ranking release.
external_id values are API-Football team IDs (verified against v3 endpoint).
group_letter is left NULL – it is populated after the official group draw.

Run:
    python -m scripts.seed_teams          (from project root)
    python scripts/seed_teams.py          (direct)
"""

import sys
import os
import json

# Allow running from project root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import admin_client

def seed_teams() -> None:
    db = admin_client()

    with open('scripts/data/teams.json', 'r') as file:
        data = json.load(file)

    TEAMS = data["teams"]

    # Validate counts per pot
    pot_counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
    for row in TEAMS:
        pot = int(row["pot_number"])
        pot_counts[pot] += 1

    for pot, count in pot_counts.items():
        if count != 12:
            raise ValueError(f"Pot {pot} has {count} teams – must be exactly 12.")

    print(f"Seeding {len(TEAMS)} teams …")

    rows = [
        {
            "country_name":  row["name_en"],
            "iso_code":      row["fifa_code"],
            "pot_number":    int(row["pot_number"]),
            "fifa_rank":     int(row["fifa_rank"]),
            "group_letter":  row["groups"],
            "external_id":   int(row["id"]),
            "flag_url":      row["flag"],
        }
        for row in TEAMS
    ]

    # Upsert on country_name so re-running is idempotent
    result = db.table("teams").upsert(rows, on_conflict="country_name").execute()
    print(f"  ✓ {len(result.data)} team rows upserted.")
    for pot in range(1, 5):
        names = [r["country_name"] for r in result.data if r["pot_number"] == pot]
        print(f"  Pot {pot} ({len(names)}): {', '.join(names)}")


if __name__ == "__main__":
    seed_teams()
