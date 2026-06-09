"""
scripts/seed_groups.py
=====================
Seeds all 12 projected 2026 FIFA World Cup groups into public.group_standings in their initial state.
Translates incoming external API team IDs into internal database team IDs to maintain foreign key integrity.

Run:
    python -m scripts.seed_groups          (from project root)
    python scripts/seed_groups.py          (direct)
"""

import sys
import os
import json

# Allow running from project root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import admin_client

def seed_groups() -> None:
    db = admin_client()

    # ── 1. FETCH TEAM TRANSLATION MAP ───────────────────────────────────────
    # Look up all teams from the database to map external_id -> internal id
    print("Fetching team records from database to map internal IDs...")
    teams_res = db.table("teams").select("id, external_id").execute()
    teams_data = teams_res.data or []
    
    # Build lookup table: { external_id: internal_db_id }
    ext_to_int_map = {
        t["external_id"]: t["id"] 
        for t in teams_data 
        if t.get("external_id") is not None
    }
    
    # Fallback map using internal IDs directly just in case some entries in 
    # your JSON are already using internal IDs.
    internal_ids = {t["id"] for t in teams_data}

    # ── 2. LOAD EXTERNAL TOURNAMENT DATA ────────────────────────────────────
    with open('scripts/data/groups.json', 'r') as file:
        data = json.load(file)

    GROUPS = data["groups"]

    print(f"Processing and seeding {len(GROUPS)} groups …")

    rows = []
    missing_teams = set()

    for group in GROUPS:
        group_letter = group["name"]
        for team in group["teams"]:
            # Force cast the JSON value to an integer to match the database types
            try:
                raw_id = int(team["team_id"])
            except (ValueError, TypeError):
                raw_id = team["team_id"] # Fallback if it's an unparseable string
            
            # Translate external API id to internal DB id
            internal_team_id = ext_to_int_map.get(raw_id)
            
            # Fallback check: if it's not in the map, check if it's already a valid internal ID
            if internal_team_id is None and raw_id in internal_ids:
                internal_team_id = raw_id

            if internal_team_id is None:
                missing_teams.add(raw_id)
                continue

            rows.append(
                {
                    "group_letter":    group_letter,
                    "team_id":         internal_team_id, # Safely populated internal ID
                    "position":        1, # assuming all teams are tied at initial load
                    "played":          team["mp"],
                    "won":             team["w"],
                    "drawn":           team["d"],
                    "lost":            team["l"],
                    "goals_for":       team["gf"],
                    "goals_against":   team["ga"],
                    "goal_difference": team["gd"],
                    "points":          0 # assuming no teams have points at initial load
                }
            )

    # Warn if there are missing teams before continuing to avoid silent data drops
    if missing_teams:
        print(f"⚠️  WARNING: {len(missing_teams)} team IDs from groups.json could not be mapped to your teams table: {list(missing_teams)}")
        print("Please ensure your 'teams' table is fully seeded with 'external_id' values populated before running this script.")
        if not rows:
            print("❌ Execution halted: No valid group rows could be built.")
            return

    # ── 3. IDEMPOTENT UPSERT ────────────────────────────────────────────────
    # Upsert on group_letter,team_id so re-running is clean and safe
    result = db.table("group_standings").upsert(rows, on_conflict="group_letter,team_id").execute()
    print(f"  ✓ {len(result.data)} groups rows upserted successfully.")
    
if __name__ == "__main__":
    seed_groups()