# Development Plan
## Helio Monitor — AI-Assisted Development Roadmap

**Version:** 1.0  
**Date:** April 28, 2026  
**Author:** Stephane  
**Status:** Draft

---

## 1. Development Philosophy

This project will be built using an **AI-agent-assisted development model** — each phase is scoped so that a focused AI coding agent can execute it end-to-end with minimal context switching. Each agent receives a clear input, a defined output, and explicit acceptance criteria.

The developer (Stephane) acts as **orchestrator**: reviewing agent output, running tests, and providing course corrections before the next phase begins.

---

## 2. Agent Roster

| Agent ID | Name | Specialty | Tooling |
|----------|------|-----------|---------|
| AGT-01 | Schema Agent | Database design and migrations | Python, SQLAlchemy, Alembic, psql |
| AGT-02 | Ingestion Agent | API clients and polling scheduler | Python, httpx, APScheduler |
| AGT-03 | Analytics Agent | Aggregation logic and PR calculations | Python, SQLAlchemy, pvlib |
| AGT-04 | API Agent | FastAPI routes and Pydantic models | Python, FastAPI, pytest |
| AGT-05 | Frontend Agent | React wiring to live API | React, Vite, fetch |
| AGT-06 | DevOps Agent | Docker, Compose, env config | Docker, bash, nginx |
| AGT-07 | QA Agent | Test suite and coverage reporting | pytest, httpx, Playwright |

---

## 3. Phases & Agent Assignments

---

### Phase 0 — Project Scaffold
**Duration:** 0.5 day  
**Agent:** AGT-06 (DevOps Agent)

**Objective:** Stand up the project skeleton so all subsequent agents work in a consistent environment.

**Deliverables:**

- Monorepo structure:
  ```
  helio/
  ├── backend/
  │   ├── helio/
  │   │   ├── core/         # config, logging
  │   │   ├── db/           # models, session, migrations
  │   │   ├── ingestion/    # API clients, poller
  │   │   ├── analytics/    # summarizer, PR calc
  │   │   └── api/          # FastAPI routes
  │   ├── tests/
  │   ├── alembic/
  │   ├── Dockerfile
  │   └── pyproject.toml
  ├── frontend/             # existing React mockup
  ├── docker-compose.yml
  ├── .env.example
  └── README.md
  ```
- `docker-compose.yml` with `db`, `api`, and `frontend` services
- `.env.example` with all required variables documented
- `pyproject.toml` with all backend dependencies pinned
- `Makefile` with targets: `make up`, `make migrate`, `make test`, `make logs`

**Acceptance Criteria:**
- `make up` starts Postgres and confirms connectivity
- `make test` runs (zero tests, zero failures)
- All directories and placeholder files present

---

### Phase 1 — Database Schema & Migrations
**Duration:** 1 day  
**Agent:** AGT-01 (Schema Agent)

**Objective:** Create all database tables, indexes, and initial seed data via versioned Alembic migrations.

**Input to Agent:**
- TRD Section 3 (Database Schema) — full DDL specifications
- SQLAlchemy 2.x async patterns

**Deliverables:**

- `helio/db/models.py` — all SQLAlchemy ORM models:
  - `System`, `EnergyInterval`, `DailySummary`, `MonthlySummary`, `Irradiance`, `PollLog`
- `helio/db/session.py` — async session factory and `get_db` dependency
- `alembic/versions/001_initial_schema.py` — creates all tables and indexes
- `alembic/versions/002_seed_system.py` — inserts placeholder system record for testing

**Acceptance Criteria:**
- `make migrate` runs clean with no errors
- All tables and indexes visible in `psql \dt` and `\di`
- All foreign key constraints enforced
- `System` model round-trips correctly (insert + select)

---

### Phase 2 — Enphase API Client
**Duration:** 1.5 days  
**Agent:** AGT-02 (Ingestion Agent — Part 1)

**Objective:** Build a reliable, token-managed async client for the Enphase API v4.

**Input to Agent:**
- TRD Section 6 (Enphase API Integration)
- Enphase API v4 OpenAPI spec (developer-v4.enphase.com/docs.html)
- Existing Postman collection patterns (reference from Five9 httpx work)

**Deliverables:**

- `helio/ingestion/enphase_client.py`:
  - `EnphaseClient` class with `httpx.AsyncClient`
  - `authenticate(auth_code)` — exchanges code for tokens, stores encrypted in DB
  - `refresh_token()` — called before each poll session
  - `get_intervals(start_date, end_date)` — returns raw interval list
  - `get_panel_data()` — returns microinverter telemetry
  - `get_system_info()` — returns system metadata
  - Exponential backoff on 429/503
  - Structured logging of all requests/responses (redacting tokens)
