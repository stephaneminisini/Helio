# Installation Guide

This guide covers a complete manual installation of Helio Monitor on any Linux host using Docker and Docker Compose.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Get Your Enphase API Credentials](#get-your-enphase-api-credentials)
3. [Clone and Configure](#clone-and-configure)
4. [Start the Application](#start-the-application)
5. [Initial Data Backfill](#initial-data-backfill)
6. [Access the Dashboard](#access-the-dashboard)
7. [Keeping It Running](#keeping-it-running)
8. [Updating](#updating)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

You need the following installed on your host:

| Tool | Minimum Version | Check |
|------|----------------|-------|
| Docker | 24.x | `docker --version` |
| Docker Compose | 2.x | `docker compose version` |
| Git | any | `git --version` |
| make | any | `make --version` |

**Platform support:** Linux (x86_64, arm64), macOS (Apple Silicon and Intel), Windows via WSL2.

Install Docker: [docs.docker.com/get-docker](https://docs.docker.com/get-docker/)

---

## Get Your Enphase API Credentials

You need three things from Enphase before configuring Helio Monitor.

### Step 1 — Create a Developer Account

1. Go to [developer-v4.enphase.com](https://developer-v4.enphase.com)
2. Click **Sign Up** and create a free account
3. Select the **Watt plan** (free) — sufficient for personal use

### Step 2 — Create an Application

1. In the developer portal, go to **My Apps → New App**
2. Fill in the details:
   - **App Name:** Helio Monitor (or anything you like)
   - **Redirect URI:** `http://localhost:3000/api/auth/enphase/callback`
   - **Scopes:** Select `production`, `consumption`, `system`
3. Click **Create**
4. Copy your **Client ID** and **Client Secret**

### Step 3 — Find Your System ID

Your System ID appears in the Enlighten URL when you are logged in:

```
https://enlighten.enphaseenergy.com/web/12345678/today/graph/hours
                                          ^^^^^^^^
                                          This is your System ID
```

## Clone and Configure

### Step 1 — Clone the repository

```bash
git clone https://github.com/stephaneminisini/Helio.git
cd Helio
```

### Step 2 — Copy the example environment file

```bash
cp .env.example .env
```

### Step 3 — Edit `.env`

Open `.env` in your editor and fill in your values:

```bash
# ── Database ──────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://helio:helio@db:5432/helio
POSTGRES_USER=helio
POSTGRES_PASSWORD=helio          # Change this to something secure
POSTGRES_DB=helio

# ── Enphase API ───────────────────────────────────────────────────
ENPHASE_CLIENT_ID=your_client_id_here
ENPHASE_CLIENT_SECRET=your_client_secret_here
ENPHASE_SYSTEM_ID=your_system_id_here

# ── Encryption ────────────────────────────────────────────────────
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=your_generated_fernet_key_here

# ── Weather / Irradiance ──────────────────────────────────────────
IRRADIANCE_SOURCE=nasa              # nasa | manual (seeds a new install only)

# ── Polling Schedule ──────────────────────────────────────────────
POLL_HOUR=4                         # Hour to poll (24h, local time)
TZ=America/Montreal                 # Your timezone

# ── App ───────────────────────────────────────────────────────────
HELIO_PORT=3000
```

### Step 4 — Generate a Fernet key

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output as your `FERNET_KEY` value.

> ⚠️ Keep your `.env` file private. It is listed in `.gitignore` and will never be committed.

---

## Start the Application

### Start all services

```bash
make up
```

This pulls and builds all Docker images, starts PostgreSQL, runs database migrations automatically, and starts the API server and frontend.

On first run this takes 2–4 minutes. Subsequent starts take a few seconds.

### Verify everything is running

```bash
make status
```

You should see three services running: `db`, `api`, `frontend`.

```bash
make logs
```

Watch logs from all services. Press `Ctrl+C` to exit.

---

## Authorize Enphase

Before data can be collected, you need to authorize Helio Monitor to access your Enphase account.

1. Open the dashboard at [http://localhost:3000](http://localhost:3000)
2. Go to the **Setup** tab
3. Your Client ID and System ID should already be populated from `.env`
4. Click **Connect Enphase Account**
5. You will be redirected to the Enphase login page
6. Log in with your Enlighten account and click **Authorize**
7. You will be redirected back to Helio Monitor
8. The status indicator will change to **Connected**

---

## Initial Data Backfill

On first run, Helio Monitor does not have any historical data yet. The backfill command fetches all available production data from your install date to today.

```bash
make backfill
```

This may take several minutes depending on how long your system has been installed. Progress is logged to the console.

> ⏱️ The Enphase API rate limit on the free plan is 1,000 requests/month. The backfill is throttled to stay well within this limit. For systems older than 2 years, the backfill may split across 2 days automatically.

Once complete, refresh the dashboard — all your historical data should be visible.

---

## Access the Dashboard

| Service | URL |
|---------|-----|
| Dashboard | [http://localhost:3000](http://localhost:3000) |
| API | [http://localhost:3000/api/health](http://localhost:3000/api/health) |
| API Docs | [http://localhost:8000/docs](http://localhost:8000/docs) |

The dashboard serves the app and proxies `/api` to the API, so port 3000 is the only one you need to reach — set `HELIO_PORT` to move it. The API's own port 8000 is published on `127.0.0.1` only, which is why the interactive docs are reachable from the machine running the stack and from nowhere else.

---

## Keeping It Running

### Auto-start on boot

To have Helio Monitor start automatically when your machine boots:

```bash
make enable-autostart
```

This installs a systemd service (Linux) or launchd plist (macOS).

### Daily polling

The poller runs automatically at 4:00 AM in your configured timezone. No action required.

### Check poller health

```bash
make poll-status
```

Shows the last 10 poll runs including success/failure status and records fetched.

---

## Updating

```bash
git pull
make update
```

`make update` pulls the latest images, runs any new migrations, and restarts services. No data is lost.

---

## Stopping

```bash
make down        # Stop containers (data preserved)
make down-full   # Stop containers AND delete all data ⚠️
```

---

## Troubleshooting

### Dashboard shows no data after backfill

- Check `make poll-status` for errors
- Verify your Enphase authorization is still valid in the Setup tab
- Run `make logs api` to see API errors

### Enphase authorization keeps failing

- Double-check your `ENPHASE_CLIENT_ID` and `ENPHASE_CLIENT_SECRET` in `.env`
- Verify the redirect URI in your Enphase app matches `http://localhost:3000/api/auth/enphase/callback` exactly
- Try revoking and re-authorizing in the Setup tab

### Database connection errors on startup

- Wait 10–15 seconds — PostgreSQL takes a moment to initialize on first run
- Run `make logs db` to check for database errors
- Verify `POSTGRES_PASSWORD` matches between `DATABASE_URL` and `POSTGRES_PASSWORD`

### Performance Ratio chart is flat or missing

- Irradiance data may not have loaded yet — run `make poll-status` and look for `irradiance` entries
- Confirm the site latitude and longitude are saved on the Setup tab; irradiance is skipped without them
- Check the Setup tab's irradiance source is `NASA POWER` rather than `Manual`
- NASA POWER publishes a few days behind, so the most recent days can legitimately have no irradiance yet

### Port conflicts

If ports 3000 or 8000 are already in use on your machine, edit `docker-compose.yml` and change the host-side port mapping:

```yaml
ports:
  - "3001:80"    # Change 3000 to something available
```

---

## Getting Help

- Open an issue: [github.com/stephaneminisini/Helio/issues](https://github.com/stephaneminisini/Helio/issues)
- Check existing issues before opening a new one
