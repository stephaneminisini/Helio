# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Helio Monitor — a self-hosted solar analytics dashboard that pulls production data
from the Enphase API v4, combines it with irradiance data (NREL or NASA POWER),
and derives historical comparisons, Performance Ratio trends, and degradation
alerts. Product/technical background lives in `docs/brd.md`, `docs/trd.md`, and
`docs/dev-plan.md`.

## Commands

Everything runs in Docker Compose. `make help` lists all targets.

```bash
make init          # first run: create .env from .env.example + generate FERNET_KEY
make up            # build + start db/api/frontend (dashboard :3000, API docs :8000/docs)
make migrate       # alembic upgrade head (inside the api container)
make logs-api      # tail API logs
make psql          # psql shell (reads POSTGRES_USER/POSTGRES_DB from the shell env)
```

### Tests and lint

`make test`, `make lint`, etc. all `docker compose exec` into a **running** `api`
container. To run them without Docker:

```bash
cd backend
uv sync --extra dev --group dev
uv run pytest tests/unit/ -v --tb=short          # unit tests (what CI runs)
uv run pytest tests/unit/test_poller.py::test_detect_gaps_returns_missing_dates -v
uv run ruff format helio/ tests/ && uv run ruff check helio/ tests/
```

Frontend: `cd frontend && npm ci && ./node_modules/.bin/tsc --noEmit && npm run build`.
There is no frontend test suite; CI only type-checks and builds.

`pytest` is configured with `asyncio_mode = "auto"` — async tests need no
`@pytest.mark.asyncio` (existing tests still carry it). There is no `conftest.py`;
tests mock `AsyncSession` directly with `AsyncMock`/`MagicMock` and mock HTTP with
`respx`. Integration tests drive FastAPI in-process via `ASGITransport` and
override the `get_db` dependency — no database is required for any test.

### Stale Makefile targets

These targets reference modules that do not exist. Use the real entry point or
fix the target rather than assuming it works:

| Target | Points at | Reality |
|---|---|---|
| `make poll-now` / `make poll-status` | `helio.ingestion.poller` CLI | `poller.py` has no CLI/`__main__` |
| `make rebuild-summaries` | `helio.analytics.summarizer --rebuild-all` | no CLI |
| `make seed-mock` | `helio.db.seed_mock` | module does not exist (mock mode is documented in `docs/CONTRIBUTING.md` but unimplemented) |

`docs/CONTRIBUTING.md` also claims Black/isort/Prettier; the project actually uses
**ruff** (format + lint, line length 88, rules `E,F,I,UP`, target py313) and has no
Prettier setup.

## Architecture

### Data flow

```
Enphase API v4 ─┐
                ├─> poller.poll_intervals ──> energy_intervals (15-min raw)
NREL/NASA ──────┴─> poller.poll_irradiance ─> irradiance (daily GHI/DNI/POA)
                                                  │
                    summarizer.build_daily_summary ┴─> daily_summaries
                    summarizer.build_monthly_summary ──> monthly_summaries (PR, expected_pr, anomaly)
                                                  │
                    analytics.degradation ────────┴─> /api/efficiency
                    routes.overview ─────────────────> /api/overview
```

Raw intervals are never queried by the API. Every endpoint reads from the summary
tables, so **any change to ingestion or aggregation semantics requires rebuilding
summaries**, not just re-polling.

### Backend layers (`backend/helio/`)

- `core/` — `config.py` is the single `Settings` singleton (pydantic-settings, reads
  `.env`); `crypto.py` wraps Fernet encrypt/decrypt for tokens.
- `db/` — `models.py` (SQLAlchemy 2 `DeclarativeBase`, `Mapped[...]` annotations,
  `Decimal`/`Numeric` for all energy values) and `session.py` (async engine,
  `AsyncSessionLocal`, `get_db` FastAPI dependency).
- `ingestion/` — `enphase_client.py` (OAuth refresh + exponential backoff on
  429/503), `irradiance_client.py` (`IrradianceClient` ABC with `NRELClient` and
  `NASAClient` impls, plus `compute_poa` using pvlib Hay-Davies transposition),
  `poller.py` (upsert + `poll_log` audit rows), `scheduler.py` (APScheduler cron),
  `backfill.py` (day-by-day catch-up from the install date; `backend/scripts/backfill.py`
  and `make backfill` are both thin wrappers over it).
