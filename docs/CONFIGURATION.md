# Configuration Reference

All configuration is done via environment variables in the `.env` file. Copy `.env.example` to `.env` to get started.

---

## Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | ✅ | — | Full PostgreSQL connection string. Format: `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `POSTGRES_USER` | ✅ | — | PostgreSQL username (used by the `db` Docker service) |
| `POSTGRES_PASSWORD` | ✅ | — | PostgreSQL password — use something secure |
| `POSTGRES_DB` | ✅ | — | Database name |

---

## Enphase API

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENPHASE_CLIENT_ID` | ✅ | — | Client ID from your Enphase developer app |
| `ENPHASE_CLIENT_SECRET` | ✅ | — | Client Secret from your Enphase developer app |
| `ENPHASE_SYSTEM_ID` | ✅ | — | Your Enphase system ID (visible in Enlighten URL) |

---

## Security

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FERNET_KEY` | ✅ | — | Symmetric encryption key for storing OAuth tokens. Generate with: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

---

## Weather & Irradiance

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IRRADIANCE_SOURCE` | No | `nrel` | Source for irradiance data. Options: `nrel`, `nasa`, `manual` |
| `NREL_API_KEY` | If using NREL | — | API key from developer.nrel.gov |

**Irradiance source options:**

- `nrel` — NREL PVDAQ (best for USA and Canada). Requires `NREL_API_KEY`.
- `nasa` — NASA POWER API (global coverage, no API key required, slightly lower resolution).
- `manual` — Disables weather normalization. Performance Ratio is calculated without irradiance correction. Simpler but less accurate for efficiency trending.

---

## Polling Schedule

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POLL_HOUR` | No | `4` | Hour of day (0–23, local time) when the daily poll runs |
| `POLL_MINUTE` | No | `0` | Minute within the poll hour |
| `TZ` | No | `UTC` | Timezone for the scheduler. Use IANA format e.g. `America/Montreal`, `America/New_York`, `Europe/Paris` |

> Set `TZ` to your local timezone so the 4 AM poll runs at 4 AM your time, after your solar day has ended and Enphase has finished processing the data.

---

## Frontend

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_BASE_URL` | No | `http://localhost:8000` | Base URL of the API server, as seen from the browser. Change this if you deploy behind a reverse proxy or use a custom domain. |

---

## Full `.env.example`

```bash
# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://helio:changeme@db:5432/helio
POSTGRES_USER=helio
POSTGRES_PASSWORD=changeme
POSTGRES_DB=helio

# ── Enphase API ───────────────────────────────────────────────────────────────
ENPHASE_CLIENT_ID=
ENPHASE_CLIENT_SECRET=
ENPHASE_SYSTEM_ID=

# ── Security ──────────────────────────────────────────────────────────────────
# Generate: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=

# ── Weather / Irradiance ──────────────────────────────────────────────────────
IRRADIANCE_SOURCE=nrel
NREL_API_KEY=

# ── Polling Schedule ──────────────────────────────────────────────────────────
POLL_HOUR=4
POLL_MINUTE=0
TZ=America/Montreal

# ── Frontend ──────────────────────────────────────────────────────────────────
VITE_API_BASE_URL=http://localhost:8000
```
