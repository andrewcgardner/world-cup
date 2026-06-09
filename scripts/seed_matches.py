"""
scripts/seed_matches.py
========================
Loads match fixtures from games.json into public.matches.

Source field → DB column mapping
─────────────────────────────────────────────────────────────
id                  → external_id          (INT, 1-104)
home_team_id        → home_team_id         ("0" or 0 → NULL)
away_team_id        → away_team_id         ("0" or 0 → NULL)
home_team_name_en   → home_team_label      (group-stage fallback name)
away_team_name_en   → away_team_label      (group-stage fallback name)
home_team_label     → home_team_label      (explicit TBD label, e.g. "Runner-up Group A")
away_team_label     → away_team_label
home_score          → home_score           (NULL when status == SCHEDULED)
away_score          → away_score           (NULL when status == SCHEDULED)
local_date          → kickoff_time         ("MM/DD/YYYY HH:MM" parsed → UTC ISO-8601)
matchday            → matchday
group               → group_letter         (only for type=="group"; NULL for knockouts)
type                → stage               ("group"→GROUP, "r32"→R32, …)
finished + time_elapsed → status          (derived — see _status() below)

Run:
    python scripts/seed_matches.py
    python scripts/seed_matches.py --file path/to/games.json
    python scripts/seed_matches.py --dry-run
"""

import sys, os, argparse, json, logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import admin_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Stage mapping ──────────────────────────────────────────────────────────
TYPE_TO_STAGE = {
    "group":  "GROUP",
    "r32":    "R32",
    "r16":    "R16",
    "qf":     "QF",
    "sf":     "SF",
    "third":  "THIRD",
    "final":  "FINAL",
}


# ── Field converters ───────────────────────────────────────────────────────