- `analytics/` — `summarizer.py` (daily/monthly rollups, PR and anomaly flagging),
  `degradation.py` (year-over-year PR drop, lost production estimate).
- `api/` — `main.py` (app, CORS, lifespan that starts the scheduler),
  `routes/` (overview, efficiency, settings, status), `schemas/` (Pydantic response
  models). `POST /api/settings` is the only code path that creates a `System` row;
  `GET /api/status` reports ingestion coverage and the last `poll_log` row so the UI
  can tell "no data yet" from "credentials broken"; `POST /api/backfill` runs
  `ingestion.backfill` as a FastAPI background task.

### Conventions that matter

- **Single-system assumption.** Every route and job does
  `select(System).limit(1)` — the schema supports multiple systems but nothing
  uses more than one. Preserve or deliberately change this, don't half-migrate it.
- **The scheduler runs inside the API process** (`lifespan` in `api/main.py`), not
  as a separate service. Multiple API replicas would double-poll. `ingestion.backfill`
  tracks progress in a module-level `BackfillProgress` singleton for the same reason —
  it is per-process state, and a second replica would report its own.
- **`irradiance_source` is read from the environment, not the DB.** Ingestion uses
  `settings.irradiance_source`; the `systems.irradiance_source` column is written by
  `PUT /api/settings` but nothing reads it. `/api/status` therefore reports the env
  value, and the Setup form shows the field read-only. Don't add a control that
  pretends to change it.
- **Money/energy values are `Decimal`** in the DB and converted with
  `Decimal(str(round(...)))` in the summarizer. Don't introduce float columns.
- **Timezone split:** ingestion and storage are UTC (`datetime.now(tz=UTC)`,
  `DateTime(timezone=True)`); the APScheduler cron and user-facing day boundaries
  use `settings.tz`.
- **Error handling in jobs is per-step and non-fatal.** `_daily_poll` and
  `backfill()` catch specific exceptions per operation, accumulate `failed_steps`,
  and continue so one bad API call doesn't lose the rest of the day's data. Match
  this shape — specific exception types first, broad `Exception` last, always logged
  with context via loguru's `{}` brace style.
- **Poll failures write a `poll_log` row.** On error the session is rolled back
  first, then a fresh error row is committed; the log-write itself is wrapped so a
  logging failure never masks the original exception.
- **Magic thresholds are named constants** near their use:
  `FULL_DAY_INTERVAL_COUNT = 88` (summarizer), `WARRANTY_THRESHOLD_PER_YEAR = 0.007`
  (efficiency route), 0.015 PR-drop anomaly cutoff (summarizer).
- **Docstrings document every raised exception** (`Raises:` sections) — this is
  applied consistently across the backend; keep it.
- `NRELClient` returns 30-year TMY *annual averages*, ignoring `target_date`. Only
  `NASAClient` gives real per-day irradiance. PR trends computed against NREL data
  are therefore weather-insensitive by construction.

### Frontend (`frontend/src/`)

Vite + React 18 + TypeScript + Tailwind. Tab-based single page (`App.tsx` holds
`useState<Tab>`, no router). `api/client.ts` is the only place that touches
`fetch`, and its exported interfaces are hand-mirrored from the backend Pydantic
schemas — **update both sides together**. Per-endpoint hooks live in `hooks/`
(`useOverview`, `useEfficiency`, `useSettings`); pages in `pages/`; shared
presentational pieces in `components/`. Custom Tailwind palette: `solar-{50,400,500,600}`.

`frontend/src/solar-app.jsx` and `frontend/src/solar-dashboard.jsx` are unreferenced
design prototypes — not part of the build.

### Migrations

Alembic lives in `backend/alembic/`, with `env.py` importing `helio.db.models.Base`
for autogenerate. Note `alembic.ini` hardcodes a `localhost` `sqlalchemy.url`, so
migrations are expected to run inside the container (`make migrate`) where
`DATABASE_URL` resolves `db`. Versions are numbered `001_`, `002_`, ... and are
excluded from ruff.

### CI

`.github/workflows/ci.yml` runs on PRs to `main`/`develop`: ruff format check,
ruff lint, Bandit (`-ll`) + Trivy (CRITICAL/HIGH, `exit-code: 1`) on `backend/`,
unit tests, and the frontend type-check/build. Integration tests are not run in CI.
