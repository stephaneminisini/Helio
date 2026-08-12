# Technical Requirements Document
## Helio Monitor — Personal Solar Analytics Platform

**Version:** 1.0  
**Date:** April 28, 2026  
**Author:** Stephane  
**Status:** Draft

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Helio Monitor                            │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Poller      │    │  Aggregator  │    │  API Server      │  │
│  │  (Scheduler) │───▶│  (SQLAlchemy)│───▶│  (FastAPI)       │  │
│  └──────┬───────┘    └──────┬───────┘    └────────┬─────────┘  │
│         │                  │                      │            │
│         ▼                  ▼                      ▼            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   PostgreSQL 15+                         │  │
│  │   systems │ energy_intervals │ daily_summaries           │  │
│  │   monthly_summaries │ irradiance │ anomalies             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  React Frontend                          │  │
│  │   Overview │ Efficiency │ Setup                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
  Enphase API v4            NREL / NASA POWER API
```

---

## 2. Technology Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Language | Python | 3.11+ | Async support, strong data ecosystem |
| ORM | SQLAlchemy | 2.x | Async-compatible, migration support via Alembic |
| HTTP Client | httpx | 0.27+ | Async-first, used for Enphase + weather APIs |
| API Framework | FastAPI | 0.110+ | Async, automatic OpenAPI docs, Pydantic validation |
| Database | PostgreSQL | 15+ | Time-series queries, window functions, JSON support |
| Migrations | Alembic | 1.13+ | Version-controlled schema changes |
| Scheduler | APScheduler | 3.x | In-process cron for polling jobs |
| Frontend | React + Vite | React 18 | Existing mockup base |
| Config | Pydantic Settings | 2.x | .env-based config with validation |
| Containerization | Docker + Compose | latest | Reproducible deployment |

---

## 3. Database Schema

### 3.1 `systems`

Stores system configuration — sourced from API where available, otherwise from Setup UI.

```sql
CREATE TABLE systems (
    id                  SERIAL PRIMARY KEY,
    enphase_system_id   VARCHAR(64) UNIQUE NOT NULL,
    name                VARCHAR(128),
    location            VARCHAR(256),
    latitude            NUMERIC(9, 6),
    longitude           NUMERIC(9, 6),
    system_size_kw      NUMERIC(6, 3),          -- DC capacity
    panel_count         INTEGER,
    panel_wattage_w     INTEGER,
    manufacturer        VARCHAR(128),
    install_date        DATE NOT NULL,
    tilt_angle_deg      NUMERIC(5, 2),
    azimuth_deg         NUMERIC(6, 2),
    degradation_rate    NUMERIC(5, 3) DEFAULT 0.5,  -- %/yr
    irradiance_source   VARCHAR(32) DEFAULT 'nrel',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.2 `energy_intervals`

Raw 15-minute production data from Enphase API.

```sql
CREATE TABLE energy_intervals (
    id                  BIGSERIAL PRIMARY KEY,
    system_id           INTEGER REFERENCES systems(id),
    interval_start      TIMESTAMPTZ NOT NULL,
    duration_seconds    INTEGER NOT NULL DEFAULT 900,  -- 15 min
    production_wh       NUMERIC(10, 3),
    consumption_wh      NUMERIC(10, 3),
    net_wh              NUMERIC(10, 3),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (system_id, interval_start)
);

CREATE INDEX idx_intervals_system_start
    ON energy_intervals (system_id, interval_start DESC);
```

### 3.3 `daily_summaries`

Pre-aggregated daily totals. Rebuilt nightly from `energy_intervals`.

```sql
CREATE TABLE daily_summaries (
    id                  BIGSERIAL PRIMARY KEY,
    system_id           INTEGER REFERENCES systems(id),
    day                 DATE NOT NULL,
    production_kwh      NUMERIC(8, 3),
    consumption_kwh     NUMERIC(8, 3),
    peak_power_w        NUMERIC(8, 1),
    peak_power_at       TIMESTAMPTZ,
    interval_count      INTEGER,           -- for gap detection
    is_complete         BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (system_id, day)
);

CREATE INDEX idx_daily_system_day
    ON daily_summaries (system_id, day DESC);
```

### 3.4 `irradiance`

Daily solar resource data from NREL or NASA POWER.

```sql
CREATE TABLE irradiance (
    id                  BIGSERIAL PRIMARY KEY,
    system_id           INTEGER REFERENCES systems(id),
    day                 DATE NOT NULL,
    ghi_kwh_m2          NUMERIC(8, 4),   -- Global Horizontal Irradiance
    dni_kwh_m2          NUMERIC(8, 4),   -- Direct Normal Irradiance
    poa_kwh_m2          NUMERIC(8, 4),   -- Plane of Array (computed)
    source              VARCHAR(32),     -- 'nrel' | 'nasa'
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (system_id, day, source)
);
```

### 3.5 `monthly_summaries`

Aggregated monthly data including calculated Performance Ratio.

```sql
CREATE TABLE monthly_summaries (
    id                  BIGSERIAL PRIMARY KEY,
    system_id           INTEGER REFERENCES systems(id),
    month               DATE NOT NULL,   -- always 1st of month
    production_kwh      NUMERIC(10, 3),
    theoretical_kwh     NUMERIC(10, 3),  -- system_size_kw * POA irradiance
    performance_ratio   NUMERIC(6, 4),   -- production / theoretical
    expected_pr         NUMERIC(6, 4),   -- baseline * (1 - deg_rate)^years
    is_anomaly          BOOLEAN DEFAULT FALSE,
    anomaly_reason      TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (system_id, month)
);

CREATE INDEX idx_monthly_system_month
    ON monthly_summaries (system_id, month DESC);
```

### 3.6 `poll_log`

Audit log for all API polling activity.

```sql
CREATE TABLE poll_log (
    id                  BIGSERIAL PRIMARY KEY,
    system_id           INTEGER REFERENCES systems(id),
    poll_type           VARCHAR(32),     -- 'intervals' | 'irradiance' | 'panels'
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    status              VARCHAR(16),     -- 'success' | 'partial' | 'error'
    records_fetched     INTEGER DEFAULT 0,
    records_inserted    INTEGER DEFAULT 0,
    error_message       TEXT,
    date_range_start    DATE,
    date_range_end      DATE
);
```

---

## 4. Key SQL Queries

### 4.1 Same Day Last Year

```sql
SELECT
    d1.day          AS today,
    d1.production_kwh AS today_kwh,
    d2.day          AS same_day_last_year,
    d2.production_kwh AS last_year_kwh,
    ROUND(((d1.production_kwh - d2.production_kwh)
        / NULLIF(d2.production_kwh, 0)) * 100, 1) AS pct_change
FROM daily_summaries d1
LEFT JOIN daily_summaries d2
    ON  d2.system_id = d1.system_id
    AND d2.day = d1.day - INTERVAL '1 year'
WHERE d1.system_id = :system_id
  AND d1.day = CURRENT_DATE;
```

### 4.2 Monthly Year-over-Year

```sql
SELECT
    m1.month,
    m1.production_kwh                           AS this_year_kwh,
    m2.production_kwh                           AS last_year_kwh,
    m1.performance_ratio                        AS this_pr,
    m2.performance_ratio                        AS last_pr
FROM monthly_summaries m1
LEFT JOIN monthly_summaries m2
    ON  m2.system_id = m1.system_id
    AND m2.month = m1.month - INTERVAL '1 year'
WHERE m1.system_id = :system_id
ORDER BY m1.month DESC
LIMIT 24;
```

### 4.3 Degradation Trend

```sql
SELECT
    month,
    performance_ratio,
    expected_pr,
    ROUND(performance_ratio / FIRST_VALUE(performance_ratio)
        OVER (PARTITION BY system_id ORDER BY month) * 100, 2) AS pct_of_baseline,
    is_anomaly,
    anomaly_reason
FROM monthly_summaries
WHERE system_id = :system_id
ORDER BY month;
```

### 4.4 Annual Degradation Rate

```sql
WITH yearly AS (
    SELECT
        EXTRACT(YEAR FROM month)::INT AS yr,
        AVG(performance_ratio) AS avg_pr
    FROM monthly_summaries
    WHERE system_id = :system_id
    GROUP BY yr
)
SELECT
    yr,
    avg_pr,
    LAG(avg_pr) OVER (ORDER BY yr) AS prev_yr_pr,
    ROUND((LAG(avg_pr) OVER (ORDER BY yr) - avg_pr), 4) AS annual_drop
FROM yearly
ORDER BY yr;
```

---

## 5. Application Modules

### 5.1 `helio/core/config.py`
- Pydantic Settings model
- Reads from `.env`: DB URL, Enphase credentials, API keys, poll schedule

### 5.2 `helio/db/models.py`
- SQLAlchemy declarative models for all tables
- Async session factory

### 5.3 `helio/db/migrations/`
- Alembic migration environment
- One migration per schema change

### 5.4 `helio/ingestion/enphase_client.py`
- OAuth 2.0 token management (access + refresh, 30-day expiry)
- Methods: `get_intervals()`, `get_panels()`, `get_system_info()`
- Exponential backoff on rate limit (429) responses

### 5.5 `helio/ingestion/irradiance_client.py`
- NREL PVDAQ and NASA POWER adapters behind common interface
- Plane-of-Array (POA) irradiance calculation from GHI + tilt + azimuth

### 5.6 `helio/ingestion/poller.py`
- APScheduler job definitions
- `poll_intervals()` — daily at 04:00 local
- `poll_irradiance()` — daily at 04:30 local
- `rebuild_summaries()` — daily at 05:00 local
- Gap detection: queries `poll_log` to identify missed dates and backfills

### 5.7 `helio/analytics/summarizer.py`
- `build_daily_summary(system_id, date)` — aggregates intervals
- `build_monthly_summary(system_id, month)` — calculates PR, expected PR, anomaly flag
- `calculate_degradation(system_id)` — returns annual rate vs. warranty threshold

### 5.8 `helio/api/routes/`
- `GET /api/overview` — today's stats + comparisons
- `GET /api/efficiency` — PR history + degradation metrics
- `GET /api/panels` — panel heatmap data
- `GET /api/compare?period=day|month|year&date=YYYY-MM-DD`
- `GET/POST/PUT /api/settings` — system configuration (`POST` creates the single
  system record on a fresh install; `409` if one already exists)

### 5.9 `helio/api/main.py`
- FastAPI app entrypoint
- CORS, lifespan (starts scheduler on startup)
- Static file serving for React build

---

## 6. Enphase API Integration

### 6.1 Authentication Flow

```
1. User provides client_id + client_secret via Setup UI
2. User is redirected to Enphase OAuth authorization URL
3. Enphase returns auth_code via redirect
4. System exchanges auth_code for access_token + refresh_token
5. access_token stored encrypted in DB; refresh_token stored separately
6. Poller refreshes access_token before each poll session
```

### 6.2 Key Endpoints Used

| Endpoint | Purpose | Frequency |
|----------|---------|-----------|
| `GET /api/v4/systems/{id}/telemetry/production_micro` | 15-min intervals | Daily |
| `GET /api/v4/systems/{id}/devices/micros` | Panel-level data | Daily |
| `GET /api/v4/systems/{id}` | System metadata | Once |
| `POST /oauth/token` | Token refresh | Per poll session |

### 6.3 Rate Limiting

- Watt plan: 10 requests/min, 1,000 requests/month
- Poller designed for 1 session/day (~3-5 requests per session)
- Well within free tier limits

---

## 7. Performance Ratio Calculation

```
PR = E_actual / E_theoretical

Where:
  E_actual      = measured kWh from Enphase for the period
  E_theoretical = system_size_kw * POA_irradiance_kWh_m2

POA irradiance = f(GHI, DNI, tilt, azimuth, latitude)
  Calculated using pvlib transposition model (Perez or Hay-Davies)
```

---

## 8. Security Requirements

- **TR-SEC-01:** Enphase API credentials encrypted at rest using Fernet symmetric encryption; key stored in environment variable, not database
- **TR-SEC-02:** `.env` file excluded from version control via `.gitignore`
- **TR-SEC-03:** FastAPI server bound to `localhost` only by default; reverse proxy (nginx) required for LAN/internet access
- **TR-SEC-04:** No credentials logged; poll_log contains only status and record counts

---

## 9. Deployment

### 9.1 Docker Compose Services

```yaml
services:
  db:
    image: postgres:15-alpine
    volumes: [pgdata:/var/lib/postgresql/data]

  api:
    build: .
    depends_on: [db]
    environment: [DB_URL, ENPHASE_CLIENT_ID, ...]
    ports: ["8000:8000"]

  frontend:
    build: ./frontend
    ports: ["3000:80"]
```

### 9.2 Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `ENPHASE_CLIENT_ID` | Enphase app client ID |
| `ENPHASE_CLIENT_SECRET` | Enphase app client secret |
| `ENPHASE_SYSTEM_ID` | Target system ID |
| `FERNET_KEY` | Encryption key for token storage |
| `NREL_API_KEY` | NREL PVDAQ API key |
| `POLL_SCHEDULE_HOUR` | Hour for daily poll (default: 4) |
| `TZ` | Timezone for scheduler (e.g. America/Montreal) |

---

## 10. Testing Requirements

| Type | Target | Tool |
|------|--------|------|
| Unit | Summarizer logic, PR calculation | pytest |
| Integration | DB read/write, API endpoints | pytest + httpx |
| Contract | Enphase API response shapes | pytest with fixture data |
| E2E | Poller → DB → API → Frontend | Manual / Playwright |

---

## 11. Repository Structure

The GitHub repository is structured for public distribution and one-click deployment:

```
helio-monitor/
├── README.md                        # Landing page with deploy buttons + referral links
├── Makefile                         # Developer and operator commands
├── .env.example                     # Documented environment variable template
├── docker-compose.yml               # Production Compose file
├── .do/
│   └── app.yaml                     # DigitalOcean App Platform spec
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/
│   └── helio/
│       ├── core/                    # Config, logging, crypto
│       ├── db/                      # Models, session, migrations
│       ├── ingestion/               # Enphase + irradiance clients, poller
│       ├── analytics/               # Summarizer, degradation, anomaly
│       └── api/                     # FastAPI routes, schemas
├── frontend/
│   ├── Dockerfile
│   ├── vite.config.ts
│   └── src/
│       ├── api/                     # Typed API client
│       ├── hooks/                   # Data-fetching hooks
│       └── pages/                   # Overview, Efficiency, Setup
└── docs/
    ├── INSTALL.md                   # Full manual install guide
    ├── CONFIGURATION.md             # Environment variable reference
    ├── CONTRIBUTING.md              # Contributor guide
    └── deploy/
        ├── digitalocean.md          # DigitalOcean one-click guide
        ├── railway.md               # Railway one-click guide
        ├── raspberry-pi.md          # Local / home server guide
        └── docker-compose.yml       # Annotated production Compose reference
```

## 12. Makefile Targets

| Target | Description |
|--------|-------------|
| `make up` | Start all services |
| `make down` | Stop all services |
| `make down-full` | Stop and delete all data |
| `make migrate` | Run Alembic migrations |
| `make backfill` | Fetch all historical data from install date |
| `make update` | Pull latest code + images, migrate, restart |
| `make test` | Run full test suite |
| `make lint` | Run Black + isort |
| `make logs` | Tail logs from all services |
| `make logs api` | Tail API logs only |
| `make status` | Show container health status |
| `make poll-status` | Show last 10 poll run results |
| `make backup-db` | Dump database to `./backups/` |
| `make restore-db` | Restore from latest backup |
| `make enable-autostart` | Install systemd service for boot start |
| `make seed-mock` | Insert 3 years of synthetic data for development |
