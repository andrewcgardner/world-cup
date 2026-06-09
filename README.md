# World Cup 2026 Pool

A self-hosted fantasy football pool app for the 2026 FIFA World Cup. Each participant is randomly assigned teams; points accumulate as those teams progress through the tournament. Built with FastAPI, Supabase, and HTMX.

## Features

- **Random team draw** — participants are assigned teams via a live reveal ceremony
- **Live scoring** — syncs match results from the [worldcup26.ir](https://worldcup26.ir) API
- **Standings & bracket views** — real-time leaderboard and knockout bracket
- **Admin panel** — manage matches, trigger score recalculation, run the sync worker
- **Cron worker** — background endpoint for automated score sync (e.g. via GitHub Actions or cron-job.org)

## Tech Stack

- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- [Supabase](https://supabase.com/) (PostgreSQL + Auth)
- [Jinja2](https://jinja.palletsprojects.com/) templates + [HTMX](https://htmx.org/)
- [uv](https://docs.astral.sh/uv/) for dependency management

## Setup

### 1. Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (`pip install uv` or `brew install uv`)
- A [Supabase](https://supabase.com/) project

### 2. Clone & install dependencies

```bash
git clone https://github.com/your-username/world-cup.git
cd world-cup
uv sync
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your Supabase credentials and other secrets
```

See `.env.example` for all required variables and their descriptions.

### 4. Initialize the database

```bash
# Run the SQL schema against your Supabase project
# (paste contents of scripts/init_db.sql into the Supabase SQL editor)

# Then seed reference data
uv run python -m scripts.seed_teams
uv run python -m scripts.seed_matches
uv run python -m scripts.seed_settings
```

### 5. Seed participants

Edit `scripts/seed_users.py` and fill in the `MANAGERS` list with your pool participants' names and emails, then run:

```bash
uv run python -m scripts.seed_users
```

### 6. Run locally

```bash
uv run uvicorn main:app --reload
```

Visit `http://localhost:8000`.

## Admin

The admin panel is at `/admin`. Authenticate with your `ADMIN_TOKEN` from `.env`.

To manually trigger a score sync:
```
POST /worker/sync  (Authorization: Bearer <CRON_TOKEN>)
```

## Running Tests

```bash
uv run pytest
```

## Deployment

The app is stateless (all data in Supabase) so it deploys easily to any Python host (Railway, Render, Fly.io, etc.). Set all `.env` variables as environment variables in your hosting platform.

For automated score sync, point a cron job or GitHub Actions workflow at your `/worker/sync` endpoint with the `CRON_TOKEN` in the `Authorization` header.

## License

MIT
