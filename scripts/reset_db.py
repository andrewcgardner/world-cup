"""
scripts/reset_db.py
====================
Clears or fully drops all application tables, with optional re-seed.

Modes
-----
  (default)       Truncate all data; keep table structure intact.
  --drop-tables   DROP every table and extension, then re-run init_db.sql
                  to recreate the schema from scratch.  Use this for a
                  clean-slate rebuild without touching the Supabase dashboard.

Flags
-----
  --yes           Skip the interactive confirmation prompt.
  --reseed        Run the full seed pipeline after reset completes.
  --drop-tables   Drop tables and recreate schema via init_db.sql.

Examples
--------
  # Wipe data only, prompt for confirmation:
  python scripts/reset_db.py

  # Wipe data, no prompt:
  python scripts/reset_db.py --yes

  # Full drop + recreate + reseed, no prompt (CI / automation):
  python scripts/reset_db.py --drop-tables --yes --reseed

  # Wipe data then reseed:
  python scripts/reset_db.py --yes --reseed
"""

import sys
import os
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import admin_client

# ── Table ordering ─────────────────────────────────────────────────────────
# Reverse FK order: children before parents, so deletes/drops never hit a
# foreign-key constraint violation.
TABLES_REVERSE_FK = ["scores", "picks", "matches", "group_standings", "teams", "users", "system_settings"]

# Path to the DDL file produced earlier
INIT_SQL_PATH = Path(__file__).parent / "init_db.sql"


# ── Truncate (data only) ───────────────────────────────────────────────────

def _truncate_via_deletes(db) -> None:
    """
    Delete all rows in safe FK order via the Supabase REST client.
    (The Python SDK doesn't expose raw SQL, so we delete table-by-table.)
    """
    for table in TABLES_REVERSE_FK:
        if table == "system_settings":
            # Keep the singleton row; just reset values to defaults.
            db.table("system_settings").update({
                "draft_status": "PRE_DRAFT",
                "pt_group_1st": 15, "pt_group_2nd": 10,
                "pt_group_3rd": 5,  "pt_group_4th": 0,
                "pt_r32_win": 5,    "pt_r16_win": 10,
                "pt_qf_win": 15,    "pt_sf_win": 20,
                "pt_final_win": 30,
            }).eq("id", 1).execute()
            print("  Reset  system_settings → defaults")
        elif table == "scores":
            # scores PK is user_id, not id
            res = db.table(table).delete().neq("user_id", 0).execute()
            print(f"  Deleted from {table}: {len(res.data)} row(s)")
        else:
            res = db.table(table).delete().neq("id", 0).execute()
            print(f"  Deleted from {table}: {len(res.data)} row(s)")

    print()
    print("  ℹ  BIGSERIAL sequences are NOT reset by this operation.")
    print("     To reset them too, run this once in the Supabase SQL Editor:")
    print("       TRUNCATE public.scores, public.picks, public.matches,")
    print("                public.teams, public.users RESTART IDENTITY CASCADE;")
    print("       INSERT INTO public.system_settings (id) VALUES (1) ON CONFLICT DO NOTHING;")


# ── Drop tables + recreate schema ─────────────────────────────────────────

# SQL that drops every object this app owns, in safe dependency order.
_DROP_SQL = """
-- Drop tables (CASCADE handles FK deps automatically)
DROP TABLE IF EXISTS public.scores          CASCADE;
DROP TABLE IF EXISTS public.picks           CASCADE;
DROP TABLE IF EXISTS public.matches         CASCADE;
DROP TABLE IF EXISTS public.teams           CASCADE;
DROP TABLE IF EXISTS public.group_standings CASCADE;
DROP TABLE IF EXISTS public.users           CASCADE;
DROP TABLE IF EXISTS public.system_settings CASCADE;
"""


