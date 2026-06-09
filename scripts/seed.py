"""
scripts/seed.py
================
Master seed orchestrator. Runs all seed scripts in dependency order:

  1. seed_settings  – system_settings singleton row
  2. seed_teams     – 48 national teams
  3. seed_users     – 12 manager slots

Safe to re-run at any time during PRE_DRAFT phase.
Will warn and abort if draft_status is no longer PRE_DRAFT (to avoid
overwriting live data).

Run:
    python -m scripts.seed            (from project root)
    python scripts/seed.py            (direct)
    python scripts/seed.py --force    (skip draft-status guard)
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import admin_client

# Import individual seeders
from scripts.seed_settings import seed_settings
from scripts.seed_teams    import seed_teams
from scripts.seed_users    import seed_users


def _check_draft_status(force: bool) -> None:
    res = admin_client().table("system_settings").select("draft_status").eq("id", 1).maybe_single().execute()
    if res and res.data:
        status = res.data.get("draft_status", "PRE_DRAFT")
        if status != "PRE_DRAFT" and not force:
            print(f"\n⛔  Draft status is '{status}'. Seeding is only safe during PRE_DRAFT.")
            print("    Use --force to override (this will NOT reset picks or matches).")
            sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the World Cup 2026 pool database.")
    parser.add_argument("--force", action="store_true",
                        help="Skip the PRE_DRAFT status guard.")
    parser.add_argument("--skip-users",   action="store_true", help="Skip seeding users.")
    parser.add_argument("--skip-teams",   action="store_true", help="Skip seeding teams.")
    parser.add_argument("--skip-settings",action="store_true", help="Skip seeding system_settings.")
    args = parser.parse_args()

    print("=" * 60)
    print("  World Cup 2026 Pool – Database Seed")
    print("=" * 60)

    _check_draft_status(args.force)

    if not args.skip_settings:
        print("\n[1/3] Seeding system_settings …")
        seed_settings()

    if not args.skip_teams:
        print("\n[2/3] Seeding teams …")
        seed_teams()

    if not args.skip_users:
        print("\n[3/3] Seeding users …")
        seed_users()

    print("\n✅  Seed complete.\n")


if __name__ == "__main__":
    main()
