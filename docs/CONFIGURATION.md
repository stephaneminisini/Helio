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
| `ENPHASE_REDIRECT_URI` | No | `http://localhost:8000/api/auth/enphase/callback` | OAuth callback URL. Must be registered on your Enphase app and reachable from your browser |
| `ENPHASE_ACCESS_TOKEN` | No | — | Optional bootstrap token; ignored once the account is connected from the Setup tab |
| `ENPHASE_REFRESH_TOKEN` | No | — | Optional bootstrap token; ignored once the account is connected from the Setup tab |

### Connecting your Enphase account

Client ID and secret stay on the server; the tokens are obtained through the browser:

1. Register `ENPHASE_REDIRECT_URI` as a redirect URI on your app at https://developer-v4.enphase.com.
2. Open the dashboard, go to the **Setup** tab, and save your system settings.
3. Click **Connect to Enphase** and approve access.
4. Enphase redirects to the callback, which exchanges the authorization code and stores the
   token pair encrypted with `FERNET_KEY`. The Setup tab then shows the connection status and
   the last successful poll time.

Enphase rotates the refresh token on every use and it expires 30 days after issue, so a system
that polls daily stays connected. After a longer outage, click **Reconnect to Enphase**.

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
| `FRONTEND_BASE_URL` | No | `http://localhost:3000` | Base URL of the dashboard. The Enphase OAuth callback redirects the browser back here. |

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
ENPHASE_REDIRECT_URI=http://localhost:8000/api/auth/enphase/callback

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
FRONTEND_BASE_URL=http://localhost:3000
```