- `helio/core/crypto.py` — Fernet-based encrypt/decrypt for token storage
- `tests/test_enphase_client.py` — unit tests using fixture JSON responses

**Acceptance Criteria:**
- `get_intervals()` returns correctly typed `IntervalData` Pydantic models
- Token refresh works without user intervention
- 429 response triggers backoff and retry (testable with mock)
- No credentials appear in logs

---

### Phase 3 — Irradiance Client
**Duration:** 0.5 day  
**Agent:** AGT-02 (Ingestion Agent — Part 2)

**Objective:** Fetch daily irradiance data from NREL or NASA POWER and compute Plane-of-Array values.

**Input to Agent:**
- TRD Section 7 (Performance Ratio Calculation)
- NREL PVDAQ API docs
- NASA POWER API docs

**Deliverables:**

- `helio/ingestion/irradiance_client.py`:
  - `IrradianceClient` abstract base
  - `NRELClient(IrradianceClient)` implementation
  - `NASAClient(IrradianceClient)` implementation
  - `compute_poa(ghi, dni, tilt, azimuth, latitude, date)` — using pvlib
- `tests/test_irradiance_client.py`

**Acceptance Criteria:**
- POA calculation matches pvlib reference for known inputs (within 0.1%)
- Client falls back to NASA if NREL returns no data for a date
- Data stored correctly in `irradiance` table

---

### Phase 4 — Poller & Scheduler
**Duration:** 1 day  
**Agent:** AGT-02 (Ingestion Agent — Part 3)

**Objective:** Build the scheduled polling engine that runs daily and keeps the database current.

**Input to Agent:**
- TRD Section 5.6 (`helio/ingestion/poller.py`)
- Phase 2 and Phase 3 client modules

**Deliverables:**

- `helio/ingestion/poller.py`:
  - APScheduler `AsyncScheduler` configuration
  - `poll_intervals(system_id, date_range)` — fetches and upserts intervals
  - `poll_irradiance(system_id, date_range)` — fetches and upserts irradiance
  - `detect_gaps(system_id)` — queries `poll_log`, returns list of missing dates
  - `backfill(system_id)` — calls `poll_intervals` for all gap dates
  - `log_poll(...)` — writes to `poll_log` on success and failure
- Schedule: intervals at 04:00, irradiance at 04:30, summaries trigger at 05:00
- Startup backfill: on first run, fetches all data from install date

**Acceptance Criteria:**
- Poller runs without error for a simulated 7-day period
- Gap detection correctly identifies a manually removed date
- Backfill correctly fills the gap
- `poll_log` contains an entry for every run

---

### Phase 5 — Analytics Engine
**Duration:** 1.5 days  
**Agent:** AGT-03 (Analytics Agent)

**Objective:** Build the aggregation and analytics layer that produces all derived metrics.

**Input to Agent:**
- TRD Section 4 (Key SQL Queries)
- TRD Section 5.7 (`helio/analytics/summarizer.py`)
- TRD Section 7 (PR calculation formula)

**Deliverables:**

- `helio/analytics/summarizer.py`:
  - `build_daily_summary(system_id, date)` — aggregates intervals → daily row
  - `build_monthly_summary(system_id, month)` — computes PR, expected PR, anomaly flag
  - `rebuild_all_summaries(system_id)` — rebuilds from scratch (useful after backfill)
- `helio/analytics/degradation.py`:
  - `calculate_annual_degradation(system_id)` → `{year: int, avg_pr: float, drop: float}`
  - `project_future_efficiency(system_id, years_ahead)` → projected PR
  - `estimate_lost_production(system_id)` → kWh and dollar value
- `helio/analytics/anomaly.py`:
  - `flag_anomalies(system_id)` — marks months > 1.5% below expected PR
  - `flag_underperforming_panels(system_id)` — marks panels > 2 std dev below fleet avg
- `tests/test_summarizer.py`, `tests/test_degradation.py`

**Acceptance Criteria:**
- PR calculation matches manual calculation for known dataset (within 0.01%)
- Annual degradation rate correct for mock 3-year dataset
- Anomaly flagged correctly for seeded Aug 2024 drop scenario
- All summaries rebuild cleanly from raw intervals

---

### Phase 6 — FastAPI Backend
**Duration:** 1.5 days  
**Agent:** AGT-04 (API Agent)

**Objective:** Expose all analytics data via a clean, typed REST API.

**Input to Agent:**
- TRD Section 5.8 (API routes)
- Phase 5 analytics modules
- Pydantic v2 patterns

**Deliverables:**

- `helio/api/schemas/` — Pydantic response models for all endpoints
- `helio/api/routes/overview.py`:
  - `GET /api/overview` — today's production, comparisons, records