def _int_or_none(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _team_id(val) -> int | None:
    """String or int "0" / 0 → NULL (TBD). Any positive int → that id."""
    v = _int_or_none(val)
    return v if v and v > 0 else None


def _status(raw: dict) -> str:
    """
    Derive status from finished + time_elapsed fields.
      finished == "TRUE"                         → FINISHED
      finished == "FALSE", time_elapsed != "notstarted" → LIVE
      finished == "FALSE", time_elapsed == "notstarted" → SCHEDULED
    """
    if str(raw.get("finished", "FALSE")).upper() == "TRUE":
        return "FINISHED"
    if str(raw.get("time_elapsed", "notstarted")).lower() != "notstarted":
        return "LIVE"
    return "SCHEDULED"


def _kickoff(raw: dict) -> str | None:
    """
    Parse local_date ("MM/DD/YYYY HH:MM") to UTC ISO-8601.
    Stored without timezone info in the source, so we treat it as UTC.
    """
    raw_str = raw.get("local_date") or ""
    raw_str = str(raw_str).strip()
    if not raw_str:
        return None
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw_str, fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    log.warning("  Could not parse local_date %r — storing NULL", raw_str)
    return None


def _build_row(raw: dict) -> dict | None:
    # ── Stage ──────────────────────────────────────────────────────────────
    type_str = str(raw.get("type", "")).strip().lower()
    stage = TYPE_TO_STAGE.get(type_str)
    if not stage:
        log.warning("Skipping id=%s — unknown type %r", raw.get("id"), raw.get("type"))
        return None

    # ── Team IDs ───────────────────────────────────────────────────────────
    home_id = _team_id(raw.get("home_team_id"))
    away_id = _team_id(raw.get("away_team_id"))

    if home_id is not None and away_id is not None and home_id == away_id:
        log.warning(
            "Skipping id=%s — home_team_id == away_team_id == %s",
            raw.get("id"), home_id,
        )
        return None

    # ── Status ─────────────────────────────────────────────────────────────
    status = _status(raw)

    # ── Scores: NULL for unplayed fixtures ─────────────────────────────────
    if status == "SCHEDULED":
        home_score = away_score = None
    else:
        home_score = _int_or_none(raw.get("home_score"))
        away_score = _int_or_none(raw.get("away_score"))

    # ── Group letter: only meaningful for group-stage rows ─────────────────
    group_letter = raw.get("group") if stage == "GROUP" else None

    # ── Team labels ────────────────────────────────────────────────────────
    # For TBD knockout fixtures, home_team_label / away_team_label are explicit.
    # For group fixtures, fall back to home_team_name_en / away_team_name_en.
    home_label = (
        raw.get("home_team_label")
        or raw.get("home_team_name_en")
        or None
    )
    away_label = (
        raw.get("away_team_label")
        or raw.get("away_team_name_en")
        or None
    )

    return {
        "external_id":     int(raw["id"]),
        "home_team_id":    home_id,
        "away_team_id":    away_id,
        "home_team_label": home_label,
        "away_team_label": away_label,
        "home_score":      home_score,
        "away_score":      away_score,
        "kickoff_time":    _kickoff(raw),
        "matchday":        _int_or_none(raw.get("matchday")),
        "group_letter":    group_letter,
        "stage":           stage,
        "status":          status,
    }


# ── Main ───────────────────────────────────────────────────────────────────

def seed_matches(file: Path, dry_run: bool = False, batch_size: int = 50) -> None:
    log.info("Reading %s …", file)
    data = json.loads(file.read_text(encoding="utf-8"))

    # Unwrap common envelope shapes
    if isinstance(data, dict):
        for key in ("matches", "fixtures", "games", "data", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                log.info("Unwrapped JSON key %r", key)
                break

    if not isinstance(data, list):
        log.error("Expected a JSON array, got %s", type(data).__name__)
        sys.exit(1)

    log.info("Loaded %d raw records.", len(data))

    rows, skipped, tbd = [], 0, 0
    for item in data:
        row = _build_row(item)
        if row is None:
            skipped += 1
            continue
        if row["home_team_id"] is None or row["away_team_id"] is None:
            tbd += 1
        rows.append(row)

    log.info(
        "Mapped %d rows  (%d TBD participants  |  %d skipped).",
        len(rows), tbd, skipped,
    )

    if dry_run:
        log.info("DRY RUN — first 3 rows:")
        for r in rows[:3]:
            print(json.dumps(r, indent=2, default=str))
        return

    if not rows:
        log.warning("Nothing to insert.")
        return

    db = admin_client()

    # Translate external API team IDs → internal DB IDs.
    # home_team_id / away_team_id in games.json are external API IDs;
    # matches.home_team_id / away_team_id are FKs to teams.id.
    teams_res = db.table("teams").select("id, external_id").execute()
    ext_to_int = {
        t["external_id"]: t["id"]
        for t in (teams_res.data or [])
        if t.get("external_id") is not None
    }
    if not ext_to_int:
        log.warning("No teams with external_id found — team ID translation will be skipped. "
                    "Ensure teams are seeded before matches.")

    untranslated = 0
    for row in rows:
        h_ext = row["home_team_id"]
        a_ext = row["away_team_id"]
        row["home_team_id"] = ext_to_int.get(h_ext) if h_ext is not None else None
        row["away_team_id"] = ext_to_int.get(a_ext) if a_ext is not None else None
        if (h_ext is not None and row["home_team_id"] is None) or \
           (a_ext is not None and row["away_team_id"] is None):
            untranslated += 1

    if untranslated:
        log.warning("  %d rows had team IDs that could not be translated — "
                    "check teams.external_id is populated.", untranslated)

    upserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        db.table("matches").upsert(batch, on_conflict="external_id").execute()
        upserted += len(batch)
        log.info("  … upserted %d / %d", upserted, len(rows))

    log.info("✅  %d match rows written to public.matches.", upserted)
    if tbd:
        log.info(
            "   %d fixtures have TBD participants — team IDs will be filled "
            "by the sync worker once participants are decided.", tbd,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed public.matches from games.json.")
    parser.add_argument(
        "--file", "-f",
        type=Path,
        default=Path(__file__).parent.parent / "games.json",
        help="Path to source JSON (default: games.json in project root).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and validate without writing to the database.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="Rows per upsert request (default: 50).",
    )
    args = parser.parse_args()

    if not args.file.exists():
        log.error("File not found: %s", args.file)
        sys.exit(1)

    seed_matches(file=args.file, dry_run=args.dry_run, batch_size=args.batch_size)
