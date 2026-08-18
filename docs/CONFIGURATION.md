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
| `ENPHASE_REDIRECT_URI` | No | `http://localhost:3000/api/auth/enphase/callback` | OAuth callback URL. Must be registered on your Enphase app and reachable from your browser. It goes through the dashboard's origin, which proxies `/api` to the API |
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
| `FERNET_KEY` | ✅ | — | Symmetric encryption key for storing OAuth tokens. Generate with: `make generate-fernet-key` |

---

## Weather & Irradiance

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IRRADIANCE_SOURCE` | No | `nasa` | Seeds the source for a new install. Options: `nasa`, `manual` |

`IRRADIANCE_SOURCE` only applies when the system record is first created. After
that, ingestion reads the source from the database and you change it on the
Setup tab; the change takes effect on the next poll with no restart.

**Irradiance source options:**

- `nasa` — NASA POWER API (global coverage, no API key required). Returns genuine daily values, which is what weather normalization needs.
- `manual` — Disables automatic irradiance collection. Performance Ratio is calculated only from irradiance rows you enter yourself.

NREL was removed as a source: its Solar Resource v1 endpoint returns a long-term
annual average rather than the requested day's measurement, so every Performance
Ratio derived from it was wrong.

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
| `HELIO_PORT` | No | `3000` | Port the dashboard is published on. It serves the app and proxies `/api` to the API, so it is the only port that must be reachable. |
| `FRONTEND_BASE_URL` | No | `http://localhost:3000` | Base URL of the dashboard. The Enphase OAuth callback redirects the browser back here. |

The frontend holds no API URL. It calls `/api` on whatever origin served it, and nginx inside the container proxies that to the API, so moving the deployment to another host, port or domain needs no image rebuild — only `HELIO_PORT`, `FRONTEND_BASE_URL` and `ENPHASE_REDIRECT_URI` kept in agreement.

The API's own port is published on `127.0.0.1` only, for the interactive docs at `http://localhost:8000/docs` and for tests run on the host. Nothing outside the machine needs it.

---

## Logs

Every service logs to stdout through Docker's `json-file` driver, capped in `docker-compose.yml`:

| Option | Value | Effect |
|--------|-------|--------|
| `max-size` | `10m` | A log file rolls over once it reaches 10 MB |
| `max-file` | `3` | Three files are kept per service, so at most 30 MB each |

That bounds the stack at roughly 90 MB of logs, which matters most on a Raspberry Pi where the database shares the disk. Raise the values in `docker-compose.yml` if you want longer history:

```yaml
x-logging: &logging
  driver: json-file
  options:
    max-size: "50m"
    max-file: "5"
```

Rotation is handled by the Docker daemon, so no host-level `logrotate` entry is needed.

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
ENPHASE_REDIRECT_URI=http://localhost:3000/api/auth/enphase/callback

# ── Security ──────────────────────────────────────────────────────────────────
# Generate: make generate-fernet-key
FERNET_KEY=

# ── Weather / Irradiance ──────────────────────────────────────────────────────
IRRADIANCE_SOURCE=nasa

# ── Polling Schedule ──────────────────────────────────────────────────────────
POLL_HOUR=4
POLL_MINUTE=0
TZ=America/Montreal

# ── Frontend ──────────────────────────────────────────────────────────────────
HELIO_PORT=3000
FRONTEND_BASE_URL=http://localhost:3000
```