- `helio/api/routes/efficiency.py`:
  - `GET /api/efficiency` — PR history, degradation metrics, anomalies
- `helio/api/routes/panels.py`:
  - `GET /api/panels` — panel heatmap data
- `helio/api/routes/compare.py`:
  - `GET /api/compare?period=day|month|year&date=YYYY-MM-DD`
- `helio/api/routes/settings.py`:
  - `GET /api/settings` — current system config
  - `PUT /api/settings` — update system config
- `helio/api/main.py` — app factory, CORS, lifespan
- `tests/test_api.py` — integration tests using `httpx.AsyncClient`

**Acceptance Criteria:**
- All endpoints return 200 with correctly typed responses for seeded data
- `GET /api/compare?period=day` returns same-day-last-year delta correctly
- `PUT /api/settings` persists to DB and returns updated record
- All endpoints documented in auto-generated OpenAPI at `/docs`

---

### Phase 7 — Frontend Integration
**Duration:** 1.5 days  
**Agent:** AGT-05 (Frontend Agent)

**Objective:** Wire the existing React mockup to the live FastAPI backend, replacing all mock data.

**Input to Agent:**
- Existing `solar-app.jsx` mockup
- Phase 6 API route definitions and response schemas
- OpenAPI spec at `http://localhost:8000/docs`

**Deliverables:**

- `frontend/src/api/client.ts` — typed fetch wrapper for all API endpoints
- `frontend/src/hooks/` — React hooks:
  - `useOverview()`, `useEfficiency()`, `usePanels()`, `useSettings()`
- Updated page components replacing mock data with hook data:
  - `OverviewPage.tsx` — live overview data
  - `EfficiencyPage.tsx` — live PR history and degradation
  - `SetupPage.tsx` — loads and saves settings via API
- Loading states and error boundaries for all async data
- Environment variable `VITE_API_BASE_URL` for configurable API host

**Acceptance Criteria:**
- Dashboard renders correctly with real data from seeded Postgres
- Same-day comparison numbers match direct DB queries
- Setup page saves and reloads correctly
- No hardcoded mock data remains in any component

---

### Phase 8 — DevOps & Hardening
**Duration:** 0.5 day  
**Agent:** AGT-06 (DevOps Agent)

**Objective:** Harden the deployment for unattended 24/7 operation.

**Deliverables:**

- Docker health checks for `db` and `api` services
- `nginx.conf` — reverse proxy for API + static frontend on port 80
- Log rotation config for API and poller logs
- `Makefile` targets: `make backup-db`, `make restore-db`
- `scripts/initial_backfill.py` — one-shot script to pull all historical data from install date
- `README.md` — complete setup guide (clone → configure .env → make up → backfill)

**Acceptance Criteria:**
- `docker compose up -d` starts all services and passes health checks
- Nginx serves frontend at `/` and proxies API at `/api`
- `make backup-db` produces a valid pg_dump file
- README walkthrough followed from scratch results in a running system

---

### Phase 9 — QA & Test Coverage
**Duration:** 1 day  
**Agent:** AGT-07 (QA Agent)

**Objective:** Ensure the system is reliable and observable before production use.

**Input to Agent:**
- All modules from Phases 1–8
- BRD functional requirements BR-01 through BR-20

**Deliverables:**

- Full pytest suite covering:
  - Unit: summarizer, PR calc, degradation, anomaly detection
  - Integration: poller → DB → API round trips
  - Contract: Enphase client response parsing
- Coverage report (target: 80%+ on analytics and API layers)
- `tests/fixtures/` — realistic JSON fixture data (1 year of intervals)
- Playwright smoke tests for 3 critical paths:
  1. Overview page loads with today's comparison data
  2. Efficiency page shows degradation trend
  3. Setup page saves and reloads settings
- GitHub Actions workflow (`.github/workflows/test.yml`) running on push

**Acceptance Criteria:**
- `make test` passes with ≥ 80% coverage on backend
- All 3 Playwright smoke tests pass against a seeded local environment
- No BRD functional requirement untested

---

## 4. Timeline Summary

| Phase | Description | Agent | Est. Days |
|-------|-------------|-------|-----------|
| 0 | Project Scaffold | AGT-06 | 0.5 |
| 1 | Database Schema | AGT-01 | 1.0 |
| 2 | Enphase API Client | AGT-02 | 1.5 |
| 3 | Irradiance Client | AGT-02 | 0.5 |
| 4 | Poller & Scheduler | AGT-02 | 1.0 |
| 5 | Analytics Engine | AGT-03 | 1.5 |
| 6 | FastAPI Backend | AGT-04 | 1.5 |
| 7 | Frontend Integration | AGT-05 | 1.5 |
| 8 | DevOps & Hardening | AGT-06 | 0.5 |
| 9 | QA & Test Coverage | AGT-07 | 1.0 |
| | **Total** | | **10.5 days** |

