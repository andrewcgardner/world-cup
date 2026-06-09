"""
scripts/seed_users.py
======================
Seeds the 12 manager slots into public.users.

Edit the MANAGERS list below to match your actual pool participants.
Any slot left as None will be auto-filled with a "House Bot" placeholder.
The draw engine later replaces remaining None slots with permanent House Bot
rows, but seeding them here gives them stable IDs from the start.

Run:
    python -m scripts.seed_users
    python scripts/seed_users.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import admin_client

# ---------------------------------------------------------------------------
# Edit this list with your real pool participants (up to 12 entries).
# Format: (name, email, is_admin)
# Leave trailing slots as None to auto-generate House Bot placeholders.
# ---------------------------------------------------------------------------

MANAGERS: list[tuple[str, str | None, bool] | None] = [
    ("Your Name",   "you@example.com", True),             # slot 1 – admin
    ("Player 2",    "player2@example.com", False),        # slot 2
    ("Player 3",    "player3@example.com", False),        # slot 3
    ("Player 4",    "player4@example.com", False),        # slot 4
    ("Player 5",    "player5@example.com", False),        # slot 5
    ("Player 6",    "player6@example.com", False),        # slot 6
    ("Player 7",    "player7@example.com", False),        # slot 7
    ("Player 8",    "player8@example.com", False),        # slot 8
    ("Player 9",    "player9@example.com", False),        # slot 9
    ("Player 10",   "player10@example.com", False),       # slot 10
    ("Player 11",   "player11@example.com", False),       # slot 11
    None,                                                  # slot 12 → House Bot
]

TOTAL_SLOTS = 12


def seed_users() -> None:
    if len(MANAGERS) != TOTAL_SLOTS:
        raise ValueError(f"MANAGERS list must have exactly {TOTAL_SLOTS} entries (got {len(MANAGERS)}).")

    db = admin_client()

    # Wipe existing users so IDs are predictable (safe pre-draft only)
    existing = db.table("users").select("id").execute()
    if existing.data:
        print(f"  ⚠  Deleting {len(existing.data)} existing user rows before re-seed …")
        db.table("users").delete().neq("id", 0).execute()

    rows = []
    bot_counter = 0

    for slot_index, entry in enumerate(MANAGERS, start=1):
        if entry is None:
            bot_counter += 1
            rows.append({
                "name":     f"House Bot {bot_counter}",
                "email":    None,
                "is_admin": False,
                "is_bot":   True,
            })
        else:
            name, email, is_admin = entry
            rows.append({
                "name":     name,
                "email":    email,
                "is_admin": is_admin,
                "is_bot":   False,
            })

    result = db.table("users").insert(rows).execute()
    print(f"  ✓ {len(result.data)} user rows inserted.")
    for row in result.data:
        tag = "[admin]" if row["is_admin"] else ("[bot]" if row["is_bot"] else "")
        print(f"    id={row['id']:>3}  {row['name']:<30} {tag}")


if __name__ == "__main__":
    seed_users()