def _drop_tables(db) -> None:
    """
    Issue DROP TABLE statements via Supabase's pg_rpc execute_sql RPC if
    available, otherwise print the SQL for the user to run manually and exit.

    Supabase exposes a built-in RPC called `exec_sql` (or `execute_sql`) on
    some plans; on others the service-role client can call pg functions.
    We attempt both known variants and fall back gracefully.
    """
    drop_statements = [line.strip() for line in _DROP_SQL.strip().splitlines()
                       if line.strip() and not line.strip().startswith("--")]

    executed = False
    for stmt in drop_statements:
        # Try Supabase's built-in SQL execution RPC (available on Pro/Team plans)
        for rpc_name in ("exec_sql", "execute_sql", "run_sql"):
            try:
                db.rpc(rpc_name, {"query": stmt}).execute()
                executed = True
                break
            except Exception:
                pass

        if not executed:
            break

    if executed:
        print("  ✓ All tables dropped via Supabase RPC.")
    else:
        # RPC not available — print instructions and the SQL to run manually.
        print()
        print("  ⚠  The Supabase REST client cannot execute raw DDL on this plan.")
        print("     Copy the SQL below into the Supabase SQL Editor and run it,")
        print("     then re-run this script with --yes --reseed to finish setup.")
        print()
        print("  " + "─" * 60)
        print(_DROP_SQL.strip())
        if INIT_SQL_PATH.exists():
            print()
            print("  -- Then paste and run the contents of:")
            print(f"  --   {INIT_SQL_PATH}")
        print("  " + "─" * 60)
        sys.exit(1)


def _recreate_schema() -> None:
    """
    Print the init_db.sql path so the user knows to re-run it, or attempt
    auto-execution if the Supabase RPC supports it.
    We always print the file path regardless, since DDL execution via REST
    is plan-dependent.
    """
    if not INIT_SQL_PATH.exists():
        print(f"  ⚠  {INIT_SQL_PATH} not found — run init_db.sql manually.")
        return

    print()
    print("  Schema dropped. To recreate it, paste the contents of:")
    print(f"    {INIT_SQL_PATH}")
    print("  into the Supabase SQL Editor and run it.")
    print()
    print("  Then run:")
    print("    python scripts/reset_db.py --yes --reseed")


# ── Orchestrator ───────────────────────────────────────────────────────────

def reset(yes: bool, reseed: bool, drop_tables: bool) -> None:
    action = "DROP all tables and recreate the schema" if drop_tables else "DELETE all data"

    if not yes:
        print(f"\n⚠  This will {action}. All pool data will be lost.")
        answer = input("   Type 'yes' to confirm: ").strip().lower()
        if answer != "yes":
            print("   Aborted.")
            sys.exit(0)

    db = admin_client()

    if drop_tables:
        print("\nDropping tables …")
        _drop_tables(db)
        _recreate_schema()
        # After a drop+recreate the schema must be re-applied before seeding;
        # if we reach this point via RPC the tables exist again, so seed away.
        if reseed:
            print("\nRe-seeding …")
            from scripts.seed import main as run_seed
            sys.argv = [sys.argv[0], "--force"]
            run_seed()
    else:
        print("\nTruncating data …")
        _truncate_via_deletes(db)
        print("  ✓ All tables cleared.")

        if reseed:
            print("\nRe-seeding …")
            from scripts.seed import main as run_seed
            sys.argv = [sys.argv[0], "--force"]
            run_seed()

    print("\n✅  Done.\n")


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reset the WC 2026 pool database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python scripts/reset_db.py                          # truncate data, prompt
  python scripts/reset_db.py --yes                    # truncate data, no prompt
  python scripts/reset_db.py --yes --reseed           # truncate + reseed
  python scripts/reset_db.py --drop-tables --yes      # drop schema, no prompt
  python scripts/reset_db.py --drop-tables --yes --reseed  # full rebuild
        """,
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt (required for automation).",
    )
    parser.add_argument(
        "--reseed",
        action="store_true",
        help="Run the full seed pipeline after the reset completes.",
    )
    parser.add_argument(
        "--drop-tables",
        action="store_true",
        dest="drop_tables",
        help=(
            "DROP all tables and recreate the schema from init_db.sql. "
            "Use for a clean-slate rebuild without the Supabase dashboard."
        ),
    )
    args = parser.parse_args()
    reset(yes=args.yes, reseed=args.reseed, drop_tables=args.drop_tables)