---

## 5. Agent Handoff Protocol

Each phase handoff follows this checklist:

```
[ ] All deliverables listed in the phase are present
[ ] Acceptance criteria verified by developer (Stephane)
[ ] `make test` passes (zero new failures)
[ ] No hardcoded credentials or secrets in committed code
[ ] Agent output reviewed for hallucinated imports or non-existent APIs
[ ] Next agent's input document prepared (module paths confirmed)
```

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Enphase API rate limit exceeded during backfill | Medium | High | Throttle backfill to 5 req/min; spread over multiple days |
| NREL API unavailable for historical dates | Low | Medium | Fallback to NASA POWER; manual entry in Setup |
| OAuth refresh token expires (30 days) | Medium | High | Scheduler checks token age daily; alerts log if < 5 days remaining |
| Enphase deprecates used endpoints | Low | High | Pin to v4; monitor deprecation notices page |
| Panel data not available on Watt plan | Medium | Medium | Heatmap gracefully shows "data unavailable"; no crash |

---

## 7. Future Phases (Post-MVP)

| ID | Feature | Notes |
|----|---------|-------|
| FP-01 | Battery / storage monitoring | Requires Enphase battery data endpoints |
| FP-02 | Email / push alerts | Degradation warnings, anomaly notifications |
| FP-03 | Export to CSV / PDF | Monthly production reports |
| FP-04 | Utility rate integration | Map production to bill savings |
| FP-05 | Weather overlay on charts | Correlate dips with cloud cover |

---

### Phase 10 — Distribution & Repo Polish
**Duration:** 0.5 day
**Agent:** AGT-06 (DevOps Agent)

**Objective:** Prepare the repository for public GitHub release with one-click deploy support and community documentation.

**Deliverables:**

- `README.md` — finalized with:
  - Deploy to DigitalOcean button (linked to `app.yaml`)
  - Deploy to Railway button
  - DigitalOcean referral link with $200 credit callout
  - Railway referral link
  - Buy Me a Coffee badge
  - Feature overview, prerequisites, tech stack table
- `.do/app.yaml` — DigitalOcean App Platform spec with all services and env variable stubs
- `docker-compose.yml` — production-ready with health checks and restart policies
- `docs/INSTALL.md` — complete manual install guide (all platforms)
- `docs/CONFIGURATION.md` — full environment variable reference
- `docs/CONTRIBUTING.md` — contributor guide including mock mode instructions
- `docs/deploy/digitalocean.md` — step-by-step DigitalOcean guide with referral details
- `docs/deploy/railway.md` — Railway guide
- `docs/deploy/raspberry-pi.md` — Pi / home server guide with Tailscale remote access
- `.env.example` — all variables with inline comments and safe defaults
- `.gitignore` — excludes `.env`, `backups/`, `logs/`, `__pycache__`, `node_modules`
- `LICENSE` — MIT
- GitHub repo topics set: `solar`, `enphase`, `self-hosted`, `docker`, `postgresql`, `fastapi`, `react`

**Acceptance Criteria:**
- "Deploy to DigitalOcean" button opens a pre-configured App Platform wizard
- "Deploy to Railway" button opens a pre-configured Railway template
- `README.md` renders correctly on GitHub (badges, buttons, tables)
- All placeholder values (`YOUR_USERNAME`, `YOUR_REFERRAL_CODE`) documented with a setup checklist in `docs/PUBLISH_CHECKLIST.md`
- `make up` from a clean clone with only `.env` filled in produces a running system

---

## Updated Timeline Summary

| Phase | Description | Agent | Est. Days |
|-------|-------------|-------|-----------|
| 0 | Project Scaffold | AGT-06 | 0.5 |
| 1 | Database Schema | AGT-01 | 1.0 |
| 2 | Enphase API Client | AGT-02 | 1.5 |
| 3 | Irradiance Client | AGT-02 | 0.5 |
| 4 | Poller & Scheduler | AGT-02 | 1.0 |
| 5 | Analytics Engine | AGT-03 | 1.5 |
| 6 | FastAPI Backend | AGT-04 | 1.5 |
| 7 | Frontend Integration | AGT-05 | 1.5 |
| 8 | DevOps & Hardening | AGT-06 | 0.5 |
| 9 | QA & Test Coverage | AGT-07 | 1.0 |
| 10 | Distribution & Repo Polish | AGT-06 | 0.5 |
| | **Total** | | **11 days** |
